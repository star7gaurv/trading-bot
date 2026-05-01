# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
import talib.abstract as ta
import logging

logger = logging.getLogger(__name__)


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy FreqAI Strategy v3 — correct feature engineering pattern.
    Features defined in feature_engineering_expand_all() with % prefix.
    ML brain: LightGBMRegressor / FinBuddyLLMModel predicts &-s_close.
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.06,
        "30": 0.04,
        "60": 0.02,
        "120": 0.01
    }

    # Stoploss was -0.03 in first backtest (Sharpe -1.58). Loosen slightly to
    # allow trades more room before being cut, then re-run Task 1.3.
    stoploss = -0.035
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    timeframe = "15m"
    can_short = False
    startup_candle_count = 40

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        FreqAI features — auto-expanded across indicator_periods_candles,
        include_timeframes, include_shifted_candles, include_corr_pairlist.
        All must be prefixed with % to be recognized by FreqAI.
        """
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-ema-period"] = ta.EMA(dataframe, timeperiod=period)
        dataframe["%-sma-period"] = ta.SMA(dataframe, timeperiod=period)

        bb = ta.BBANDS(dataframe, timeperiod=period)
        dataframe["%-bb_width-period"] = (bb["upperband"] - bb["lowerband"]) / bb["middleband"]
        dataframe["%-bb_pct-period"] = (dataframe["close"] - bb["lowerband"]) / (bb["upperband"] - bb["lowerband"] + 1e-9)

        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)
        dataframe["%-relative_volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Features expanded across timeframes/corr pairs but not periods."""
        macd = ta.MACD(dataframe)
        dataframe["%-macd"] = macd["macd"]
        dataframe["%-macd_signal"] = macd["macdsignal"]
        dataframe["%-macd_hist"] = macd["macdhist"]

        dataframe["%-atr"] = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]

        rolling_high = dataframe["high"].rolling(96).max()
        rolling_low = dataframe["low"].rolling(96).min()
        dataframe["%-price_position"] = (
            (dataframe["close"] - rolling_low) / (rolling_high - rolling_low + 1e-9)
        )
        return dataframe

    def feature_engineering_std(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Standard features computed once on base timeframe."""
        dataframe["%-day_of_week"] = pd.to_datetime(dataframe["date"]).dt.dayofweek
        dataframe["%-hour_of_day"] = pd.to_datetime(dataframe["date"]).dt.hour
        dataframe["%-raw_close"] = dataframe["close"]
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_open"] = dataframe["open"]
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define what FreqAI predicts.
        &-s_close = avg % price change over next label_period_candles.
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # All features come from feature_engineering_*() methods above.
        # FreqAI injects &-s_close prediction + do_predict into dataframe.
        dataframe = self.freqai.start(dataframe, metadata, self)

        # TA indicators for entry/exit filters (not FreqAI features)
        dataframe["rsi_14"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        bb = ta.BBANDS(dataframe, timeperiod=20)
        dataframe["bb_upperband"] = bb["upperband"]
        dataframe["bb_lowerband"] = bb["lowerband"]
        dataframe["bb_pct"] = (dataframe["close"] - bb["lowerband"] ) / (bb["upperband"] - bb["lowerband"] + 1e-9)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ml_signal = (dataframe["do_predict"] == 1) & (dataframe["&-s_close"] > 0.008)
        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 72)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )
        safety = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["rsi_14"] < 78)
        )

        dataframe.loc[ml_signal & ta_filter & safety, "enter_long"] = 1
        dataframe.loc[ml_signal & ta_filter & safety, "enter_tag"] = "freqai_lgbm"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        ml_exit = (dataframe["do_predict"] == 1) & (dataframe["&-s_close"] < -0.003)
        ta_exit = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit | ta_exit, "exit_long"] = 1
        return dataframe
