# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
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
    FinBuddy FreqAI Strategy v2 — ML Brain
    LightGBM trained on OHLCV + TA indicators predicts 3-candle (45min) price direction.
    Primary signal: FreqAI &-s_close prediction. TA used as secondary filter.
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.06,
        "30": 0.04,
        "60": 0.02,
        "120": 0.01
    }

    stoploss = -0.03
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    timeframe = "15m"
    can_short = False
    startup_candle_count = 300

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define what FreqAI predicts.
        &-s_close = % price change after label_period_candles (3 candles = 45 min).
        Positive = price goes up, negative = price goes down.
        """
        dataframe["&-s_close"] = (
            dataframe["close"]
            .shift(-self.freqai.dk.label_period_candles)
            / dataframe["close"]
        ) - 1
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI
        dataframe["rsi_14"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_7"] = ta.RSI(dataframe, timeperiod=7)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"] = macd["macdhist"]

        # EMA
        dataframe["ema_9"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # Bollinger Bands
        bb = ta.BBANDS(dataframe, timeperiod=20)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_mid"] = bb["middleband"]
        dataframe["bb_width"] = bb["upperband"] - bb["lowerband"]
        dataframe["bb_pct"] = (dataframe["close"] - bb["lowerband"]) / (dataframe["bb_width"] + 1e-10)

        # ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        # Volume momentum
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_change"] = dataframe["volume"] / (dataframe["volume_ma"] + 1e-10)

        # Price position in 24h range
        dataframe["high_24"] = dataframe["high"].rolling(96).max()
        dataframe["low_24"] = dataframe["low"].rolling(96).min()
        dataframe["price_position"] = (
            (dataframe["close"] - dataframe["low_24"])
            / (dataframe["high_24"] - dataframe["low_24"] + 1e-10)
        )

        # EMA slope
        dataframe["ema_21_slope"] = dataframe["ema_21"] - dataframe["ema_21"].shift(3)

        # FreqAI: trains model + injects predictions into dataframe
        # Adds: &-s_close (ML prediction), do_predict (1=valid, 0=warmup/skip)
        dataframe = self.freqai.start(dataframe, metadata, self)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        PRIMARY: FreqAI predicts >0.8% gain in next 45 min.
        SECONDARY: TA filters (trend + not overbought).
        do_predict == 1 means model is trained and prediction is valid.
        """
        ml_signal = (
            (dataframe["do_predict"] == 1) &
            (dataframe["&-s_close"] > 0.008)
        )
        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"]) &
            (dataframe["rsi_14"] < 72) &
            (dataframe["bb_pct"] < 0.90) &
            (dataframe["volume"] > 0)
        )
        dataframe.loc[ml_signal & ta_filter, "enter_long"] = 1
        dataframe.loc[ml_signal & ta_filter, "enter_tag"] = "freqai_lgbm"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        PRIMARY: FreqAI predicts price will fall.
        SECONDARY: TA overbought / reversal signals.
        """
        ml_exit = (
            (dataframe["do_predict"] == 1) &
            (dataframe["&-s_close"] < -0.003)
        )
        ta_exit = (
            (dataframe["rsi_14"] > 75) |
            (
                (dataframe["close"] < dataframe["ema_21"]) &
                (dataframe["close"].shift(1) > dataframe["ema_21"].shift(1))
            ) |
            (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit | ta_exit, "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """Safety gate: macro trend + not extreme overbought."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False
        last = dataframe.iloc[-1]
        if last["close"] < last["ema_200"]:
            logger.info(f"[{pair}] Entry rejected: price below 200 EMA")
            return False
        if last["rsi_14"] > 78:
            logger.info(f"[{pair}] Entry rejected: RSI {last['rsi_14']:.1f} > 78")
            return False
        return True

    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Tiered stoploss — tighten as profit grows."""
        if current_profit > 0.04:
            return -0.01
        if current_profit > 0.02:
            return -0.015
        return -0.03
