# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce

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
    FinBuddy FreqAI Strategy v4 — entry filter tightened after Task 1.3 FAIL.

    Root cause of v3 failure (2026-05-01):
      - Win rate was fine (60.3%) but 36 stoploss exits at avg -3.69% wiped all gains.
      - Entries were firing too early / in counter-trend moves on 15m.
      - ML signal threshold was too low (0.008), allowing marginal-confidence entries.

    Fixes applied in v4:
      1. ML entry threshold raised: &-s_close > 0.008 -> > 0.012
         (only enter on high-conviction FreqAI predictions)
      2. 1h trend filter added: require 1h close >= 1h EMA-50
         (do not fight the macro 1h trend)
      3. RSI entry ceiling tightened: < 72 -> < 68
         (avoid entering near overbought conditions)
      4. Stoploss kept at -0.035 (root cause was bad entries, not stoploss width)

    ML brain: LightGBMRegressor / FinBuddyLLMModel predicts &-s_close.
    Features: feature_engineering_expand_all() with % prefix (FreqAI standard).
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.06,
        "30": 0.04,
        "60": 0.02,
        "120": 0.01
    }

    # Stoploss: -3.5% — kept from v3. Root cause of Task 1.3 failure was entry
    # quality, not stoploss width. Tightening stoploss further would hurt win rate.
    stoploss = -0.035
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    timeframe = "15m"

    # informative_timeframes: fetch 1h candles for trend filter
    # (used in populate_indicators via self.dp.get_pair_dataframe)
    informative_timeframes = ["1h"]

    can_short = False
    startup_candle_count = 40

    # ------------------------------------------------------------------ #
    # FreqAI feature engineering                                          #
    # ------------------------------------------------------------------ #

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        Auto-expanded across indicator_periods_candles, include_timeframes,
        include_shifted_candles, include_corr_pairlist.
        All columns MUST be prefixed with % to be recognised by FreqAI.
        """
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
        """Expanded across timeframes/corr pairs but NOT across periods."""
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
        """Standard features computed once on the base timeframe."""
        dataframe["%-day_of_week"] = pd.to_datetime(dataframe["date"]).dt.dayofweek
        dataframe["%-hour_of_day"] = pd.to_datetime(dataframe["date"]).dt.hour
        dataframe["%-raw_close"] = dataframe["close"]
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_open"] = dataframe["open"]
        return dataframe

    def set_freqai_targets(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        FreqAI prediction target: avg % price change over next label_period_candles.
        Positive &-s_close = expected price rise = bullish signal.
        """
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
        """
        1. Run FreqAI — injects &-s_close prediction + do_predict columns.
        2. Compute TA filters for entry/exit rules (not FreqAI features).
        3. Merge 1h EMA-50 for macro trend filter (v4 addition).
        """
        # --- FreqAI inference ---
        dataframe = self.freqai.start(dataframe, metadata, self)

        # --- 15m TA filters ---
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

        # --- 1h trend filter (v4) ---
        # Fetch 1h candles and compute EMA-50 on them.
        # Merge back onto 15m dataframe using forward-fill so every 15m
        # candle knows the latest 1h EMA-50 value.
        if self.dp:
            informative_1h = self.dp.get_pair_dataframe(
                pair=metadata["pair"], timeframe="1h"
            )
            if not informative_1h.empty:
                informative_1h["ema_50_1h"] = ta.EMA(
                    informative_1h, timeperiod=50
                )
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
                # Fallback: no 1h data available; disable trend filter
                dataframe["ema_50_1h"] = dataframe["close"]
                dataframe["close_1h"] = dataframe["close"]
        else:
            dataframe["ema_50_1h"] = dataframe["close"]
            dataframe["close_1h"] = dataframe["close"]

        return dataframe

    # ------------------------------------------------------------------ #
    # Entry / Exit signals                                                #
    # ------------------------------------------------------------------ #

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Entry conditions (v4 tightened):
          1. FreqAI predicts > +1.2% price rise (raised from 0.8% in v3)
          2. do_predict == 1 (model is confident in its own prediction)
          3. 15m close > 15m EMA-50  (short-term uptrend)
          4. 1h close >= 1h EMA-50   (macro trend filter — NEW in v4)
          5. RSI-14 < 68             (not overbought — tightened from 72 in v3)
          6. BB% < 0.90              (not at the top of the band)
          7. close > EMA-200         (long-term safety filter)
          8. volume > 0
        """
        # High-conviction ML signal only
        ml_signal = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] > 0.012)   # v4: raised from 0.008
        )

        # 15m short-term filter
        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)           # v4: tightened from 72
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )

        # 1h macro trend filter (v4 — prevents counter-trend entries)
        trend_filter_1h = (
            dataframe["close_1h"] >= dataframe["ema_50_1h"]
        )

        # Long-term safety
        safety = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["rsi_14"] < 78)
        )

        dataframe.loc[
            ml_signal & ta_filter & trend_filter_1h & safety,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal & ta_filter & trend_filter_1h & safety,
            "enter_tag"
        ] = "freqai_lgbm_v4"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Exit conditions (unchanged from v3 — exit logic was not the problem):
          - FreqAI predicts > -0.3% price drop, OR
          - RSI > 75, OR
          - BB% > 0.95 (price at top of band)
        """
        ml_exit = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] < -0.003)
        )
        ta_exit = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit | ta_exit, "exit_long"] = 1
        return dataframe
