# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.persistence import Trade
import talib.abstract as ta
import logging

logger = logging.getLogger(__name__)


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy AI Strategy v1 — Technical Analysis Brain
    Multi-indicator strategy using RSI, MACD, EMA, Bollinger, ATR, Volume.
    FreqAI ML layer: disabled until infrastructure upgraded.
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
    startup_candle_count = 200

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

        # ATR (normalized)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        # Volume momentum
        dataframe["volume_ma"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_change"] = dataframe["volume"] / (dataframe["volume_ma"] + 1e-10)

        # Price position in 24h range
        dataframe["high_24"] = dataframe["high"].rolling(96).max()
        dataframe["low_24"] = dataframe["low"].rolling(96).min()
        dataframe["price_position"] = (dataframe["close"] - dataframe["low_24"]) / (dataframe["high_24"] - dataframe["low_24"] + 1e-10)

        # Trend: EMA slope
        dataframe["ema_21_slope"] = dataframe["ema_21"] - dataframe["ema_21"].shift(3)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry conditions — all must be true:
        1. RSI 14 between 35-60 (not overbought, recovering)
        2. MACD histogram positive and growing (momentum building)
        3. EMA 9 > EMA 21 (short-term bullish crossover)
        4. Price above EMA 50 (medium-term uptrend)
        5. Volume above average (confirmation)
        6. BB pct below 0.85 (not near upper band)
        """
        conditions = (
            (dataframe["rsi_14"] > 35) &
            (dataframe["rsi_14"] < 65) &
            (dataframe["macd_hist"] > 0) &
            (dataframe["macd_hist"] > dataframe["macd_hist"].shift(1)) &
            (dataframe["ema_9"] > dataframe["ema_21"]) &
            (dataframe["close"] > dataframe["ema_50"]) &
            (dataframe["volume_change"] > 1.0) &
            (dataframe["bb_pct"] < 0.85) &
            (dataframe["volume"] > 0)
        )
        dataframe.loc[conditions, "enter_long"] = 1
        dataframe.loc[conditions, "enter_tag"] = "rsi_macd_ema_vol"
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit conditions — any one triggers exit:
        1. RSI overbought (> 75)
        2. Price crosses below EMA 21
        3. MACD histogram turns negative after being positive
        4. Price near top of Bollinger (bb_pct > 0.95)
        """
        conditions = (
            (dataframe["rsi_14"] > 75) |
            (
                (dataframe["close"] < dataframe["ema_21"]) &
                (dataframe["close"].shift(1) > dataframe["ema_21"].shift(1))
            ) |
            (
                (dataframe["macd_hist"] < 0) &
                (dataframe["macd_hist"].shift(1) > 0)
            ) |
            (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[conditions, "exit_long"] = 1
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """Safety gate: reject entries against the trend."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False

        last = dataframe.iloc[-1]

        # Reject if price below 200 EMA (macro downtrend)
        if last["close"] < last["ema_200"]:
            logger.info(f"[{pair}] Entry rejected: price below 200 EMA (downtrend)")
            return False

        # Reject if RSI is extremely overbought
        if last["rsi_14"] > 78:
            logger.info(f"[{pair}] Entry rejected: RSI {last[rsi_14]:.1f} > 78 (overbought)")
            return False

        return True

    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """ATR-based trailing stoploss."""
        if current_profit > 0.04:
            return -0.01
        if current_profit > 0.02:
            return -0.015
        return -0.03
