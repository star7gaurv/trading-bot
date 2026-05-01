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
    FinBuddy FreqAI Strategy v5 — ROI/SL restructure after Round 1 grid analysis.

    Root cause of v4 failure (2026-05-01 Round 1 grid):
      - Win rate was fine (65% at ml=0.009) but Sharpe was negative across ALL 12 combos.
      - Diagnosis: avg winner ~0.8-1.0%, avg loser ~2.5-3.5% => negative expectancy.
      - Tweaking EMA period and RSI ceiling had zero effect (confirmed by grid CSV).
      - Also: autobacktest.py chmod bug meant ALL 12 combos tested same params (combo 1).

    Fixes in v5:
      1. ROI table widened: give winners room to run (was 0.06/0.04/0.02/0.01)
         New: 0.08 at 0min, 0.05 at 45min, 0.03 at 90min, 0.015 at 180min
      2. Stoploss tightened: -0.025 (was -0.035) to cut losers smaller
      3. ATR volatility filter: skip entries when market is flat/dead
         Only enter when atr_ratio (ATR/close) > 0.003 (i.e. >0.3% range)
      4. ML threshold back to 0.010 baseline (0.012 was too restrictive — 29 trades)
      5. Grid in v2 now tests stoploss + roi_scale combos (the real levers)

    ML brain: LightGBMRegressor / FinBuddyLLMModel predicts &-s_close.
    Features: feature_engineering_expand_all() with % prefix (FreqAI standard).
    """
    INTERFACE_VERSION = 3

    # v5: wider ROI — let winners run past early 1% targets
    # previous tight ROI was killing avg winner size
    minimal_roi = {
        "0": 0.08,
        "45": 0.05,
        "90": 0.03,
        "180": 0.015
    }

    # v5: tighter stoploss — cut losers smaller
    # avg loser was ~3.5%, reducing to 2.5% improves reward:risk ratio
    stoploss = -0.025
    trailing_stop = True
    trailing_stop_positive = 0.012
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True

    timeframe = "15m"
    informative_timeframes = ["1h"]

    can_short = False
    startup_candle_count = 40

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

        # v5: ATR volatility filter — only enter when market has real movement
        # atr_ratio = ATR(14) / close price = normalized volatility
        # if atr_ratio < 0.003 the candles are too flat; skip entry
        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ratio"] = dataframe["atr_14"] / dataframe["close"]

        # --- 1h trend filter ---
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
        Entry conditions (v5):
          1. FreqAI predicts > +1.0% price rise (relaxed from 1.2% — was too few trades)
          2. do_predict == 1
          3. 15m close > 15m EMA-50  (short-term uptrend)
          4. 1h close >= 1h EMA-50   (macro trend filter)
          5. RSI-14 < 68             (not overbought)
          6. BB% < 0.90              (not at top of band)
          7. close > EMA-200         (long-term safety filter)
          8. atr_ratio > 0.003       (v5 NEW: market must have real volatility)
          9. volume > 0
        """
        ml_signal = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] > 0.010)  # v5: relaxed from 0.012
        )

        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )

        # v5 NEW: only enter when ATR shows real market movement
        volatility_filter = (
            dataframe["atr_ratio"] > 0.003  # >0.3% of price — not a flat/dead market
        )

        trend_filter_1h = (
            dataframe["close_1h"] >= dataframe["ema_50_1h"]
        )

        safety = (
            (dataframe["close"] > dataframe["ema_200"])
            & (dataframe["rsi_14"] < 78)
        )

        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h & safety,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h & safety,
            "enter_tag"
        ] = "freqai_lgbm_v5"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Exit conditions (unchanged — exit logic was not the problem):
          - FreqAI predicts > -0.3% price drop, OR
          - RSI > 75, OR
          - BB% > 0.95
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
