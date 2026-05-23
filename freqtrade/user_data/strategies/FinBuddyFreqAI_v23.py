# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce
from datetime import datetime
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
    startup_candle_count = 2400  # max safe: Binance 15m cap=2494 (5x499). ROLLING=2880 min_periods=200 so z-score valid from candle 200+

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
    #   "no_macro"  — drop fear_greed + btc_strength + news_sentiment
    #   "no_regime" — drop regime_numeric
    #   "minimal"   — drop all of the above (only raw OHLCV-derived indicators)
    FEATURE_SET = os.getenv("FREQAI_FEATURE_SET", "all").lower()

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative = [(pair, "15m") for pair in pairs]
        informative += [(pair, "1h") for pair in pairs]
        informative += [(pair, "4h") for pair in pairs]
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
        candles_open = int((current_time - trade.open_date_utc).total_seconds() / timeframe_to_seconds(self.timeframe))
        if candles_open <= 2 and current_profit < -0.005:
            last = dataframe.iloc[-1]
            rel_vol = last.get("%-relative_volume-period", 1.0)
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
        tp_pct = self.K_TP * atr_pct        # trail lock - live ATR (can widen with vol)
        
        # Trail activation threshold: once profit exceeds 1.0 * tp_pct
        lock_threshold = tp_pct * 1.0

        # Trail: once profit exceeds the lock threshold, lock stop at max(0.25 * tp_pct, 0.002) from entry.
        if current_profit > lock_threshold:
            locked_stop = max(tp_pct * 0.25, 0.002)
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

    def custom_exit(self, pair: str, trade: "Trade", current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # Time-limit exit: close trade after label_period_candles=24 (timeframe-aware).
        # Equals the model's prediction horizon — holding beyond 24 candles (6h on 15m TF)
        # means the signal has fully expired. Was 72 (3× horizon) which let dead
        # positions drift 18h on 15m TF — the 11 force_exit + 3 time_limit
        # trades in the live log all averaged -0.83% at >12h open.
        candles_open = int((current_time - trade.open_date_utc).total_seconds() / timeframe_to_seconds(self.timeframe))
        if candles_open >= 24:
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
    _HISTORICAL_FUNDING_FILE = "/freqtrade/finbuddy_memory/historical/funding_rate.parquet"
    _COMBINED_CTX_FILE = "/freqtrade/user_data/data/external/combined_context.json"
    _PAIR_REGIME_FILE  = "/freqtrade/finbuddy_memory/regimes/pair_regime_stats.json"

    # Class-level caches: loaded once, shared across all strategy instances.
    _historical_regime_df  = None
    _historical_macro_df   = None
    _historical_funding_df = None
    # Pair-regime block cache: refreshed when JSON mtime changes (every 30 min via cron).
    _pair_regime_blocks       = None    # dict[pair] -> set[regime]
    _pair_regime_blocks_mtime = 0.0

    def _load_historical_regime(self):
        """Load BTC-derived historical regime parquet once. Cached at class level."""
        if FinBuddyFreqAI_v23._historical_regime_df is not None:
            return FinBuddyFreqAI_v23._historical_regime_df
        try:
            df = pd.read_parquet(self._HISTORICAL_REGIME_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True)
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
        """Return {pair: set(blocked_regimes)}. Refreshes when JSON mtime changes."""
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

    def _load_historical_macro(self):
        """Load historical macro features (F&G + BTC strength). Cached at class level."""
        if FinBuddyFreqAI_v23._historical_macro_df is not None:
            return FinBuddyFreqAI_v23._historical_macro_df
        try:
            df = pd.read_parquet(self._HISTORICAL_MACRO_FILE)
            df["date"] = pd.to_datetime(df["date"], utc=True)
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
        dates = pd.to_datetime(dataframe["date"], utc=True)
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
            df["date"] = pd.to_datetime(df["date"], utc=True)
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
        dates = pd.to_datetime(dataframe["date"], utc=True)
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, hist, on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        return {
            "funding_rate":      pd.Series(merged["funding_rate"].fillna(0.0).values,      index=dataframe.index),
            "funding_rate_z30d": pd.Series(merged["funding_rate_z30d"].fillna(0.0).values, index=dataframe.index),
            "funding_rate_chg":  pd.Series(merged["funding_rate_chg"].fillna(0.0).values,  index=dataframe.index),
        }

    def _get_regime_series(self, dataframe: DataFrame) -> pd.Series:
        """
        Vectorized lookup: map every candle's date to its historical regime.
        Returns a Series of regime strings aligned with the input dataframe.

        For LIVE trading where historical regime hasn't been built yet, falls
        back to repeating the live regime across all rows.
        """
        hist = self._load_historical_regime()
        if hist.empty:
            return pd.Series([self._get_current_regime()] * len(dataframe), index=dataframe.index)

        dates = pd.to_datetime(dataframe["date"], utc=True)
        # merge_asof requires both sides sorted by the join key
        df_for_join = pd.DataFrame({"date": dates}).sort_values("date").reset_index()
        merged = pd.merge_asof(df_for_join, hist[["date", "regime"]], on="date", direction="backward")
        merged = merged.sort_values("index").reset_index(drop=True)
        result = pd.Series(merged["regime"].fillna("NEUTRAL").values, index=dataframe.index)
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
        _daily_limit = float(os.environ.get("FREQAI_DAILY_LOSS_LIMIT", "10"))
        from datetime import datetime, timezone as _tz
        _today_utc = datetime.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        _today_pnl = sum(
            (t.close_profit_abs or 0.0)
            for t in Trade.get_trades_proxy(is_open=False)
            if t.close_date_utc and t.close_date_utc >= _today_utc
        )
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
        result = round(base_stake * multiplier, 2)
        logger.info(f"[RiskEngine] stake={result} regime={regime} mult={multiplier}")
        return max(result, min_stake or 0)

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
            # Fix 7 (2026-05-22): per-pair median offset removed. Target is now z-scored
            # (mean~0 by construction), so subtracting the rolling median was double-correcting
            # and producing inconsistent centering vs populate_entry_trend's rolling() median.
            centered = pred

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
                f"[Leverage] {pair} {side}: pred={pred:+.3f} (z-scored, no median offset) "
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
        #   1) cluster cap         (in-memory list scan, ~µs)
        #   2) macro fear/greed    (file read, ~ms)
        #   3) funding-rate guard  (HTTP/cache read, ~10–500 ms)
        # Previously funding-rate ran before cluster cap, making wasted Binance
        # HTTP calls every time a cluster-full pair tried to enter.

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

        rolling_high = dataframe["high"].rolling(96).max()
        rolling_low = dataframe["low"].rolling(96).min()
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
          %-news_sentiment   — 0=bearish…1=bullish (Phase 2 cron)
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
            ctx = self._get_combined_context()
            dataframe["%-news_sentiment"] = float(ctx.get("news_sentiment_ratio", 0.5))

            # BTC perp funding rate (added 2026-05-19): strongest cheap signal for
            # 1–4h crypto perp moves. Already used as a long-block gate; now also
            # fed to LightGBM so the model can learn funding × momentum × regime.
            funding = self._get_funding_series(dataframe)
            dataframe["%-funding_rate"]      = funding["funding_rate"]
            dataframe["%-funding_rate_z30d"] = funding["funding_rate_z30d"]
            dataframe["%-funding_rate_chg"]  = funding["funding_rate_chg"]
        else:
            logger.info(f"[FeatureSet] mode={self.FEATURE_SET} — skipping fear_greed/btc_strength/news_sentiment/funding")

        if include_regime:
            # HMM regime encoding — per-candle historical regime (Fix 2026-05-17)
            regime_series = self._get_regime_series(dataframe)
            dataframe["%-regime_numeric"] = regime_series.map(lambda r: self._REGIME_NUMERIC.get(r, 0)).astype(float)
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

        return dataframe

    # ------------------------------------------------------------------ #
    # v23 — Regression target: predicted future % return                #
    # ------------------------------------------------------------------ #

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
        horizon = self.freqai_info["feature_parameters"]["label_period_candles"]
        raw_return_pct = (
            dataframe["close"].shift(-horizon) / dataframe["close"] - 1.0
        ) * 100

        # Compute past return over the same horizon (uses 100% past data) to avoid look-ahead bias
        past_return = (dataframe["close"] / dataframe["close"].shift(horizon) - 1.0) * 100
        
        # Calculate mean and std on past_return, which has NO look-ahead bias at all
        ROLLING = 2880
        mu  = past_return.rolling(ROLLING, min_periods=200).mean()
        sig = past_return.rolling(ROLLING, min_periods=200).std().replace(0, 1e-9)
        
        # Standardize the raw FUTURE target using past parameters.
        # DO NOT fillna here — let NaN rows stay NaN so FreqAI drops them correctly:
        #   - Last label_period_candles=24 rows: raw_return_pct is NaN (future unknown).
        #     fillna(0.0) would label them "return=0%" and train on unlabeled future.
        #   - First ~199 rows: mu/sig are NaN (rolling min_periods). fillna(0.0) would
        #     assign a neutral-but-wrong z-score=0 to those samples.
        # FreqAI filters NaN-target rows before fitting. Dropping them is correct.
        dataframe["&-future_return"] = (raw_return_pct - mu) / sig
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

        # Map regimes → multipliers vectorized
        long_mult_series  = regime_series.map(lambda r: self._REGIME_THRESHOLD_MULTS.get(r, (1.0, 1.0))[0])
        short_mult_series = regime_series.map(lambda r: self._REGIME_THRESHOLD_MULTS.get(r, (1.0, 1.0))[1])

        recent_wr = float(os.getenv("FINBUDDY_RECENT_WR", "0.50"))
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
        dataframe["dynamic_long_threshold"]  = base_long  * combined_long
        dataframe["dynamic_short_threshold"] = -(base_short * combined_short)
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

        # Fix 7 (2026-05-22): per-pair median offset REMOVED.
        # Original purpose (2026-05-20): raw-% predictions had +1 to +8% long-bias from
        # bull training. Solution: subtract rolling-100 median to center predictions at 0.
        # Now invalid: target is z-scored in set_freqai_targets (mean=0, std=1 by construction)
        # so the per-pair rolling median is already ≈0 for a well-trained model. Subtracting
        # it again added noise and — critically — produced a different centering from the
        # leverage() callback (which used tail(100) instead of rolling(100)), creating
        # inconsistent threshold comparisons between entry and leverage decisions.
        centered_pred = predicted_return  # z-scored target → no offset needed

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

        # Long: price above EMA-50 (uptrend context), not overbought, not at BB top
        ta_long = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )
        # OB veto REMOVED (2026-05-22): ob_long_ok = close < bearish_ob * 0.99 was
        # blocking 100% of longs. In ranging/trending markets close is always near or
        # above bearish_ob so the condition was never true. Confirmed: 0/100 candles
        # passed on live BTC data. OB columns kept in populate_indicators for future use.

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
            & (dataframe["volume"] > 0)
        )
        # OB veto REMOVED (2026-05-22): ob_short_ok = close > bullish_ob * 1.01 was
        # blocking 95% of shorts. Same root cause as ob_long_ok — price trapped in
        # the tight OB range. Confirmed: only 5/100 candles passed on live BTC data.

        enter_short = (
            (dataframe["do_predict"] == 1)
            & short_stable
            & ta_short
            & volatility_ok
        )

        # Apply the same per-pair-per-regime block to shorts.
        if blocked_regimes:
            enter_short = enter_short & ~is_blocked

        dataframe.loc[enter_short, "enter_short"] = 1
        dataframe.loc[enter_short, "enter_tag"]   = "freqai_regression_v23_short"

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v23 Regression exit — predicted return has flipped direction.

        Exit long:  model now predicts negative return (< -half_short_thresh)
                    OR RSI/BB technical exhaustion
        Exit short: model now predicts positive return (> half_long_thresh)
                    OR RSI/BB technical exhaustion

        Using half the entry threshold as the exit trigger avoids whipsaw —
        a small reversal in prediction doesn't immediately close the trade.
        """
        predicted_return = dataframe.get(
            "&-future_return",
            pd.Series(0.0, index=dataframe.index)
        )
        # Fix 7 (2026-05-22): per-pair median offset removed — target is z-scored.
        centered_pred = predicted_return

        # Regime-aware exit flip thresholds (half the entry threshold)
        long_thresh  = dataframe["dynamic_long_threshold"]
        short_thresh = dataframe["dynamic_short_threshold"]

        ml_exit_long = (
            (dataframe["do_predict"] == 1)
            & (centered_pred < (short_thresh * 0.5))   # prediction flipped negative
        )
        ta_exit_long = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit_long | ta_exit_long, "exit_long"] = 1

        ml_exit_short = (
            (dataframe["do_predict"] == 1)
            & (centered_pred > (long_thresh * 0.5))    # prediction flipped positive
        )
        ta_exit_short = (
            (dataframe["rsi_14"] < 25)
            | (dataframe["bb_pct"] < 0.05)
        )
        dataframe.loc[ml_exit_short | ta_exit_short, "exit_short"] = 1

        return dataframe
