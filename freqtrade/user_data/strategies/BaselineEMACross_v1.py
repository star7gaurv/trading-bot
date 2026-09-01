"""
BaselineEMACross_v1 — dumb-entry benchmark for the ML entry signal.

Inherits EVERYTHING from CortexaAI_v23 (FreqAI features/targets, ML-driven
exits, ATR stops, leverage, circuit breaker, confirm gates) and replaces ONLY
populate_entry_trend with a plain EMA20/50 crossover.

Purpose (2026-06-11 plan, C6): quantify what the ML *entry* adds. Live data
shows exits earn (+256 USDT @ 87.5% WR) while 38% of entries ride to the full
stop-loss. If this baseline matches or beats the ML entries on the same test
windows, the entry model is not adding value and entry work is the priority.

Benchmark only — never deploy live. Excluded from brain promotion/parenting
via target_version='baseline' on its queue entries.
"""
import talib.abstract as ta
from pandas import DataFrame

from CortexaAI_v23 import CortexaAI_v23


class BaselineEMACross_v1(CortexaAI_v23):

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df["baseline_ema_fast"] = ta.EMA(df, timeperiod=20)
        df["baseline_ema_slow"] = ta.EMA(df, timeperiod=50)

        cross_up = (
            (df["baseline_ema_fast"] > df["baseline_ema_slow"])
            & (df["baseline_ema_fast"].shift(1) <= df["baseline_ema_slow"].shift(1))
        )
        cross_dn = (
            (df["baseline_ema_fast"] < df["baseline_ema_slow"])
            & (df["baseline_ema_fast"].shift(1) >= df["baseline_ema_slow"].shift(1))
        )
        # do_predict==1 keeps the same data-quality gating the ML entries get,
        # so the comparison isolates the entry signal, not data availability.
        ok = (df.get("do_predict", 1) == 1) & (df["volume"] > 0)

        df.loc[cross_up & ok, ["enter_long", "enter_tag"]] = (1, "baseline_ema_cross_long")
        df.loc[cross_dn & ok, ["enter_short", "enter_tag"]] = (1, "baseline_ema_cross_short")
        return df
