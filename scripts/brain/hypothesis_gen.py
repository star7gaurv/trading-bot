"""
hypothesis_gen.py — Generate new strategy variants for the brain to test.

Two bands of aggressiveness:

SAFE BAND — small perturbations around the current best-known config.
  Examples: long_threshold ±0.25, K_SL ±0.25, STABILITY_N ±1, timeframe held.
  Purpose: local search, gradient-descent-like refinement.

AGGRESSIVE BAND — wide combinatorial sweep + structural variants.
  Examples: switch timeframe, swap filters on/off, change label_period, try
  label scheme variants (return vs delta vs barrier).
  Purpose: discover non-local optima the safe band can't reach.

Both bands run in parallel — the brain isn't supposed to choose between them.
"""
from __future__ import annotations

import itertools
import random
from typing import Any

from experiment_log import queue_hypothesis, read_log, best_by_metric


# ── Windows the brain evaluates on (3-month each, finish in <25min) ─────────
# Mix of regimes for diversified evaluation. Each backtest must fit within the
# runner's 30-min lock window so we keep these tight.
WINDOWS = {
    "bull_2024Q1":  "20240101-20240401",   # BTC +60% — strong bull early-2024
    "bull_2024Q2":  "20240401-20240701",   # mid-2024 chop/consolidation
    "bear_2025Q1":  "20250101-20250401",   # BTC -28% — bear leg
}

# ── Seed config (the current best-known, pre-fix-#10 winner) ──────────────
SEED_CONFIG = {
    "strategy":           "FinBuddyFreqAI_v23",
    "freqaimodel":        "LightGBMRegressor",
    "config_file":        "v23_regression_15m_di_config.json",
    "timeframe":          "15m",
    "long_threshold":     3.0,
    "short_threshold":    -3.0,
    "k_sl":               2.0,
    "k_tp":               2.0,
    "stability_n":        2,
    "label_period_candles": 24,
    "filter_di":          True,    # DI_threshold filter
    "filter_svm":         True,    # SVM outlier removal
}


# ── SAFE BAND ─────────────────────────────────────────────────────────────

def generate_safe_band(seed: dict | None = None, n: int = 8) -> list[dict]:
    """
    Small perturbations around the current best config.

    For each variant: pick ONE parameter, shift it by a small step.
    The brain learns a local gradient quickly.
    """
    base = seed or _current_best_config() or SEED_CONFIG
    perturbations = [
        # (param, delta, rationale)
        ("long_threshold",      +0.25, "tighter long entries"),
        ("long_threshold",      -0.25, "looser long entries"),
        ("short_threshold",     -0.25, "tighter short entries"),
        ("short_threshold",     +0.25, "looser short entries"),
        ("k_sl",                +0.25, "wider stop"),
        ("k_sl",                -0.25, "tighter stop"),
        ("k_tp",                +0.25, "more upside on trail"),
        ("k_tp",                -0.25, "tighter trail lock"),
        ("stability_n",         +1,    "stricter signal stability"),
        ("stability_n",         -1,    "looser signal stability"),
    ]
    random.shuffle(perturbations)
    out = []
    for (param, delta, rationale) in perturbations[:n]:
        v = dict(base)
        if isinstance(v[param], int):
            v[param] = max(1, int(v[param] + delta))
        else:
            v[param] = round(float(v[param]) + float(delta), 3)
            # Clamp to sane ranges
            if "threshold" in param:
                if param == "short_threshold":
                    v[param] = max(-6.0, min(-0.25, v[param]))
                else:
                    v[param] = max(0.25, min(6.0, v[param]))
            elif param.startswith("k_"):
                v[param] = max(0.5, min(4.0, v[param]))
        # don't duplicate seed
        if v == base:
            continue
        out.append({
            "band": "safe",
            "rationale": f"safe: {param} {'+' if delta>=0 else ''}{delta} ({rationale})",
            "config": v,
        })
    return out


# ── AGGRESSIVE BAND ───────────────────────────────────────────────────────

AGGRESSIVE_CHOICES = {
    "timeframe":          ["5m", "15m", "30m", "1h", "4h"],
    "long_threshold":     [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
    "short_threshold":    [-0.5, -1.0, -1.5, -2.0, -2.5, -3.0, -4.0],
    "k_sl":               [1.0, 1.5, 2.0, 2.5, 3.0],
    "k_tp":               [1.5, 2.0, 2.5, 3.0],
    "stability_n":        [1, 2, 3, 4],
    "label_period_candles": [12, 24, 48, 72, 144],
    "filter_di":          [True, False],
    "filter_svm":         [True, False],
}

# Map timeframe → which config file to use
TF_CONFIG_MAP = {
    "5m":  "backtest_config.json",          # 5m base + 15m/1h/4h informative
    "15m": "v23_regression_15m_di_config.json",
    "30m": "v23_regression_30m_config.json",
    "1h":  "v23_regression_1h_config.json",
    "4h":  "v23_regression_4h_config.json",
}


def generate_aggressive_band(n: int = 12) -> list[dict]:
    """
    Random sample from the wide combinatorial space.

    We don't enumerate (too many combos = 5×7×7×5×4×4×5×2×2 = 196,000) — instead
    we sample randomly each cycle so over time the space is explored.
    """
    out = []
    seen_keys: set[tuple] = set()
    attempts = 0
    while len(out) < n and attempts < n * 5:
        attempts += 1
        v = {}
        for k, choices in AGGRESSIVE_CHOICES.items():
            v[k] = random.choice(choices)
        # constrain: short_threshold must be negative
        if v["short_threshold"] >= 0:
            v["short_threshold"] = -abs(v["short_threshold"])

        v["strategy"]    = "FinBuddyFreqAI_v23"
        v["freqaimodel"] = "LightGBMRegressor"
        v["config_file"] = TF_CONFIG_MAP[v["timeframe"]]

        # Dedupe based on parameter tuple
        key = tuple(sorted(v.items()))
        if key in seen_keys:
            continue
        seen_keys.add(key)

        rationale = (
            f"aggr: tf={v['timeframe']} lt={v['long_threshold']:+} st={v['short_threshold']:+} "
            f"ksl={v['k_sl']} ktp={v['k_tp']} N={v['stability_n']} lp={v['label_period_candles']} "
            f"di={v['filter_di']} svm={v['filter_svm']}"
        )
        out.append({
            "band": "aggressive",
            "rationale": rationale,
            "config": v,
        })
    return out


# ── Helpers ───────────────────────────────────────────────────────────────

def _current_best_config() -> dict | None:
    """The seed for safe-band perturbation is the current best-by-profit."""
    best = best_by_metric("profit_pct", window=None, min_trades=20)
    if best is None:
        return None
    return best["config"]


# ── Public API ────────────────────────────────────────────────────────────

def queue_seed_if_empty() -> int:
    """If queue and log are both empty, queue SEED_CONFIG on each window."""
    from experiment_log import read_log, read_queue
    if read_log() or read_queue():
        return 0
    queued = 0
    for win_name, timerange in WINDOWS.items():
        queue_hypothesis(
            config=SEED_CONFIG,
            band="seed",
            rationale="seed: baseline from smoke-test best-known",
            window=win_name,
            timerange=timerange,
        )
        queued += 1
    return queued


def generate_and_queue(safe_n: int = 6, aggressive_n: int = 6, windows: list[str] | None = None) -> int:
    """
    One brain cycle: generate safe + aggressive variants, queue them on each window.
    Returns count of newly queued hypotheses.
    """
    target_windows = windows or list(WINDOWS.keys())
    safe = generate_safe_band(n=safe_n)
    aggr = generate_aggressive_band(n=aggressive_n)
    all_variants = safe + aggr

    queued = 0
    for v in all_variants:
        for win_name in target_windows:
            queue_hypothesis(
                config=v["config"],
                band=v["band"],
                rationale=v["rationale"],
                window=win_name,
                timerange=WINDOWS[win_name],
            )
            queued += 1
    return queued


if __name__ == "__main__":
    import json
    n = queue_seed_if_empty()
    if n > 0:
        print(f"Queued seed × {n} windows")
    else:
        added = generate_and_queue(safe_n=4, aggressive_n=6, windows=["bull_2024Q1", "bear_2025Q1"])
        print(f"Queued {added} new hypotheses")
