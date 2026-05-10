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


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy FreqAI Strategy v18 — 1h TF, Futures Long/Short, Symmetric Barriers (2026-05-10)

    2-class LightGBM classifier (L/S). Triple-barrier labeling with k_tp=k_sl=K_MULT
    (symmetric → P(L)=50% base rate, degenerate models auto-filtered at ML_THRESHOLD).
    Regime kill-switches: CRASH/BEAR block longs, BULL/EUPHORIA block shorts.
    custom_stoploss: K_MULT×ATR initial, trail locks at +K_MULT×ATR once profit > K_MULT×ATR.

    v18 bug fix (2026-05-10):
      v17 had two bugs in custom_stoploss that made it effectively a no-op:
        1. Trail activated at profit > 1×ATR but locked at 2×ATR → stoploss_from_open
           returned POSITIVE (stop above current) → FreqTrade fell back to hard -8% stop.
        2. Both branches checked `> 0` instead of `< 0` for the valid-stop test → every
           valid (negative) stop was discarded, only hard config stoploss ever fired.
      Fix: trail activates at profit > K_MULT×ATR (same as lock level), and all return
      checks use `< 0` (valid stop = below current price for longs, above for shorts).

    ENV VARs for grid search:
      FREQAI_K_MULT        float  default 2.0  — barrier multiplier + stoploss scale
      FREQAI_ML_THRESHOLD  float  default 0.60 — entry probability threshold
    """
    INTERFACE_VERSION = 3

    minimal_roi = {"0": 0.99}

    stoploss = -0.08
    trailing_stop = False
    use_custom_stoploss = True

    timeframe = "1h"

    can_short = True
    startup_candle_count = 400

    # v18: ENV VAR configurable — read once at class load time.
    # Grid search passes FREQAI_K_MULT / FREQAI_ML_THRESHOLD via `docker exec -e`.
    # Defaults match v17 live config so the running bot is unaffected.
    K_MULT       = float(os.getenv("FREQAI_K_MULT",       "2.0"))
    ML_THRESHOLD = float(os.getenv("FREQAI_ML_THRESHOLD", "0.60"))

    # v11.1 — BTC daily MA200 macro-regime gate.
    # Long  entries require  BTC_1d_close > BTC_1d_MA200 (macro bull).
    # Short entries require  BTC_1d_close < BTC_1d_MA200 (macro bear).
    # Toggle via env BTC_MA200_GATE=0 to disable for ablation testing.
    use_btc_ma200_gate = (__import__("os").environ.get("BTC_MA200_GATE", "0") == "1")

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative = [(pair, "1h") for pair in pairs]
        informative += [(pair, "4h") for pair in pairs]
        informative += [("BTC/USDT:USDT", "1d")]
        informative += [("BTC/USDT:USDT", "4h")]
        return informative

    # ------------------------------------------------------------------ #
    # ATR-adaptive custom stoploss (v17 — symmetric 2.0×ATR barriers)   #
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
        v18 ATR-adaptive stoploss — symmetric barriers (k_tp=k_sl=K_MULT).
        Initial: K_MULT×ATR below entry (matches k_sl=K_MULT in set_freqai_targets).
        Trailing: once profit > K_MULT×ATR, lock at +K_MULT×ATR above entry.
        Symmetric R:R = 1:1; any WR > 50% is genuine alpha (no base-rate bias).
        Returns None on missing data (no reset of existing stop).

        v18 fix: trail activates only when profit EXCEEDS the lock level (K_MULT×ATR),
        not at 1×ATR. Activation below the lock caused stoploss_from_open to return a
        POSITIVE value (desired stop above current price) which FreqTrade interpreted as
        "use hard stoploss". Also fixed: checks now use `< 0` (valid stop) not `> 0`
        (invalid/above-price stop) — the old `> 0` guard discarded every valid stop.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        last = dataframe.iloc[-1]
        atr = last.get("atr_14", None)
        if atr is None or atr <= 0 or current_rate <= 0:
            return None

        atr_pct = atr / current_rate
        atr_pct = max(0.003, min(atr_pct, 0.025))
        lock_pct = self.K_MULT * atr_pct

        # Trail: once profit exceeds the lock level, trail the stop at the lock level.
        # current_profit > lock_pct guarantees stoploss_from_open returns negative (valid).
        if current_profit > lock_pct:
            trail_pct = stoploss_from_open(
                lock_pct,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
            if trail_pct is not None and trail_pct < 0:
                return trail_pct
            return None

        # Initial: K_MULT×ATR below entry. Returns negative for all normal profit levels.
        initial_stop = stoploss_from_open(
            -lock_pct,
            current_profit,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        if initial_stop is not None and initial_stop < 0:
            return initial_stop
        return None

    def custom_exit(self, pair: str, trade: "Trade", current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # Time-limit exit: close trade after 24 candles (24h on 1h TF)
        # 4× label_period_candles=6 — gives signal time to play out while capping dead positions
        candles_open = int((current_time - trade.open_date_utc).total_seconds() / 3600)
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

    def _get_current_regime(self) -> str:
        import json, os
        regime_file = os.path.join(
            str(self.config.get("user_data_dir", "/freqtrade/user_data")),
            "../../finbuddy_memory/regimes/current.json"
        )
        try:
            with open(regime_file) as f:
                return json.load(f).get("regime", "NEUTRAL")
        except Exception:
            return "NEUTRAL"

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
        REGIME_FILE = os.path.join(os.path.dirname(__file__), '../../finbuddy_memory/regimes/current.json')
        regime = _risk_engine.get_regime(REGIME_FILE)
        multiplier = _risk_engine.stake_multiplier(regime)
        current_profit_ratio = kwargs.get('current_profit_ratio', 0.0) or 0.0
        if not _risk_engine.max_drawdown_gate(abs(current_profit_ratio)):
            logger.warning(f"[RiskEngine] DD gate CLOSED — skipping trade (dd={current_profit_ratio:.2%})")
            return 0
        if multiplier == 0.0:
            logger.warning(f"[RiskEngine] CRASH regime — skipping trade")
            return 0
        base_stake = min(proposed_stake, max_stake)
        result = round(base_stake * multiplier, 2)
        logger.info(f"[RiskEngine] stake={result} regime={regime} mult={multiplier}")
        return max(result, min_stake or 0)

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
        "ARB/USDT:USDT":  "L2",
        "OP/USDT:USDT":   "L2",
        "APT/USDT:USDT":  "L2",
        "SUI/USDT:USDT":  "L2",
        # Everything else → "ALTCOIN" (independent enough)
    }
    _MAX_CLUSTER_POSITIONS = 2  # hard cap per cluster

    # Funding-rate long guard (added v16.2)
    # When BTC perpetual funding rate is very high, longs are overcrowded and
    # expensive. Block new longs above threshold to avoid entering bubble tops.
    _FUNDING_LONG_BLOCK_THRESHOLD = 0.0005   # 0.05% per 8h (extreme bullish)
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
        # 1. Funding-rate long guard
        if side == "long":
            funding = self._get_btc_funding_rate()
            if funding is not None and funding > self._FUNDING_LONG_BLOCK_THRESHOLD:
                logger.info(
                    f"[FundingGuard] Blocking long on {pair}: "
                    f"BTC funding={funding:.4%} > {self._FUNDING_LONG_BLOCK_THRESHOLD:.4%}"
                )
                return False

        # 2. Correlation cluster cap
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

    def feature_engineering_std(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe["%-day_of_week"] = pd.to_datetime(dataframe["date"]).dt.dayofweek
        dataframe["%-hour_of_day"] = pd.to_datetime(dataframe["date"]).dt.hour
        dataframe["%-raw_close"] = dataframe["close"]
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_open"] = dataframe["open"]

        tv = self._get_tradingview_signal()
        dataframe["%-tv_supertrend_bullish"] = tv["tv_supertrend_bullish"]
        dataframe["%-tv_signal_age_minutes"] = tv["tv_signal_age_minutes"]

        return dataframe

    # ------------------------------------------------------------------ #
    # v17 — Triple-barrier labeling (symmetric k_tp=k_sl=2.0, 2-class)  #
    # ------------------------------------------------------------------ #

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Triple-barrier labeling (López de Prado, AFML ch.3) — v17.

        For each candle t (using 1h data):
          - atr_pct = ATR_14[t] / close[t], clamped to [0.003, 0.025]
          - TP at close[t] * (1 + k_tp * atr_pct)   → label "L"
          - SL at close[t] * (1 - k_sl * atr_pct)   → label "S"
          - Neither hit within label_period candles  → dropped (label=None)

        v17 params:
          k_tp = 2.0   (take-profit 2×ATR above entry)
          k_sl = 2.0   (stop-loss 2×ATR below entry — symmetric, P(L)=50% base rate)
          label_period_candles = 6  (6 hours on 1h TF)

        FreqAI classifier emits one proba column per class:
          "L" → P(TP hit first), "S" → P(SL hit first).

        NOTE: last label_period rows → NaN (FreqAI drops automatically).

        v16 — HOLD class removed (2-class model: L / S only).
        Root cause of KeyError: with label_period_candles=6, TP/SL barriers are
        nearly always hit within 6 candles in volatile crypto. HOLD samples are
        so rare that LightGBM trains a 2-class model, but FreqAI data_drawer
        expects 3 columns ("H","L","S") and crashes with KeyError('H').

        v16.1 — time-barrier samples are DROPPED (label=None), not forced to "S".
        Earlier draft mapped time-barrier → "S" as a "conservative tie-break",
        but that bakes a systematic short bias into training: sideways-market
        candles get labeled as bearish. The clean fix is to train only on
        RESOLVED candles (TP hit → L, SL hit → S) and let FreqAI drop the
        unresolved ones automatically (None labels are dropped before fit).
        """
        self.freqai.class_names = ["L", "S"]

        k_tp = self.K_MULT
        k_sl = self.K_MULT  # v18: ENV VAR configurable — aligned with custom_stoploss lock level
        label_period = self.freqai_info["feature_parameters"]["label_period_candles"]

        close = dataframe["close"].values
        high = dataframe["high"].values
        low = dataframe["low"].values
        atr_raw = ta.ATR(dataframe, timeperiod=14).values

        n = len(close)
        # 0 = unresolved (time barrier). Set to ±1 only when TP/SL actually hits.
        labels = np.zeros(n, dtype=np.float32)

        for t in range(n - label_period):
            c0 = close[t]
            atr_pct = (atr_raw[t] / c0) if c0 > 0 else 0.005
            atr_pct = max(0.003, min(atr_pct, 0.025))

            tp_price = c0 * (1.0 + k_tp * atr_pct)
            sl_price = c0 * (1.0 - k_sl * atr_pct)

            for i in range(t + 1, t + label_period + 1):
                if high[i] >= tp_price:
                    labels[t] = 1
                    break
                if low[i] <= sl_price:
                    labels[t] = -1
                    break
            # else: labels[t] stays 0 (unresolved → drop in encoding step)

        # 2-class encoding. Time-barrier (0) → None so FreqAI drops them.
        # Training signal is restricted to RESOLVED candles only — no
        # sideways-as-bearish pollution.
        labels_obj = np.full(n, None, dtype=object)
        labels_obj[labels == 1.0] = "L"
        labels_obj[labels == -1.0] = "S"
        # Tail of length label_period → None (cannot peek into future)
        labels_obj[n - label_period:] = None
        dataframe["&-s_label"] = pd.Series(labels_obj, index=dataframe.index, dtype=object)
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

        if self.dp:
            informative_1h = self.dp.get_pair_dataframe(
                pair=metadata["pair"], timeframe="1h"
            )
            if not informative_1h.empty:
                informative_1h["ema_50_1h"] = ta.EMA(informative_1h, timeperiod=50)
                informative_1h = informative_1h[["date", "close", "ema_50_1h"]].copy()
                informative_1h.columns = ["date", "close_1h", "ema_50_1h"]
                informative_1h["date"] = pd.to_datetime(informative_1h["date"])
                dataframe = pd.merge_asof(
                    dataframe.sort_values("date"),
                    informative_1h.sort_values("date"),
                    on="date",
                    direction="backward",
                )
            else:
                dataframe["ema_50_1h"] = dataframe["close"]
                dataframe["close_1h"] = dataframe["close"]

            btc_4h = self.dp.get_pair_dataframe(
                pair="BTC/USDT:USDT", timeframe="4h"
            )
            if not btc_4h.empty:
                btc_4h["ema_50_4h_btc"] = ta.EMA(btc_4h, timeperiod=50)
                btc_4h["btc_4h_below_ema50"] = (
                    btc_4h["close"] < btc_4h["ema_50_4h_btc"]
                ).astype(int)
                btc_4h = btc_4h[["date", "btc_4h_below_ema50"]].copy()
                btc_4h["date"] = pd.to_datetime(btc_4h["date"])
                dataframe = pd.merge_asof(
                    dataframe.sort_values("date"),
                    btc_4h.sort_values("date"),
                    on="date",
                    direction="backward",
                )
            else:
                dataframe["btc_4h_below_ema50"] = 0

            # v11.1 — BTC daily MA200 macro regime
            btc_1d = self.dp.get_pair_dataframe(
                pair="BTC/USDT:USDT", timeframe="1d"
            )
            if not btc_1d.empty:
                btc_1d["btc_ma200_1d"] = ta.SMA(btc_1d, timeperiod=200)
                btc_1d["btc_macro_bull"] = (
                    btc_1d["close"] > btc_1d["btc_ma200_1d"]
                ).astype(int)
                btc_1d = btc_1d[["date", "btc_macro_bull"]].copy()
                btc_1d["date"] = pd.to_datetime(btc_1d["date"])
                dataframe = pd.merge_asof(
                    dataframe.sort_values("date"),
                    btc_1d.sort_values("date"),
                    on="date",
                    direction="backward",
                )
            else:
                dataframe["btc_macro_bull"] = 1
        else:
            dataframe["ema_50_1h"] = dataframe["close"]
            dataframe["close_1h"] = dataframe["close"]
            dataframe["btc_4h_below_ema50"] = 0
            dataframe["btc_macro_bull"] = 1

        if "btc_macro_bull" not in dataframe.columns:
            dataframe["btc_macro_bull"] = 1

        return dataframe

    # ------------------------------------------------------------------ #
    # Entry / Exit signals — v17 classifier probability columns          #
    # ------------------------------------------------------------------ #

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v18 entry rules — 2-class LightGBM (L/S), ML_THRESHOLD (default 0.60).

        Long:  proba_L > ML_THRESHOLD + TA filter + regime not CRASH/BEAR
        Short: proba_S > ML_THRESHOLD + TA filter + regime not BULL/EUPHORIA
        """
        # v17 — two-class proba columns: "L" / "S".
        # Defensive fallbacks kept for legacy feather files.
        proba_long = (
            dataframe.get("L",
            dataframe.get("1.0",
            dataframe.get("1", None)))
        )
        proba_short = (
            dataframe.get("S",
            dataframe.get("-1.0",
            dataframe.get("-1", None)))
        )
        # v16: HOLD class removed — pure 2-class model (L/S). No proba_hold needed.
        if proba_long is None:
            proba_long  = pd.Series(0.0, index=dataframe.index)
        if proba_short is None:
            proba_short = pd.Series(0.0, index=dataframe.index)

        # v18: ENV VAR configurable threshold (default 0.60 = R8 grid winner)
        ml_threshold_long = (proba_long > self.ML_THRESHOLD)

        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )

        volatility_filter = dataframe["atr_ratio"] > 0.003
        trend_filter_1h   = dataframe["close_1h"] >= dataframe["ema_50_1h"]

        # v11.1 macro-bull gate — opt-in via BTC_MA200_GATE=1 env var
        if self.use_btc_ma200_gate:
            macro_long_gate  = (dataframe["btc_macro_bull"] == 1)
            macro_short_gate = (dataframe["btc_macro_bull"] == 0)
        else:
            macro_long_gate  = pd.Series(True, index=dataframe.index)
            macro_short_gate = pd.Series(True, index=dataframe.index)

        ml_signal_long_final = (
            (dataframe["do_predict"] == 1)
            & ml_threshold_long
            & macro_long_gate
        )

        dataframe.loc[
            ml_signal_long_final & ta_filter & volatility_filter & trend_filter_1h,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal_long_final & ta_filter & volatility_filter & trend_filter_1h,
            "enter_tag"
        ] = "freqai_lgbm_v18_long"

        # Short — model-gated (v17: removed hardcoded btc_4h_below_ema50 deadlock).
        ml_signal_short = (
            (dataframe["do_predict"] == 1)
            & (proba_short > self.ML_THRESHOLD)
            & macro_short_gate
        )

        ta_filter_short = (
            (dataframe["close"] < dataframe["ema_50"])
            & (dataframe["rsi_14"] > 20)
            & (dataframe["bb_pct"] > 0.10)
            & (dataframe["volume"] > 0)
        )

        trend_filter_1h_short = (
            dataframe["close_1h"] < dataframe["ema_50_1h"] * 1.02
        )

        safety_short = dataframe["rsi_14"] > 15

        dataframe.loc[
            ml_signal_short & ta_filter_short & volatility_filter & trend_filter_1h_short & safety_short,
            "enter_short"
        ] = 1
        dataframe.loc[
            ml_signal_short & ta_filter_short & volatility_filter & trend_filter_1h_short & safety_short,
            "enter_tag"
        ] = "freqai_lgbm_v18_short"

        # v17 — full trend-following regime kill-switches.
        # CRASH+BEAR: downtrends — no new longs (shorts only).
        # BULL+EUPHORIA: uptrends — no new shorts (longs only).
        # NEUTRAL: both directions allowed.
        # This eliminates systematic losses from trading against the macro trend.
        regime = self._get_current_regime()
        if regime in ("CRASH", "BEAR"):
            dataframe.loc[:, "enter_long"] = 0
            dataframe.loc[dataframe["enter_long"] == 0, "enter_tag"] = (
                dataframe["enter_tag"].where(dataframe["enter_short"] == 1, None)
            )
        elif regime in ("BULL", "EUPHORIA"):
            dataframe.loc[:, "enter_short"] = 0
            dataframe.loc[dataframe["enter_short"] == 0, "enter_tag"] = (
                dataframe["enter_tag"].where(dataframe["enter_long"] == 1, None)
            )

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v17 — regime-aware asymmetric exit thresholds.

        In CRASH/BEAR: exit longs fast (proba_short > 0.55) — limit damage.
                      Hold shorts longer (proba_long > 0.65) — let winners run.
        In BULL/EUPHORIA: hold longs longer (proba_short > 0.65).
                         Exit shorts fast (proba_long > 0.55).
        In NEUTRAL: symmetric 0.65 thresholds.

        TA exits unchanged (RSI/BB extremes).
        """
        proba_long = (
            dataframe.get("L",
            dataframe.get("1.0",
            dataframe.get("1", None)))
        )
        proba_short = (
            dataframe.get("S",
            dataframe.get("-1.0",
            dataframe.get("-1", None)))
        )

        if proba_long is None:
            proba_long  = pd.Series(0.0, index=dataframe.index)
        if proba_short is None:
            proba_short = pd.Series(0.0, index=dataframe.index)

        # v17: regime-aware exit thresholds
        regime = self._get_current_regime()
        if regime in ("CRASH", "BEAR"):
            long_exit_thr, short_exit_thr = 0.55, 0.65   # bail longs fast, hold shorts
        elif regime in ("BULL", "EUPHORIA"):
            long_exit_thr, short_exit_thr = 0.65, 0.55   # hold longs, bail shorts fast
        else:
            long_exit_thr, short_exit_thr = 0.65, 0.65   # NEUTRAL — symmetric

        ml_exit_long = (
            (dataframe["do_predict"] == 1)
            & (proba_short > long_exit_thr)
        )
        ta_exit_long = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit_long | ta_exit_long, "exit_long"] = 1

        ml_exit_short = (
            (dataframe["do_predict"] == 1)
            & (proba_long > short_exit_thr)
        )
        ta_exit_short = (
            (dataframe["rsi_14"] < 25)
            | (dataframe["bb_pct"] < 0.05)
        )
        dataframe.loc[ml_exit_short | ta_exit_short, "exit_short"] = 1

        return dataframe
