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
    FinBuddy FreqAI Strategy v6 — Option C: Trailing stop + tighter ML exit combined.

    Root cause of v5 failure (2026-05-01 Round 2 grid, 36 combos):
      - roi_multiplier confirmed dead lever: FreqAI exits via ML signal before ROI hits.
      - stoploss IS the working lever: best result at -0.030 (Sharpe -0.236).
      - Sharpe structurally negative: avg loser still > avg winner in dollar terms.
      - Best Round 2: stoploss=-0.030, ml=0.009, atr=0.002 → 60.8% WR, Sharpe -0.236, PF 0.815.

    Strategy v6 fixes — Option C (both combined):
      1. Trailing stop tightened:
         - positive offset lowered: 0.025 → 0.020 (activate trail sooner, lock in at +2%)
         - positive amount lowered: 0.012 → 0.010 (tighter trail = larger captured profit)
         - Goal: widen avg winner by letting trail protect gains from +2% onward
      2. ML exit threshold tightened:
         - exit on &-s_close < -0.001 (was -0.003)
         - Cut losers 3x faster — exit as soon as ML predicts even tiny reversal
         - Goal: shrink avg loser from ~3.5% toward ~1.5%
      3. Combined effect targets:
         - Wider avg winner (trailing locks in more upside)
         - Smaller avg loser (faster ML exit)
         - Together: flip reward:risk ratio positive → Sharpe > 0.5

    Grid v3 tests:
      - trailing_offset: [0.018, 0.020, 0.022, 0.025] — when to activate trail
      - ml_exit_threshold: [-0.001, -0.002, -0.003] — how fast to exit on ML reversal
      - stoploss: [-0.020, -0.025, -0.030] — hard floor (still the main lever)
      - ml_threshold: [0.009, 0.011]
      - atr_threshold: [0.002, 0.003]
      Total: 72 combos (4x3x3x2x2)

    ML brain: LightGBMRegressor / FinBuddyLLMModel predicts &-s_close.
    Features: feature_engineering_expand_all() with % prefix (FreqAI standard).
    """
    INTERFACE_VERSION = 3

    # v6: ROI table — wide targets (ML exit fires first anyway, confirmed Round 2)
    # roi_multiplier proved to be a dead lever so keeping these wide and stable
    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "120": 0.04,
        "240": 0.02
    }

    # v6: stoploss — hard floor, grid will sweep -0.020 to -0.030
    stoploss = -0.025

    # v6 Option C fix 1: tighter trailing stop
    # offset lowered 0.025 -> 0.020: trail activates at +2% (was +2.5%)
    # positive lowered 0.012 -> 0.010: tighter trail = more profit captured
    trailing_stop = True
    trailing_stop_positive = 0.010  # v6: was 0.012
    trailing_stop_positive_offset = 0.020  # v6: was 0.025 — grid param
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

        # ATR volatility filter — only enter when market has real movement
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
        Entry conditions (v6 — same as v5, unchanged):
          1. FreqAI predicts > +1.0% price rise
          2. do_predict == 1
          3. 15m close > 15m EMA-50
          4. 1h close >= 1h EMA-50
          5. RSI-14 < 68
          6. BB% < 0.90
          7. close > EMA-200
          8. atr_ratio > 0.003 (grid param: atr_threshold)
          9. volume > 0
        """
        ml_signal = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] > 0.010)  # v6: grid param ml_threshold
        )

        ta_filter = (
            (dataframe["close"] > dataframe["ema_50"])
            & (dataframe["rsi_14"] < 68)
            & (dataframe["bb_pct"] < 0.90)
            & (dataframe["volume"] > 0)
        )

        volatility_filter = (
            dataframe["atr_ratio"] > 0.003  # v6: grid param atr_threshold
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
        ] = "freqai_lgbm_v6"
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Exit conditions (v6 Option C fix 2):
          - ML exit threshold tightened: -0.001 (was -0.003)
            Cut losers 3x faster — exit as soon as ML predicts tiny reversal
          - RSI > 75 (unchanged)
          - BB% > 0.95 (unchanged)
        """
        ml_exit = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] < -0.001)  # v6: was -0.003, grid param ml_exit_threshold
        )
        ta_exit = (
            (dataframe["rsi_14"] > 75)
            | (dataframe["bb_pct"] > 0.95)
        )
        dataframe.loc[ml_exit | ta_exit, "exit_long"] = 1
        return dataframe
