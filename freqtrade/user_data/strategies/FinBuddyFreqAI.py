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
    FinBuddy FreqAI Strategy v1
    Uses FreqAI LightGBM model trained on OHLCV + indicators.
    Target: predict price direction 3 candles out (45 min on 15m).
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.10,
        "30": 0.05,
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add indicators for FreqAI training."""
        # Momentum indicators
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
        dataframe["bb_width"] = bb["upperband"] - bb["lowerband"]
        dataframe["bb_pct"] = (dataframe["close"] - bb["lowerband"]) / (dataframe["bb_width"] + 1e-10)

        # ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Volume
        dataframe["volume_change"] = dataframe["volume"] / (dataframe["volume"].rolling(20).mean() + 1e-10)

        # Price position in 24h range
        dataframe["high_24"] = dataframe["high"].rolling(96).max()
        dataframe["low_24"] = dataframe["low"].rolling(96).min()
        dataframe["price_position"] = (dataframe["close"] - dataframe["low_24"]) / (dataframe["high_24"] - dataframe["low_24"] + 1e-10)

        # Time features (cyclical encoding)
        # Note: Temporarily disabled due to dataframe index type issue
        # dataframe["hour"] = dataframe.index.hour
        # dataframe["hour_sin"] = np.sin(2 * np.pi * dataframe["hour"] / 24)
        # dataframe["hour_cos"] = np.cos(2 * np.pi * dataframe["hour"] / 24)

        # dataframe["dayofweek"] = dataframe.index.dayofweek
        # dataframe["day_sin"] = np.sin(2 * np.pi * dataframe["dayofweek"] / 7)
        # dataframe["day_cos"] = np.cos(2 * np.pi * dataframe["dayofweek"] / 7)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """FreqAI handles entry signals via predict."""
        dataframe.loc[:, "enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """FreqAI handles exit signals via predict."""
        dataframe.loc[:, "exit_long"] = 0
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """Safety gate: confirm trade makes sense."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False

        last = dataframe.iloc[-1]

        # Reject if price below 200 EMA (downtrend)
        if "ema_200" in last and last["close"] < last["ema_200"]:
            logger.warning(f"Entry rejected {pair}: price below 200 EMA")
            return False

        return True

    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Custom stop loss logic."""
        if current_profit > 0.02:
            return -0.01
        return -0.03
