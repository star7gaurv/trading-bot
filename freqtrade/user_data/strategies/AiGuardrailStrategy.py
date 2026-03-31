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

    # ROI table: Let the AI ride the trend, but take profits if it surges
    minimal_roi = {
        "0": 0.10,    # 10% profit target
        "30": 0.05,   # 5% profit target after 30 minutes
        "60": 0.02,   # 2% profit target after 60 minutes
        "120": 0.01   # 1% profit target after 120 minutes
    }

    # Stoploss: Hard 5% stop loss to protect the account if AI makes a huge mistake
    stoploss = -0.03

    # Trailing stop: Secure profits dynamically as the price rises
    trailing_stop = True
    trailing_stop_positive = 0.01  # Trail by 1%
    trailing_stop_positive_offset = 0.02  # Start trailing once we reach 2% profit
    trailing_only_offset_is_reached = True

    # Optimal timeframe for the strategy.
    timeframe = "15m"

    # Can this strategy go short?
    can_short = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Calculate 200 EMA for Macro Trend Guardrail
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        
        # Calculate RSI for Micro Pullback Guardrail
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        
        # Calculate ATR for volatility context
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        We DO NOT want Freqtrade to buy automatically. 
        We only want n8n to trigger trades via `/forceenter`.
        """
        dataframe.loc[:, "enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exits are managed by ROI, Stoploss, and Trailing Stop.
        """
        dataframe.loc[:, "exit_long"] = 0
        return dataframe
        
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        Strict Guardrail: Intercepts even `/forceenter` commands from the AI.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if not dataframe.empty:
            last_candle = dataframe.iloc[-1].squeeze()
            
            # Guardrail 1: Price must be above 200 EMA (Macro Uptrend)
            if last_candle["close"] < last_candle["ema_200"]:
                logger.warning(f"AI Trade Rejected: {pair} price is below 200 EMA (Downtrend).")
                return False 
                
            # Guardrail 2: RSI shouldn"t be overbought
            if last_candle["rsi"] > 70:
                logger.warning(f"AI Trade Rejected: {pair} RSI is {last_candle[\"rsi\"]} (Too overbought).")
                return False 

        logger.info(f"AI Trade Approved: {pair} passed all risk guardrails.")
        return True
