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
    FinBuddy FreqAI Strategy v7 — Round 2 fixes based on backtest analysis (2026-05-02)

    Round 1 backtest verdict:
      - WR: 63%+ in both bull AND bear  ✅
      - Drawdown: 3.73% / 8.23%         ✅
      - Sharpe: -0.145 / -0.258         ❌
      - Profit Factor: 0.909 / 0.829    ❌

    Root cause (confirmed from exit reason breakdown):
      1. Stoploss avg loss = -3.59% per hit (13-14 hits per period)
         avg winner = +0.43-0.48% — reward:risk was ~0.13:1 — impossible to be profitable
      2. In a -39% bear market only 26 shorts fired vs 56 longs — short filter too restrictive
      3. Math: 13 stops × -3.59% = -93 USDT; winners only generated +82 USDT

    v7 Fix 1 — Stoploss tightened: -0.025 → -0.015
      - Reduces avg loser from -3.59% to approx -1.6% (after fees)
      - reward:risk improves from 0.13:1 to ~0.28:1
      - Combined with 63% WR: Sharpe should flip positive

    v7 Fix 2 — Short entry filter relaxed (3 changes):
      - Removed `close < ema_200` requirement (too slow to trigger in early bear)
      - Changed `close_1h <= ema_50_1h` → `close_1h < ema_50_1h * 1.02` (2% buffer)
      - Lowered RSI floor: `rsi_14 > 32` → `rsi_14 > 20`
      - Expected: 2-3x more short entries in bear period

    v7 Fix 3 — BTC 4h trend filter added
      - `btc_4h_below_ema50`: True when BTC 4h close < BTC 4h EMA-50
      - In bear conditions: only allow shorts (block marginal longs)
      - In bull conditions: both directions allowed
      - Prevents longing alts in a sustained BTC downtrend

    v7 Fix 4 — Dynamic long ML threshold
      - When BTC trend is DOWN (btc_4h_below_ema50=True): require &-s_close > 0.015
      - When BTC trend is UP: normal threshold &-s_close > 0.010
      - Reduces false long signals in bear market

    ML brain: LightGBMRegressor / FinBuddyLLMModel predicts &-s_close.
    Features: feature_engineering_expand_all() with % prefix (FreqAI standard).
    """
    INTERFACE_VERSION = 3

    # v7: ROI — wide, ML exit fires first (confirmed Round 1)
    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "120": 0.04,
        "240": 0.02
    }

    # v7 Fix 1: stoploss tightened -0.025 → -0.015
    # avg loser: -3.59% → approx -1.6% after fees
    stoploss = -0.015

    # v7: trailing stop — keep same as v6, working well (100% WR on trailing exits)
    trailing_stop = True
    trailing_stop_positive = 0.010
    trailing_stop_positive_offset = 0.020
    trailing_only_offset_is_reached = True

    timeframe = "15m"
    informative_timeframes = ["1h", "4h"]

    can_short = True
    startup_candle_count = 400

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

        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ratio"] = dataframe["atr_14"] / dataframe["close"]

        # --- 1h trend filter ---
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

            # --- v7 Fix 3: BTC 4h trend filter ---
            # Load BTC/USDT:USDT 4h regardless of which pair we're trading
            # When BTC 4h is below its EMA-50 → macro bear → block marginal longs
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
        Entry conditions v7:

        LONG:
          1. FreqAI signal > +1.0% (or > +1.5% when BTC 4h bearish) — v7 Fix 4
          2. do_predict == 1
          3. 15m close > EMA-50
          4. 1h close >= EMA-50 1h
          5. RSI-14 < 68 (not overbought)
          6. BB% < 0.90
          7. atr_ratio > 0.003 (real movement present)
          8. volume > 0
          NOTE: ema_200 safety removed from long — was over-filtering in early trend

        SHORT (v7 Fix 2 — relaxed):
          1. FreqAI signal < -1.0%
          2. do_predict == 1
          3. 15m close < EMA-50
          4. 1h close < EMA-50 * 1.02 (2% buffer — was exact <=, too strict)
          5. RSI-14 > 20 (was > 32 — too restrictive, missed deep shorts)
          6. BB% > 0.10
          7. atr_ratio > 0.003
          8. volume > 0
          NOTE: close < ema_200 requirement removed — fires too late in early bear
        """
        # v7 Fix 4: dynamic long ML threshold based on BTC macro trend
        # Bear macro (BTC 4h < EMA-50): require stronger signal 1.5% vs normal 1.0%
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

        volatility_filter = (
            dataframe["atr_ratio"] > 0.003
        )

        trend_filter_1h = (
            dataframe["close_1h"] >= dataframe["ema_50_1h"]
        )

        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h,
            "enter_tag"
        ] = "freqai_lgbm_v7_long"

        # --- v7 Fix 2: Relaxed short entry ---
        ml_signal_short = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] < -0.010)
        )

        ta_filter_short = (
            (dataframe["close"] < dataframe["ema_50"])
            & (dataframe["rsi_14"] > 20)       # v7: was > 32 — too restrictive
            & (dataframe["bb_pct"] > 0.10)
            & (dataframe["volume"] > 0)
        )

        # v7: 2% buffer on 1h trend — was strict <=, now allows slight overshoot
        trend_filter_1h_short = (
            dataframe["close_1h"] < dataframe["ema_50_1h"] * 1.02
        )

        # v7: removed close < ema_200 from short safety — fires too late in early bear
        safety_short = (
            dataframe["rsi_14"] > 15  # only block extreme oversold (< 15)
        )

        dataframe.loc[
            ml_signal_short & ta_filter_short & volatility_filter & trend_filter_1h_short & safety_short,
            "enter_short"
        ] = 1
        dataframe.loc[
            ml_signal_short & ta_filter_short & volatility_filter & trend_filter_1h_short & safety_short,
            "enter_tag"
        ] = "freqai_lgbm_v7_short"

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Exit conditions v7 (unchanged from v6 — working well):
          Long exit: ML predicts reversal < -0.001 OR RSI > 75 OR BB% > 0.95
          Short exit: ML predicts rise > +0.001 OR RSI < 25 OR BB% < 0.05
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
