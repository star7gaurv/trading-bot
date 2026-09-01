# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce
from datetime import datetime, timedelta
from typing import Optional

import json
import numpy as np
import pandas as pd
from pathlib import Path
from pandas import DataFrame
from freqtrade.strategy import IStrategy, stoploss_from_open
from freqtrade.exchange import timeframe_to_seconds
from freqtrade.persistence import Trade
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import logging
import sys
import os

for _p in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'),
    '/freqtrade/user_data/scripts',
    '/home/ubuntu/var/www/html/trade/freqtrade/user_data/scripts',
]:
    if os.path.isdir(_p):
        sys.path.insert(0, os.path.realpath(_p))
        break
from risk_engine import RiskEngine
_risk_engine = RiskEngine()

logger = logging.getLogger(__name__)

# ── datasieve compatibility shim ───────────────────────────────────────────────
# FreqTrade 2026.5 + datasieve: Pipeline._validate_arguments accesses
# self.features_in, but some code paths in backtesting can call
# transform(outlier_check=True) before features_in is populated.
# Safe fallback: if features_in is missing, use feature_list (same data,
# just a rename between datasieve versions).
try:
    import datasieve.pipeline as _dsp

    _orig_validate = _dsp.Pipeline._validate_arguments

    def _patched_validate(self, X, y, sample_weight, fit=False, outlier_check=False):
        if not fit and not hasattr(self, "features_in"):
            if hasattr(self, "feature_list") and len(self.feature_list) > 0:
                self.features_in = self.feature_list
            elif hasattr(X, "columns"):
                self.features_in = list(X.columns)
        return _orig_validate(self, X, y, sample_weight, fit=fit, outlier_check=outlier_check)

    _dsp.Pipeline._validate_arguments = _patched_validate
    logger.info("[FinBuddyFreqAI] datasieve Pipeline.features_in patch applied")
except Exception as _shim_err:
    logger.debug(f"[FinBuddyFreqAI] datasieve shim skipped: {_shim_err}")


class FinBuddyFreqAI_v23(IStrategy):
    """
    FinBuddy FreqAI Strategy v23 — Conscious Brain (2026-05-17)

    ARCHITECTURE: Regression, not classification.
      LightGBMRegressor predicts continuous future_return (% over next LABEL_PERIOD candles).
      No class labels → no class imbalance → no base-rate short-bias.
      Root cause of 0-longs-in-bull-market failure eliminated.

    ENTRY: long when predicted_return > dynamic_long_threshold
           short when predicted_return < dynamic_short_threshold

    SELF-AWARENESS (Layer 2): dynamic thresholds per candle.
      - Base: LONG_THRESHOLD / SHORT_THRESHOLD env vars
      - Regime multiplier: tighter threshold in counter-trend direction
        (BEAR → easy short, hard long; BULL → easy long, hard short)
      - WR feedback: if recent WR > 55%, lower threshold (trade more aggressively)

    RISK MANAGEMENT: ATR stoploss unchanged (K_TP/K_SL still control stop/trail).

    WIDER CONTEXT (Layer 4): external macro signals injected as FreqAI features:
      fear_greed index, BTC dominance, news sentiment, HMM regime encoding, recent WR.

    ENV VARs for grid search:
      FREQAI_LONG_THRESHOLD   float  default 1.0  — predicted return % to enter long
      FREQAI_SHORT_THRESHOLD  float  default -1.0 — predicted return % to enter short
      FREQAI_K_TP             float  default 2.0  — trail lock level (ATR×K_TP)
      FREQAI_K_SL             float  default 1.0  — initial stop (ATR×K_SL)
      FINBUDDY_RECENT_WR      float  default 0.50 — written by trade_postmortem cron
    """
    INTERFACE_VERSION = 3

    minimal_roi = {"0": 0.99}

    stoploss = -0.04
    trailing_stop = False
    use_custom_stoploss = True

    timeframe = "15m"  # matches config.json; was "5m" (stale, overridden at load 2026-05-20)

    can_short = True

    # ── Timeframe-derived candle-count constants (CENTRALIZED 2026-06-20) ──────────
    # Every lookback below is expressed in WALL-CLOCK and converted to candles for the
    # ACTIVE timeframe, so changing `timeframe` propagates everywhere — there are no
    # scattered magic numbers left to miss when migrating TF. At 15m each reproduces
    # the exact prior hardcoded value (verified by unit test). 86400 = seconds/day.
    _CANDLES_PER_DAY       = 86400 // timeframe_to_seconds(timeframe)  # 96@15m · 24@1h
    startup_candle_count   = 25 * _CANDLES_PER_DAY        # 2400@15m — z-score/centering warmup
    _Z_ROLLING             = 30 * _CANDLES_PER_DAY        # 2880@15m — z-score window (set_freqai_targets)
    _CENTERING_WINDOW      = 20 * _CANDLES_PER_DAY        # 1920@15m — serve-time recentering (3 sites)
    _CENTERING_MIN_PERIODS = 200                          # warmup floor (TF-independent count)
    _DAY_CANDLES           = _CANDLES_PER_DAY             # 96@15m — 1-day rolling high/low
    _PRED_STD_WINDOW       = round(_CANDLES_PER_DAY * 25 / 24)  # 100@15m — ~25h per-pair pred-std
    _META_HORIZON_DEFAULT  = 6 * _CANDLES_PER_DAY // 24   # 24@15m — 6h meta-label horizon

    # Regression entry thresholds (grid search via docker env).
    LONG_THRESHOLD  = float(os.getenv("FREQAI_LONG_THRESHOLD",  "1.0"))   # predicted % return to enter long
    SHORT_THRESHOLD = float(os.getenv("FREQAI_SHORT_THRESHOLD", "-1.0"))  # predicted % return to enter short (negative)

    # Entry stability filter: require N consecutive candles past threshold to fire entry.
    # Single-candle spikes get filtered. 2-3 is a good range; raise for higher quality.
    STABILITY_N = int(os.getenv("FREQAI_STABILITY_N", "2"))

    # ATR-based stoploss parameters (unchanged — risk management independent of entry model).
    K_TP = float(os.getenv("FREQAI_K_TP", "2.0"))
    K_SL = float(os.getenv("FREQAI_K_SL", "1.0"))

    # Feature-set toggle (brain Fix F, 2026-05-19).
    # Lets the brain test which external features actually help. Values:
    #   "all"       — include macro (fear_greed, btc_strength) + regime + recent_wr (default, live behavior unchanged)
    #   "no_macro"  — drop fear_greed + btc_strength + funding/OI features
    #   "no_regime" — drop regime_numeric
    #   "minimal"   — drop all of the above (only raw OHLCV-derived indicators)
    FEATURE_SET = os.getenv("FREQAI_FEATURE_SET", "all").lower()

    def bot_start(self, **kwargs) -> None:
        """Recompute the TF-derived candle constants from the EFFECTIVE (runtime) timeframe.

        The class-level constants are computed at import from the class's literal `timeframe`.
        FreqTrade applies the config's timeframe override at the INSTANCE level AFTER the class
        is defined, so without this hook a config timeframe ≠ the class default would run with
        15m-scaled windows (the 2026-06-21 bug). bot_start runs after the override is applied.
        At 15m this reproduces the exact frozen values (byte-identical → live unchanged)."""
        cpd = 86400 // timeframe_to_seconds(self.timeframe)
        self._CANDLES_PER_DAY      = cpd
        self.startup_candle_count  = 25 * cpd
        self._Z_ROLLING            = 30 * cpd
        self._CENTERING_WINDOW     = 20 * cpd
        self._DAY_CANDLES          = cpd
        self._PRED_STD_WINDOW      = round(cpd * 25 / 24)
        self._META_HORIZON_DEFAULT = 6 * cpd // 24
        logger.info(
            f"[TF-init] timeframe={self.timeframe} candles/day={cpd} "
            f"startup={self.startup_candle_count} z_roll={self._Z_ROLLING} "
            f"centering={self._CENTERING_WINDOW} day={self._DAY_CANDLES} "
            f"pred_std={self._PRED_STD_WINDOW} meta_h={self._META_HORIZON_DEFAULT}"
        )

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        # Base TF + the higher TFs that differ from base (avoids a base==informative
        # collision when timeframe changes). At 15m → [15m,1h,4h] (identical to before);
        # at 1h → [1h,4h] (the redundant 1h-as-informative is dropped automatically).
        tfs = [self.timeframe] + [tf for tf in ("1h", "4h") if tf != self.timeframe]
        informative = [(pair, tf) for tf in tfs for pair in pairs]  # TF-grouped (matches prior order)
        informative += [("BTC/USDT:USDT", "1d")]
        informative += [("BTC/USDT:USDT", "4h")]
        return informative

    # ------------------------------------------------------------------ #
    # ATR-adaptive custom stoploss (v19 — asymmetric K_TP/K_SL barriers) #
    # ------------------------------------------------------------------ #

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[float]:
        """
        v19 ATR-adaptive stoploss - asymmetric barriers (K_SL initial, K_TP trail lock).

        Initial stop:  K_SL*ATR below entry (tight - cuts losers fast, matches labeling SL).
        Trail lock:    once profit > K_TP*ATR, lock in at +0.25 * K_TP*ATR above entry (floor 0.002).

        Tighter initial stop also reduces funding fee drag on losing trades (they exit sooner).

        Returns None on missing data (no reset of existing stop).
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        # --- Phase 13 Volatility Hook (Emergency Shield) ---
        # FIXED 2026-06-12: this read "%-relative_volume-period", a pre-rename
        # FreqAI feature name that never exists in the analyzed dataframe —
        # .get() returned the 1.0 default on every candle, so the shield NEVER
        # fired since it shipped. Compute relative volume directly instead.
        candles_open = int((current_time - trade.open_date_utc).total_seconds() / timeframe_to_seconds(self.timeframe))
        if candles_open <= 2 and current_profit < -0.005:
            vol = dataframe["volume"].tail(20)
            vol_mean = vol.mean()
            rel_vol = (vol.iloc[-1] / vol_mean) if vol_mean and vol_mean > 0 else 1.0
            if rel_vol > 5.0:  # 500% volume spike
                return current_profit - 0.0001
        # ---------------------------------------------------

        last = dataframe.iloc[-1]
        atr = last.get("atr_14", None)
        if atr is None or atr <= 0 or current_rate <= 0:
            return None

        entry_atr_pct = trade.get_custom_data("entry_atr_pct")
        if entry_atr_pct is None:
            entry_atr_pct = atr / trade.open_rate
            entry_atr_pct = max(0.003, min(entry_atr_pct, 0.025))
            trade.set_custom_data("entry_atr_pct", float(entry_atr_pct))

        atr_pct = atr / current_rate
        atr_pct = max(0.003, min(atr_pct, 0.025))

        sl_pct = self.K_SL * entry_atr_pct  # initial stop - FIXED at entry-time ATR
        tp_pct = self.K_TP * entry_atr_pct  # trail lock - also entry-anchored (live ATR caused moving goalposts)

        # Trail activation threshold: once profit exceeds 1.0 * tp_pct
        lock_threshold = tp_pct * 1.0

        # Leverage/ATR mismatch fix (2026-08-31, env-gated FREQAI_TRAIL_LEVERAGE_FIX, default
        # off): current_profit is FreqTrade's LEVERAGED profit ratio, but tp_pct/lock_threshold
        # are computed from raw price ATR (unleveraged). Comparing them directly means the trail
        # activates at 1/leverage of the intended price move — e.g. at 2x leverage, a trade
        # locks in after only half the ATR distance the K_TP setting was meant to require.
        # Documented as a known discrepancy for months, never fixed or measured pending brain
        # validation (this is that validation). Default off preserves exact prior behavior.
        _trail_compare_profit = current_profit
        if os.environ.get("FREQAI_TRAIL_LEVERAGE_FIX", "0") == "1" and trade.leverage:
            _trail_compare_profit = current_profit / trade.leverage

        # Trail: once profit exceeds the lock threshold, lock stop at max(0.5 * tp_pct, 0.005) from entry.
        # Floor raised from 0.25→0.5 and 0.002→0.005 (0.25× was too tight, caused profit give-back).
        if _trail_compare_profit > lock_threshold:
            locked_stop = max(tp_pct * 0.5, 0.005)
            trail_pct = stoploss_from_open(
                locked_stop,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
            if trail_pct is not None and trail_pct > 0:
                return trail_pct
            return None

        # Initial: K_SL*ATR from entry.
        initial_stop = stoploss_from_open(
            -sl_pct,
            current_profit,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        if initial_stop is not None and initial_stop > 0:
            return initial_stop
        return None

    # Cache for _today_closed_pnl: (epoch_ts, value). custom_exit runs per open
    # trade per iteration — without the cache every call re-sums all closed trades.
    _today_pnl_cache = (0.0, 0.0)

    def _today_closed_pnl(self) -> float:
        """Sum of today's (UTC, wall-clock) closed-trade P&L, cached 60s.

        Wall-clock semantics match the original circuit breaker: in backtests
        historical close dates never fall on the real today, so both breaker
        tiers are inert there — brain/WF results are unaffected by design.
        """
        import time as _time
        now_ts = _time.time()
        ts, val = FinBuddyFreqAI_v23._today_pnl_cache
        if now_ts - ts < 60:
            return val
        from datetime import timezone as _tz
        today = datetime.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        val = sum(
            (t.close_profit_abs or 0.0)
            for t in Trade.get_trades_proxy(is_open=False)
            if t.close_date_utc and t.close_date_utc >= today
        )
        FinBuddyFreqAI_v23._today_pnl_cache = (now_ts, val)
        return val

    def _label_period_candles(self) -> int:
        """The model's prediction horizon, in candles — single source of truth.

        Reads `freqai.feature_parameters.label_period_candles` from config (which the
        brain tunes via `FREQTRADE__FREQAI__FEATURE_PARAMETERS__LABEL_PERIOD_CANDLES`
        and apply_timeframe.py sets per TF). Used both by `set_freqai_targets` (target
        horizon) and the `custom_exit` time-limit, so the two can never diverge across
        a timeframe switch. (Before 2026-06-21 the time-limit read a separate
        FREQAI_LABEL_CANDLES env var that the 1h switch left stale at 12 while the model
        moved to 6 — that env var is now removed.)
        """
        try:
            return int(self.freqai_info["feature_parameters"]["label_period_candles"])
        except (AttributeError, KeyError, TypeError, ValueError):
            return 12

    def custom_exit(self, pair: str, trade: "Trade", current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # Daily flatten tier (2026-06-11): the entry-block breaker caps NEW trades
        # at -limit, but positions already open can ride to their own stops
        # (2026-06-11: blocked at -10, day still ended -11.28; theoretical worst
        # ~-21 with 8 open). If the day reaches -limit × FREQAI_DAILY_FLATTEN_MULT
        # (default 1.5 → -15), close everything.
        _daily_limit = float(os.environ.get("FREQAI_DAILY_LOSS_LIMIT", "10"))
        _flatten_mult = float(os.environ.get("FREQAI_DAILY_FLATTEN_MULT", "1.5"))
        if _flatten_mult > 0 and self._today_closed_pnl() < -(_daily_limit * _flatten_mult):
            logger.warning(
                f"[CircuitBreaker] Daily flatten: today P&L "
                f"{self._today_closed_pnl():.2f} < -{_daily_limit * _flatten_mult:.1f}. "
                f"Force-exiting {pair}."
            )
            return "daily_flatten"

        candles_open = int((current_time - trade.open_date_utc).total_seconds() / timeframe_to_seconds(self.timeframe))

        # ── Capital Preservation Layer (2026-06-16): prediction-decay early exit ──
        # The bleed pattern: shorts win in the morning, then a counter-trend bounce
        # stops out a cluster of them at full SL in the afternoon. This watches the
        # MODEL's live view of every open trade and cuts it EARLY — the moment the
        # model stops supporting the position while it's underwater — turning a
        # -1.2 full stop-loss into a ~-0.4 early exit. Only fires on losers (never
        # cuts a winner) and only when the model has gone neutral/against the trade.
        # FREQAI_PRED_DECAY_LEVEL = centered-prediction level at which the model no
        # longer supports the side (default 0.0).
        # DEFAULT OFF (2026-06-16): A/B backtest showed early-exit made the bleed
        # WORSE (-553.9 vs -545.6, WR 38.1% vs 40.4%, +243 more trades). The
        # per-candle prediction is too noisy as a real-time abandon trigger — it
        # cuts trades that recover and churns re-entries. Kept gated for reference.
        if os.environ.get("FREQAI_PRED_DECAY_EXIT", "0") == "1" and candles_open >= 1 and current_profit < -0.002:
            decay_level = float(os.environ.get("FREQAI_PRED_DECAY_LEVEL", "0.0"))
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if df is not None and not df.empty:
                last = df.iloc[-1]
                if int(last.get("do_predict", 0)) == 1 and "&-future_return" in df.columns:
                    pred = float(last.get("&-future_return", 0.0))
                    centered = pred - df["&-future_return"].tail(self._CENTERING_WINDOW).median()
                    # short supported while centered < 0; long supported while centered > 0
                    if trade.is_short and centered >= decay_level:
                        return "pred_decay_exit"
                    if (not trade.is_short) and centered <= -decay_level:
                        return "pred_decay_exit"

        # ── Persistence-gated prediction-disagreement exit (2026-09-01) ──────────
        # Same intent as pred_decay_exit above, but noise-resistant: requires
        # FREQAI_PRED_PERSIST_EXIT_N CONSECUTIVE candles of model disagreement
        # (mirrors the entry-side STABILITY_N pattern, populate_entry_trend
        # ~line 1941) instead of a single raw candle. pred_decay_exit's
        # single-candle version was A/B-tested and made results WORSE (see
        # above); this is the persistence-gated redesign, gated OFF pending
        # its own brain A/B. Reports a distinct exit_reason so its effect is
        # measurable in isolation from pred_decay_exit (which stays OFF).
        # DEFAULT OFF: FREQAI_PRED_PERSIST_EXIT=0 → byte-identical prior behavior.
        if os.environ.get("FREQAI_PRED_PERSIST_EXIT", "0") == "1":
            _persist_n = max(1, int(os.environ.get("FREQAI_PRED_PERSIST_EXIT_N", "3")))
            _persist_level = float(os.environ.get("FREQAI_PRED_PERSIST_EXIT_LEVEL", "0.0"))
            _persist_min_loss = float(os.environ.get("FREQAI_PRED_PERSIST_EXIT_MIN_LOSS", "-0.002"))
            if candles_open >= _persist_n and current_profit < _persist_min_loss:
                df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if df is not None and len(df) >= _persist_n and "&-future_return" in df.columns:
                    rolling_median = df["&-future_return"].rolling(
                        self._CENTERING_WINDOW, min_periods=self._CENTERING_MIN_PERIODS
                    ).median()
                    centered_tail = (df["&-future_return"] - rolling_median).tail(_persist_n)
                    dp_tail = df.get("do_predict", pd.Series(1, index=df.index)).tail(_persist_n)
                    if len(centered_tail) == _persist_n and bool((dp_tail == 1).all()):
                        if trade.is_short:
                            disagreeing = bool((centered_tail >= _persist_level).all())
                        else:
                            disagreeing = bool((centered_tail <= -_persist_level).all())
                        if disagreeing:
                            return "pred_persist_exit"

        # ── Progress-cut exit (2026-06-23, env-gated FREQAI_PROGRESS_CUT=1; default off) ──
        # Different from pred_decay (which cut on the noisy per-candle PREDICTION and made
        # things worse). This cuts on lack of PRICE PROGRESS: winners declare themselves fast
        # (exit_signal fires at ~2.5 candles avg, 100% WR in backtest); a trade still underwater
        # after PROGRESS_CUT_CANDLES with no exit_signal is almost certainly a loser. Cutting it
        # here — cheaply, before it drifts to the full time-limit or a catastrophe stop — is the
        # asymmetric idea: give trades room through noise (wide price stop), but cut them on TIME
        # if the thesis isn't playing out. Pairs with a wide K_SL so the price stop handles only
        # tail risk and THIS handles the slow bleeders.
        if os.environ.get("FREQAI_PROGRESS_CUT", "0") == "1":
            cut_candles = int(os.environ.get("FREQAI_PROGRESS_CUT_CANDLES", "3"))
            cut_profit  = float(os.environ.get("FREQAI_PROGRESS_CUT_PROFIT", "-0.005"))
            if candles_open >= cut_candles and current_profit < cut_profit:
                return "progress_cut"

        # Time-limit exit: close trade after the model's prediction horizon
        # (label_period_candles) candles. Holding beyond the horizon the model was
        # trained to predict is undefined territory. Derived from config (single source
        # of truth via _label_period_candles) so the exit horizon always tracks the
        # model — e.g. 6 candles @1h, 12 @15m — and the brain's label_period_candles
        # tuning applies to both automatically.
        label_candles = self._label_period_candles()

        # NEUTRAL-chop exit horizon override (2026-08-31): shorten the time-limit
        # exit for trades ENTERED during a NEUTRAL/choppy regime. Diagnosed: shorts
        # entered during a multi-week NEUTRAL stretch spent the full horizon
        # drifting nowhere 66% of the time (34.5% WR once they finally timed out)
        # instead of resolving via a real signal exit or stop. Raising the entry
        # conviction bar for NEUTRAL shorts (FREQAI_NEUTRAL_SHORT_MULT) barely
        # moved trade count/WR/PF when tested — the fix isn't fewer entries, it's
        # giving undecided trades less rope in chop specifically. Per-direction
        # (diagnosis was short-specific; longs did fine in the same stretch).
        # Default 1.0/1.0 = byte-identical to prior behavior.
        _neutral_exit_mult_long  = float(os.environ.get("FREQAI_NEUTRAL_EXIT_MULT_LONG", "1.0"))
        _neutral_exit_mult_short = float(os.environ.get("FREQAI_NEUTRAL_EXIT_MULT_SHORT", "1.0"))
        _neutral_exit_mult = _neutral_exit_mult_short if trade.is_short else _neutral_exit_mult_long
        if _neutral_exit_mult != 1.0 and self._get_current_regime(as_of=trade.open_date_utc) == "NEUTRAL":
            label_candles = max(1, int(round(label_candles * _neutral_exit_mult)))

        # ── Time-limit grace extension (2026-09-01) ──────────────────────────────
        # The branch below used to force-close unconditionally at the deadline with
        # ZERO model input — even a trade the model still likes gets killed blind.
        # If the model still supports the trade's direction (even weakly) when the
        # deadline hits, extend by FREQAI_TIME_LIMIT_GRACE_CANDLES instead of
        # blind-closing, capped at FREQAI_TIME_LIMIT_GRACE_MAX_EXTENSIONS grants per
        # trade (bounded, not unlimited holding). Extension count persisted via
        # trade.get/set_custom_data, same mechanism as entry_atr_pct in
        # custom_stoploss. DEFAULT OFF: FREQAI_TIME_LIMIT_GRACE_CANDLES=0 is a true
        # no-op even if FREQAI_TIME_LIMIT_GRACE is mistakenly flipped on.
        _grace_on = os.environ.get("FREQAI_TIME_LIMIT_GRACE", "0") == "1"
        _grace_candles = int(os.environ.get("FREQAI_TIME_LIMIT_GRACE_CANDLES", "0")) if _grace_on else 0
        _grace_extensions_used = int(trade.get_custom_data("time_limit_grace_used") or 0) if _grace_candles > 0 else 0
        _effective_label_candles = label_candles + _grace_candles * _grace_extensions_used

        if candles_open >= _effective_label_candles:
            if _grace_candles > 0:
                _grace_level = float(os.environ.get("FREQAI_TIME_LIMIT_GRACE_LEVEL", "0.0"))
                _grace_max = int(os.environ.get("FREQAI_TIME_LIMIT_GRACE_MAX_EXTENSIONS", "1"))
                if _grace_extensions_used < _grace_max:
                    df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                    if df is not None and not df.empty and "&-future_return" in df.columns:
                        last = df.iloc[-1]
                        if int(last.get("do_predict", 0)) == 1:
                            pred = float(last.get("&-future_return", 0.0))
                            rolling_median = df["&-future_return"].tail(self._CENTERING_WINDOW).median()
                            centered = pred - rolling_median
                            still_supported = (
                                centered < -_grace_level if trade.is_short
                                else centered > _grace_level
                            )
                            if still_supported:
                                trade.set_custom_data(
                                    "time_limit_grace_used", _grace_extensions_used + 1
                                )
                                logger.info(
                                    f"[TimeLimitGrace] {pair} deadline extended by "
                                    f"{_grace_candles} candles "
                                    f"({_grace_extensions_used + 1}/{_grace_max} used)."
                                )
                                return None
            return "time_limit_exit"
        return None

    # ------------------------------------------------------------------ #
    # Phase 3 — Regime-aware position sizing                             #
    # ------------------------------------------------------------------ #
    _REGIME_MULTIPLIERS = {
        "CRASH":    0.0,
        "BEAR":     0.5,
        "NEUTRAL":  1.0,
        "BULL":     1.0,
        "EUPHORIA": 0.75,
    }

    # Fixed path: /freqtrade/user_data/../finbuddy_memory/ = /freqtrade/finbuddy_memory/
    _REGIME_FILE = "/freqtrade/finbuddy_memory/regimes/current.json"
    _HISTORICAL_REGIME_FILE = "/freqtrade/finbuddy_memory/regimes/historical_regime.parquet"
    _HISTORICAL_MACRO_FILE  = "/freqtrade/finbuddy_memory/historical/macro_features.parquet"
    _HISTORICAL_FUNDING_FILE         = "/freqtrade/finbuddy_memory/historical/funding_rate.parquet"
    _HISTORICAL_FUNDING_PERPAIR_FILE = "/freqtrade/finbuddy_memory/historical/funding_perpair.parquet"
    _HISTORICAL_OI_FILE              = "/freqtrade/finbuddy_memory/historical/open_interest.parquet"
    _HISTORICAL_OI_PERPAIR_FILE      = "/freqtrade/finbuddy_memory/historical/oi_perpair.parquet"
    _COMBINED_CTX_FILE = "/freqtrade/user_data/data/external/combined_context.json"
    _PAIR_REGIME_FILE  = "/freqtrade/finbuddy_memory/regimes/pair_regime_stats.json"

    # Class-level caches: loaded once, shared across all strategy instances.
    _historical_regime_df  = None
    _historical_macro_df   = None
    _historical_funding_df         = None
    _historical_funding_perpair    = None   # dict[symbol -> DataFrame] after first load
    _historical_oi_df              = None
    _historical_oi_perpair         = None   # dict[symbol -> DataFrame] after first load
    # Pair-regime block cache: refreshed when JSON mtime changes (every 30 min via cron).
    _pair_regime_blocks       = None    # dict[pair] -> set[regime]
    _pair_regime_blocks_mtime = 0.0

    # ---------------------------------------------------------------------- #
    # Serve-time prediction centering window (FIXED 2026-06-08).             #
    # ---------------------------------------------------------------------- #
    # The model's raw z-scored predictions are DIRECTIONAL: ~69-72% positive
    # in the current up-market (verified from historic_predictions.pkl). This
    # is the alpha — the model correctly leans long when the market rises.
    #
    # We subtract a slow trailing-median baseline to remove ONLY the
    # training-serving distribution drift (the model is trained on older data;
    # at serve time the prediction mean drifts, which previously caused the
    # 2026-06-06 BEAR deadlock where raw preds never went negative → 0 shorts).
    #
    # BUG (until 2026-06-08): the window was rolling(100) = 25 HOURS on 15m.
    # A 25h median tracks the price TREND itself, so subtracting it stripped out
    # the directional signal — centered preds collapsed to ~46-49% positive
    # (forced 50/50 long/short regardless of trend). This caused:
    #   • brain: 60 zscore experiments with 0 longs in BULL windows
    #   • live : 37.7% WR — model forced to short into uptrends (mean-reversion)
    #
    # FIX: window = 1920 candles = 20 DAYS. Empirically (historic_predictions):
    #   raw 69% → centered 69% (BTC), 72% → 69% (ETH) — DIRECTION PRESERVED,
    #   and ~31% of preds stay negative so BEAR shorts still fire (no deadlock).
    #   1920 < startup_candle_count (2400) so the window is fully populated and
    #   IDENTICAL in live and backtest. min_periods=200 matches the z-score
    #   normalization warmup (ROLLING=2880, min_periods=200 in set_freqai_targets).
    #
    # ⚠️ COUPLING: _CENTERING_WINDOW (defined up top, TF-derived = 20*_CANDLES_PER_DAY:
    #   1920@15m, 480@1h) MUST be identical in all 3 centering sites — leverage(),
    #   populate_entry_trend(), populate_exit_trend() — so the threshold comparison is
    #   coherent across sizing, entry, and exit. It stays < startup_candle_count by design.

    # BTC reference OHLCV for the rel-strength feature — loaded at the ACTIVE timeframe.
    _HISTORICAL_BTC_15M_FILE = f"/freqtrade/user_data/data/binance/futures/BTC_USDT_USDT-{timeframe}-futures.feather"
    _btc_15m_df = None  # class-level cache for BTC base-TF OHLCV (rel-strength feature)

    _RECENT_WR_FILE = "/home/ubuntu/.finbuddy/state/recent_wr.json"
    _recent_wr_cache = 0.50
    _recent_wr_mtime = 0.0

    def _load_historical_regime(self):
        """Load BTC-derived historical regime parquet once. Cached at class level."""
        if FinBuddyFreqAI_v23._historical_regime_df is not None:
            return FinBuddyFreqAI_v23._historical_regime_df
        try:
            df = pd.read_parquet(self._HISTORICAL_REGIME_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            df = df.sort_values("date").reset_index(drop=True)
            FinBuddyFreqAI_v23._historical_regime_df = df
            max_date = df['date'].max()
            now_utc = pd.Timestamp.now(tz="UTC")
            gap_days = (now_utc - max_date).days
            logger.info(f"[Regime] Loaded {len(df)} historical regime candles from {df['date'].min()} to {max_date} (gap from now: {gap_days}d)")
            if gap_days > 3:
                logger.warning(f"[Regime] STALE: historical_regime.parquet is {gap_days}d behind now — re-run scripts/build_historical_regime.py (will cause NaN in live feature pipeline)")
            return df
        except Exception as e:
            logger.warning(f"[Regime] Could not load historical regime parquet ({e}) — falling back to live regime file")
            FinBuddyFreqAI_v23._historical_regime_df = pd.DataFrame()  # empty marker to skip retry
            return FinBuddyFreqAI_v23._historical_regime_df

    def _get_current_regime(self, as_of: pd.Timestamp | None = None) -> str:
        """
        Return regime at a specific timestamp (backtest) or current (live).

        If `as_of` is provided AND historical regime parquet exists, look up the
        regime that was active at that candle. Otherwise fall back to reading
        the live current.json (live trading).

        This is the fix for the backtest regime-blind bug: previously this
        always read live state, making dynamic thresholds inert during backtests.
        """
        if as_of is not None:
            hist = self._load_historical_regime()
            if not hist.empty:
                as_of_utc = pd.Timestamp(as_of).tz_convert("UTC") if pd.Timestamp(as_of).tz else pd.Timestamp(as_of).tz_localize("UTC")
                # Find the most recent regime row at or before this timestamp
                idx = hist["date"].searchsorted(as_of_utc, side="right") - 1
                if 0 <= idx < len(hist):
                    return hist.iloc[idx]["regime"]
        # Fallback: live regime file
        try:
            with open(self._REGIME_FILE) as f:
                return json.load(f).get("regime", "NEUTRAL")
        except Exception:
            return "NEUTRAL"

    # ------------------------------------------------------------------ #
    # Phase 1 (2026-05-19) — Per-Pair-Per-Regime Dynamic Gate            #
    # ------------------------------------------------------------------ #
    # `scripts/pair_regime_performance.py` writes `pair_regime_stats.json`
    # every 30 min based on rolling 30-day closed-trade performance.
    # A pair-regime combo that has lost over the lookback (n>=5, WR<40%,
    # PF<0.7) gets listed in `blocked[]`. This method loads + caches that
    # list. Strategy zeroes out entries when (pair, current_regime) is blocked.
    # ------------------------------------------------------------------ #
    def _load_pair_regime_blocks(self) -> dict:
        """Return {pair: set(blocked_regimes)}. Refreshes when JSON mtime changes.

        WF bypass (2026-05-26): when FREQAI_DISABLE_PAIR_REGIME_GATE=1 is set,
        return an empty dict so WF backtests see raw strategy signals. The gate
        is designed for LIVE trading (accumulates real trade stats over 30 days).
        In WF each fold trains from scratch with fresh pair_regime_stats, so the
        live stats would either over-block (if live is in a bad BEAR streak) or
        under-block (if live has never seen some pairs). Bypassing gives the WF
        a clean view of the raw signal quality — which is what we want to validate.
        """
        if os.environ.get("FREQAI_DISABLE_PAIR_REGIME_GATE", "0") == "1":
            return {}
        try:
            mtime = os.path.getmtime(self._PAIR_REGIME_FILE)
        except OSError:
            return {}
        if (FinBuddyFreqAI_v23._pair_regime_blocks is not None
                and mtime <= FinBuddyFreqAI_v23._pair_regime_blocks_mtime):
            return FinBuddyFreqAI_v23._pair_regime_blocks
        try:
            with open(self._PAIR_REGIME_FILE) as f:
                data = json.load(f)
            blocks: dict[str, set] = {}
            for b in data.get("blocked", []):
                blocks.setdefault(b["pair"], set()).add(b["regime"])
            FinBuddyFreqAI_v23._pair_regime_blocks       = blocks
            FinBuddyFreqAI_v23._pair_regime_blocks_mtime = mtime
            return blocks
        except Exception:
            return FinBuddyFreqAI_v23._pair_regime_blocks or {}

    def _load_recent_wr(self) -> float:
        """Return the recent WR. Refreshes when JSON mtime changes."""
        try:
            mtime = os.path.getmtime(self._RECENT_WR_FILE)
        except OSError:
            return FinBuddyFreqAI_v23._recent_wr_cache
        if mtime <= FinBuddyFreqAI_v23._recent_wr_mtime:
            return FinBuddyFreqAI_v23._recent_wr_cache
        try:
            with open(self._RECENT_WR_FILE) as f:
                data = json.load(f)
            wr = float(data.get("wr", 0.50))
            FinBuddyFreqAI_v23._recent_wr_cache = wr
            FinBuddyFreqAI_v23._recent_wr_mtime = mtime
            return wr
        except Exception:
            return FinBuddyFreqAI_v23._recent_wr_cache

    def _load_historical_macro(self):
        """Load historical macro features (F&G + BTC strength). Cached at class level."""
        if FinBuddyFreqAI_v23._historical_macro_df is not None:
            return FinBuddyFreqAI_v23._historical_macro_df
        try:
            df = pd.read_parquet(self._HISTORICAL_MACRO_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            df = df.sort_values("date").reset_index(drop=True)
            FinBuddyFreqAI_v23._historical_macro_df = df
            max_date = df['date'].max()
            now_utc = pd.Timestamp.now(tz="UTC")
            gap_days = (now_utc - max_date).days
            logger.info(f"[Macro] Loaded {len(df)} historical macro rows from {df['date'].min()} to {max_date} (gap from now: {gap_days}d)")
            if gap_days > 3:
                logger.warning(f"[Macro] STALE: macro_features.parquet is {gap_days}d behind now — re-run scripts/build_historical_macro.py (will cause NaN in live feature pipeline)")
            return df
        except Exception as e:
            logger.warning(f"[Macro] Could not load historical macro parquet ({e}) — using live combined_context")
            FinBuddyFreqAI_v23._historical_macro_df = pd.DataFrame()
            return FinBuddyFreqAI_v23._historical_macro_df

    def _load_btc_15m(self) -> pd.DataFrame:
        """Load BTC/USDT_USDT 15m OHLCV feather once. Cached at class level.

        Used to compute per-candle BTC return for the rel-strength feature.
        Falls back to empty DataFrame (feature defaults to 0.0) if file missing.
        """
        if FinBuddyFreqAI_v23._btc_15m_df is not None:
            return FinBuddyFreqAI_v23._btc_15m_df
        try:
            df = pd.read_feather(self._HISTORICAL_BTC_15M_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            df = df[["date", "close"]].sort_values("date").reset_index(drop=True)
            FinBuddyFreqAI_v23._btc_15m_df = df
            logger.info(f"[RelStrength] Loaded {len(df)} BTC 15m rows from {df['date'].min()} to {df['date'].max()}")
            return df
        except Exception as e:
            logger.warning(f"[RelStrength] Could not load BTC 15m feather ({e}) — rel_strength_btc defaulting to 0.0")
            FinBuddyFreqAI_v23._btc_15m_df = pd.DataFrame()
            return FinBuddyFreqAI_v23._btc_15m_df

    def _get_btc_returns(self, dataframe: DataFrame, windows: tuple) -> dict[str, pd.Series]:
        """Return per-candle BTC pct_change at each window, aligned to dataframe dates.

        Uses merge_asof(direction='backward') — same pattern as macro/funding loaders.
        Falls back to 0.0 series if BTC data unavailable.
        """
        n = len(dataframe)
        btc = self._load_btc_15m()
        if btc.empty:
            return {w: pd.Series(0.0, index=dataframe.index) for w in windows}
        # pre-compute all window returns on BTC once
        btc_with_rets = btc.copy()
        for w in windows:
            btc_with_rets[f"btc_ret_{w}"] = btc_with_rets["close"].pct_change(w)
        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, btc_with_rets.drop(columns=["close"]), on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        return {w: pd.Series(merged[f"btc_ret_{w}"].fillna(0.0).values, index=dataframe.index) for w in windows}

    def _get_macro_series(self, dataframe: DataFrame) -> dict[str, pd.Series]:
        """
        Vectorized lookup: per-candle historical fear_greed and btc_strength.

        Returns a dict with 'fear_greed' and 'btc_strength' Series aligned to dataframe.
        Falls back to constant from live combined_context.json if historical missing.
        """
        hist = self._load_historical_macro()
        if hist.empty:
            ctx = self._get_combined_context()
            n = len(dataframe)
            return {
                "fear_greed":   pd.Series([float(ctx.get("fear_greed", 50))]   * n, index=dataframe.index),
                "btc_strength": pd.Series([0.0] * n, index=dataframe.index),
            }
        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, hist, on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        return {
            "fear_greed":   pd.Series(merged["fear_greed"].fillna(50.0).values,    index=dataframe.index),
            "btc_strength": pd.Series(merged["btc_strength"].fillna(0.0).values,   index=dataframe.index),
        }

    def _load_historical_funding(self):
        """Load historical BTC perp funding-rate events. Cached at class level.

        Built by scripts/build_historical_funding.py — refreshed daily via cron.
        Falls back to live funding rate (single value, repeated) if parquet missing.
        """
        if FinBuddyFreqAI_v23._historical_funding_df is not None:
            return FinBuddyFreqAI_v23._historical_funding_df
        try:
            df = pd.read_parquet(self._HISTORICAL_FUNDING_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            df = df.sort_values("date").reset_index(drop=True)
            FinBuddyFreqAI_v23._historical_funding_df = df
            max_date = df["date"].max()
            gap_days = (pd.Timestamp.now(tz="UTC") - max_date).days
            logger.info(
                f"[Funding] Loaded {len(df)} historical funding events from "
                f"{df['date'].min()} to {max_date} (gap={gap_days}d)"
            )
            if gap_days > 3:
                logger.warning(
                    f"[Funding] STALE: funding_rate.parquet is {gap_days}d behind — "
                    f"re-run scripts/build_historical_funding.py"
                )
            return df
        except Exception as e:
            logger.warning(f"[Funding] Could not load historical parquet ({e}) — using live cache fallback")
            FinBuddyFreqAI_v23._historical_funding_df = pd.DataFrame()
            return FinBuddyFreqAI_v23._historical_funding_df

    def _get_funding_series(self, dataframe: DataFrame) -> dict[str, pd.Series]:
        """
        Vectorized lookup: per-candle BTC funding_rate + z-score + change.

        Funding events are every 8h; merge_asof(direction='backward') assigns each
        candle the most recent funding event preceding it. Same pattern as macro.

        Returns 3 Series aligned to dataframe.index:
          funding_rate      — raw per-8h rate
          funding_rate_z30d — z-score vs 30d rolling (extremeness)
          funding_rate_chg  — change vs previous event (momentum)
        """
        hist = self._load_historical_funding()
        n = len(dataframe)
        if hist.empty:
            # Live fallback: single current value from the existing _get_btc_funding_rate cache
            live = self._get_btc_funding_rate()
            live = float(live) if live is not None else 0.0
            return {
                "funding_rate":      pd.Series([live] * n, index=dataframe.index),
                "funding_rate_z30d": pd.Series([0.0]  * n, index=dataframe.index),
                "funding_rate_chg":  pd.Series([0.0]  * n, index=dataframe.index),
            }
        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, hist, on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        return {
            "funding_rate":      pd.Series(merged["funding_rate"].fillna(0.0).values,      index=dataframe.index),
            "funding_rate_z30d": pd.Series(merged["funding_rate_z30d"].fillna(0.0).values, index=dataframe.index),
            "funding_rate_chg":  pd.Series(merged["funding_rate_chg"].fillna(0.0).values,  index=dataframe.index),
        }

    def _load_historical_funding_perpair(self) -> dict:
        """Load per-pair funding rate parquet into a dict[symbol → DataFrame].

        Built by scripts/build_historical_funding_perpair.py, refreshed daily.
        Falls back to empty dict (features default to 0.0) if parquet missing.
        """
        if FinBuddyFreqAI_v23._historical_funding_perpair is not None:
            return FinBuddyFreqAI_v23._historical_funding_perpair
        try:
            df = pd.read_parquet(self._HISTORICAL_FUNDING_PERPAIR_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
            by_sym = {sym: grp.reset_index(drop=True) for sym, grp in df.groupby("symbol")}
            FinBuddyFreqAI_v23._historical_funding_perpair = by_sym
            max_date = df["date"].max()
            gap_days = (pd.Timestamp.now(tz="UTC") - max_date).days
            logger.info(
                f"[FundingPP] Loaded {len(df)} rows across {len(by_sym)} symbols "
                f"(gap={gap_days}d)"
            )
            if gap_days > 3:
                logger.warning(
                    f"[FundingPP] STALE: funding_perpair.parquet is {gap_days}d behind — "
                    f"re-run scripts/build_historical_funding_perpair.py"
                )
            return by_sym
        except Exception as e:
            logger.warning(f"[FundingPP] Could not load ({e}) — per-pair funding defaulting to 0")
            FinBuddyFreqAI_v23._historical_funding_perpair = {}
            return {}

    def _get_pair_funding_series(self, dataframe: "DataFrame", pair: str) -> dict:
        """Return per-candle funding_rate/z30d/chg for the given pair.

        Converts FreqTrade pair format ('ETH/USDT:USDT') to Binance symbol
        ('ETHUSDT'), looks up in the per-pair cache, and merges backward.
        Defaults to 0.0 if the symbol is missing from the parquet.
        """
        n   = len(dataframe)
        sym = pair.replace("/", "").replace(":USDT", "")
        by_sym = self._load_historical_funding_perpair()
        hist   = by_sym.get(sym)
        if hist is None or hist.empty:
            return {
                "pair_funding_rate":      pd.Series([0.0] * n, index=dataframe.index),
                "pair_funding_rate_z30d": pd.Series([0.0] * n, index=dataframe.index),
                "pair_funding_rate_chg":  pd.Series([0.0] * n, index=dataframe.index),
            }
        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        df_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged  = pd.merge_asof(df_join, hist[["date","funding_rate","funding_rate_z30d","funding_rate_chg"]],
                                on="date", direction="backward")
        merged  = merged.sort_values("index").reset_index(drop=True)
        return {
            "pair_funding_rate":      pd.Series(merged["funding_rate"].fillna(0.0).values,      index=dataframe.index),
            "pair_funding_rate_z30d": pd.Series(merged["funding_rate_z30d"].fillna(0.0).values, index=dataframe.index),
            "pair_funding_rate_chg":  pd.Series(merged["funding_rate_chg"].fillna(0.0).values,  index=dataframe.index),
        }

    def _load_historical_oi_perpair(self) -> dict:
        """Load per-pair OI history as dict[symbol -> DataFrame]. Cached at class level."""
        if FinBuddyFreqAI_v23._historical_oi_perpair is not None:
            return FinBuddyFreqAI_v23._historical_oi_perpair
        try:
            df = pd.read_parquet(self._HISTORICAL_OI_PERPAIR_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            by_sym = {
                sym: g.sort_values("date").reset_index(drop=True)
                for sym, g in df.groupby("symbol")
            }
            FinBuddyFreqAI_v23._historical_oi_perpair = by_sym
            logger.info(f"[OI-perpair] Loaded {len(df)} rows for {len(by_sym)} symbols")
            return by_sym
        except Exception as e:
            logger.warning(f"[OI-perpair] load failed ({e}) — features default to 0.0")
            FinBuddyFreqAI_v23._historical_oi_perpair = {}
            return {}

    def _get_pair_oi_series(self, dataframe: "DataFrame", pair: str) -> dict:
        """Per-candle OI z30d/chg for the given pair (C5, 2026-06-11).

        Same merge_asof(backward) pattern as _get_pair_funding_series.
        Defaults to 0.0 when the symbol is missing from the parquet.
        """
        n = len(dataframe)
        sym = pair.replace("/", "").replace(":USDT", "")
        hist = self._load_historical_oi_perpair().get(sym)
        if hist is None or hist.empty:
            return {
                "pair_oi_z30d": pd.Series([0.0] * n, index=dataframe.index),
                "pair_oi_chg":  pd.Series([0.0] * n, index=dataframe.index),
            }
        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        df_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_join, hist[["date", "oi_z30d", "oi_chg"]],
                               on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        return {
            "pair_oi_z30d": pd.Series(merged["oi_z30d"].fillna(0.0).values, index=dataframe.index),
            "pair_oi_chg":  pd.Series(merged["oi_chg"].fillna(0.0).values,  index=dataframe.index),
        }

    def _load_historical_oi(self):
        """Load historical BTC Open Interest. Cached at class level."""
        if FinBuddyFreqAI_v23._historical_oi_df is not None:
            return FinBuddyFreqAI_v23._historical_oi_df
        try:
            df = pd.read_parquet(self._HISTORICAL_OI_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True).astype("datetime64[ns, UTC]")
            df = df.sort_values("date").reset_index(drop=True)
            FinBuddyFreqAI_v23._historical_oi_df = df
            max_date = df["date"].max()
            gap_days = (pd.Timestamp.now(tz="UTC") - max_date).days
            logger.info(
                f"[OI] Loaded {len(df)} historical OI events from "
                f"{df['date'].min()} to {max_date} (gap={gap_days}d)"
            )
            if gap_days > 3:
                logger.warning(f"[OI] STALE: open_interest.parquet is {gap_days}d behind")
            return df
        except Exception as e:
            logger.warning(f"[OI] Could not load historical OI parquet ({e})")
            FinBuddyFreqAI_v23._historical_oi_df = pd.DataFrame()
            return FinBuddyFreqAI_v23._historical_oi_df

    def _get_oi_series(self, dataframe: DataFrame) -> dict[str, pd.Series]:
        """
        Vectorized lookup: per-candle BTC Open Interest features.
        Returns 2 Series aligned to dataframe.index.
        """
        hist = self._load_historical_oi()
        n = len(dataframe)
        if hist.empty:
            return {
                "btc_oi_z30d":   pd.Series([0.0] * n, index=dataframe.index),
                "btc_oi_chg":    pd.Series([0.0] * n, index=dataframe.index),
                "btc_ls_ratio":  pd.Series([1.0] * n, index=dataframe.index),  # neutral default
            }
        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, hist, on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        return {
            "btc_oi_z30d":  pd.Series(merged["btc_oi_z30d"].fillna(0.0).values,  index=dataframe.index),
            "btc_oi_chg":   pd.Series(merged["btc_oi_chg"].fillna(0.0).values,   index=dataframe.index),
            "btc_ls_ratio": pd.Series(merged["btc_ls_ratio"].fillna(1.0).values,  index=dataframe.index),
        }

    def _get_regime_series(self, dataframe: DataFrame) -> pd.Series:
        """
        Vectorized lookup: map every candle's date to its historical regime.
        Returns a Series of regime strings aligned with the input dataframe.

        For LIVE trading where historical regime hasn't been built yet, falls
        back to repeating the live regime across all rows.

        FIXED 2026-06-08 — stale-parquet deadlock. historical_regime.parquet is rebuilt
        by a DAILY cron (build_historical_regime.py) and lags real time by up to ~36h.
        merge_asof(direction=backward) forward-fills the parquet's LAST value onto every
        live candle past its coverage. When that last value is a restrictive regime
        (CRASH/BEAR), it blocks ALL longs on live candles even though the live HMM
        (current.json) reports something else — a total no-trade deadlock (observed
        2026-06-08: parquet ended CRASH @ 2026-06-07 while live HMM = NEUTRAL → 0 trades).
        Fix: for candles BEYOND the parquet's coverage (i.e. live "now" candles), use the
        FRESH live regime from current.json instead of the stale forward-filled value.
        Backtest is unaffected — all its candles fall within parquet coverage.
        """
        hist = self._load_historical_regime()
        if hist.empty:
            return pd.Series([self._get_current_regime()] * len(dataframe), index=dataframe.index)

        dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
        # merge_asof requires both sides sorted by the join key
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, hist[["date", "regime"]], on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        result = pd.Series(merged["regime"].fillna("NEUTRAL").values, index=dataframe.index)

        # Override live candles past the parquet's coverage with the fresh live regime.
        hist_max = hist["date"].max()
        beyond = (dates > hist_max).values
        if beyond.any():
            live_regime = self._get_current_regime()
            result.loc[beyond] = live_regime
            logger.info(
                f"[Regime] {int(beyond.sum())} live candles past parquet coverage "
                f"({hist_max}) set to live regime '{live_regime}' (current.json)"
            )
        return result

    def _get_combined_context(self) -> dict:
        """Read the latest external macro context (Fear & Greed, news, etc.)."""
        try:
            with open(self._COMBINED_CTX_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

    def custom_stake_amount(
        self,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake,
        max_stake: float,
        leverage: float,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> float:
        # Daily circuit breaker (2026-05-23): block new trades if today's closed P&L
        # has already lost more than FREQAI_DAILY_LOSS_LIMIT USDT (default 10).
        # Protects against runaway loss days like May 14 (-26.53 USDT) and May 21 (-14.44 USDT).
        # Tier 2 (flatten at limit × FREQAI_DAILY_FLATTEN_MULT) lives in custom_exit.
        _daily_limit = float(os.environ.get("FREQAI_DAILY_LOSS_LIMIT", "10"))
        _today_pnl = self._today_closed_pnl()
        if _today_pnl < -_daily_limit:
            logger.warning(
                f"[CircuitBreaker] Today P&L = {_today_pnl:.2f} USDT "
                f"(limit={-_daily_limit:.1f}). Blocking new trade entry."
            )
            return 0

        # Bug V fix (2026-05-20): use strategy's _get_current_regime() so all
        # regime reads in one candle agree. Previously called
        # _risk_engine.get_regime() which re-read the JSON — could disagree
        # with populate_entry_trend's cached value on cron-boundary candles.
        regime = self._get_current_regime()
        multiplier = _risk_engine.stake_multiplier(regime)

        # HMM confidence-gated stake sizing (Fix 3, 2026-05-26).
        # The HMM already emits a confidence score (0–1) in current.json but it
        # was NEVER used — only the regime LABEL affected thresholds/stakes.
        # Regime TRANSITIONS are highest-risk (model temporarily miscalibrated).
        # Low confidence → transitioning → reduce stake to limit drawdown.
        # Formula: conf=0.3 → 0.65x stake; conf=0.9 → 0.95x; conf=1.0 → 1.0x.
        # Risk is one-sided: confidence can ONLY REDUCE stake, never increase it.
        try:
            with open(self._REGIME_FILE) as _rf:
                _regime_data = json.load(_rf)
            _regime_conf = float(_regime_data.get("confidence", 0.5))
        except Exception:
            _regime_conf = 0.5
        confidence_factor = 0.5 + 0.5 * _regime_conf   # maps [0,1] → [0.5, 1.0]
        logger.debug(
            f"[HMMConfidence] regime={regime} conf={_regime_conf:.2f} "
            f"factor={confidence_factor:.3f}"
        )
        current_profit_ratio = kwargs.get('current_profit_ratio', 0.0) or 0.0
        if not _risk_engine.max_drawdown_gate(abs(current_profit_ratio)):
            logger.warning(f"[RiskEngine] DD gate CLOSED — skipping trade (dd={current_profit_ratio:.2%})")
            return 0
        if multiplier == 0.0:
            logger.warning(f"[RiskEngine] CRASH regime — skipping trade")
            return 0

        # Bug II fix (2026-05-20): defensive secondary cluster-cap check.
        # confirm_trade_entry has a race (two same-candle entries snapshot
        # the same pre-write state and both pass). By the time we hit
        # custom_stake_amount the DB is fresher — re-check and return 0 if
        # the cluster overflowed since confirm_trade_entry passed.
        pair = kwargs.get("pair") or (entry_tag or "")
        cluster = self._PAIR_CLUSTER.get(pair, "ALTCOIN")
        if cluster != "ALTCOIN":
            cluster_open = sum(
                1 for t in Trade.get_trades_proxy(is_open=True)
                if self._PAIR_CLUSTER.get(t.pair, "ALTCOIN") == cluster
            )
            if cluster_open >= self._MAX_CLUSTER_POSITIONS:
                logger.warning(
                    f"[CorrLimit/secondary] Blocking {pair} stake: cluster={cluster} "
                    f"now has {cluster_open}/{self._MAX_CLUSTER_POSITIONS} (race-cap)"
                )
                return 0

        base_stake = min(proposed_stake, max_stake)
        result = round(base_stake * multiplier * confidence_factor, 2)
        # ── Probe-scale (2026-06-23, env-gated FREQAI_PROBE_SCALE=1; default off) ──
        # Anti-martingale: enter at a REDUCED "probe" size. adjust_trade_position then
        # adds the rest ONLY to trades that confirm (go green in the first candles). The
        # measured structure: ~28 trades/2mo ride to a 100%-WR exit_signal; the other ~180
        # are coin-flip noise. We can't tell them apart at entry — so let the market reveal
        # them with a small probe, then back the winners. Winners get full size, losers stay
        # small. Sidesteps the unsolvable "predict direction at entry" problem entirely.
        if os.environ.get("FREQAI_PROBE_SCALE", "0") == "1":
            probe_frac = float(os.environ.get("FREQAI_PROBE_FRACTION", "0.5"))
            result = round(result * probe_frac, 2)
        logger.info(
            f"[RiskEngine] stake={result} regime={regime} mult={multiplier} "
            f"conf_factor={confidence_factor:.3f}"
        )
        return max(result, min_stake or 0)

    def adjust_trade_position(
        self, trade, current_time: datetime, current_rate: float,
        current_profit: float, min_stake, max_stake: float,
        current_entry_rate: float, current_exit_rate: float,
        current_entry_profit: float, current_exit_profit: float, **kwargs,
    ):
        """Anti-martingale probe-scale: add to confirmed winners once.

        Only active when FREQAI_PROBE_SCALE=1. The initial entry is a reduced probe
        (custom_stake_amount × FREQAI_PROBE_FRACTION). When a trade has gone green past
        FREQAI_PROBE_CONFIRM_PCT within the first FREQAI_PROBE_WINDOW candles, add the
        remaining size — backing the trades the market has shown are working. Losers are
        never added to; they stay at the small probe size and exit via stop/progress/signal.
        """
        # ── Partial take-profit (Lever 3, 2026-07-08; env-gated, default OFF) ──
        # Live measurement: signal exits +406.87 (91% WR) vs stop_loss −394.10 (0% WR)
        # — the exit side is the edge, entries are coin flips. Lever 1 (K_SL 3.5)
        # cuts the stop-bleed rate but PF stayed <1 across the whole sweep. This
        # banks PARTIAL_TP_FRACTION of the position once profit reaches
        # PARTIAL_TP_TRIGGER × (K_TP × entry-ATR) — locking in the winners the
        # exit alpha finds before they can round-trip — while the remainder rides
        # to signal/trail. Fires once per trade. Brain A/B queued before any live use.
        if (os.environ.get("FREQAI_PARTIAL_TP", "0") == "1"
                and trade.nr_of_successful_exits == 0):
            entry_atr_pct = trade.get_custom_data("entry_atr_pct")
            if entry_atr_pct:
                trigger = float(os.environ.get("FREQAI_PARTIAL_TP_TRIGGER", "0.5"))
                fraction = float(os.environ.get("FREQAI_PARTIAL_TP_FRACTION", "0.5"))
                # current_profit is leverage-inclusive while ATR% is a raw price
                # move — same convention as the custom_stoploss trail trigger
                # (documented 2026-06-12); the two stay coherent.
                tp_pct = self.K_TP * float(entry_atr_pct)
                if current_profit >= tp_pct * trigger:
                    reduce_stake = round(trade.stake_amount * fraction, 2)
                    if reduce_stake > 0:
                        return -reduce_stake

        if os.environ.get("FREQAI_PROBE_SCALE", "0") != "1":
            return None
        # Add only once (initial probe = 1 entry; after add = 2).
        if trade.nr_of_successful_entries >= 2:
            return None
        confirm_pct = float(os.environ.get("FREQAI_PROBE_CONFIRM_PCT", "0.004"))  # +0.4%
        window = int(os.environ.get("FREQAI_PROBE_WINDOW", "2"))
        candles_open = int((current_time - trade.open_date_utc).total_seconds()
                           / timeframe_to_seconds(self.timeframe))
        if candles_open > window:
            return None  # confirmation window passed — never scale a late/lagging trade
        if current_profit < confirm_pct:
            return None  # not confirmed yet (or underwater) — hold the small probe
        # Confirmed winner — add the complement of the probe fraction (≈ bring to full size).
        probe_frac = float(os.environ.get("FREQAI_PROBE_FRACTION", "0.5"))
        try:
            add_frac = max(0.0, (1.0 / probe_frac) - 1.0)  # 0.5 → +1.0× (doubles to full)
            add_stake = round(trade.stake_amount * add_frac, 2)
            if add_stake <= 0:
                return None
            if max_stake and trade.stake_amount + add_stake > max_stake:
                add_stake = round(max_stake - trade.stake_amount, 2)
            if min_stake and add_stake < min_stake:
                return None
            return add_stake
        except Exception:
            return None

    # Confidence-based leverage tiers (added 2026-05-20).
    # Read from env so they can be tuned without code changes.
    # Each tier = (min_confidence_ratio, leverage). Confidence ratio = how far
    # the centered_pred exceeds its threshold. ratio 1.0 = exactly at threshold,
    # ratio 2.0 = double the threshold magnitude. Pick the highest tier whose
    # min_ratio the trade clears.
    _LEV_LOW_CONF_RATIO  = float(os.getenv("FREQAI_LEV_LOW_CONF_RATIO",  "1.0"))   # bare-minimum entry
    _LEV_MED_CONF_RATIO  = float(os.getenv("FREQAI_LEV_MED_CONF_RATIO",  "1.5"))   # solid signal
    _LEV_HIGH_CONF_RATIO = float(os.getenv("FREQAI_LEV_HIGH_CONF_RATIO", "2.0"))   # strong conviction
    _LEV_LOW  = float(os.getenv("FREQAI_LEV_LOW",  "1.0"))   # bare entry → no leverage
    _LEV_MED  = float(os.getenv("FREQAI_LEV_MED",  "2.0"))   # solid → 2x (old default)
    _LEV_HIGH = float(os.getenv("FREQAI_LEV_HIGH", "3.0"))   # strong → 3x (capped by exchange max)

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        """
        Confidence-based leverage (2026-05-20).

        Reads the latest centered prediction (per-pair median offset, same as
        populate_entry_trend) and compares its magnitude to the dynamic
        threshold for this side. The further past threshold, the higher the
        leverage tier. If we can't read the dataframe (rare race), default
        to MED (2x) — the prior fixed-leverage behavior.

        Tier table (defaults, env-tunable):
          ratio  < 1.0   → reject (shouldn't happen — entry already passed)
          1.0 ≤ ratio < 1.5  → 1x (low conviction, just past threshold)
          1.5 ≤ ratio < 2.0  → 2x (solid signal)
          ratio ≥ 2.0        → 3x (strong conviction)
        Always clamped to max_leverage from exchange.
        """
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if df is None or df.empty:
                return min(self._LEV_MED, max_leverage)
            last = df.iloc[-1]
            pred = float(last.get("&-future_return", 0.0))
            # Serve-time recentering: same slow trailing median as entry/exit.
            # tail(N).median() == last value of rolling(N, min_periods=..).median().
            # FIXED 2026-06-08: window 100 (25h) → _CENTERING_WINDOW (20d) so the
            # directional signal is preserved (see _CENTERING_WINDOW docstring).
            rolling_median = df["&-future_return"].tail(self._CENTERING_WINDOW).median()
            centered = pred - rolling_median

            if side == "long":
                thresh = float(last.get("dynamic_long_threshold", 1.0))
                # threshold is positive; centered should be > thresh
                ratio = centered / thresh if thresh != 0 else 0.0
            else:  # short
                thresh = float(last.get("dynamic_short_threshold", -1.0))
                # threshold is negative; centered should be < thresh (both negative).
                # ratio = how many threshold-magnitudes below 0 the prediction is.
                ratio = centered / thresh if thresh != 0 else 0.0

            if ratio >= self._LEV_HIGH_CONF_RATIO:
                lev = self._LEV_HIGH
                tier = "HIGH"
            elif ratio >= self._LEV_MED_CONF_RATIO:
                lev = self._LEV_MED
                tier = "MED"
            elif ratio >= self._LEV_LOW_CONF_RATIO:
                lev = self._LEV_LOW
                tier = "LOW"
            else:
                # Below 1.0 — entry passed populate_entry_trend but by the time
                # this leverage callback fires, the per-pair median has shifted
                # and centered_pred is no longer above threshold. Size DOWN to
                # 1x (was MED/2x). Fixed 2026-05-20 (Bug III round-3 audit):
                # the prior "MED defensively" gave 2x to sub-threshold trades.
                lev = self._LEV_LOW
                tier = "FALLBACK"

            final = min(lev, max_leverage)
            logger.info(
                f"[Leverage] {pair} {side}: pred={pred:+.3f} centered={centered:+.3f} (median={rolling_median:+.3f}) "
                f"thresh={thresh:+.3f} ratio={ratio:+.2f} "
                f"→ tier={tier} lev={final:.1f}x (cap={max_leverage:.0f}x)"
            )
            return final
        except Exception as e:
            logger.warning(f"[Leverage] {pair} fell back to MED ({self._LEV_MED}x) due to: {e}")
            return min(self._LEV_MED, max_leverage)

    # ------------------------------------------------------------------ #
    # Correlation-aware position gate (added v16.2)                       #
    # ------------------------------------------------------------------ #
    # Pairs are grouped into clusters that move together (high BTC beta,
    # L2 ecosystem, etc.).  At most MAX_CLUSTER_POSITIONS open trades are
    # allowed from any single cluster to avoid over-concentration when e.g.
    # BTC sells off and all MEGA_CAP longs lose simultaneously.
    # ------------------------------------------------------------------ #

    _PAIR_CLUSTER: dict[str, str] = {
        "BTC/USDT:USDT":  "MEGA_CAP",
        "ETH/USDT:USDT":  "MEGA_CAP",
        "SOL/USDT:USDT":  "MEGA_CAP",
        "XRP/USDT:USDT":  "MEGA_CAP",
        "ADA/USDT:USDT":  "MEGA_CAP",
        "AVAX/USDT:USDT": "MEGA_CAP",
        "DOT/USDT:USDT":  "MEGA_CAP",
        "LINK/USDT:USDT": "MEGA_CAP",
        "ATOM/USDT:USDT": "MEGA_CAP",
        "NEAR/USDT:USDT": "MEGA_CAP",
        "BNB/USDT:USDT":  "MEGA_CAP",
        "ARB/USDT:USDT":  "L2",
        "OP/USDT:USDT":   "L2",
        "APT/USDT:USDT":  "L2",
        "SUI/USDT:USDT":  "L2",
        "POL/USDT:USDT":  "L2",
        "1000SHIB/USDT:USDT": "MEME",
        "1000PEPE/USDT:USDT": "MEME",
        "WIF/USDT:USDT":  "MEME",
        "FET/USDT:USDT":  "AI",
        "RENDER/USDT:USDT": "AI",
        "AAVE/USDT:USDT": "DEFI",
        "LDO/USDT:USDT":  "DEFI",
        "INJ/USDT:USDT":  "L1_ALT",
        "HBAR/USDT:USDT": "L1_ALT",
        "FIL/USDT:USDT":  "INFRA",
        # Everything else -> "ALTCOIN" (independent enough)
    }
    _MAX_CLUSTER_POSITIONS = 2  # hard cap per cluster

    # Funding-rate crowding guard. Renamed 2026-05-20 from _FUNDING_LONG_BLOCK_THRESHOLD
    # because the gate is now applied SYMMETRICALLY: longs blocked when funding
    # > +threshold (longs crowded); shorts blocked when funding < -threshold
    # (shorts crowded). Previous one-sided gate contributed to long bias.
    _FUNDING_CROWDED_THRESHOLD = 0.0005   # 0.05% per 8h (extreme crowding either side)
    _FUNDING_LONG_BLOCK_THRESHOLD = _FUNDING_CROWDED_THRESHOLD  # backward-compat alias
    # Use container-writable path; falls back gracefully if dir missing
    _FUNDING_CACHE_FILE = Path("/freqtrade/user_data/data/external/funding_rate_cache.json")
    _FUNDING_CACHE_TTL_MIN = 15

    def _get_btc_funding_rate(self) -> float | None:
        """Return latest BTC perpetual funding rate with 15-min on-disk cache."""
        import time
        import urllib.request
        cache = self._FUNDING_CACHE_FILE
        try:
            if cache.exists():
                cached = json.loads(cache.read_text())
                if (time.time() - cached.get("ts", 0)) / 60 < self._FUNDING_CACHE_TTL_MIN:
                    return cached.get("funding_rate")
        except Exception:
            pass
        try:
            url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read().decode())
            rate = float(data.get("lastFundingRate", 0))
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"funding_rate": rate, "ts": time.time()}))
            return rate
        except Exception as e:
            logger.warning(f"[FundingGuard] fetch failed: {e}")
            return None

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        # Gate order (cheapest + most-often-blocking first — Bug IV fix 2026-05-20):
        #   0) re-entry cooldown   (local DB query, ~ms)
        #   1) cluster cap         (in-memory list scan, ~µs)
        #   2) macro fear/greed    (file read, ~ms)
        #   3) funding-rate guard  (HTTP/cache read, ~10–500 ms)
        # Previously funding-rate ran before cluster cap, making wasted Binance
        # HTTP calls every time a cluster-full pair tried to enter.

        # 0. Re-entry cooldown after stop-loss (2026-06-11): a (pair, side) that
        # just stopped out may not re-enter while the prediction is still pinned
        # past the entry cutoff. Counter-trend days churn otherwise — 2026-06-11
        # bounce: APT shorted 3x, ADA 2x, paying the stop-loss each time.
        cooldown_candles = int(os.environ.get("FREQAI_REENTRY_COOLDOWN_CANDLES", "8"))
        if cooldown_candles > 0:
            cutoff = current_time - timedelta(
                seconds=timeframe_to_seconds(self.timeframe) * cooldown_candles
            )
            for t in Trade.get_trades_proxy(pair=pair, is_open=False):
                if (
                    t.close_date_utc
                    and t.close_date_utc >= cutoff
                    and t.is_short == (side == "short")
                    and (t.exit_reason or "") == "stop_loss"
                ):
                    logger.info(
                        f"[ReentryCooldown] Blocking {side} on {pair}: stop_loss "
                        f"exit at {t.close_date_utc} within {cooldown_candles}-candle cooldown."
                    )
                    return False

        # 1. Correlation cluster cap
        cluster = self._PAIR_CLUSTER.get(pair, "ALTCOIN")
        if cluster != "ALTCOIN":
            open_trades = Trade.get_trades_proxy(is_open=True)
            cluster_open = sum(
                1 for t in open_trades
                if self._PAIR_CLUSTER.get(t.pair, "ALTCOIN") == cluster
            )
            if cluster_open >= self._MAX_CLUSTER_POSITIONS:
                logger.info(
                    f"[CorrLimit] Blocking {pair} entry: cluster={cluster} "
                    f"already has {cluster_open}/{self._MAX_CLUSTER_POSITIONS} open trades."
                )
                return False

        # 2. Macro safety gate — reads combined_context.json from external fetchers.
        ctx = self._get_combined_context()
        fear_greed = ctx.get("fear_greed", 50)
        market_change = ctx.get("market_cap_change_24h_pct", 0)

        if side == "long":
            if fear_greed < 20:
                logger.info(f"[MacroGate] Blocking long on {pair}: Fear & Greed={fear_greed} (Extreme Fear)")
                return False
            if market_change < -3.0:
                logger.info(f"[MacroGate] Blocking long on {pair}: market cap 24h change={market_change:.2f}% (crash signal)")
                return False
        else:  # short
            if fear_greed > 80:
                logger.info(f"[MacroGate] Blocking short on {pair}: Fear & Greed={fear_greed} (Extreme Greed)")
                return False

        # 3. Funding-rate crowding guard (symmetric since Bug C fix 2026-05-20).
        # Block longs when longs overcrowded (funding strongly positive) AND
        # block shorts when shorts overcrowded (funding strongly negative).
        funding = self._get_btc_funding_rate()
        if funding is not None:
            if side == "long" and funding > self._FUNDING_CROWDED_THRESHOLD:
                logger.info(
                    f"[FundingGuard] Blocking long on {pair}: "
                    f"BTC funding={funding:.4%} > +{self._FUNDING_CROWDED_THRESHOLD:.4%} (longs crowded)"
                )
                return False
            if side == "short" and funding < -self._FUNDING_CROWDED_THRESHOLD:
                logger.info(
                    f"[FundingGuard] Blocking short on {pair}: "
                    f"BTC funding={funding:.4%} < -{self._FUNDING_CROWDED_THRESHOLD:.4%} (shorts crowded)"
                )
                return False

        return True

    # ------------------------------------------------------------------ #
    # FreqAI feature engineering (v10 — unchanged)                       #
    # ------------------------------------------------------------------ #

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        # B1 pruning (2026-06-11): raw EMA/SMA are price-level (non-stationary)
        # features — every one ranked in the dead tail of the importance report
        # (finbuddy_memory/analytics/feature_importance.json). Env-gated: brain
        # validates FREQAI_PRUNE_INDICATORS=1 before the live identifier bump.
        if os.environ.get("FREQAI_PRUNE_INDICATORS", "0") != "1":
            dataframe["%-ema-period"] = ta.EMA(dataframe, timeperiod=period)
            dataframe["%-sma-period"] = ta.SMA(dataframe, timeperiod=period)

        bb = ta.BBANDS(dataframe, timeperiod=period)
        dataframe["%-bb_width-period"] = (
            (bb["upperband"] - bb["lowerband"]) / bb["middleband"]
        )
        dataframe["%-bb_pct-period"] = (
            (dataframe["close"] - bb["lowerband"])
            / (bb["upperband"] - bb["lowerband"] + 1e-9)
        )

        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)
        dataframe["%-relative_volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        macd = ta.MACD(dataframe)
        dataframe["%-macd"] = macd["macd"]
        dataframe["%-macd_signal"] = macd["macdsignal"]
        dataframe["%-macd_hist"] = macd["macdhist"]

        dataframe["%-atr"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]

        rolling_high = dataframe["high"].rolling(self._DAY_CANDLES).max()
        rolling_low = dataframe["low"].rolling(self._DAY_CANDLES).min()
        dataframe["%-price_position"] = (
            (dataframe["close"] - rolling_low)
            / (rolling_high - rolling_low + 1e-9)
        )
        return dataframe

    # Numeric mapping for HMM regime → FreqAI feature
    _REGIME_NUMERIC = {"CRASH": -2, "BEAR": -1, "NEUTRAL": 0, "BULL": 1, "EUPHORIA": 2}

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        v23 standard features — temporal context + raw OHLCV + external macro signals.

        Temporal (v19): day_of_week, hour_of_day, raw_close/volume/open

        Layer 4 (v23) — wider context from existing cron pipelines:
          %-fear_greed       — Fear & Greed index 0-100 (Phase 2 cron, every 15m)
          %-btc_dominance    — BTC market dominance % (Phase 2 cron)
          %-regime_numeric   — HMM regime encoding: CRASH=-2…EUPHORIA=+2 (Phase 3, every 4h)
          %-recent_wr        — rolling 50-trade WR, written to env by trade_postmortem cron

        All external reads have safe fallbacks — if a file is missing or env var absent,
        the feature defaults to a neutral value so the bot never crashes on missing data.
        """
        # Temporal
        dataframe["%-day_of_week"] = pd.to_datetime(dataframe["date"]).dt.dayofweek
        dataframe["%-hour_of_day"] = pd.to_datetime(dataframe["date"]).dt.hour
        dataframe["%-raw_close"]   = dataframe["close"]
        dataframe["%-raw_volume"]  = dataframe["volume"]
        dataframe["%-raw_open"]    = dataframe["open"]

        # External macro/regime/wr features — gated by FEATURE_SET (brain ablation toggle, 2026-05-19).
        # "all" (default) preserves live behavior; "no_macro" / "no_regime" / "minimal" let the brain
        # test whether these features actually help (117 experiments / 0 winners on "all").
        include_macro  = self.FEATURE_SET in ("all", "no_regime")
        include_regime = self.FEATURE_SET in ("all", "no_macro")

        if include_macro:
            # fear_greed from alternative.me historical, btc_strength = BTC 7d ret − ETH 7d ret
            macros = self._get_macro_series(dataframe)
            dataframe["%-fear_greed"]    = macros["fear_greed"]
            dataframe["%-btc_strength"]  = macros["btc_strength"]
            # BTC perp funding rate (added 2026-05-19): strongest cheap signal for
            # 1–4h crypto perp moves. Already used as a long-block gate; now also
            # fed to LightGBM so the model can learn funding × momentum × regime.
            funding = self._get_funding_series(dataframe)
            dataframe["%-funding_rate"]      = funding["funding_rate"]
            dataframe["%-funding_rate_z30d"] = funding["funding_rate_z30d"]
            dataframe["%-funding_rate_chg"]  = funding["funding_rate_chg"]

            # Per-pair funding rate (added 2026-06-04): pair's own crowding signal.
            # BTC funding is market-wide; each pair has independent positioning dynamics.
            # ETH at -0.02% (longs paid) vs BTC at +0.03% (longs paying) = totally different
            # setups. 3 features: raw rate, z30d extremeness, momentum (chg).
            pair_funding = self._get_pair_funding_series(dataframe, metadata.get("pair", ""))
            dataframe["%-pair_funding_rate"]      = pair_funding["pair_funding_rate"]
            dataframe["%-pair_funding_rate_z30d"] = pair_funding["pair_funding_rate_z30d"]
            dataframe["%-pair_funding_rate_chg"]  = pair_funding["pair_funding_rate_chg"]

            # Open Interest Delta (added 2026-05-23): global proxy for market leverage
            oi = self._get_oi_series(dataframe)
            dataframe["%-btc_oi_z30d"]  = oi["btc_oi_z30d"]
            dataframe["%-btc_oi_chg"]   = oi["btc_oi_chg"]
            dataframe["%-btc_ls_ratio"] = oi["btc_ls_ratio"]  # L/S positioning ratio; high=crowded longs

            # Per-pair Open Interest (C5, 2026-06-11). Env-gated: enabling changes
            # the feature set → requires identifier bump + pkl flush on the live
            # bot (feature-added recovery recipe). Brain validates with
            # FREQAI_PERPAIR_OI=1 before any live flip.
            if os.environ.get("FREQAI_PERPAIR_OI", "0") == "1":
                pair_oi = self._get_pair_oi_series(dataframe, metadata.get("pair", ""))
                dataframe["%-pair_oi_z30d"] = pair_oi["pair_oi_z30d"]
                dataframe["%-pair_oi_chg"]  = pair_oi["pair_oi_chg"]
        else:
            logger.info(f"[FeatureSet] mode={self.FEATURE_SET} — skipping fear_greed/btc_strength/funding")

        if include_regime:
            # HMM regime encoding — per-candle historical regime (Fix 2026-05-17)
            regime_series = self._get_regime_series(dataframe)
            dataframe["%-regime_numeric"] = regime_series.map(lambda r: self._REGIME_NUMERIC.get(r, 0)).astype(float)

            # Trend-horizon score (E3, 2026-06-11): -3..+3 multi-horizon trend
            # agreement from historical_regime.parquet. Env-gated — enabling
            # changes the feature set (identifier bump + pkl flush required).
            if os.environ.get("FREQAI_TREND_HORIZON", "0") == "1":
                hist = self._load_historical_regime()
                if not hist.empty and "trend_horizon" in hist.columns:
                    dates = pd.to_datetime(dataframe["date"], utc=True).astype("datetime64[ns, UTC]")
                    dj = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
                    merged = pd.merge_asof(dj, hist[["date", "trend_horizon"]],
                                           on="date", direction="backward")
                    merged = merged.sort_values("index").reset_index(drop=True)
                    dataframe["%-trend_horizon"] = pd.Series(
                        merged["trend_horizon"].fillna(0.0).values, index=dataframe.index)
                else:
                    dataframe["%-trend_horizon"] = 0.0
        else:
            logger.info(f"[FeatureSet] mode={self.FEATURE_SET} — skipping regime_numeric")

        # Bug D fix (2026-05-20): %-recent_wr REMOVED.
        # The feature read os.getenv("FINBUDDY_RECENT_WR", "0.50") which is
        # written live every 15min by trade_postmortem.py (~0.34 right now)
        # but defaults to 0.50 in brain backtests and walk-forward (those
        # processes don't see the .env file). Result was classical
        # training-serving skew: model trained on a constant 0.50 then served
        # ~0.34 in production — feature distribution mismatch. The feature
        # was never validated as predictive in the first place. Dropping
        # cleanly is the right call. Brain hypothesis space loses one knob
        # but no profitable config has ever relied on it.

        # Per-pair relative strength vs BTC (added 2026-05-25).
        # Cross-sectional momentum: how strongly is this pair moving vs BTC?
        # Positive = outperforming BTC (structural strength → long signal).
        # Negative = underperforming BTC (structural weakness → short signal).
        # Uses 3 lookback windows on 15m base: 14 (~3.5h), 28 (~7h), 56 (~14h).
        # Diagnostic (2026-05-25): BTC informative features rank 4th/8th in the live model,
        # confirming the model values BTC-relative signals. Per-pair RS is the natural extension.
        if include_macro and metadata.get("pair") != "BTC/USDT:USDT":
            rs_windows = (14, 28, 56)
            btc_rets = self._get_btc_returns(dataframe, rs_windows)
            for w in rs_windows:
                pair_ret = dataframe["close"].pct_change(w).fillna(0.0)
                dataframe[f"%-rel_strength_btc_{w}"] = pair_ret - btc_rets[w]
        else:
            for w in (14, 28, 56):
                dataframe[f"%-rel_strength_btc_{w}"] = 0.0

        return dataframe

    # ------------------------------------------------------------------ #
    # v23 — Regression target: predicted future % return                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _meta_outcome_labels(dataframe, horizon, tp_mult, sl_mult, side, atr, fee_pct):
        """Net-of-fees realized-outcome label for META-LABELING (Phase 3, CORRECTED 2026-06-20).

        Returns a float Series: 1.0 if — entering at this candle on `side` — the trade ends
        NET-PROFITABLE, else 0.0. Last `horizon` rows + ATR warmup are NaN (future unknown) so
        FreqAI drops them — same treatment as &-future_return.

        WHY THIS REPLACES the old 3*ATR/2*ATR triple-barrier (the 2026-06-17 version):
          The bot does NOT exit on a far TP barrier — it exits on SIGNAL/trail/ROI, and real
          winners cash out at ~+0.9% (median), often BELOW the old 3*ATR TP. Validated against
          783 real trades: the old label caught only 24.8% of actual winners (mislabeled 75% of
          the positive class as losses) — its meta-model was trained on a corrupted target, which
          is why the 2026-06-19 A/B showed "no separation". This label, scored against the same
          783 real outcomes, agrees 77.4% of the time (winner-recall 0.77, +rate 0.445 vs true
          base 0.405). See session note 2026-06-20.

        Outcome rule (path-aware, first-touch within `horizon`):
          • favorable barrier touched first (+tp_mult*ATR, padded by round-trip fee) → 1 (win)
          • stop barrier touched first (-sl_mult*ATR)                                → 0 (loss)
          • neither (timeout)        → judge by forward return at horizon, net of fee_pct
          • both in same candle (tie) → 0 (conservative)

        Defaults (env-tunable, see set_freqai_targets): tp_mult=2.0, sl_mult=2.0 (symmetric — the
        empirically-best definition), horizon=24 (≈ p90 of real holding; median is 4.6 candles),
        fee_pct=0.10 (round-trip taker). O(horizon) vectorized numpy; no NaN-compare warnings.
        """
        close = dataframe["close"].to_numpy(dtype=float)
        high  = dataframe["high"].to_numpy(dtype=float)
        low   = dataframe["low"].to_numpy(dtype=float)
        a     = np.asarray(atr, dtype=float)
        n     = len(close)
        h     = int(horizon)
        feep  = close * (fee_pct / 100.0)        # round-trip fee, in price units

        if side == "long":
            tp_level = close + tp_mult * a + feep    # favorable = price rises; pad TP by fee
            sl_level = close - sl_mult * a
        else:  # short: favorable = price falls
            tp_level = close - tp_mult * a - feep
            sl_level = close + sl_mult * a

        tp_hit = np.full(n, np.inf)
        sl_hit = np.full(n, np.inf)
        for d in range(1, h + 1):
            fut_high = np.full(n, -np.inf); fut_high[: n - d] = high[d:]
            fut_low  = np.full(n,  np.inf); fut_low[: n - d]  = low[d:]
            if side == "long":
                tp_touch = fut_high >= tp_level
                sl_touch = fut_low  <= sl_level
            else:
                tp_touch = fut_low  <= tp_level
                sl_touch = fut_high >= sl_level
            # Record earliest offset only (where not already hit).
            tp_hit = np.where(np.isinf(tp_hit) & tp_touch, float(d), tp_hit)
            sl_hit = np.where(np.isinf(sl_hit) & sl_touch, float(d), sl_hit)

        # TP strictly before SL = win; SL-first and same-candle ties = loss.
        label = np.where(tp_hit < sl_hit, 1.0, 0.0)

        # Timeout (neither barrier touched): judge by realized forward return net of fees.
        # This is what fixes the old label's blindness to small signal-exit winners.
        neither   = np.isinf(tp_hit) & np.isinf(sl_hit)
        close_fwd = np.full(n, np.nan); close_fwd[: n - h] = close[h:]
        raw_ret   = (close_fwd / close - 1.0) * 100.0
        fwd_ret   = raw_ret if side == "long" else -raw_ret
        fwd_cmp   = np.where(np.isfinite(fwd_ret), fwd_ret, -np.inf)   # avoid NaN-compare warns
        label     = np.where(neither & (fwd_cmp - fee_pct > 0.0), 1.0, label)

        label[~np.isfinite(a)] = np.nan            # ATR warmup rows
        if h > 0:
            label[n - h:] = np.nan                 # incomplete future
        return pd.Series(label, index=dataframe.index)

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Regression target: future_return = (close[t+horizon] / close[t] - 1) * 100

        Why regression instead of triple-barrier classification:
          Classification with K_TP=2.0/K_SL=1.0 produces P(SL_first) = 2/(2+1) = 67% "S" labels.
          LightGBM biases toward the majority class -> near-zero long predictions in bull markets.
          Even with class_weight=balanced, the WR ceiling was 35% (unprofitable at any R:R).

          Regression has no classes -> no imbalance. The model predicts a continuous % return.
          Entry only when predicted magnitude exceeds dynamic thresholds.
          Positive predicted_return -> favorable for longs.
          Negative predicted_return -> favorable for shorts.

        FreqAI column: "&-future_return" - the regressor predicts this value.
        Last label_period_candles rows are NaN (future not yet available - FreqAI drops them).

        2026-05-22: target is now Z-SCORED over a 30-day rolling window of PAST returns
        to completely eliminate look-ahead bias and ensure the distribution is standard-normal.
        """
        horizon = self._label_period_candles()
        raw_return_pct = (
            dataframe["close"].shift(-horizon) / dataframe["close"] - 1.0
        ) * 100

        # Compute past return over the same horizon (uses 100% past data) to avoid look-ahead bias
        past_return = (dataframe["close"] / dataframe["close"].shift(horizon) - 1.0) * 100
        
        # Calculate mean and std on past_return, which has NO look-ahead bias at all
        ROLLING = self._Z_ROLLING   # 2880@15m, TF-derived (30 days)
        mu  = past_return.rolling(ROLLING, min_periods=self._CENTERING_MIN_PERIODS).mean()
        sig = past_return.rolling(ROLLING, min_periods=self._CENTERING_MIN_PERIODS).std().replace(0, 1e-9)
        
        # Standardize the raw FUTURE target using past parameters.
        # DO NOT fillna here — let NaN rows stay NaN so FreqAI drops them correctly:
        #   - Last label_period_candles=24 rows: raw_return_pct is NaN (future unknown).
        #     fillna(0.0) would label them "return=0%" and train on unlabeled future.
        #   - First ~199 rows: mu/sig are NaN (rolling min_periods). fillna(0.0) would
        #     assign a neutral-but-wrong z-score=0 to those samples.
        # FreqAI filters NaN-target rows before fitting. Dropping them is correct.
        dataframe["&-future_return"] = (raw_return_pct - mu) / sig

        # Phase 3 META-LABELING targets (2026-06-17, default OFF). Only emitted when
        # FREQAI_META_LABEL=1 so the live single-target model is byte-identical. Two binary
        # triple-barrier targets (long/short) train a 2nd model that, at entry time, predicts
        # "will this trade reach TP before the stop?". Used with freqaimodel=
        # LightGBMRegressorMultiTarget (one independent model per target → the primary
        # &-future_return regressor is unchanged). Barriers match live risk geometry (K_TP/K_SL).
        if os.getenv("FREQAI_META_LABEL", "0") == "1":
            atr      = ta.ATR(dataframe, timeperiod=14)
            meta_h   = int(os.getenv("FREQAI_META_HORIZON", str(self._META_HORIZON_DEFAULT)))
            meta_tp  = float(os.getenv("FREQAI_META_TP_MULT", "2.0"))
            meta_sl  = float(os.getenv("FREQAI_META_SL_MULT", "2.0"))
            meta_fee = float(os.getenv("FREQAI_META_FEE_PCT", "0.10"))
            dataframe["&-meta_long"] = self._meta_outcome_labels(
                dataframe, meta_h, meta_tp, meta_sl, "long", atr, meta_fee)
            dataframe["&-meta_short"] = self._meta_outcome_labels(
                dataframe, meta_h, meta_tp, meta_sl, "short", atr, meta_fee)
        return dataframe

    # ------------------------------------------------------------------ #
    # Layer 2: Regime-aware dynamic entry thresholds                    #
    # ------------------------------------------------------------------ #

    # Regime multipliers: (long_mult, short_mult).
    # Higher multiplier = harder to enter in that direction.
    _REGIME_THRESHOLD_MULTS = {
        "CRASH":    (2.0, 0.5),   # very hard to long, very easy to short
        "BEAR":     (1.3, 0.7),
        "NEUTRAL":  (1.0, 1.0),
        "BULL":     (0.7, 1.3),
        "EUPHORIA": (0.5, 2.0),   # very easy to long, very hard to short
    }

    def _compute_dynamic_thresholds(self, dataframe: DataFrame) -> DataFrame:
        """
        Per-candle entry thresholds that adapt to regime and recent performance.

        Logic (PER CANDLE — uses historical regime in backtest, live regime when running):
          1. Base = LONG_THRESHOLD / abs(SHORT_THRESHOLD) env vars (grid-searchable).
          2. Regime multiplier scales base in each direction PER CANDLE.
             In BEAR: long_mult=1.3 (harder longs), short_mult=0.7 (easier shorts).
             In BULL: long_mult=0.7 (easier longs), short_mult=1.3 (harder shorts).
          3. WR feedback: if FINBUDDY_RECENT_WR > 0.55, lower threshold proportionally
             so the brain trades more aggressively when its model is hot.
             Floor at 50% reduction (wr_adj >= 0.5) to prevent collapse.

        Fix 2026-05-17: regime is now looked up PER CANDLE from historical_regime.parquet
        (built by scripts/build_historical_regime.py). Previously this read the static
        current.json which made dynamic thresholds inert during backtests.
        """
        regime_series = self._get_regime_series(dataframe)

        # NEUTRAL-regime override (2026-08-31): _REGIME_THRESHOLD_MULTS ships NEUTRAL
        # as (1.0, 1.0) — no extra caution either direction, on the assumption that a
        # trendless market is equally hospitable to longs and shorts. Live data showed
        # otherwise: in a multi-week NEUTRAL/choppy stretch, short trades hit the
        # time_limit_exit far more than longs (66% of shorts vs comparable longs) with
        # a losing bias (34.5% WR) — shorts were structurally the weaker side in chop,
        # not because of a regime-mismatch (regime was NEUTRAL for good reason most of
        # that window) but because chop gives directional bets less room to resolve
        # within the fixed exit horizon. Default 1.0/1.0 preserves exact prior behavior
        # — this is purely an opt-in A/B knob until the brain validates a value.
        neutral_mults = (
            float(os.getenv("FREQAI_NEUTRAL_LONG_MULT", "1.0")),
            float(os.getenv("FREQAI_NEUTRAL_SHORT_MULT", "1.0")),
        )
        regime_mults = dict(self._REGIME_THRESHOLD_MULTS)
        regime_mults["NEUTRAL"] = neutral_mults

        # Map regimes → multipliers vectorized
        long_mult_series  = regime_series.map(lambda r: regime_mults.get(r, (1.0, 1.0))[0])
        short_mult_series = regime_series.map(lambda r: regime_mults.get(r, (1.0, 1.0))[1])

        recent_wr = self._load_recent_wr()
        # Fix 8 (2026-05-22): bidirectional WR feedback (was one-directional — only
        # rewarded good WR, never penalized bad WR).
        # Now: WR=32% → wr_adj=1.46 (46% harder to enter)
        #      WR=55% → wr_adj=1.00 (neutral)
        #      WR=70% → wr_adj=0.70 (30% easier to enter)
        # Clamped to [0.5, 2.0] to prevent threshold collapse or near-infinity.
        wr_adj = 1.0 - ((recent_wr - 0.55) * 2.0)
        wr_adj = max(0.5, min(2.0, wr_adj))

        base_long  = self.LONG_THRESHOLD
        base_short = abs(self.SHORT_THRESHOLD)

        # 2026-05-23: cap combined multiplier so regime × WR_adj never push threshold
        # past 2× base. Without cap: BEAR (×1.3) × bad_WR (×1.5) = ×1.95 → longs need
        # prediction > 0.975 → effectively 0 trades on bad-WR BEAR days.
        combined_long  = (long_mult_series  * wr_adj).clip(upper=2.0)
        combined_short = (short_mult_series * wr_adj).clip(upper=2.0)

        dataframe["regime"] = regime_series

        # C1 (2026-06-11): quantile entry mode — threshold is a rolling quantile of
        # the pair's own centered-prediction distribution, so it is attainable BY
        # CONSTRUCTION. The "mathematically unreachable threshold" bug class
        # (4 deadlocks: LT=3.25 promo 05-28, _GLOBAL_STD + std_factor 06-08 x2,
        # stale-regime 06-08) cannot exist in this mode. Default remains "absolute"
        # (legacy path below) until brain validation promotes quantile mode.
        if os.environ.get("FREQAI_ENTRY_MODE", "absolute").lower() == "quantile":
            return self._quantile_thresholds(dataframe, combined_long, combined_short)

        # Per-pair prediction percentile thresholds (Fix 4, 2026-05-26).
        # Each pair has a different prediction std from the model (ZEC std≈3.42,
        # BTC std≈0.40). A global threshold is too tight for volatile pairs
        # (near-zero signals on ZEC) and too loose for stable ones (noisy entries
        # on BTC). We normalize by the pair's own rolling std vs the global
        # expected std=0.95, so every pair is judged at the same signal-quality bar.
        #
        # The column "%-future_return" is the raw target BEFORE FreqAI labels it —
        # in inference it reflects the model's rolling prediction distribution for
        # THIS pair specifically.  Use it during live inference; fall back to the
        # global baseline (0.95) if the column is absent (early candles, backtest
        # first rows, etc.).
        #
        # Clip: min 0.5× (never collapse threshold below half-base for noisy pairs)
        #       max 3.0× (never push threshold above 3× for very stable pairs)
        # FIXED 2026-06-08: _GLOBAL_STD updated from 0.95 (raw-% era) → 0.30 (z-score era).
        # After z-scoring (2026-05-22), model predictions have std≈0.30. With old 0.95:
        #   std_factor = 0.13/0.95 = 0.14 → floored to 0.5 always → threshold = 1.5×1.3×0.5 = 0.975
        #   max centered_pred across all 26 pairs = 0.535 (OP) → ZERO entries ever (no-trade deadlock)
        # With 0.30: std_factor = 0.13/0.30 = 0.43 → floored to 0.5 for immature model,
        #   scales to 1.0 when model pred_std reaches 0.30 (mature). LT was halved to 0.5
        #   simultaneously (.env FREQAI_LONG_THRESHOLD=0.5, SHORT=-0.5).
        # Effective threshold in NEUTRAL+bad_WR: 0.5×1.3×0.5 = 0.325 (immature) → 0.65 (mature).
        # ⚠️ COUPLING: if you change _GLOBAL_STD again, you MUST also update:
        #   .env FREQAI_LONG_THRESHOLD + FREQAI_SHORT_THRESHOLD,
        #   hypothesis_gen.py SEED_CONFIG_V23 LT/ST + AGGRESSIVE_CHOICES + _clamp bounds.
        _GLOBAL_STD = 0.30
        if "%-future_return" in dataframe.columns:
            pair_pred_std = (
                dataframe["%-future_return"]
                .rolling(self._PRED_STD_WINDOW, min_periods=10)
                .std()
                .fillna(_GLOBAL_STD)
            )
        elif "&-future_return" in dataframe.columns:
            pair_pred_std = (
                dataframe["&-future_return"]
                .rolling(self._PRED_STD_WINDOW, min_periods=10)
                .std()
                .fillna(_GLOBAL_STD)
            )
        else:
            pair_pred_std = pd.Series(_GLOBAL_STD, index=dataframe.index)
        # Cap at 1.0 (not 3.0): std_factor > 1.0 means a pair with HIGHER prediction variance
        # gets a HARDER threshold — backwards. High pred_std = better model discrimination,
        # not more noise. Only degenerate pairs (pred_std << 0.30) should be penalized (floor=0.5).
        std_factor = (pair_pred_std / _GLOBAL_STD).clip(lower=0.5, upper=1.0)

        dataframe["dynamic_long_threshold"]  = base_long  * combined_long  * std_factor
        dataframe["dynamic_short_threshold"] = -(base_short * combined_short * std_factor)

        # 2026-06-01: Cap the FINAL effective threshold, not just the multiplier.
        # Previous cap `combined.clip(upper=2.0)` only capped the multiplier product,
        # so LT=3.25 × cap(2.0) = 6.5σ — still mathematically impossible (deadlock).
        # This cap ensures any LT value the brain promotes stays tradeable:
        #   LT=3.25, BEAR(×1.3), bad_WR(×1.3) = 6.5σ → capped to 2.5σ ✓
        #   LT=1.5,  BEAR(×1.3), bad_WR(×1.3) = 2.535σ → capped to 2.5σ ✓
        #   LT=1.5,  BULL(×0.7), good_WR(×0.7) = 0.735σ → not capped ✓
        MAX_EFFECTIVE_THRESHOLD = float(os.getenv("FREQAI_MAX_EFFECTIVE_THRESHOLD", "2.5"))
        dataframe["dynamic_long_threshold"]  = dataframe["dynamic_long_threshold"].clip(upper=MAX_EFFECTIVE_THRESHOLD)
        dataframe["dynamic_short_threshold"] = dataframe["dynamic_short_threshold"].clip(lower=-MAX_EFFECTIVE_THRESHOLD)

        # 2026-07-08: Floor the FINAL effective threshold at the nominal base value.
        # Measured 2026-06-19 (Phase-1 post-mortem): raising .env thresholds
        # 0.3→0.7/−0.6 did NOT cut trade frequency — regime scaling (BEAR
        # short_mult 0.7) × std_factor (≤1.0) absorbed the raise, leaving the
        # effective short threshold ≈ −0.38. The "trade less" lever was never
        # actually pulled. With this floor, multipliers may only make entries
        # STRICTER than the nominal env threshold, never easier — the nominal
        # value means what it says. Env-gated so the brain can A/B floor-off.
        if os.environ.get("FREQAI_THRESHOLD_FLOOR", "1") == "1":
            dataframe["dynamic_long_threshold"]  = dataframe["dynamic_long_threshold"].clip(lower=base_long)
            dataframe["dynamic_short_threshold"] = dataframe["dynamic_short_threshold"].clip(upper=-base_short)
        return dataframe

    def _quantile_thresholds(
        self, dataframe: DataFrame,
        combined_long: pd.Series, combined_short: pd.Series,
    ) -> DataFrame:
        """C1 (2026-06-11): quantile-based adaptive entry thresholds.

        Long threshold  = rolling q-quantile of the pair's centered predictions.
        Short threshold = rolling (1-q)-quantile (negative tail).
        Regime x WR multiplier product shifts q by tiers (easier/normal/stricter)
        instead of multiplying an absolute sigma value, so adverse conditions
        tighten entries without ever making them impossible.

        An absolute floor (FREQAI_ENTRY_ABS_FLOOR) keeps the system flat when the
        prediction distribution is degenerate (quantiles near zero = no signal).
        Window/min_periods reuse _CENTERING_WINDOW so live == backtest exactly,
        matching the centering used in entry/exit/leverage.
        """
        q_base = float(os.environ.get("FREQAI_ENTRY_QUANTILE", "0.92"))
        abs_floor = float(os.environ.get("FREQAI_ENTRY_ABS_FLOOR", "0.10"))
        win, mp = self._CENTERING_WINDOW, self._CENTERING_MIN_PERIODS

        pred = dataframe.get("&-future_return", pd.Series(0.0, index=dataframe.index))
        centered = pred - pred.rolling(win, min_periods=mp).median()

        def rq(q: float) -> pd.Series:
            return centered.rolling(win, min_periods=mp).quantile(min(0.995, max(0.005, q)))

        # Tier the multiplier product: <0.9 easier, 0.9-1.2 normal, >1.2 stricter.
        long_thr = pd.Series(
            np.select(
                [combined_long < 0.9, combined_long > 1.2],
                [rq(q_base - 0.04), rq(q_base + 0.04)],
                default=rq(q_base),
            ),
            index=dataframe.index,
        ).clip(lower=abs_floor)
        short_thr = pd.Series(
            np.select(
                [combined_short < 0.9, combined_short > 1.2],
                [rq(1 - q_base + 0.04), rq(1 - q_base - 0.04)],
                default=rq(1 - q_base),
            ),
            index=dataframe.index,
        ).clip(upper=-abs_floor)

        dataframe["dynamic_long_threshold"] = long_thr
        dataframe["dynamic_short_threshold"] = short_thr
        return dataframe

    # ------------------------------------------------------------------ #
    # Indicator population                                                #
    # ------------------------------------------------------------------ #

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)

        dataframe["rsi_14"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"]  = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        bb = ta.BBANDS(dataframe, timeperiod=20)
        dataframe["bb_upperband"] = bb["upperband"]
        dataframe["bb_lowerband"] = bb["lowerband"]
        dataframe["bb_pct"] = (
            (dataframe["close"] - bb["lowerband"])
            / (bb["upperband"] - bb["lowerband"] + 1e-9)
        )

        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ratio"] = dataframe["atr_14"] / dataframe["close"]

        # Fix 12 (2026-05-22): Order Block column computation REMOVED (dead code).
        # OB veto was removed from populate_entry_trend on 2026-05-22 (commit b44aebe)
        # because it blocked 100% of longs (reversal logic incompatible with trend-following ML).
        # The column computation still ran every candle for all 37 pairs, wasting CPU.
        # Removed here. If OB columns are reintroduced as ML features in future, re-add
        # in feature_engineering_standard() under a FREQAI_FEATURE_SET flag.

        # Layer 2: dynamic thresholds (regime-aware + WR feedback)
        dataframe = self._compute_dynamic_thresholds(dataframe)

        return dataframe

    # ------------------------------------------------------------------ #
    # Entry / Exit signals — v17 classifier probability columns          #
    # ------------------------------------------------------------------ #

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v23 Regression entry — predicted future return vs dynamic thresholds.

        Long:  predicted_return > dynamic_long_threshold  (positive return expected)
        Short: predicted_return < dynamic_short_threshold (negative return expected)

        dynamic thresholds adapt per-candle to regime + recent WR (see _compute_dynamic_thresholds).
        TA filters and OB veto remain as quality gates on top of the ML signal.
        """
        predicted_return = dataframe.get(
            "&-future_return",
            pd.Series(0.0, index=dataframe.index)
        )

        # Serve-time recentering: subtract a SLOW trailing median to remove only the
        # training-serving distribution drift (the ~+0.6σ positive bias that caused the
        # 2026-06-06 BEAR deadlock), WITHOUT eating the directional signal.
        # FIXED 2026-06-08: window 100 (25h) → _CENTERING_WINDOW (1920 = 20d). A 25h median
        # tracked the price trend itself and stripped the alpha (preds forced to 50/50
        # long/short → 0-longs brain bug + 37.7% live WR). A 20d median preserves the
        # model's directional lean (~69% positive stays ~69%) while still removing drift.
        # Consistent with exit and leverage() — all three use _CENTERING_WINDOW.
        rolling_median = predicted_return.rolling(
            self._CENTERING_WINDOW, min_periods=self._CENTERING_MIN_PERIODS
        ).median()
        centered_pred = predicted_return - rolling_median

        long_thresh  = dataframe["dynamic_long_threshold"]
        short_thresh = dataframe["dynamic_short_threshold"]

        # Stability filter: require N consecutive candles past threshold (filters noise spikes).
        # Long: all of last N candles' centered predictions were above long_threshold.
        # Short: all of last N candles' centered predictions were below short_threshold.
        n = max(1, self.STABILITY_N)
        long_above = (centered_pred > long_thresh).astype(int)
        short_below = (centered_pred < short_thresh).astype(int)
        long_stable  = long_above.rolling(n, min_periods=n).sum() >= n
        short_stable = short_below.rolling(n, min_periods=n).sum() >= n

        volatility_ok = dataframe["atr_ratio"] > 0.003

        # ── Option 2+3 entry mode (env-gated FREQAI_ENTRY_MODE=trend_vol; default off) ──
        # Research (2026-06-22): the model's DIRECTION prediction is a coin flip out-of-sample
        # (dir-acc ~55%, IC 0.03) and it leans long even in bear → only ~1% of candles cleared
        # the short threshold, so the bot stopped trading. But the model's EXIT is genuine alpha
        # (exit_signal 90.8% WR), and the ONLY feature that passed the IC gate was volatility
        # (btc_vol_12, IC 0.07). So trend_vol mode: the ENTRY no longer uses the model's direction
        # — it follows the confirmed local TREND (close vs EMA-50 + EMA slope), gated by VOLATILITY
        # EXPANSION (atr_ratio above its own rolling median). The model keeps owning the EXIT
        # (custom_exit / exit_signal). Direction comes from price (which is trending), timing from
        # volatility (the real signal); the coin-flip directional prediction is removed from entry.
        _slope_n = max(1, self._DAY_CANDLES // 4)   # ~6h EMA-50 slope window
        _ema_rising  = dataframe["ema_50"] > dataframe["ema_50"].shift(_slope_n)
        _ema_falling = dataframe["ema_50"] < dataframe["ema_50"].shift(_slope_n)
        _vol_med = dataframe["atr_ratio"].rolling(
            self._DAY_CANDLES, min_periods=max(2, self._DAY_CANDLES // 2)
        ).median()
        _vol_expanding = dataframe["atr_ratio"] > _vol_med
        tv_long = (
            (dataframe["close"] > dataframe["ema_50"]) & _ema_rising
            & _vol_expanding & (dataframe["rsi_14"] < 75) & (dataframe["volume"] > 0)
        )
        tv_short = (
            (dataframe["close"] < dataframe["ema_50"]) & _ema_falling
            & _vol_expanding & (dataframe["rsi_14"] > 25) & (dataframe["volume"] > 0)
        )
        _entry_mode = os.environ.get("FREQAI_ENTRY_MODE", "absolute")

        # Hard regime gate: no longs in BEAR/CRASH, no shorts in BULL/EUPHORIA.
        # Dynamic threshold (×1.3 in BEAR) is insufficient — std_factor can reduce
        # effective threshold to 1.6σ, still allowing longs when market is trending down.
        # Result was 8 longs in 80% BEAR → 170 stop losses at 0% WR (-207 USDT).
        is_long_regime  = dataframe["regime"].isin(["NEUTRAL", "BULL", "EUPHORIA"])
        is_short_regime = dataframe["regime"].isin(["NEUTRAL", "BEAR", "CRASH"])

        # ── Primary-trend filter (2026-06-23, env-gated FREQAI_TREND_FILTER=1; default off) ──
        # Measured pathology: the 5-state regime is too coarse — it labeled 1/3 of a +47% BULL
        # window as NEUTRAL, which allows shorts, so the bot SHORTED a raging uptrend and bled
        # (-75 stop-loss bucket). The model's direction is a coin flip, so without a trend anchor
        # it fights the primary trend. This blocks counter-trend entries using EMA-200 (the primary
        # trend, much finer than the 5-state regime): never long below it, never short above it.
        # When on, this REPLACES the regime gate as the directional anchor (regime still sizes).
        if os.environ.get("FREQAI_TREND_FILTER", "0") == "1":
            _above_primary = dataframe["close"] > dataframe["ema_200"]
            is_long_regime  = is_long_regime  & _above_primary
            is_short_regime = is_short_regime & ~_above_primary

        # C3 bounce guard (2026-06-11, env-gated, default off until brain-validated):
        # block entries against a stretched ~1h-horizon move. RSI(56) on 15m
        # approximates RSI(14) on 1h without informative-pair plumbing.
        # Motivation: 2026-06-11 bounce day — model kept shorting oversold pairs
        # into a +1.9% BTC recovery, 13 shorts at 15% WR (-11.28 USDT).
        if os.environ.get("FREQAI_BOUNCE_GUARD", "0") == "1":
            rsi_1h_proxy = ta.RSI(dataframe, timeperiod=56)
            bounce_ok_long = rsi_1h_proxy < 70    # don't long into overbought
            bounce_ok_short = rsi_1h_proxy > 35   # don't short into oversold
        else:
            bounce_ok_long = pd.Series(True, index=dataframe.index)
            bounce_ok_short = pd.Series(True, index=dataframe.index)

        # Long: price above EMA-50 (uptrend context), not overbought, not at BB top
        ta_long = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
            & is_long_regime
            & bounce_ok_long
        )
        # OB veto REMOVED (2026-05-22): ob_long_ok = close < bearish_ob * 0.99 was
        # blocking 100% of longs. In ranging/trending markets close is always near or
        # above bearish_ob so the condition was never true. Confirmed: 0/100 candles
        # passed on live BTC data. OB columns kept in populate_indicators for future use.

        if _entry_mode == "trend_vol":
            enter_long = (
                (dataframe["do_predict"] == 1)
                & tv_long
                & is_long_regime
            )
        else:
            enter_long = (
                (dataframe["do_predict"] == 1)
                & long_stable
                & ta_long
                & volatility_ok
            )

        # Phase 1 (2026-05-19) — Per-Pair-Per-Regime Dynamic Block.
        # Zero out entries for this pair on candles whose regime matches a
        # blocked (pair, regime) combo (rolling 30d WR<40% AND PF<0.7).
        pair = metadata.get("pair", "")
        blocked_regimes = self._load_pair_regime_blocks().get(pair, set())
        if blocked_regimes:
            is_blocked = dataframe["regime"].isin(blocked_regimes)
            if is_blocked.any():
                enter_long = enter_long & ~is_blocked
                # Single info log per dataframe pass when something is gated
                logger.info(
                    f"[pair-regime gate] {pair}: blocked regimes={sorted(blocked_regimes)}, "
                    f"gated {int(is_blocked.sum())} candles"
                )

        # Phase 3 META-LABELING gate (2026-06-17, default OFF). AND-only: can only REMOVE
        # entries the primary already wants, never add — so worst case is fewer trades, never
        # a new class of bad trade. When FREQAI_META_LABEL=1 and the meta classifier column is
        # present, require predicted win-probability > META_THRESHOLD (filters the ~40% of
        # entries that die at the stop loss). Live behavior is identical while disabled.
        if os.getenv("FREQAI_META_LABEL", "0") == "1" and "&-meta_long" in dataframe.columns:
            meta_thr = float(os.getenv("FREQAI_META_THRESHOLD", "0.5"))
            enter_long = enter_long & (dataframe["&-meta_long"] > meta_thr)

        dataframe.loc[enter_long, "enter_long"] = 1
        dataframe.loc[enter_long, "enter_tag"]  = "freqai_regression_v23_long"

        # Short: price below EMA-50 (downtrend), not in deeply-oversold territory.
        # Bug B fix (2026-05-20): RSI short gate was 15 < rsi_14 < 50 — a 35-point
        # band that blocked shorts on ~50% of candles vs the long gate's 87-point
        # band (rsi_14 < 68) that passed ~90%. Symmetric to long gate.
        # Symmetry fix (2026-05-22): removed * 0.99 gap — ta_long uses plain > ema_50,
        # ta_short now uses plain < ema_50 to match (no artificial dead zone).
        ta_short = (
            (dataframe["close"] < dataframe["ema_50"])
            & (dataframe["rsi_14"] > 32)   # symmetric mirror of long's "rsi_14 < 68"
            & (dataframe["bb_pct"] > 0.10)
            & is_short_regime
            & (dataframe["volume"] > 0)
            & bounce_ok_short
        )
        # OB veto REMOVED (2026-05-22): ob_short_ok = close > bullish_ob * 1.01 was
        # blocking 95% of shorts. Same root cause as ob_long_ok — price trapped in
        # the tight OB range. Confirmed: only 5/100 candles passed on live BTC data.

        if _entry_mode == "trend_vol":
            enter_short = (
                (dataframe["do_predict"] == 1)
                & tv_short
                & is_short_regime
            )
        else:
            enter_short = (
                (dataframe["do_predict"] == 1)
                & short_stable
                & ta_short
                & volatility_ok
            )

        # Apply the same per-pair-per-regime block to shorts.
        if blocked_regimes:
            enter_short = enter_short & ~is_blocked

        # Phase 3 META-LABELING gate (short side, mirror of the long gate above).
        if os.getenv("FREQAI_META_LABEL", "0") == "1" and "&-meta_short" in dataframe.columns:
            meta_thr = float(os.getenv("FREQAI_META_THRESHOLD", "0.5"))
            enter_short = enter_short & (dataframe["&-meta_short"] > meta_thr)

        dataframe.loc[enter_short, "enter_short"] = 1
        dataframe.loc[enter_short, "enter_tag"]   = "freqai_regression_v23_short"

        # META-LABELING AUC EVAL DUMP (2026-06-20, default OFF). When FREQAI_META_DUMP=1 this
        # writes the OOS meta predictions alongside the freshly-recomputed ground-truth labels
        # to a parquet, so scripts/brain/meta_auc.py can score the meta-model's separation
        # (AUC) — the GO/NO-GO gate that was skipped in the 2026-06-17 run. EVAL-ONLY: it uses
        # future bars to build the label, but writes to disk only and NEVER touches any entry
        # decision. Gated OFF in live (the env is unset) → byte-identical live behavior.
        if os.getenv("FREQAI_META_DUMP", "0") == "1" and "&-meta_long" in dataframe.columns:
            try:
                atr_e   = ta.ATR(dataframe, timeperiod=14)
                m_h     = int(os.getenv("FREQAI_META_HORIZON", str(self._META_HORIZON_DEFAULT)))
                m_tp    = float(os.getenv("FREQAI_META_TP_MULT", "2.0"))
                m_sl    = float(os.getenv("FREQAI_META_SL_MULT", "2.0"))
                m_fee   = float(os.getenv("FREQAI_META_FEE_PCT", "0.10"))
                dump = pd.DataFrame({
                    "date":       dataframe["date"],
                    "do_predict": dataframe.get("do_predict", 0),
                    "pred_long":  dataframe["&-meta_long"],   # model prediction (OOS in backtest)
                    "pred_short": dataframe["&-meta_short"],
                    "y_long":  self._meta_outcome_labels(dataframe, m_h, m_tp, m_sl, "long",  atr_e, m_fee),
                    "y_short": self._meta_outcome_labels(dataframe, m_h, m_tp, m_sl, "short", atr_e, m_fee),
                })
                outdir = Path("/freqtrade/user_data/meta_eval")
                outdir.mkdir(parents=True, exist_ok=True)
                safe = metadata["pair"].replace("/", "_").replace(":", "_")
                # Date-range suffix so different backtest windows (e.g. bull vs bear) never
                # overwrite each other's dump → meta_auc.py groups & scores per window.
                d0 = pd.to_datetime(dump["date"].iloc[0]).strftime("%Y%m%d")
                d1 = pd.to_datetime(dump["date"].iloc[-1]).strftime("%Y%m%d")
                dump.to_parquet(outdir / f"{safe}__{d0}_{d1}.parquet")
            except Exception as e:
                logger.warning(f"[meta dump] {metadata.get('pair')}: {e}")

        # RAW PREDICTION DUMP (2026-06-30, default OFF). When FREQAI_DUMP_PREDICTIONS=1
        # this writes the model's OOS prediction (&-future_return), do_predict and close
        # per pair to a parquet for the whole backtest window. Feeds
        # scripts/research/cross_sectional_backtest.py with clean, multi-regime,
        # do_predict==1 predictions (the live historic_predictions.pkl only has ~9 days).
        # Write-only, touches no entry decision; env unset in live → byte-identical.
        if os.getenv("FREQAI_DUMP_PREDICTIONS", "0") == "1" and "&-future_return" in dataframe.columns:
            try:
                from pathlib import Path as _P
                pdump = pd.DataFrame({
                    "date_pred":       dataframe["date"],
                    "&-future_return": dataframe["&-future_return"],
                    "do_predict":      dataframe.get("do_predict", 1),
                    "close_price":     dataframe["close"],
                })
                outdir = _P("/freqtrade/user_data/pred_dump")
                outdir.mkdir(parents=True, exist_ok=True)
                safe = metadata["pair"].replace("/", "_").replace(":", "_")
                pdump.to_parquet(outdir / f"{safe}.parquet")
            except Exception as e:
                logger.warning(f"[pred dump] {metadata.get('pair')}: {e}")

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v23 Regression exit — predicted return has flipped direction.

        Exit long:  model now predicts negative return (< short_thresh * hysteresis_frac)
                    OR RSI/BB technical exhaustion
        Exit short: model now predicts positive return (> long_thresh * hysteresis_frac)
                    OR RSI/BB technical exhaustion

        Using a fraction of the entry threshold (FREQAI_EXIT_HYSTERESIS_FRAC, default 0.5) as
        the exit trigger avoids whipsaw — a small reversal in prediction doesn't immediately
        close the trade. See _exit_hyst below for the tuning rationale.
        """
        predicted_return = dataframe.get(
            "&-future_return",
            pd.Series(0.0, index=dataframe.index)
        )
        # Serve-time recentering: same slow _CENTERING_WINDOW median as populate_entry_trend.
        # FIXED 2026-06-08: window 100 → _CENTERING_WINDOW (see entry/docstring).
        rolling_median = predicted_return.rolling(
            self._CENTERING_WINDOW, min_periods=self._CENTERING_MIN_PERIODS
        ).median()
        centered_pred = predicted_return - rolling_median

        # Regime-aware exit flip thresholds (half the entry threshold)
        long_thresh  = dataframe["dynamic_long_threshold"]
        short_thresh = dataframe["dynamic_short_threshold"]

        # Exit hysteresis fraction (2026-08-31): how much of the entry threshold the prediction
        # must reverse before exit_signal fires. Was a bare 0.5 constant, never varied or A/B
        # tested despite exit_signal being the project's one consistently-proven edge (87-100% WR
        # when it fires) — every trade that DOESN'T reach it instead resolves via stop_loss (0% WR
        # by definition) or time_limit_exit (35-42% WR). Default 0.5 = byte-identical prior
        # behavior. Lower = fires earlier/more often (more trades reach the good exit, but risks
        # firing on noise); higher = fires later (closer to full threshold, more whipsaw-resistant
        # but lets more trades drift into the worse exit paths).
        _exit_hyst = float(os.environ.get("FREQAI_EXIT_HYSTERESIS_FRAC", "0.5"))

        ml_exit_long = (
            (dataframe["do_predict"] == 1)
            & (centered_pred < (short_thresh * _exit_hyst))   # prediction flipped negative
        )
        ta_exit_long = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit_long | ta_exit_long, "exit_long"] = 1

        ml_exit_short = (
            (dataframe["do_predict"] == 1)
            & (centered_pred > (long_thresh * _exit_hyst))    # prediction flipped positive
        )
        ta_exit_short = (
            (dataframe["rsi_14"] < 25)
            | (dataframe["bb_pct"] < 0.05)
        )
        dataframe.loc[ml_exit_short | ta_exit_short, "exit_short"] = 1

        return dataframe
