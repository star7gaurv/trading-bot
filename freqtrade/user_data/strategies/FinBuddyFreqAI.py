# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
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


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy FreqAI Strategy v15 — 1h TF + Pullback Entry + ema_20 Gate (2026-05-05)

    R5 (v12) verdict: FAIL. 90/90 combos negative Sharpe (best -5.43, identical to R4).
    v12 changes (Hold class, multi-TF, ATR multiplier) had zero effect.

    R5 root-cause analysis — 3 compounding exit bugs:
      Bug A — Grid stoploss too tight (-0.02 to -0.03): autobacktest patches BOTH
               config AND strategy stoploss, making the hard floor tighter than
               ATR-based stop in volatile periods (ATR>1.33%). Hard floor fires
               instead of custom_stoploss, breaking the intended R:R geometry.
               Fix: grid sweep -0.08 to -0.12 (wider than max ATR stop of 3.75%).

      Bug B — minimal_roi {"240": 0.02} exposed during grid: autobacktest removes
               the config's minimal_roi override, exposing the strategy's table.
               Winners exit at +2% after 4h by ROI; losers ride to full ATR stop.
               This alone causes avg_win < avg_loss regardless of WR.
               Fix: minimal_roi = {"0": 0.99} — effectively disabled, custom_stoploss
               trail owns ALL winner exits.

      Bug C — ML exit threshold 0.45 too low: proba_short > 0.45 fires constantly
               in a 3-class model (P(L)+P(S)+P(H)=1; P(S)>0.45 happens frequently
               when model is uncertain). Cuts winning longs at <1% gain while
               losers wait for the stoploss. Avg_win ≈ 0.7×avg_loss → PF=0.749.
               Fix: raise exit threshold to 0.65 (requires high reversal confidence).

    Additional improvements in v13:
      - Revert include_timeframes to ["15m"] only: multi-TF degraded model with
        30-day training window (too few 4h candles for LightGBM to learn from).
      - Increase train_period_days from 30 to 60: more data → better model.
      - Add class_names declaration for consistent probability column ordering.

    Retained from v12:
      - k_sl=1.5, initial stop -1.5×ATR, trail +2.0×ATR (R:R=1.33:1)
      - HOLD ("H") class with proba_H < 0.4 gate
      - stoploss_from_open() anchored stops (confirmed working)
      - trailing_stop = False (custom_stoploss owns the trail)
      - BTC 4h/daily macro gates
    """
    INTERFACE_VERSION = 3

    minimal_roi = {"0": 0.99}

    stoploss = -0.08
    trailing_stop = False
    use_custom_stoploss = True

    timeframe = "15m"

    can_short = True
    startup_candle_count = 400

    # v11.1 — BTC daily MA200 macro-regime gate.
    # Long  entries require  BTC_1d_close > BTC_1d_MA200 (macro bull).
    # Short entries require  BTC_1d_close < BTC_1d_MA200 (macro bear).
    # Toggle via env BTC_MA200_GATE=0 to disable for ablation testing.
    use_btc_ma200_gate = (__import__("os").environ.get("BTC_MA200_GATE", "1") == "1")

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative = [(pair, "1h") for pair in pairs]
        informative += [(pair, "4h") for pair in pairs]
        informative += [("BTC/USDT:USDT", "1d")]
        informative += [("BTC/USDT:USDT", "4h")]
        return informative

    # ------------------------------------------------------------------ #
    # ATR-adaptive custom stoploss (v10 — unchanged, confirmed working)  #
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
        v12 ATR-adaptive stoploss — geometry rebalanced for positive R:R.
        Initial: 1.5×ATR below entry (anchored via stoploss_from_open).
        Trailing: once profit > 1×ATR, lock at +2.0×ATR above entry.
        Realized R:R = 2.0/1.5 ≈ 1.33:1 (was 1.5/2.0 = 0.75:1 in v11).
        k_sl in label is set to 1.5 to match this initial stop exactly.
        Returns None on missing data (no reset of existing stop).
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

        if current_profit > atr_pct:
            trail_pct = stoploss_from_open(
                2.0 * atr_pct,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
            if trail_pct and trail_pct > 0:
                return trail_pct
            return None

        initial_stop = stoploss_from_open(
            -1.5 * atr_pct,
            current_profit,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        if initial_stop and initial_stop > 0:
            return initial_stop
        return None

    def custom_exit(self, pair: str, trade: "Trade", current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        # Time-limit exit: close trade after 24 candles (6h on 15m TF)
        # Aligns trade lifetime with label_period_candles=12 × 2 buffer
        candles_open = int((current_time - trade.open_date_utc).total_seconds() / 900)
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

    def _get_tradingview_signal(self):
        """Load latest TradingView webhook signal."""
        import json, os
        from datetime import datetime, timezone
        signal_file = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/external/tradingview_signals.json"
        try:
            with open(signal_file) as f:
                signals = json.load(f)
            if not signals:
                return {"tv_supertrend_bullish": 0, "tv_signal_age_minutes": 999}
            latest = signals[-1]
            ts = datetime.fromisoformat(latest["timestamp"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).seconds / 60
            return {
                "tv_supertrend_bullish": 1 if latest.get("signal", "") == "BUY" else 0,
                "tv_signal_age_minutes": round(age, 1)
            }
        except Exception:
            return {"tv_supertrend_bullish": 0, "tv_signal_age_minutes": 999}

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
    # v12 — Triple-barrier label with HOLD class                          #
    # ------------------------------------------------------------------ #

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Triple-barrier labeling (López de Prado, AFML ch.3) — v12.

        For each candle t (using 15m data):
          - atr_pct = ATR_14[t] / close[t], clamped to [0.003, 0.025]
          - TP at close[t] * (1 + k_tp * atr_pct)   → label "L"
          - SL at close[t] * (1 - k_sl * atr_pct)   → label "S"
          - Neither hit within label_period candles  → label "H" (HOLD)

        v12 params:
          k_tp = 2.0   (take-profit 2×ATR above entry)
          k_sl = 1.5   (stop-loss 1.5×ATR below entry — matches custom_stoploss)
          label_period_candles = 12  (3 hours on 15m)

        v12 changes from v11:
          1. k_sl 1.0 → 1.5 to match custom_stoploss initial stop.
          2. HOLD ("H") class now retained instead of dropped — model can
             abstain on candles whose path resolves neither TP nor SL within
             the time window. Entry rules require proba_H < 0.4 to fire.

        FreqAI classifier emits one proba column per class:
          "L" → P(TP hit first), "S" → P(SL hit first), "H" → P(no resolution).

        NOTE: last label_period rows → NaN (FreqAI drops automatically).
        """
        self.freqai.class_names = ["H", "L", "S"]

        k_tp = 2.0
        k_sl = 1.5
        label_period = self.freqai_info["feature_parameters"]["label_period_candles"]

        close = dataframe["close"].values
        high = dataframe["high"].values
        low = dataframe["low"].values
        atr_raw = ta.ATR(dataframe, timeperiod=14).values

        n = len(close)
        labels = np.zeros(n, dtype=np.float32)

        for t in range(n - label_period):
            c0 = close[t]
            atr_pct = (atr_raw[t] / c0) if c0 > 0 else 0.005
            atr_pct = max(0.003, min(atr_pct, 0.025))

            tp_price = c0 * (1.0 + k_tp * atr_pct)
            sl_price = c0 * (1.0 - k_sl * atr_pct)

            label = 0  # default: time barrier (HOLD)
            for i in range(t + 1, t + label_period + 1):
                if high[i] >= tp_price:
                    label = 1
                    break
                if low[i] <= sl_price:
                    label = -1
                    break
            # No else clause — time-barrier candles stay as HOLD (0).

            labels[t] = label

        # v12 — three-class encoding: L/S/H. HOLD is no longer dropped.
        # IMPORTANT: must build into object dtype from the start. np.where
        # with all-string branches returns <U1 dtype, which silently truncates
        # None → "N" on assignment and breaks training (LightGBM raises
        # "y contains previously unseen labels: 'N'"). Direct fill avoids it.
        labels_obj = np.empty(n, dtype=object)
        labels_obj[labels == 1.0] = "L"
        labels_obj[labels == -1.0] = "S"
        labels_obj[labels == 0.0] = "H"
        # Tail of length label_period → None (FreqAI drops automatically)
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
    # Entry / Exit signals — v11 uses classifier probability columns     #
    # ------------------------------------------------------------------ #

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v11 entry rules using LightGBMClassifier output probabilities.

        FreqAI's LightGBMClassifier emits one probability column per class,
        named with the stringified class label only (no `&-s_label_proba_` prefix).
        Labels are float32, so the columns are "1.0" and "-1.0".
        Verified from models/finbuddy_backtest_v11/backtesting_predictions/*.feather
        whose columns are: ['date', '&-s_label', '&-s_label_mean',
        '&-s_label_std', '-1.0', '1.0', 'do_predict'].

        Long:  P(+1) > 0.55 — model confident TP hits before SL
        Short: P(-1) > 0.55 — model confident SL hits (price drops) before TP

        TA filters and macro gate unchanged from v10.
        """
        # v12 — three-class proba columns: "L" / "S" / "H".
        # Defensive fallbacks kept for legacy two-class feather files.
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
        proba_hold = (
            dataframe.get("H",
            dataframe.get("0.0",
            dataframe.get("0", None)))
        )

        if proba_long is None:
            # column doesn't exist yet (first candle before FreqAI trains)
            proba_long  = pd.Series(0.0, index=dataframe.index)
        if proba_short is None:
            proba_short = pd.Series(0.0, index=dataframe.index)
        if proba_hold is None:
            # No H column yet (legacy v11 model still loaded) → never gate-block.
            proba_hold = pd.Series(0.0, index=dataframe.index)

        # v12 — HOLD gate: model must NOT predict "no resolution" with high prob.
        not_hold = proba_hold < 0.4

        ml_signal_long = (
            (dataframe["do_predict"] == 1)
            & (proba_long > 0.55)
            & not_hold
        )

        # Bull/bear dynamic threshold — in classifier land we tighten in bear
        # by requiring higher confidence (0.60) when macro is bearish for longs
        ml_threshold_long = (
            (
                (dataframe["btc_4h_below_ema50"] == 0)
                & (proba_long > 0.55)
            ) | (
                (dataframe["btc_4h_below_ema50"] == 1)
                & (proba_long > 0.60)
            )
        )

        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )

        volatility_filter = dataframe["atr_ratio"] > 0.003
        trend_filter_1h   = dataframe["close_1h"] >= dataframe["ema_50_1h"]

        # v11.1 macro-bull gate — long requires BTC daily > MA200
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
            & not_hold
        )

        dataframe.loc[
            ml_signal_long_final & ta_filter & volatility_filter & trend_filter_1h,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal_long_final & ta_filter & volatility_filter & trend_filter_1h,
            "enter_tag"
        ] = "freqai_lgbm_v11_long"

        # Short — macro-gated (v9 fix, retained) + v12 HOLD gate
        ml_signal_short = (
            (dataframe["do_predict"] == 1)
            & (proba_short > 0.55)
            & (dataframe["btc_4h_below_ema50"] == 1)
            & macro_short_gate
            & not_hold
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
        ] = "freqai_lgbm_v11_short"

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        v11 exit — same ML-reversal logic, adapted for classifier output.
        Exit long when P(-1) > 0.45 (model sees SL risk rising).
        Exit short when P(+1) > 0.45 (model sees TP risk rising for shorts).
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

        ml_exit_long = (
            (dataframe["do_predict"] == 1)
            & (proba_short > 0.65)
        )
        ta_exit_long = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit_long | ta_exit_long, "exit_long"] = 1

        ml_exit_short = (
            (dataframe["do_predict"] == 1)
            & (proba_long > 0.65)
        )
        ta_exit_short = (
            (dataframe["rsi_14"] < 25)
            | (dataframe["bb_pct"] < 0.05)
        )
        dataframe.loc[ml_exit_short | ta_exit_short, "exit_short"] = 1

        return dataframe
