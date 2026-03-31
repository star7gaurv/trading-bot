# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import logging

logger = logging.getLogger(__name__)

class AiGuardrailStrategy(IStrategy):
    """
    AI Guardrail Strategy
    Designed to be driven by n8n / AI via API (/forceenter).
    This strategy acts as a safety net. It prevents buying if the market is too risky,
    and manages the exit automatically using trailing stops and hard stop losses.
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
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, "exit_long"] = 0
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if not dataframe.empty:
            last_candle = dataframe.iloc[-1].squeeze()

            if last_candle["close"] < last_candle["ema_200"]:
                logger.warning(f'AI Trade Rejected: {pair} price is below 200 EMA (Downtrend).')
                return False

            if last_candle["rsi"] > 70:
                logger.warning(f'AI Trade Rejected: {pair} RSI is {last_candle["rsi"]} (Too overbought).')
                return False

        logger.info(f'AI Trade Approved: {pair} passed all risk guardrails.')
        return True
