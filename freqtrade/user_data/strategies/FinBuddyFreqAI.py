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

logger = logging.getLogger(__name__)


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy FreqAI Strategy v11 — Triple-Barrier Label + LightGBMClassifier (2026-05-03)

    Walk-forward verdict on v10: FAILED OOS. 4/4 fail criteria.
      - Avg monthly Sharpe -1.88 (target > 0), 22% months positive (target ≥50%)
      - P&L -11.58%, concentrated in one month (2025-02)
      - Root cause: path-blind label. mean(next 3 closes) ignores whether the
        path to that mean crosses the stoploss. Five rounds of stop tuning proved
        we were treating the symptom. The disease is in set_freqai_targets().

    v11 Fix — Triple-Barrier Labeling (López de Prado, AFML ch.3):
      For each candle t, look forward label_period_candles (default 12 = 3h on 15m):
        - TP barrier : close[t] * (1 + k_tp * atr_pct[t])   → label +1
        - SL barrier : close[t] * (1 - k_sl * atr_pct[t])   → label -1
        - Time barrier: window expires before either          → label by sign of return
      Starting params: k_tp=2.0, k_sl=1.0, label_period_candles=12

      The model now learns to REFUSE setups whose path is bad even when the
      mean is okay. This is the exact pathology the 79/62 trailing chops exposed.

    v11 model change — LightGBMClassifier:
      Output: class probabilities {-1, 0, +1}
      Entry rule: &-s_label_proba_+1 > 0.55 for long,
                  &-s_label_proba_-1 > 0.55 for short
      (FreqAI classifier outputs one column per class:
       &-s_label_proba_-1, &-s_label_proba_0, &-s_label_proba_+1)

    v11 keeps from v10:
      - stoploss_from_open() anchored stops (confirmed working)
      - trailing_stop = False (framework trailing OFF)
      - BTC 4h macro short-gate
      - ATR volatility filter on entry
      - All feature engineering unchanged
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "120": 0.04,
        "240": 0.02
    }

    stoploss = -0.08
    trailing_stop = False
    use_custom_stoploss = True

    timeframe = "15m"
    informative_timeframes = ["1h", "4h", "1d"]

    can_short = True
    startup_candle_count = 400

    # v11.1 — BTC daily MA200 macro-regime gate.
    # Long  entries require  BTC_1d_close > BTC_1d_MA200 (macro bull).
    # Short entries require  BTC_1d_close < BTC_1d_MA200 (macro bear).
    # Toggle via env BTC_MA200_GATE=0 to disable for ablation testing.
    use_btc_ma200_gate = (__import__("os").environ.get("BTC_MA200_GATE", "1") == "1")

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
        v10 ATR-adaptive stoploss — carried forward to v11 unchanged.
        Initial: 2×ATR below entry (anchored via stoploss_from_open).
        Trailing: once profit > 1×ATR, lock at +1.5×ATR above entry.
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
                1.5 * atr_pct,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
            if trail_pct and trail_pct > 0:
                return trail_pct
            return None

        initial_stop = stoploss_from_open(
            -2.0 * atr_pct,
            current_profit,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        if initial_stop and initial_stop > 0:
            return initial_stop
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
        regime = self._get_current_regime()
        multiplier = self._REGIME_MULTIPLIERS.get(regime, 1.0)
        if multiplier == 0.0:
            return 0.0
        return max(min_stake or 0, proposed_stake * multiplier)

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
    # v11 — Triple-barrier label                                          #
    # ------------------------------------------------------------------ #

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Triple-barrier labeling (López de Prado, AFML ch.3).

        For each candle t (using 15m data):
          - atr_pct = ATR_14[t] / close[t], clamped to [0.003, 0.025]
          - TP at close[t] * (1 + k_tp * atr_pct)   → label +1
          - SL at close[t] * (1 - k_sl * atr_pct)   → label -1
          - Time barrier at t + label_period_candles  → label by sign of return
            (0 if flat, +1 if positive, -1 if negative)

        Starting params (v11):
          k_tp = 2.0   (take-profit 2×ATR above entry)
          k_sl = 1.0   (stop-loss 1×ATR below entry — asymmetric, favours longs)
          label_period_candles = 12  (3 hours on 15m; gives path time to resolve)

        Output column: &-s_label  (integer: -1, 0, +1)
        FreqAI classifier (LightGBMClassifier in freqai config) will produce:
          &-s_label_proba_-1, &-s_label_proba_0, &-s_label_proba_+1
        at inference time. Entry rules below use those probability columns.

        NOTE: shift(-label_period) makes the last label_period rows NaN.
        FreqAI drops NaN-labelled rows automatically before training.
        """
        k_tp = 2.0
        k_sl = 1.0
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

            label = 0  # default: time barrier
            for i in range(t + 1, t + label_period + 1):
                if high[i] >= tp_price:
                    label = 1
                    break
                if low[i] <= sl_price:
                    label = -1
                    break
            else:
                # time barrier: label by direction of close
                ret = (close[t + label_period] - c0) / c0 if c0 > 0 else 0.0
                label = 1 if ret > 0 else (-1 if ret < 0 else 0)

            labels[t] = label

        # last label_period rows → NaN (FreqAI drops automatically)
        labels[n - label_period:] = np.nan
        dataframe["&-s_label"] = labels.astype("float32")
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
        # Probability columns produced by LightGBMClassifier — per-class, named
        # after the stringified float label. Try a few spellings defensively.
        proba_long = (
            dataframe.get("1.0",
            dataframe.get("1",
            dataframe.get("&-s_label_proba_1",
            dataframe.get("&-s_label_proba_+1", None))))
        )
        proba_short = (
            dataframe.get("-1.0",
            dataframe.get("-1",
            dataframe.get("&-s_label_proba_-1", None)))
        )

        if proba_long is None:
            # column doesn't exist yet (first candle before FreqAI trains)
            proba_long  = pd.Series(0.0, index=dataframe.index)
        if proba_short is None:
            proba_short = pd.Series(0.0, index=dataframe.index)

        ml_signal_long = (
            (dataframe["do_predict"] == 1)
            & (proba_long > 0.55)
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
        )

        dataframe.loc[
            ml_signal_long_final & ta_filter & volatility_filter & trend_filter_1h,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal_long_final & ta_filter & volatility_filter & trend_filter_1h,
            "enter_tag"
        ] = "freqai_lgbm_v11_long"

        # Short — macro-gated (v9 fix, retained)
        ml_signal_short = (
            (dataframe["do_predict"] == 1)
            & (proba_short > 0.55)
            & (dataframe["btc_4h_below_ema50"] == 1)
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
            dataframe.get("1.0",
            dataframe.get("1",
            dataframe.get("&-s_label_proba_1",
            dataframe.get("&-s_label_proba_+1", None))))
        )
        proba_short = (
            dataframe.get("-1.0",
            dataframe.get("-1",
            dataframe.get("&-s_label_proba_-1", None)))
        )

        if proba_long is None:
            proba_long  = pd.Series(0.0, index=dataframe.index)
        if proba_short is None:
            proba_short = pd.Series(0.0, index=dataframe.index)

        ml_exit_long = (
            (dataframe["do_predict"] == 1)
            & (proba_short > 0.45)
        )
        ta_exit_long = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit_long | ta_exit_long, "exit_long"] = 1

        ml_exit_short = (
            (dataframe["do_predict"] == 1)
            & (proba_long > 0.45)
        )
        ta_exit_short = (
            (dataframe["rsi_14"] < 25)
            | (dataframe["bb_pct"] < 0.05)
        )
        dataframe.loc[ml_exit_short | ta_exit_short, "exit_short"] = 1

        return dataframe
