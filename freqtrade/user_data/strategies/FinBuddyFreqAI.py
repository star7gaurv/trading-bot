# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
from functools import reduce
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, stoploss_from_open
from freqtrade.persistence import Trade
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import logging

logger = logging.getLogger(__name__)


class FinBuddyFreqAI(IStrategy):
    """
    FinBuddy FreqAI Strategy v8 — ATR-adaptive stoploss (2026-05-02)

    Round 2 forensics:
      - WR: 48.2% / 50.0% (was 63% R1) — stoploss was CHOPPING good signals
      - Fixed SL -1.5% is within 15m candle noise: price touches it before signal plays out
      - Evidence: Bear longs (exit_signal) had 93.5% WR at +0.84% avg when NOT stopped out
      - 41-42 stop-loss hits destroyed -130 USDT each run — all profit evaporated

    v8 Fix — ATR-based custom_stoploss():
      - Replace fixed % stoploss with 2.0 × ATR-based floor
      - On 15m BTC: ATR ~0.3-0.8% of price. 2×ATR = 0.6-1.6% = true noise floor
      - Floor: never less than -4% (protects against gaps/flash crashes)
      - Ceiling: never triggered above -0.5% (minimum viable stop)
      - Trailing ATR: once trade is +1 ATR in profit, trail at 1.5×ATR below peak

    v8 keeps from v7 (all working):
      - BTC 4h macro trend filter
      - Relaxed short entry (RSI > 20, 2% 1h buffer, no ema_200 requirement)
      - Dynamic long threshold (> 0.010 bull / > 0.015 bear)
      - ML-based exit on signal reversal (< -0.001 / > +0.001)
      - Trailing stop positive offset for winners

    Expected outcome:
      - Stop hits drop from 41-42 back toward 10-15 (stops only on real reversals)
      - WR recovers to 60%+ (ML signals get to play out)
      - reward:risk improves: avg winner +0.84% / avg stopper ~2×ATR ~0.8% = 1:1
    """
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.10,
        "60": 0.06,
        "120": 0.04,
        "240": 0.02
    }

    # v8: wide fallback stoploss — custom_stoploss() does the real work
    # This is just the emergency hard floor (gap protection, exchange outage)
    stoploss = -0.08

    # v9: framework trailing DISABLED — custom_stoploss() owns the trail exclusively.
    # Round 3 showed 79/62 trailing_stop_loss exits at -0.55% avg from the two
    # trailing systems (framework + Chandelier in custom_stoploss) fighting each
    # other. With this off, custom_stoploss is the single source of truth.
    trailing_stop = False

    # v8: enable custom stoploss
    use_custom_stoploss = True

    timeframe = "15m"
    informative_timeframes = ["1h", "4h"]

    can_short = True
    startup_candle_count = 400

    # ------------------------------------------------------------------ #
    # ATR-adaptive custom stoploss                                        #
    # ------------------------------------------------------------------ #

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> Optional[float]:
        """
        v10 — ATR-adaptive stoploss, rebuilt for docs-correctness.

        Per Freqtrade strategy-callbacks docs:
          - Returning None = "no desire to change" the existing stop.
            Do NOT fall back to self.stoploss — that resets a previously
            tightened stop on every candle when ATR is unavailable.
          - Return value is treated as |abs| % of current_rate; sign ignored.
          - The stop can only ever move upwards (Freqtrade enforces).

        v10 fixes vs v9:
          1. None on missing data (was: self.stoploss → forced reset).
          2. Return positive floats (was: negative; same effect, but explicit).
          3. trailing_stop = False already (set at class level).
          4. Anchor stops to ENTRY price via stoploss_from_open(), not to
             current_rate. Stops the chop where price runs up and the
             current-rate-relative stop tightens beneath it.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None  # v10 Fix 1

        last = dataframe.iloc[-1]
        atr = last.get("atr_14", None)
        if atr is None or atr <= 0 or current_rate <= 0:
            return None  # v10 Fix 1

        atr_pct = atr / current_rate
        atr_pct = max(0.003, min(atr_pct, 0.025))  # clamp 0.3%–2.5%

        # --- Trailing arm: profit > 1×ATR → lock at +1.5×ATR above entry ---
        # Positive open_relative_stop = profit-lock above open (canonical use).
        # stoploss_from_open returns 0 if the lock would be at/above current
        # price (profit not yet large enough); treat that as "no change".
        if current_profit > atr_pct:
            trail_pct = stoploss_from_open(
                1.5 * atr_pct,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
            if trail_pct and trail_pct > 0:
                return trail_pct  # v10 Fix 2: positive float
            return None

        # --- Initial arm: 2×ATR below entry, anchored via the same helper ---
        # NEGATIVE open_relative_stop = loss-cap below open. The helper
        # returns 0 when current price has already breached the open-anchored
        # floor, which is correctly handled by Freqtrade as "stop now".
        initial_stop = stoploss_from_open(
            -2.0 * atr_pct,
            current_profit,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
        if initial_stop and initial_stop > 0:
            return initial_stop  # v10 Fix 2: positive float
        return None

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

        # --- 15m TA ---
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

        # ATR — used both for entry filter AND custom_stoploss
        dataframe["atr_14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ratio"] = dataframe["atr_14"] / dataframe["close"]

        # --- 1h trend ---
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

            # --- BTC 4h macro trend filter (from v7) ---
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
        Entry conditions v8 (inherited from v7, all working):

        LONG:
          - ML > +1.0% (bull) / > +1.5% (bear via BTC 4h filter)
          - close > EMA-50 (15m trend)
          - close_1h >= ema_50_1h (1h trend)
          - RSI < 68 | BB% < 0.90 | atr_ratio > 0.003 | volume > 0

        SHORT (relaxed from v7):
          - ML < -1.0%
          - close < EMA-50
          - close_1h < ema_50_1h * 1.02 (2% buffer)
          - RSI > 20 (was 32) | BB% > 0.10 | atr_ratio > 0.003 | volume > 0
          - No ema_200 requirement (fires too late)
        """
        # Dynamic long ML threshold — v7 carry-forward
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

        volatility_filter = dataframe["atr_ratio"] > 0.003

        trend_filter_1h = dataframe["close_1h"] >= dataframe["ema_50_1h"]

        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h,
            "enter_long"
        ] = 1
        dataframe.loc[
            ml_signal & ta_filter & volatility_filter & trend_filter_1h,
            "enter_tag"
        ] = "freqai_lgbm_v10_long"

        # --- Short entry (v9: macro-gated) ---
        # v9 fix: shorts only fire when BTC 4h is below its EMA-50 (macro bear).
        # Round 3 bull period had 81 shorts vs 31 longs in a +122% bull market —
        # the macro filter was leaking. Requiring btc_4h_below_ema50 == 1 here
        # prevents shorting alts during a sustained BTC uptrend.
        ml_signal_short = (
            (dataframe["do_predict"] == 1)
            & (dataframe["&-s_close"] < -0.010)
            & (dataframe["btc_4h_below_ema50"] == 1)
        )

        ta_filter_short = (
            (dataframe["close"] < dataframe["ema_50"])
            & (dataframe["rsi_14"] > 20)
            & (dataframe["bb_pct"] > 0.10)
            & (dataframe["volume"] > 0)
        )

        trend_filter_1h_short = (
            dataframe["close_1h"] < dataframe["ema_50_1h"] * 1.02
        )

        safety_short = dataframe["rsi_14"] > 15

        dataframe.loc[
            ml_signal_short & ta_filter_short & volatility_filter & trend_filter_1h_short & safety_short,
            "enter_short"
        ] = 1
        dataframe.loc[
            ml_signal_short & ta_filter_short & volatility_filter & trend_filter_1h_short & safety_short,
            "enter_tag"
        ] = "freqai_lgbm_v10_short"

        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict
    ) -> DataFrame:
        """
        Exit conditions v8 (unchanged — ML exit is confirmed working):
          Long:  ML < -0.001 OR RSI > 75 OR BB% > 0.95
          Short: ML > +0.001 OR RSI < 25 OR BB% < 0.05
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
