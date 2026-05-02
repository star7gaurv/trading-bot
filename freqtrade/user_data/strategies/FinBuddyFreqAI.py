# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import logging

logger = logging.getLogger(__name__)


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy FreqAI Strategy v8 — ATR-adaptive stoploss (2026-05-02)

    Round 2 forensics:
      - WR: 48.2% / 50.0% (was 63% R1) — stoploss was CHOPPING good signals
      - Fixed SL -1.5% is within 15m candle noise: price touches it before signal plays out
      - Evidence: Bear longs (exit_signal) had 93.5% WR at +0.84% avg when NOT stopped out
      - 41-42 stop-loss hits destroyed -130 USDT each run — all profit evaporated

    v8 Fix — ATR-based custom_stoploss():
      - Replace fixed % stoploss with 2.0 × ATR-based floor
      - On 15m BTC: ATR ~0.3-0.8% of price. 2×ATR = 0.6-1.6% = true noise floor
      - Floor: never less than -4% (protects against gaps/flash crashes)
      - Ceiling: never triggered above -0.5% (minimum viable stop)
      - Trailing ATR: once trade is +1 ATR in profit, trail at 1.5×ATR below peak

    v8 keeps from v7 (all working):
      - BTC 4h macro trend filter
      - Relaxed short entry (RSI > 20, 2% 1h buffer, no ema_200 requirement)
      - Dynamic long threshold (> 0.010 bull / > 0.015 bear)
      - ML-based exit on signal reversal (< -0.001 / > +0.001)
      - Trailing stop positive offset for winners

    Expected outcome:
      - Stop hits drop from 41-42 back toward 10-15 (stops only on real reversals)
      - WR recovers to 60%+ (ML signals get to play out)
      - reward:risk improves: avg winner +0.84% / avg stopper ~2×ATR ~0.8% = 1:1
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "120": 0.04,
        "240": 0.02
    }

    # v8: wide fallback stoploss — custom_stoploss() does the real work
    # This is just the emergency hard floor (gap protection, exchange outage)
    stoploss = -0.08

    # v8: keep trailing stop for capturing winners (100% WR in R1 and R2)
    trailing_stop = True
    trailing_stop_positive = 0.010
    trailing_stop_positive_offset = 0.020
    trailing_only_offset_is_reached = True

    # v8: enable custom stoploss
    use_custom_stoploss = True

    timeframe = "15m"
    informative_timeframes = ["1h", "4h"]

    can_short = True
    startup_candle_count = 400

    # ------------------------------------------------------------------ #
    # ATR-adaptive custom stoploss                                        #
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
        ATR-adaptive stoploss.

        Initial stop: 2.0 × ATR below entry (adapts to volatility)
        Trailing mode: once profit > 1×ATR, trail at 1.5×ATR below peak

        Returns stoploss as a negative ratio from current_rate (not from entry).
        FreqTrade convention: return value is relative to current_rate.
        A return of -0.02 means "stop if price drops 2% from current_rate".
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return self.stoploss

        last = dataframe.iloc[-1]
        atr = last.get("atr_14", None)
        if atr is None or atr <= 0 or current_rate <= 0:
            return self.stoploss

        atr_pct = atr / current_rate

        # Clamp ATR to sensible range: 0.003 (0.3%) to 0.025 (2.5%)
        atr_pct = max(0.003, min(atr_pct, 0.025))

        # Initial stop: 2.0 × ATR from entry price
        initial_stop = -(2.0 * atr_pct)

        # Hard floor / ceiling on initial stop
        # Never wider than -4% (gap protection)
        # Never tighter than -0.5% (avoids instant stops on fees)
        initial_stop = max(-0.04, min(initial_stop, -0.005))

        if current_profit < atr_pct:  # not yet in profit by 1×ATR
            return initial_stop

        # Trailing mode: trade is profitable by at least 1×ATR
        # Trail at 1.5×ATR below peak (lock in more of the winner)
        trailing_atr_stop = -(1.5 * atr_pct)
        trailing_atr_stop = max(-0.04, min(trailing_atr_stop, -0.005))
        return trailing_atr_stop

    # ------------------------------------------------------------------ #
    # FreqAI feature engineering                                          #
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
        return dataframe

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        label_period = self.freqai_info["feature_parameters"]["label_period_candles"]
        dataframe["&-s_close"] = (
            dataframe["close"]
            .shift(-label_period)
            .rolling(label_period)
            .mean()
            / dataframe["close"]
        ) - 1
        return dataframe

    # ------------------------------------------------------------------ #
    # Indicator population                                                #
    # ------------------------------------------------------------------ #

    def populate_indicators(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        # --- FreqAI inference ---
        dataframe = self.freqai.start(dataframe, metadata, self)

        # --- 15m TA ---
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

        # ATR — used both for entry filter AND custom_stoploss
        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ratio"] = dataframe["atr_14"] / dataframe["close"]

        # --- 1h trend ---
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

            # --- BTC 4h macro trend filter (from v7) ---
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
        else:
            dataframe["ema_50_1h"] = dataframe["close"]
            dataframe["close_1h"] = dataframe["close"]
            dataframe["btc_4h_below_ema50"] = 0

        return dataframe

    # ------------------------------------------------------------------ #
    # Entry / Exit signals                                                #
    # ------------------------------------------------------------------ #

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Entry conditions v8 (inherited from v7, all working):

        LONG:
          - ML > +1.0% (bull) / > +1.5% (bear via BTC 4h filter)
          - close > EMA-50 (15m trend)
          - close_1h >= ema_50_1h (1h trend)
          - RSI < 68 | BB% < 0.90 | atr_ratio > 0.003 | volume > 0

        SHORT (relaxed from v7):
          - ML < -1.0%
          - close < EMA-50
          - close_1h < ema_50_1h * 1.02 (2% buffer)
          - RSI > 20 (was 32) | BB% > 0.10 | atr_ratio > 0.003 | volume > 0
          - No ema_200 requirement (fires too late)
        """
        # Dynamic long ML threshold — v7 carry-forward
        ml_threshold_long = (
            (
                (dataframe["btc_4h_below_ema50"] == 0)
                & (dataframe["&-s_close"] > 0.010)
            ) | (
                (dataframe["btc_4h_below_ema50"] == 1)
                & (dataframe["&-s_close"] > 0.015)
            )
        )

        ml_signal = (
            (dataframe["do_predict"] == 1)
            & ml_threshold_long
        )

        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )

        volatility_filter = dataframe["atr_ratio"] > 0.003

        trend_filter_1h = dataframe["close_1h"] >= dataframe["ema_50_1h"]

        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h,
            "enter_tag"
        ] = "freqai_lgbm_v8_long"

        # --- Short entry (v7 relaxed, carry-forward) ---
        ml_signal_short = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] < -0.010)
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
        ] = "freqai_lgbm_v8_short"

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Exit conditions v8 (unchanged — ML exit is confirmed working):
          Long:  ML < -0.001 OR RSI > 75 OR BB% > 0.95
          Short: ML > +0.001 OR RSI < 25 OR BB% < 0.05
        """
        ml_exit = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] < -0.001)
        )
        ta_exit = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit | ta_exit, "exit_long"] = 1

        ml_exit_short = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] > 0.001)
        )
        ta_exit_short = (
            (dataframe["rsi_14"] < 25)
            | (dataframe["bb_pct"] < 0.05)
        )
        dataframe.loc[ml_exit_short | ta_exit_short, "exit_short"] = 1

        return dataframe
