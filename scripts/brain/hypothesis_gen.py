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

# ══════════════════════════════════════════════════════════════════════════
# Two architectures live in the brain. Each has its own seed + param space.
# Brain explores BOTH in parallel — vision says broader perspective wins.
# ══════════════════════════════════════════════════════════════════════════

# v23 Regression — LightGBMRegressor predicting future_return %
SEED_CONFIG_V23 = {
    "arch":               "v23",
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
    "filter_di":          True,
    "filter_svm":         True,
}

# v22 Classifier+LLM — currently live, +110 USDT all-time
# Uses LightGBMClassifier (pure, no LLM layer) for clean brain backtests.
# When promoted to live, the LIVE strategy adds the LLM layer on top.
SEED_CONFIG_V22 = {
    "arch":               "v22",
    "strategy":           "FinBuddyFreqAI",
    "freqaimodel":        "LightGBMClassifier",   # pure backtest; live wraps with LLM
    "config_file":        "v22_backtest_config.json",
    "timeframe":          "5m",
    "k_tp":               2.0,
    "k_sl":               1.0,
    "ml_threshold":       0.60,
    "label_period_candles": 72,
}

# Back-compat alias
SEED_CONFIG = SEED_CONFIG_V23


# ── SAFE BAND (architecture-aware) ────────────────────────────────────────

# Per-architecture perturbation menus. Each tuple: (param, delta, rationale).
PERTURB_V23 = [
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

PERTURB_V22 = [
    ("k_tp",                +0.25, "wider take-profit"),
    ("k_tp",                -0.25, "tighter take-profit"),
    ("k_sl",                +0.20, "wider stop"),
    ("k_sl",                -0.20, "tighter stop"),
    ("ml_threshold",        +0.05, "tighter classifier threshold"),
    ("ml_threshold",        -0.05, "looser classifier threshold"),
]


def _clamp(v: dict, param: str) -> dict:
    """Clamp a perturbed param to a sane range."""
    if "threshold" == param.split("_")[-1] and param != "ml_threshold":
        if param == "short_threshold":
            v[param] = max(-6.0, min(-0.25, v[param]))
        else:
            v[param] = max(0.25, min(6.0, v[param]))
    elif param == "ml_threshold":
        v[param] = max(0.45, min(0.85, v[param]))
    elif param.startswith("k_"):
        v[param] = max(0.5, min(4.0, v[param]))
    return v


def generate_safe_band(seed: dict | None = None, n: int = 8) -> list[dict]:
    """Small perturbations around the current best config — for the SAME architecture."""
    base = dict(seed or _current_best_config() or SEED_CONFIG_V23)
    # Older log entries don't have 'arch' — infer from strategy name
    if "arch" not in base:
        base["arch"] = "v22" if base.get("strategy") == "FinBuddyFreqAI" else "v23"
    perturbations = PERTURB_V22 if base["arch"] == "v22" else PERTURB_V23

    random.shuffle(perturbations)
    out = []
    for (param, delta, rationale) in perturbations[:n]:
        v = dict(base)
        if param not in v:
            continue
        if isinstance(v[param], int):
            v[param] = max(1, int(v[param] + delta))
        else:
            v[param] = round(float(v[param]) + float(delta), 3)
            v = _clamp(v, param)
        if v == base:
            continue
        out.append({
            "band": "safe",
            "rationale": f"safe [{base['arch']}]: {param} {'+' if delta>=0 else ''}{delta} ({rationale})",
            "config": v,
        })
    return out


def generate_safe_band_both(n_per_arch: int = 4) -> list[dict]:
    """SAFE band for BOTH architectures. Seed each from its own current-best."""
    out = []
    for arch_seed in (SEED_CONFIG_V22, SEED_CONFIG_V23):
        best = _current_best_config_for_arch(arch_seed["arch"]) or arch_seed
        out += generate_safe_band(seed=best, n=n_per_arch)
    return out


# ── AGGRESSIVE BAND (architecture-aware) ──────────────────────────────────

AGGRESSIVE_CHOICES_V23 = {
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

AGGRESSIVE_CHOICES_V22 = {
    "timeframe":          ["5m", "15m", "30m", "1h"],     # 4h underperforms v22-style classifier
    "k_tp":               [1.5, 2.0, 2.5, 3.0],
    "k_sl":               [0.8, 1.0, 1.2, 1.5, 2.0],
    "ml_threshold":       [0.55, 0.60, 0.65, 0.70, 0.75],
    "label_period_candles": [6, 12, 24, 48, 72],
}

# Timeframe → config file map (per architecture)
TF_CONFIG_MAP_V23 = {
    "5m":  "backtest_config.json",
    "15m": "v23_regression_15m_di_config.json",
    "30m": "v23_regression_30m_config.json",
    "1h":  "v23_regression_1h_config.json",
    "4h":  "v23_regression_4h_config.json",
}

TF_CONFIG_MAP_V22 = {
    # All v22 variants share v22_backtest_config.json but override timeframe via env.
    # FreqTrade respects --timeframe CLI arg over config's timeframe.
    "5m":  "v22_backtest_config.json",
    "15m": "v22_backtest_config.json",
    "30m": "v22_backtest_config.json",
    "1h":  "v22_backtest_config.json",
}


def _generate_aggressive_v23(n: int) -> list[dict]:
    out, seen = [], set()
    attempts = 0
    while len(out) < n and attempts < n * 5:
        attempts += 1
        v = {k: random.choice(c) for k, c in AGGRESSIVE_CHOICES_V23.items()}
        v["short_threshold"] = -abs(v["short_threshold"])
        v["arch"] = "v23"
        v["strategy"]    = "FinBuddyFreqAI_v23"
        v["freqaimodel"] = "LightGBMRegressor"
        v["config_file"] = TF_CONFIG_MAP_V23[v["timeframe"]]
        key = tuple(sorted(v.items()))
        if key in seen:
            continue
        seen.add(key)
        rationale = (
            f"aggr [v23]: tf={v['timeframe']} lt={v['long_threshold']:+} st={v['short_threshold']:+} "
            f"ksl={v['k_sl']} ktp={v['k_tp']} N={v['stability_n']} lp={v['label_period_candles']} "
            f"di={v['filter_di']} svm={v['filter_svm']}"
        )
        out.append({"band": "aggressive", "rationale": rationale, "config": v})
    return out


def _generate_aggressive_v22(n: int) -> list[dict]:
    out, seen = [], set()
    attempts = 0
    while len(out) < n and attempts < n * 5:
        attempts += 1
        v = {k: random.choice(c) for k, c in AGGRESSIVE_CHOICES_V22.items()}
        v["arch"] = "v22"
        v["strategy"]    = "FinBuddyFreqAI"
        v["freqaimodel"] = "LightGBMClassifier"
        v["config_file"] = TF_CONFIG_MAP_V22[v["timeframe"]]
        key = tuple(sorted(v.items()))
        if key in seen:
            continue
        seen.add(key)
        rationale = (
            f"aggr [v22]: tf={v['timeframe']} ktp={v['k_tp']} ksl={v['k_sl']} "
            f"thr={v['ml_threshold']} lp={v['label_period_candles']}"
        )
        out.append({"band": "aggressive", "rationale": rationale, "config": v})
    return out


def _top_k_results(k: int = 3, min_trades: int = 20) -> list[dict]:
    """Return top-K experiments by profit_pct (filtered by min trade count)."""
    log = [r for r in read_log()
           if r.get("status") == "completed"
           and r.get("metrics", {}).get("trades", 0) >= min_trades]
    if not log:
        return []
    log.sort(key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    return log[:k]


def _generate_guided_aggressive(n: int) -> list[dict]:
    """
    Guided exploration — pick top-K from experiment log and generate medium
    perturbations around each (between safe-band ±0.25 and aggressive random).
    Focuses compute on promising regions instead of pure-random sweep.
    """
    top = _top_k_results(k=3)
    if not top:
        return []  # no signal yet — caller falls back to pure-random aggressive
    out = []
    attempts = 0
    while len(out) < n and attempts < n * 8:
        attempts += 1
        parent = random.choice(top)
        base = dict(parent["config"])
        arch = base.get("arch") or ("v22" if base.get("strategy") == "FinBuddyFreqAI" else "v23")
        choices = AGGRESSIVE_CHOICES_V22 if arch == "v22" else AGGRESSIVE_CHOICES_V23
        # Mutate 2 random dimensions with medium step (one notch in the choice list)
        v = dict(base)
        for param in random.sample(list(choices.keys()), k=min(2, len(choices))):
            opts = choices[param]
            if v.get(param) in opts:
                idx = opts.index(v[param])
                step = random.choice([-1, 1])
                v[param] = opts[max(0, min(len(opts) - 1, idx + step))]
            else:
                v[param] = random.choice(opts)
        if arch == "v23":
            v["short_threshold"] = -abs(v["short_threshold"])
            v["arch"]        = "v23"
            v["strategy"]    = "FinBuddyFreqAI_v23"
            v["freqaimodel"] = "LightGBMRegressor"
            v["config_file"] = TF_CONFIG_MAP_V23[v["timeframe"]]
        else:
            v["arch"]        = "v22"
            v["strategy"]    = "FinBuddyFreqAI"
            v["freqaimodel"] = "LightGBMClassifier"
            v["config_file"] = TF_CONFIG_MAP_V22[v["timeframe"]]
        if v == base:
            continue
        parent_metrics = parent["metrics"]
        rationale = (
            f"guided [{arch}]: derived from {parent['hypothesis_id'][:6]} "
            f"(profit={parent_metrics.get('profit_pct')}% WR={parent_metrics.get('wr',0)*100:.1f}%)"
        )
        out.append({"band": "aggressive", "rationale": rationale, "config": v,
                    "parent_id": parent["hypothesis_id"]})
    return out


def generate_aggressive_band(n: int = 12) -> list[dict]:
    """
    Mix:
      - 50% guided (perturbations around top-3 known results) — focus on promising regions
      - 50% pure-random (across full param space) — keeps exploring
    If no completed experiments yet, falls back to 100% pure-random.
    """
    n_guided = n // 2
    n_random = n - n_guided
    guided = _generate_guided_aggressive(n_guided)
    # If log is empty, guided returns []; use that budget for more random
    if not guided:
        n_random = n
    n_v23 = n_random // 2 + n_random % 2
    n_v22 = n_random // 2
    random_pool = _generate_aggressive_v23(n_v23) + _generate_aggressive_v22(n_v22)
    return guided + random_pool


# ── Helpers ───────────────────────────────────────────────────────────────

def _current_best_config(arch: str | None = None) -> dict | None:
    """Current best-by-profit overall (or restricted to one architecture)."""
    from experiment_log import read_log
    log = [r for r in read_log()
           if r.get("status") == "completed"
           and r.get("metrics", {}).get("trades", 0) >= 20]
    if arch is not None:
        log = [r for r in log if (r.get("config", {}).get("arch") == arch
                                   or (arch == "v23" and r.get("config", {}).get("strategy") == "FinBuddyFreqAI_v23")
                                   or (arch == "v22" and r.get("config", {}).get("strategy") == "FinBuddyFreqAI"))]
    if not log:
        return None
    log.sort(key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    return log[0]["config"]


def _current_best_config_for_arch(arch: str) -> dict | None:
    return _current_best_config(arch=arch)


# ── Public API ────────────────────────────────────────────────────────────

def queue_seed_if_empty() -> int:
    """If queue and log are both empty, queue BOTH v23 + v22 seeds on each window."""
    from experiment_log import read_log, read_queue
    if read_log() or read_queue():
        return 0
    queued = 0
    for seed in (SEED_CONFIG_V23, SEED_CONFIG_V22):
        for win_name, timerange in WINDOWS.items():
            queue_hypothesis(
                config=seed,
                band="seed",
                rationale=f"seed [{seed['arch']}]: baseline",
                window=win_name,
                timerange=timerange,
            )
            queued += 1
    return queued


def queue_v22_seeds() -> int:
    """One-shot helper to seed v22 hypotheses into an existing queue."""
    queued = 0
    for win_name, timerange in WINDOWS.items():
        queue_hypothesis(
            config=SEED_CONFIG_V22,
            band="seed",
            rationale="seed [v22]: live-config baseline (5m, classifier, balanced)",
            window=win_name,
            timerange=timerange,
        )
        queued += 1
    return queued


def generate_and_queue(safe_n: int = 6, aggressive_n: int = 6, windows: list[str] | None = None) -> int:
    """
    One brain cycle: generate safe + aggressive variants for BOTH architectures,
    queue on each window. Returns count of newly queued hypotheses.
    """
    target_windows = windows or list(WINDOWS.keys())
    safe = generate_safe_band_both(n_per_arch=safe_n // 2 + safe_n % 2)
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
                parent_id=v.get("parent_id"),
            )
            queued += 1
    return queued


if __name__ == "__main__":
    import json
    n = queue_seed_if_empty()
    if n > 0:
        print(f"Queued seed × {n} (both v22 + v23 × all windows)")
    else:
        added = generate_and_queue(safe_n=4, aggressive_n=6, windows=["bull_2024Q1", "bear_2025Q1"])
        print(f"Queued {added} new hypotheses")
