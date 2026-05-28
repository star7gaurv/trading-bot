"""
analyst.py — Self-diagnosis engine for the FinBuddy brain.

Runs every 6 h (after the generate cron). Reads all completed experiment
results, identifies what is failing and why, prunes dead hypotheses from
the queue, and injects targeted replacements.

This closes the self-awareness loop:

  run experiments → log results → ANALYSE patterns → prune dead queue
  → inject targeted hypotheses → run experiments → …

Without this the brain would keep rerunning the same failing patterns
forever.  With this it steers itself toward productive search regions.

Patterns detected
─────────────────
1. Dead timeframes       — avg PF < threshold for ≥3 runs → prune from queue
2. Window divergence     — bear WR >> bull WR → short-bias detected
3. Fee-drag signature    — WR>50 % but PF<1.0 → exit geometry wrong
4. Trade-count noise     — trades/day > N → entry too permissive
5. Stuck config regions  — param value consistently yields low PF → blacklist

Actions taken
─────────────
- prune_queue(patterns)       — remove queued experiments matching dead patterns
- inject_targeted(patterns)   — add hypotheses that specifically address root causes
- optional llm_insight()      — ask DeepSeek to reason about the patterns
- send_telegram_report()      — digest of findings + actions taken

CLI
───
  python scripts/brain/analyst.py               # run analysis
  python scripts/brain/analyst.py --dry-run     # print report, no queue changes
  python scripts/brain/analyst.py --no-llm      # skip LLM call
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/ubuntu/var/www/html/trade")
sys.path.insert(0, str(ROOT / "scripts" / "brain"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from experiment_log import read_log, read_queue, queue_hypothesis, _remove_from_queue
from hypothesis_gen import WINDOWS, TF_CONFIG_MAP_V23, TF_CONFIG_MAP_V22
from telegram_template import send as tg_send, Subsystem, Status

ANALYST_REPORT = ROOT / "finbuddy_memory" / "experiments" / "analyst_report.json"

# ─── Thresholds ────────────────────────────────────────────────────────────
MIN_RUNS_TO_JUDGE    = 3      # need at least this many runs before judging a timeframe
DEAD_TF_RELATIVE     = 0.80   # TF avg PF < best_TF_avg_pf × this → relative underperformer
SHORT_BIAS_GAP       = 0.05   # bear WR - bull WR > this → short bias detected
NEAR_BREAKEVEN_LOW   = 0.85   # best PF in this range → near-breakeven, push harder
NEAR_BREAKEVEN_HIGH  = 1.05
FEE_DRAG_WR_MIN      = 0.50   # WR > this AND PF < 1.0 → fee drag (winners cut short)
NOISE_TRADES_PER_DAY = 5.5    # avg trades/day above this = too noisy on that TF
WINDOW_DAYS = {
    "bull_2024Q1": 91, "bull_2024Q2": 91, "bear_2025Q1": 90,
    "bull_2025Q4": 92, "bear_2026Q1": 90,   # Fix 5 (2026-05-22): added new windows
}


# ─── Data loading ──────────────────────────────────────────────────────────

def _completed(min_trades: int = 10) -> list[dict]:
    return [
        r for r in read_log()
        if r.get("status") == "completed"
        and r.get("metrics", {}).get("trades", 0) >= min_trades
    ]


# ─── Pattern detection ─────────────────────────────────────────────────────

def detect_patterns(completed: list[dict]) -> dict:
    """
    Return a findings dict with keys:
      dead_timeframes   — TFs whose avg PF is significantly below the best TF (relative)
      noisy_timeframes  — TFs with too many trades/day
      short_bias        — bool: bear WR consistently outperforms bull WR
      fee_drag          — bool: best WR>50% but PF<1 (direction right, exit wrong)
      near_breakeven    — bool: best PF 0.85–1.05 (close but not profitable yet)
      best_bear         — top experiment on bear window
      best_bull         — top experiment on bull window
      best_overall      — global best by profit_pct
      window_stats      — {window: {avg_wr, avg_pf, n}}
      tf_stats          — {timeframe: {avg_wr, avg_pf, avg_trades_day, n}}
    """
    findings: dict[str, Any] = {
        "dead_timeframes":  [],
        "noisy_timeframes": [],
        "short_bias":       False,
        "fee_drag":         False,
        "near_breakeven":   False,
        "best_bear":        None,
        "best_bull":        None,
        "best_overall":     None,
        "window_stats":     {},
        "tf_stats":         {},
    }
    if not completed:
        return findings

    # ── Per-timeframe stats ───────────────────────────────────────────────
    tf_buckets: dict[str, list[dict]] = defaultdict(list)
    for r in completed:
        tf = r.get("config", {}).get("timeframe", "?")
        tf_buckets[tf].append(r)

    for tf, runs in tf_buckets.items():
        pfs = [r["metrics"]["pf"] for r in runs]
        wrs = [r["metrics"]["wr"] for r in runs]
        days = WINDOW_DAYS.get(runs[0].get("window", ""), 90)
        trades_day = [r["metrics"]["trades"] / max(days, 1) for r in runs]
        findings["tf_stats"][tf] = {
            "n":              len(runs),
            "avg_pf":         round(sum(pfs) / len(pfs), 3),
            "avg_wr":         round(sum(wrs) / len(wrs), 3),
            "avg_trades_day": round(sum(trades_day) / len(trades_day), 2),
        }

    # Relative dead-TF detection: flag TFs significantly worse than the best TF
    if findings["tf_stats"]:
        best_tf_pf = max(s["avg_pf"] for s in findings["tf_stats"].values())
        for tf, s in findings["tf_stats"].items():
            if s["n"] >= MIN_RUNS_TO_JUDGE:
                if s["avg_pf"] < best_tf_pf * DEAD_TF_RELATIVE:
                    findings["dead_timeframes"].append(tf)
                if s["avg_trades_day"] > NOISE_TRADES_PER_DAY:
                    findings["noisy_timeframes"].append(tf)

    # ── Per-window stats ──────────────────────────────────────────────────
    win_buckets: dict[str, list[dict]] = defaultdict(list)
    for r in completed:
        win_buckets[r.get("window", "?")].append(r)

    win_wr: dict[str, float] = {}
    for win, runs in win_buckets.items():
        wrs = [r["metrics"]["wr"] for r in runs]
        pfs = [r["metrics"]["pf"] for r in runs]
        win_wr[win] = sum(wrs) / len(wrs)
        findings["window_stats"][win] = {
            "n":      len(runs),
            "avg_wr": round(win_wr[win], 3),
            "avg_pf": round(sum(pfs) / len(pfs), 3),
        }

    # short-bias: bear WR significantly outperforms bull WR
    bear_windows = [w for w in win_wr if "bear" in w]
    bull_windows = [w for w in win_wr if "bull" in w]
    if bear_windows and bull_windows:
        avg_bear_wr = sum(win_wr[w] for w in bear_windows) / len(bear_windows)
        avg_bull_wr = sum(win_wr[w] for w in bull_windows) / len(bull_windows)
        if avg_bear_wr - avg_bull_wr > SHORT_BIAS_GAP:
            findings["short_bias"] = True

    # ── Best experiments ──────────────────────────────────────────────────
    sorted_all = sorted(completed, key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    findings["best_overall"] = sorted_all[0] if sorted_all else None

    bear = [r for r in completed if "bear" in r.get("window", "")]
    bear.sort(key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    findings["best_bear"] = bear[0] if bear else None

    bull = [r for r in completed if "bull" in r.get("window", "")]
    bull.sort(key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    findings["best_bull"] = bull[0] if bull else None

    # fee-drag: best result has WR>50% but PF<1.0
    if findings["best_overall"]:
        m = findings["best_overall"]["metrics"]
        if m["wr"] > FEE_DRAG_WR_MIN and m["pf"] < 1.0:
            findings["fee_drag"] = True
        # near-breakeven: PF is close to 1.0 — a small push could flip to profitable
        if NEAR_BREAKEVEN_LOW <= m["pf"] <= NEAR_BREAKEVEN_HIGH:
            findings["near_breakeven"] = True

    return findings


# ─── Queue pruning ─────────────────────────────────────────────────────────

def prune_queue(findings: dict, dry_run: bool = False) -> int:
    """
    Remove queued hypotheses that match dead patterns.

    Rules:
    - non-zscore entries (no target_version='zscore') → always pruned; they use
      raw-% label semantics incompatible with the current z-scored model and can
      never qualify for promotion
    - dead timeframe → prune all aggressive/seed experiments with that TF
      (keep safe-band experiments since those target current best, not dead zones)
    - noisy timeframe (too many trades) → same pruning logic
    - never prune if queue would drop below 10 (protect minimum experiment flow)

    Returns count of pruned entries.
    """
    # ── Phase 0: always remove non-zscore entries (incompatible label semantics) ──
    zscore_pruned = 0
    _all = read_queue()
    non_zscore_ids = [
        h["hypothesis_id"] for h in _all
        if h.get("config", {}).get("target_version") != "zscore"
    ]
    if non_zscore_ids:
        if not dry_run:
            for hid in non_zscore_ids:
                _remove_from_queue(hid)
        zscore_pruned = len(non_zscore_ids)
        print(f"[analyst] pruned {zscore_pruned} non-zscore queue entries (incompatible label semantics)")

    # ── Phase 0.5: prune queued configs proven to generate 0 trades on bear windows ──
    # Root cause: lt ≥ 3.0 on bear_2026Q1 (recent bear market, lower prediction
    # amplitude) produces 0-5 trades — structurally impossible to reach
    # MIN_TOTAL_TRADES=60. Detect this from completed experiments and blacklist
    # the (long_threshold, window) pairs that consistently generate <5 trades.
    zero_trade_blacklist: set[tuple] = set()
    all_log = read_log()
    for r in all_log:
        if r.get("status") not in ("completed", "scout_failed"):
            continue
        m = r.get("metrics") or {}
        if m.get("trades", 999) < 5 and "bear" in r.get("window", ""):
            lt = r.get("config", {}).get("long_threshold")
            win = r.get("window", "")
            if lt is not None:
                zero_trade_blacklist.add((lt, win))

    zero_trade_pruned = 0
    if zero_trade_blacklist:
        _queue = read_queue()
        zero_ids = []
        for h in _queue:
            if h.get("band") == "safe":
                continue
            lt = h.get("config", {}).get("long_threshold")
            win = h.get("window", "")
            if (lt, win) in zero_trade_blacklist:
                zero_ids.append(h["hypothesis_id"])
        if zero_ids:
            if not dry_run:
                for hid in zero_ids:
                    _remove_from_queue(hid)
            zero_trade_pruned = len(zero_ids)
            print(f"[analyst] pruned {zero_trade_pruned} zero-trade bear configs "
                  f"(blacklisted (lt,window) pairs: {len(zero_trade_blacklist)})")
    zscore_pruned += zero_trade_pruned

    # ── Phase 1: timeframe-based pruning ──
    dead_tfs  = set(findings.get("dead_timeframes", []))
    noisy_tfs = set(findings.get("noisy_timeframes", []))
    bad_tfs   = dead_tfs | noisy_tfs
    if not bad_tfs:
        return zscore_pruned

    queue = read_queue()
    prunable = []
    for h in queue:
        if h.get("band") == "safe":
            continue  # always keep safe-band refinements
        tf = h.get("config", {}).get("timeframe", "")
        if tf in bad_tfs:
            prunable.append(h["hypothesis_id"])

    # Safety: leave at least 10 in queue
    safe_count = len([h for h in queue if h.get("band") == "safe"])
    non_prunable = len(queue) - len(prunable)
    if non_prunable + safe_count < 10:
        keep_n = max(0, 10 - (non_prunable + safe_count))
        prunable = prunable[keep_n:]  # spare the first N

    if dry_run:
        return zscore_pruned + len(prunable)

    for hid in prunable:
        _remove_from_queue(hid)
    return zscore_pruned + len(prunable)


# ─── Targeted hypothesis injection ─────────────────────────────────────────

def _queue_targeted(config: dict, band: str, rationale: str, windows: list[str] | None = None) -> int:
    target = windows or list(WINDOWS.keys())
    n = 0
    for win in target:
        if win not in WINDOWS:
            continue
        queue_hypothesis(
            config=config,
            band=band,
            rationale=rationale,
            window=win,
            timerange=WINDOWS[win],
        )
        n += 1
    return n


def inject_targeted(findings: dict, dry_run: bool = False) -> list[str]:
    """
    Generate and queue hypotheses that directly address the detected patterns.
    Returns a list of human-readable action strings (for the report).
    """
    actions: list[str] = []
    best_overall = findings.get("best_overall")
    best_bear    = findings.get("best_bear")
    best_bull    = findings.get("best_bull")

    if dry_run:
        if findings["fee_drag"]:
            actions.append("[DRY-RUN] Would queue: fee-drag fix (wider K_TP, tighter K_SL)")
        if findings["short_bias"]:
            actions.append("[DRY-RUN] Would queue: short-bias fix (lower long_threshold, symmetric thresholds)")
        if findings["dead_timeframes"]:
            actions.append(f"[DRY-RUN] Would skip dead TFs: {findings['dead_timeframes']}")
        return actions

    # ── Fix 1: Fee-drag ───────────────────────────────────────────────────
    # WR>50% but PF<1 → winners are smaller than losers.
    # Try: (a) wider K_TP to let winners run, (b) tighter K_SL to cut losers faster.
    if findings["fee_drag"] and best_overall:
        base = dict(best_overall["config"])
        arch = base.get("arch", "v23")
        parent_id = best_overall["hypothesis_id"]

        # Variant A: wider K_TP (+0.5)
        va = dict(base)
        old_ktp = float(va.get("k_tp", 2.0))
        va["k_tp"] = round(min(4.0, old_ktp + 0.5), 2)
        if va["k_tp"] != old_ktp:
            n = _queue_targeted(
                va, "safe",
                f"analyst: fee-drag fix — K_TP {old_ktp}→{va['k_tp']} (let winners run); "
                f"parent={parent_id[:6]} WR={best_overall['metrics']['wr']*100:.0f}% PF={best_overall['metrics']['pf']:.2f}",
            )
            actions.append(f"Queued ×{n} fee-drag/wider-K_TP (K_TP {old_ktp}→{va['k_tp']})")

        # Variant B: tighter K_SL (-0.25)
        vb = dict(base)
        old_ksl = float(vb.get("k_sl", 2.0))
        vb["k_sl"] = round(max(0.5, old_ksl - 0.25), 2)
        if vb["k_sl"] != old_ksl:
            n = _queue_targeted(
                vb, "safe",
                f"analyst: fee-drag fix — K_SL {old_ksl}→{vb['k_sl']} (cut losers faster); "
                f"parent={parent_id[:6]}",
            )
            actions.append(f"Queued ×{n} fee-drag/tighter-K_SL (K_SL {old_ksl}→{vb['k_sl']})")

    # ── Fix 2: Short-bias / bull failure ──────────────────────────────────
    # Bear WR >> Bull WR → model predicts shorts well but misses longs.
    # Try: (a) lower long_threshold (easier long entry),
    #      (b) symmetric thresholds (same barrier for L and S),
    #      (c) use BEST BEAR config but test on ALL windows (maybe it generalises).
    if findings["short_bias"]:
        if best_bear:
            base = dict(best_bear["config"])
            arch = base.get("arch", "v23")

            # Variant A: lower long_threshold (more longs)
            if arch == "v23" and "long_threshold" in base:
                vc = dict(base)
                old_lt = float(vc["long_threshold"])
                vc["long_threshold"] = round(max(0.25, old_lt - 0.5), 2)
                if vc["long_threshold"] != old_lt:
                    n = _queue_targeted(
                        vc, "aggressive",
                        f"analyst: short-bias fix — long_threshold {old_lt}→{vc['long_threshold']} "
                        f"(improve bull capture); parent={best_bear['hypothesis_id'][:6]}",
                        windows=["bull_2024Q1", "bull_2024Q2"],
                    )
                    actions.append(f"Queued ×{n} short-bias/lower-long-threshold on BULL windows")

            # Variant B: symmetric thresholds (long = |short|)
            if arch == "v23" and "long_threshold" in base and "short_threshold" in base:
                vd = dict(base)
                sym = round((abs(float(vd["long_threshold"])) + abs(float(vd["short_threshold"]))) / 2, 2)
                vd["long_threshold"] = sym
                vd["short_threshold"] = -sym
                if vd != base:
                    n = _queue_targeted(
                        vd, "aggressive",
                        f"analyst: short-bias fix — symmetric thresholds ±{sym} "
                        f"(force equal L/S sensitivity); parent={best_bear['hypothesis_id'][:6]}",
                    )
                    actions.append(f"Queued ×{n} short-bias/symmetric-thresholds ±{sym}")

        # Variant C: cross-validate — run best-overall on both windows if not already done
        if best_overall:
            existing_hids = {r["hypothesis_id"] for r in read_log()}
            existing_rationales = {r.get("rationale", "") for r in read_log()}
            cross_key = f"cross-validate {best_overall['hypothesis_id'][:6]}"
            if not any(cross_key in rat for rat in existing_rationales):
                n = _queue_targeted(
                    best_overall["config"], "safe",
                    f"analyst: cross-validate best-overall on all windows — "
                    f"{cross_key} (confirm it isn't window-specific)",
                )
                actions.append(f"Queued ×{n} cross-window validation of best config")

    # ── Fix 2b: Near-breakeven — micro-tune the best config ──────────────
    # PF 0.85–1.05: we're right on the edge. Generate very fine perturbations
    # around the best config to nudge it over PF=1.0.
    if findings.get("near_breakeven") and best_overall:
        base = dict(best_overall["config"])
        arch = base.get("arch", "v23")
        parent_id = best_overall["hypothesis_id"]
        m = best_overall["metrics"]

        nudges = []
        if arch == "v23":
            # Tighter long entry: fewer but higher-quality longs
            for lt_delta in (+0.25, +0.5):
                old = float(base.get("long_threshold", 3.0))
                new = round(min(6.0, old + lt_delta), 2)
                if new != old:
                    v = dict(base); v["long_threshold"] = new
                    nudges.append((v, f"near-breakeven: lt {old}→{new} (quality filter)"))
            # Tighter short entry too
            for st_delta in (-0.25, -0.5):
                old = float(base.get("short_threshold", -3.0))
                new = round(max(-6.0, old + st_delta), 2)
                if new != old:
                    v = dict(base); v["short_threshold"] = new
                    nudges.append((v, f"near-breakeven: st {old}→{new} (quality filter)"))
            # Stability filter: require one extra confirmation candle
            old_n = int(base.get("stability_n", 2))
            v = dict(base); v["stability_n"] = old_n + 1
            nudges.append((v, f"near-breakeven: stability_n {old_n}→{old_n+1} (reduce noise)"))
        else:  # v22
            old_thr = float(base.get("ml_threshold", 0.60))
            for delta in (+0.05, +0.10):
                new = round(min(0.85, old_thr + delta), 2)
                if new != old_thr:
                    v = dict(base); v["ml_threshold"] = new
                    nudges.append((v, f"near-breakeven: threshold {old_thr}→{new}"))

        for cfg, rationale in nudges[:4]:  # max 4 nudges to keep queue clean
            n = _queue_targeted(
                cfg, "safe",
                f"analyst: {rationale}; parent={parent_id[:6]} "
                f"PF={m['pf']:.2f} profit={m['profit_pct']:+.2f}%",
            )
            actions.append(f"Queued ×{n} near-breakeven nudge: {rationale}")

    # ── Fix 3: Add second-best window as new target ───────────────────────
    # If brain has only tested 2 windows, add the 3rd for broader coverage.
    tested_windows = {r.get("window") for r in read_log() if r.get("status") == "completed"}
    untested = [w for w in WINDOWS if w not in tested_windows]
    if untested and best_overall:
        for w in untested[:1]:  # add one new window at a time
            n = _queue_targeted(
                best_overall["config"], "safe",
                f"analyst: expand coverage — test best config on untested window {w}",
                windows=[w],
            )
            actions.append(f"Queued ×{n} expansion to untested window {w}")

    # ── Fix 4: Dead TFs + promising bear with no bull success ─────────────
    # When non-15m TFs are marked dead AND we have a great bear config that
    # hasn't succeeded on any bull window, cross-validate it on bull windows.
    # This fixes the gap where inject_targeted detected dead_tfs but did nothing.
    bull_windows  = [w for w in WINDOWS if "bull" in w]
    bear_windows  = [w for w in WINDOWS if "bear" in w]
    if findings.get("dead_timeframes") and best_bear:
        bear_cfg_sig = json.dumps(
            {k: best_bear["config"].get(k) for k in sorted(best_bear["config"])},
            sort_keys=True
        )
        # Check if this bear config has ANY completed bull run
        log_all = read_log()
        bear_bull_runs = [
            r for r in log_all
            if r.get("status") == "completed"
            and r.get("window", "") in bull_windows
            and json.dumps(
                {k: r.get("config", {}).get(k) for k in sorted(best_bear["config"])},
                sort_keys=True
            ) == bear_cfg_sig
        ]
        if not bear_bull_runs:
            parent_id = best_bear.get("hypothesis_id", "?")
            n = _queue_targeted(
                best_bear["config"], "aggressive",
                f"analyst: dead-TF cross-validate — best bear config has 0 bull results; "
                f"queue on bull windows (parent={parent_id[:6]}, "
                f"bear WR={best_bear['metrics'].get('wr',0)*100:.0f}% "
                f"PF={best_bear['metrics'].get('pf',0):.2f})",
                windows=bull_windows,
            )
            actions.append(
                f"Queued ×{n} dead-TF cross-validate: best bear config on bull windows "
                f"(WR={best_bear['metrics'].get('wr',0)*100:.0f}% PF={best_bear['metrics'].get('pf',0):.2f})"
            )

    return actions


# ─── Optional LLM insight (DeepSeek) ──────────────────────────────────────

def llm_insight(findings: dict) -> str:
    """
    Ask DeepSeek to reason about the detected patterns and suggest next steps.
    Returns a 2-3 sentence insight string, or empty string on failure.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return ""

    # Compact summary for the prompt
    tf_summary = {
        tf: f"n={s['n']} avg_pf={s['avg_pf']:.2f} avg_wr={s['avg_wr']*100:.0f}%"
        for tf, s in findings.get("tf_stats", {}).items()
    }
    win_summary = {
        w: f"n={s['n']} avg_pf={s['avg_pf']:.2f} avg_wr={s['avg_wr']*100:.0f}%"
        for w, s in findings.get("window_stats", {}).items()
    }
    best_m = {}
    if findings.get("best_overall"):
        m = findings["best_overall"]["metrics"]
        best_m = {"WR": f"{m['wr']*100:.1f}%", "PF": m["pf"], "profit": f"{m['profit_pct']:+.2f}%"}

    prompt = f"""You are analysing a LightGBM regression-based crypto trading strategy (FinBuddy v23).
The brain has run {sum(s['n'] for s in findings.get('tf_stats', {}).values())} backtests.

Timeframe performance:
{json.dumps(tf_summary, indent=2)}

Window performance (bull vs bear):
{json.dumps(win_summary, indent=2)}

Detected patterns:
- Dead timeframes (avg PF < 0.75): {findings.get('dead_timeframes', [])}
- Short bias (bear WR >> bull WR): {findings.get('short_bias', False)}
- Fee drag (WR>50% but PF<1.0): {findings.get('fee_drag', False)}
- Noisy timeframes (trades/day > 6): {findings.get('noisy_timeframes', [])}
- Best overall result: {best_m}

In 2–3 sentences, diagnose the most likely root cause and recommend the single most impactful parameter change to try next. Be specific (name the parameter and value)."""

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.3,
    }
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(LLM unavailable: {e})"


# ─── Telegram report ───────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v*100:.0f}%"


def send_report(findings: dict, pruned: int, actions: list[str], insight: str) -> None:
    best = findings.get("best_overall")
    best_str = "none"
    if best:
        m = best["metrics"]
        best_str = (
            f"WR={_pct(m['wr'])} PF={m['pf']:.2f} profit={m['profit_pct']:+.2f}% "
            f"({best.get('window','?')} · {best.get('config',{}).get('timeframe','?')})"
        )

    # Pattern summary line
    flags = []
    if findings.get("near_breakeven"):
        flags.append("🔥 near-breakeven (PF close to 1.0 — nudging)")
    if findings.get("dead_timeframes"):
        flags.append(f"dead TFs: {','.join(findings['dead_timeframes'])}")
    if findings.get("short_bias"):
        flags.append("short-bias detected")
    if findings.get("fee_drag"):
        flags.append("fee-drag detected")
    if findings.get("noisy_timeframes"):
        flags.append(f"noisy TFs: {','.join(findings['noisy_timeframes'])}")
    pattern_line = "; ".join(flags) if flags else "no strong patterns yet"

    actions_line = "\n".join(f"  · {a}" for a in actions) if actions else "  · none"

    fields = {
        "Patterns":   pattern_line,
        "Best so far": best_str,
        "Pruned":     f"{pruned} queued experiments removed",
        "Injected":   f"{len(actions)} targeted hypothesis batches",
    }
    tf_ctx = {k: "pf={:.2f} n={}".format(v["avg_pf"], v["n"]) for k, v in findings.get("tf_stats", {}).items()}
    context = "TF stats: " + json.dumps(tf_ctx)
    action_text = insight if insight else None

    tg_send(
        subsystem=Subsystem.BRAIN_CYCLE,
        status=Status.INFO,
        title="Brain Self-Diagnosis Complete",
        fields=fields,
        context=context,
        action=action_text,
        silent=False,
    )


# ─── Main ──────────────────────────────────────────────────────────────────

def analyse(dry_run: bool = False, no_llm: bool = False) -> dict:
    completed = _completed(min_trades=10)
    print(f"[analyst] {len(completed)} completed experiments to analyse")

    findings = detect_patterns(completed)

    print(f"[analyst] patterns: dead_tfs={findings['dead_timeframes']} "
          f"short_bias={findings['short_bias']} fee_drag={findings['fee_drag']} "
          f"near_breakeven={findings['near_breakeven']} "
          f"noisy_tfs={findings['noisy_timeframes']}")

    pruned = prune_queue(findings, dry_run=dry_run)
    print(f"[analyst] pruned {pruned} dead-pattern experiments from queue")

    actions = inject_targeted(findings, dry_run=dry_run)
    for a in actions:
        print(f"[analyst] {a}")

    insight = ""
    if not no_llm:
        insight = llm_insight(findings)
        if insight:
            print(f"[analyst] LLM insight: {insight}")

    # Save report
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings":     findings,
        "pruned":       pruned,
        "actions":      actions,
        "llm_insight":  insight,
    }
    # Serialise non-serialisable objects (experiment dicts can have nested structure)
    def _default(o):
        if isinstance(o, dict):
            return o
        return str(o)

    ANALYST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with ANALYST_REPORT.open("w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[analyst] report saved → {ANALYST_REPORT}")

    if not dry_run:
        send_report(findings, pruned, actions, insight)

    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="FinBuddy Brain — self-diagnosis analyst")
    p.add_argument("--dry-run", action="store_true", help="analyse only, no queue changes")
    p.add_argument("--no-llm", action="store_true", help="skip DeepSeek call")
    args = p.parse_args()
    result = analyse(dry_run=args.dry_run, no_llm=args.no_llm)
    print(json.dumps(
        {k: v for k, v in result.items() if k not in ("findings",)},
        indent=2, default=str
    ))
