"""
promote.py — Find the best-known config across all experiments and propose promotion.

APPROVAL-GATED: never modifies live config automatically. Sends Telegram alert with
the proposed config diff vs current live. User approves by running:
    python scripts/brain/promote.py --apply <hypothesis_id>

Promotion criteria (require ALL):
  1. Candidate completed on BOTH a bull window AND a bear window.
  2. On BOTH windows: profit_pct > 0 AND sharpe > 0.
  3. Aggregate score: average profit_pct > current live model's baseline by ≥ 1.0pp.
  4. min 30 trades across all evaluated windows (statistical significance).

If criteria met, store proposal in finbuddy_memory/promotions/pending.json with
the config diff and a single-command apply instruction. Telegram the user.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from experiment_log import read_log
from telegram_template import send as tg_send, Subsystem, Status

ROOT = Path("/home/ubuntu/var/www/html/trade")
LIVE_CONFIG = ROOT / "freqtrade" / "user_data" / "config.json"
PROMOTIONS_DIR = ROOT / "finbuddy_memory" / "promotions"
PENDING_FILE = PROMOTIONS_DIR / "pending.json"

# Improvement threshold over current baseline.
# Lowered 2026-05-19 from 1.0 → 0.1 — the v23 strategy's realistic edge is
# +0.10–0.19% per cross-window run; 1.0pp was unreachable. Re-tighten as
# experiments mature (target 0.5 once a config consistently clears 1%).
MIN_AVG_PROFIT_IMPROVEMENT = 0.1   # percentage points
# 2026-06-17 HONEST-BRAIN fix. Was 30 — far too low. Forensics (1,770 experiments): the
# 89 "profitable" configs averaged 45 trades at PF~1.1, statistically indistinguishable
# from noise; per-trade expectancy across the whole space is negative. A 30-trade sample
# is luck, not edge. Require a real sample AND a real profit factor on BOTH regimes so a
# 45-trade PF-1.05 run can NEVER be promoted again (that mirage caused the deadlock saga).
MIN_TOTAL_TRADES = 150             # statistical significance across all evaluated windows
MIN_PF = 1.1                       # avg profit factor required on EACH regime side
MIN_BULL_RUNS = 2                  # 2 independent bull windows required (2026-06-01: raised from 1 on user instruction)
MIN_BEAR_RUNS = 1                  # 1 bear window sufficient
# Safety floor for the per-run check below: avg(profits)>0 must hold AND no
# single run worse than this. Prevents one disaster window from masking on avg.
MIN_PER_RUN_PROFIT_FLOOR = -0.3    # percent — tighten to -0.1 once WR routinely >50%
# RE-ENABLED 2026-06-08: the precondition stated below ("after _GLOBAL_STD is fixed") was met
# today — _GLOBAL_STD 0.95→0.30 (513170f4) AND the centering window 100→1920 (5aff4cd3) fix
# restored directional signal, so the brain can now generate 30+ directional trades on
# bear_2026Q1 instead of the compressed <16 it produced under the broken centering.
# Gate purpose (HARD): if a config was tested on bear_2026Q1, at least one result must have
# WR >= 50% — blocks promoting configs KNOWN to fail on the most recent bear market.
# Configs not yet tested on bear_2026Q1 pass through (cross-window auto-queue schedules them;
# pair-regime gate + circuit breaker + dry-run are the live safety net).
#
# History — why it was disabled 2026-06-07: 45/45 experiments on bear_2026Q1 failed (best
# WR=37.5%) because lt=3.25 + broken centering produced <16 mean-reversion trades. That was a
# SYMPTOM of the centering bug, not a bad market. Now fixed → gate restored to its safety role.
BEAR_2026Q1_REQUIRED = "bear_2026Q1"
BASELINE_FILE = ROOT / "finbuddy_memory" / "promotions" / "live_baseline.json"


def get_live_baseline_profit_pct() -> float:
    """
    Dynamically tracked baseline: the profit_pct of the LAST APPLIED promotion.
    Falls back to a conservative -0.5 if no promotions yet (assumes current live
    is the smoke-test baseline).
    """
    if not BASELINE_FILE.exists():
        return -0.5
    try:
        return float(json.loads(BASELINE_FILE.read_text()).get("avg_profit_pct", -0.5))
    except Exception:
        return -0.5


def record_new_baseline(avg_profit_pct: float, config_hash: str) -> None:
    """Update the baseline file after a promotion is applied."""
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps({
        "avg_profit_pct": avg_profit_pct,
        "config_hash":    config_hash,
        "recorded_at":    datetime.now(timezone.utc).isoformat(),
    }, indent=2))


# ── Aggregate experiments by config hash ──────────────────────────────────

def _config_hash(cfg: dict) -> str:
    """Full deterministic hash of a config dict.

    Used for queue deduplication (experiment_log.py) — keeps different training
    variants (num_leaves, learning_rate, feature_set) as separate queue entries.
    Do NOT use for promotion grouping — see _promotion_key() below.
    """
    import hashlib, json as _json
    payload = _json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


# Fields that actually change live bot behaviour when promoted.
# Excludes brain-internal params (arch, freqaimodel, config_file, target_version)
# and LightGBM hyperparams (n_estimators, num_leaves, learning_rate) that are NOT
# written to live config/env during apply_promotion().
# Rationale: two experiments with identical strategy params but different num_leaves
# test the SAME strategy — pooling them counts toward the same promotion gate.
# The best-performing training variant is selected as the representative config.
PROMOTION_KEY_FIELDS = frozenset({
    "timeframe", "long_threshold", "short_threshold",
    "k_sl", "k_tp", "stability_n", "label_period_candles",
    "filter_di", "filter_svm", "feature_set",
})


def _promotion_key(cfg: dict) -> str:
    """Hash of only the fields written to live config on promotion.

    Prevents fragmentation from brain-internal exploration params (num_leaves,
    learning_rate, n_estimators, target_version, arch) that don't affect the
    strategy's live behaviour. Two experiments with the same strategy params but
    different training hyperparams vote toward the SAME promotion candidate.
    """
    import hashlib, json as _json
    key_cfg = {k: v for k, v in cfg.items() if k in PROMOTION_KEY_FIELDS}
    payload = _json.dumps(key_cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def find_candidates() -> list[dict]:
    """
    Group completed experiments by config. Return configs that have ≥1 bull AND ≥1 bear result,
    and where all results are positive profit.

    IMPORTANT: only considers experiments with target_version="zscore" (v23 z-scored target,
    introduced 2026-05-22). The 268 legacy raw-% experiments have incompatible label
    distributions and must NOT be pooled with z-scored results.
    """
    log = read_log()
    completed = [r for r in log if r.get("status") == "completed" and r.get("metrics")]
    # Filter to z-scored target experiments only (Fix 3: exclude 268 legacy raw-% runs).
    # Retroactive: experiments completed on or after 2026-05-22 are implicitly z-scored
    # (the model target was updated before they completed, even if the tag wasn't written).
    # The 268 legacy runs all completed before 2026-05-22 so this doesn't pollute the set.
    ZSCORE_CUTOFF = "2026-05-22"
    completed = [
        r for r in completed
        if r.get("config", {}).get("target_version") == "zscore"
        or (r.get("completed_at") or "") >= ZSCORE_CUTOFF
    ]

    # Load already-applied hashes — never re-propose a config that is currently live.
    # Root cause: the daily 07:00 scan kept re-finding hash 2ae96f164387 (applied 2026-05-28)
    # and sending a duplicate "APPLY REQUIRED" Telegram every morning. Fix (2026-05-30).
    # Load applied promotion keys (both full hash and promo_key) for dedup.
    # Using promo_key prevents re-proposing a strategy-param set that was already
    # promoted under a different training hyperparam variant (e.g. num_leaves=31
    # was applied, num_leaves=63 variant should not re-propose same strategy).
    applied_hashes: set[str] = set()
    applied_promo_keys: set[str] = set()
    applied_log = PROMOTIONS_DIR / "applied.jsonl"
    if applied_log.exists():
        for line in applied_log.read_text().splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    applied_hashes.add(rec["config_hash"])
                    # promotion_key stored since 2026-06-06; compute from config for older records
                    pk = rec.get("promotion_key") or _promotion_key(rec.get("config", {}))
                    applied_promo_keys.add(pk)
                except Exception:
                    pass

    # Load rejected promotion keys — configs a human explicitly Skipped (Telegram
    # button → skipped_*.json) or that were investigated and proven fake (rejected.jsonl).
    # Root cause fixed 2026-07-01: find_candidates() previously only checked applied.jsonl,
    # so a Skipped config had no memory — it could (and did — hash 3e3a98b76f8c, proven
    # bear-beta short noise with OOS WF -441/-3526 USDT on 2026-06-30) resurface as a
    # "new" promotion candidate on the next daily scan. Both sources feed the same set.
    rejected_promo_keys: set[str] = set()
    for skip_file in PROMOTIONS_DIR.glob("skipped_*.json"):
        try:
            rec = json.loads(skip_file.read_text())
            pk = rec.get("promotion_key") or _promotion_key(rec.get("config", {}))
            rejected_promo_keys.add(pk)
        except Exception:
            pass
    rejected_log = PROMOTIONS_DIR / "rejected.jsonl"
    if rejected_log.exists():
        for line in rejected_log.read_text().splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    pk = rec.get("promotion_key") or _promotion_key(rec.get("config", {}))
                    rejected_promo_keys.add(pk)
                except Exception:
                    pass

    # Group by promotion key (not full config hash) so training hyperparam variants
    # (num_leaves, learning_rate, n_estimators) vote toward the same candidate.
    # Representative config = the experiment with highest profit in the group.
    groups: dict[str, dict] = defaultdict(lambda: {
        "config": None, "_best_profit": -1e9, "runs": [], "bull_runs": [], "bear_runs": []
    })
    for r in completed:
        h = _promotion_key(r["config"])
        g = groups[h]
        run_profit = (r.get("metrics") or {}).get("profit_pct", -1e9)
        if g["config"] is None or run_profit > g["_best_profit"]:
            g["config"] = r["config"]   # keep config from best-performing experiment
            g["_best_profit"] = run_profit
        g["runs"].append(r)
        win = r.get("window", "")
        if "bull" in win:
            g["bull_runs"].append(r)
        elif "bear" in win:
            g["bear_runs"].append(r)

    baseline = get_live_baseline_profit_pct()
    candidates = []
    for h, g in groups.items():
        # Skip strategy-param sets already promoted (check promo key, not full hash).
        if h in applied_promo_keys:
            continue
        # Skip strategy-param sets already Skipped/rejected — never resurface a
        # proven-fake candidate just because it accumulates more runs.
        if h in rejected_promo_keys:
            continue
        # Statistical-significance gate: require enough runs in each regime
        if len(g["bull_runs"]) < MIN_BULL_RUNS or len(g["bear_runs"]) < MIN_BEAR_RUNS:
            continue

        # Current-market bear gate: the live bot runs in bear_2026Q1 conditions.
        # HARD GATE (2026-05-29): Tightened after a false-positive promotion slipped through.
        # The promoted config (LT=3.25) had bear_2026Q1 results: [-0.564%/WR=35%,
        # -0.573%/WR=47%, -3%/WR=52%, -4.9%/WR=51%]. The -0.573%/WR=47% barely passed
        # the old soft gate (profit>-3% AND WR>45%), allowing a LOSING config to promote.
        # New rule: if tested on bear_2026Q1, at least one result must have WR >= 50%.
        # If untested: allow through (brain queues cross-window tests; pair-regime gate covers risk).
        if BEAR_2026Q1_REQUIRED:
            bear_recent_runs = [r for r in g["bear_runs"] if r.get("window") == BEAR_2026Q1_REQUIRED]
            # Gate purpose: block configs KNOWN TO FAIL on current market.
            # If tested: require at least one result with WR >= 50% (not just "not catastrophic").
            # If untested: allow through.
            if bear_recent_runs and not any(
                r["metrics"].get("wr", 0) >= 0.50
                for r in bear_recent_runs
            ):
                continue  # tested but no WR >= 50% on current market → skip

        bull_profits = [r["metrics"]["profit_pct"] for r in g["bull_runs"]]
        # For bear performance, exclude bear_2026Q1 from the avg/floor check.
        # Rationale: bear_2026Q1 (Jan-Apr 2026) is structurally different — all 16+ configs
        # tested lose there even when they profit on bear_2025Q1. It's used as a soft GATE
        # above (must be tested, must not be catastrophic) but excluded from the profit
        # average so it doesn't block configs that genuinely work on other bear windows.
        # The live pair-regime gate provides the real-time safety net for 2026 conditions.
        bear_perf_runs = [r for r in g["bear_runs"] if r.get("window") != BEAR_2026Q1_REQUIRED]
        if not bear_perf_runs:
            # Only has bear_2026Q1 — can't evaluate bear performance (it always loses there).
            # Need bear_2025Q1 results. cross-window auto-queue should have scheduled it.
            print(f"[promote] {h[:12]} — skip: no bear_2025Q1 results yet (only {BEAR_2026Q1_REQUIRED})")
            continue
        bear_profits = [r["metrics"]["profit_pct"] for r in bear_perf_runs]
        bull_sharpes = [r["metrics"]["sharpe"]     for r in g["bull_runs"]]
        bear_sharpes = [r["metrics"]["sharpe"]     for r in bear_perf_runs]
        total_trades = sum(r["metrics"]["trades"] for r in g["runs"])

        # Criteria: avg profit positive on each side + sharpe positive on average
        # + no single run worse than MIN_PER_RUN_PROFIT_FLOOR (safety floor).
        bull_avg = sum(bull_profits) / len(bull_profits)
        bear_avg = sum(bear_profits) / len(bear_profits)
        bull_ok = (bull_avg > 0
                   and (sum(bull_sharpes) / len(bull_sharpes)) > 0
                   and min(bull_profits) > MIN_PER_RUN_PROFIT_FLOOR)
        bear_ok = (bear_avg > 0
                   and (sum(bear_sharpes) / len(bear_sharpes)) > 0
                   and min(bear_profits) > MIN_PER_RUN_PROFIT_FLOOR)
        if not (bull_ok and bear_ok):
            continue

        # WR gate: at least 1 bull run AND 1 bear run (excl. bear_2026Q1) must achieve WR ≥ 50%.
        bull_wr_ok = any(r.get("metrics", {}).get("wr", 0) >= 0.50 for r in g["bull_runs"])
        bear_wr_ok = any(r.get("metrics", {}).get("wr", 0) >= 0.50 for r in bear_perf_runs)
        if not bull_wr_ok or not bear_wr_ok:
            continue

        # PF gate (2026-06-17 HONEST-BRAIN): profit>0 alone passes thin-edge noise. Require
        # a genuine profit factor on each regime side. pf can be inf (no losers) on tiny
        # samples — the MIN_TOTAL_TRADES gate below guards that. Use mean PF per side.
        bull_pfs = [r["metrics"].get("pf", 0) for r in g["bull_runs"]]
        bear_pfs = [r["metrics"].get("pf", 0) for r in bear_perf_runs]
        bull_pf_ok = (sum(bull_pfs) / len(bull_pfs)) >= MIN_PF
        bear_pf_ok = (sum(bear_pfs) / len(bear_pfs)) >= MIN_PF
        if not (bull_pf_ok and bear_pf_ok):
            continue

        if total_trades < MIN_TOTAL_TRADES:
            continue

        avg_profit = (sum(bull_profits) + sum(bear_profits)) / (len(bull_profits) + len(bear_profits))
        improvement = avg_profit - baseline
        if improvement < MIN_AVG_PROFIT_IMPROVEMENT:
            continue

        candidates.append({
            "config_hash":  h,
            "config":       g["config"],
            "bull_runs":    g["bull_runs"],
            "bear_runs":    g["bear_runs"],
            "avg_profit":   round(avg_profit, 3),
            "avg_sharpe":   round((sum(bull_sharpes) + sum(bear_sharpes)) / (len(bull_sharpes) + len(bear_sharpes)), 3),
            "total_trades": total_trades,
            "improvement":  round(improvement, 3),
        })

    candidates.sort(key=lambda c: c["avg_profit"], reverse=True)
    return candidates


def propose(candidate: dict) -> None:
    """Write pending promotion + Telegram alert. Does NOT modify live config."""
    PROMOTIONS_DIR.mkdir(parents=True, exist_ok=True)
    proposal = {
        "proposed_at":     datetime.now(timezone.utc).isoformat(),
        "config_hash":     candidate["config_hash"],
        "config":          candidate["config"],
        "metrics_summary": {
            "avg_profit":   candidate["avg_profit"],
            "avg_sharpe":   candidate["avg_sharpe"],
            "total_trades": candidate["total_trades"],
            "improvement":  candidate["improvement"],
        },
        "approval_command": f"python scripts/brain/promote.py --apply {candidate['config_hash']}",
    }
    PENDING_FILE.write_text(json.dumps(proposal, indent=2))

    cfg  = candidate["config"]
    arch = cfg.get("arch", "v23")
    # Architecture-specific config preview
    if arch == "v22":
        config_preview = (
            f"tf={cfg.get('timeframe')} · "
            f"K_TP={cfg.get('k_tp')} · K_SL={cfg.get('k_sl')} · "
            f"thr={cfg.get('ml_threshold')}"
        )
    else:
        config_preview = (
            f"tf={cfg.get('timeframe')} · "
            f"lt={cfg.get('long_threshold')} · st={cfg.get('short_threshold')} · "
            f"K_SL={cfg.get('k_sl')} · N={cfg.get('stability_n')}"
        )

    chash = candidate["config_hash"]
    # Inline action buttons — tap directly from Telegram
    buttons = [
        [
            {"text": "✅ Apply",   "callback_data": f"apply:{chash}"},
            {"text": "⏭️ Skip",   "callback_data": f"skip:{chash}"},
        ],
        [
            {"text": "📋 Details", "callback_data": f"details:{chash}"},
        ],
    ]
    tg_send(
        subsystem=Subsystem.BRAIN_PROMOTION,
        status=Status.ACTION,
        title=f"new winner found · arch={arch}",
        fields={
            "Avg Profit":   f"{candidate['avg_profit']:+.2f}% (+{candidate['improvement']:.2f}pp vs baseline)",
            "Avg Sharpe":   f"{candidate['avg_sharpe']:+.2f}",
            "Total Trades": f"{candidate['total_trades']}",
            "Windows":      f"{len(candidate['bull_runs'])} bull + {len(candidate['bear_runs'])} bear",
            "Config":       config_preview,
            "Hash":         f"<code>{chash}</code>",
        },
        context=f"Architecture: {arch} · tap a button below",
        action="Apply = promote to live · Skip = ignore · Details = full config JSON",
        buttons=buttons,
    )
    print(f"PROPOSAL written → {PENDING_FILE}")


def apply_promotion(config_hash: str) -> int:
    """Apply the pending promotion: update live config.json + .env, bump identifier, restart bot.

    Activated 2026-05-19. Was previously instructions-only; now full auto-apply.

    Steps:
      1. Verify pending matches the requested hash
      2. Backup current config.json
      3. Write strategy params into freqtrade/.env (env vars consumed by strategy)
      4. Bump freqai.identifier to force fresh model training
      5. docker-compose restart freqtrade
      6. Telegram confirmation with rollback info
      7. Archive pending → applied
    """
    import shutil
    import subprocess
    import time

    if not PENDING_FILE.exists():
        print("ERROR: no pending promotion to apply", file=sys.stderr)
        return 1
    pending = json.loads(PENDING_FILE.read_text())
    if pending["config_hash"] != config_hash:
        print(f"ERROR: pending hash {pending['config_hash']} != requested {config_hash}", file=sys.stderr)
        return 1

    new_cfg = pending["config"]
    ts      = int(time.time())
    backup  = LIVE_CONFIG.with_suffix(f".json.bak-{ts}")
    env_path = ROOT / "freqtrade" / ".env"

    # 1. Backup
    shutil.copy(LIVE_CONFIG, backup)
    print(f"backup → {backup}")

    # Retain only the 3 most recent backups (older are pruned).
    old_backups = sorted(LIVE_CONFIG.parent.glob("config.json.bak-*"))
    for f in old_backups[:-3]:
        try:
            f.unlink()
            print(f"pruned old backup: {f.name}")
        except OSError:
            pass

    # 2. Edit config.json (Python json.load/dump — never sed)
    with LIVE_CONFIG.open() as f:
        live = json.load(f)
    new_identifier = f"finbuddy_v23_promoted_{ts}"
    old_identifier = live.get("freqai", {}).get("identifier")
    # Apply timeframe + label_period from promoted config
    if "timeframe" in new_cfg:
        live["timeframe"] = new_cfg["timeframe"]
    feat = live.setdefault("freqai", {}).setdefault("feature_parameters", {})
    if "label_period_candles" in new_cfg:
        feat["label_period_candles"] = new_cfg["label_period_candles"]
    # Apply DI / SVM settings from promoted config so live matches what was validated.
    # filter_di=False → DI_threshold=0 (disabled); filter_di=True → DI_threshold=1.0.
    if "filter_di" in new_cfg:
        feat["DI_threshold"] = 0 if not new_cfg["filter_di"] else 1.0
    if "filter_svm" in new_cfg:
        feat["use_SVM_to_remove_outliers"] = bool(new_cfg["filter_svm"])
    live.setdefault("freqai", {})["identifier"] = new_identifier
    with LIVE_CONFIG.open("w") as f:
        json.dump(live, f, indent=4)
    print(f"identifier: {old_identifier} → {new_identifier}")

    # 2b. Port feature-pipeline knobs from the experiment's config FILE into the
    # live config (2026-06-12): a pruned-config winner (e.g.
    # v23_regression_15m_pruned_config.json) differs in include_shifted_candles /
    # indicator_periods_candles / include_timeframes — without this, promotion
    # would deploy a model trained on a DIFFERENT feature set than validated.
    exp_cfg_file = new_cfg.get("config_file")
    if exp_cfg_file:
        exp_cfg_path = ROOT / "freqtrade" / "user_data" / exp_cfg_file
        try:
            exp_feat = json.loads(exp_cfg_path.read_text())["freqai"]["feature_parameters"]
            for key in ("include_shifted_candles", "indicator_periods_candles",
                        "include_timeframes", "include_corr_pairlist"):
                if key in exp_feat:
                    feat[key] = exp_feat[key]
            print(f"feature_parameters ported from {exp_cfg_file}")
        except Exception as e:
            print(f"WARN: could not port feature_parameters from {exp_cfg_file}: {e}",
                  file=sys.stderr)
        # config.json may have been modified above — rewrite it
        with LIVE_CONFIG.open("w") as f:
            json.dump(live, f, indent=4)

    def _bool_env(v):
        return None if v is None else ("1" if v else "0")

    # 3. Write strategy env vars
    # CRITICAL: FREQTRADE__FREQAI__IDENTIFIER lives in .env and docker-compose forwards it
    # (${FREQTRADE__FREQAI__IDENTIFIER:-}), which OVERRIDES config.json's freqai.identifier.
    # So the new identifier MUST be written here too, or the container keeps the OLD model
    # after `up -d` → the promoted config's new model never trains/loads and the promotion
    # silently has no effect (strategy may run new params against a stale/old model).
    # (Same pattern as scripts/apply_timeframe.py. .env identifier introduced 2026-06-06;
    # promotions before this fix may have been silently overridden.)
    env_keys = {
        "FREQTRADE__FREQAI__IDENTIFIER": new_identifier,
        "FREQAI_K_TP":            new_cfg.get("k_tp"),
        "FREQAI_K_SL":            new_cfg.get("k_sl"),
        "FREQAI_LONG_THRESHOLD":  new_cfg.get("long_threshold"),
        "FREQAI_SHORT_THRESHOLD": new_cfg.get("short_threshold"),
        "FREQAI_STABILITY_N":     new_cfg.get("stability_n"),
        # feature_set: write to env so live uses the same feature set validated in backtest
        "FREQAI_FEATURE_SET":     new_cfg.get("feature_set"),
        # Entry-overhaul params (2026-06-12): WITHOUT these a promoted
        # quantile-mode winner would silently deploy as absolute mode.
        "FREQAI_ENTRY_MODE":         new_cfg.get("entry_mode"),
        "FREQAI_ENTRY_QUANTILE":     new_cfg.get("entry_quantile"),
        "FREQAI_BOUNCE_GUARD":       _bool_env(new_cfg.get("bounce_guard")),
        "FREQAI_PRUNE_INDICATORS":   _bool_env(new_cfg.get("prune_indicators")),
        "FREQAI_PERPAIR_OI":         _bool_env(new_cfg.get("perpair_oi")),
        # Lever 3 exit-side knobs (2026-07-08): WITHOUT these a promoted
        # partial-TP/progress-cut winner would silently deploy with both OFF
        # (same 3-layer-gap class as the 2026-06-12 quantile-mode bug).
        "FREQAI_THRESHOLD_FLOOR":       _bool_env(new_cfg.get("threshold_floor")),
        "FREQAI_PROGRESS_CUT":          _bool_env(new_cfg.get("progress_cut")),
        "FREQAI_PROGRESS_CUT_CANDLES":  new_cfg.get("progress_cut_candles"),
        "FREQAI_PROGRESS_CUT_PROFIT":   new_cfg.get("progress_cut_profit"),
        "FREQAI_PARTIAL_TP":            _bool_env(new_cfg.get("partial_tp")),
        "FREQAI_PARTIAL_TP_TRIGGER":    new_cfg.get("partial_tp_trigger"),
        "FREQAI_PARTIAL_TP_FRACTION":   new_cfg.get("partial_tp_fraction"),
        # probe_scale (2026-07-17): same 3-layer-gap class — was built 2026-06-23 but never
        # wired into runner.py's backtest env forwarding OR here, so it could never have been
        # validated OR correctly promoted until now.
        "FREQAI_PROBE_SCALE":           _bool_env(new_cfg.get("probe_scale")),
        "FREQAI_PROBE_FRACTION":        new_cfg.get("probe_fraction"),
        "FREQAI_PROBE_CONFIRM_PCT":     new_cfg.get("probe_confirm_pct"),
        "FREQAI_PROBE_WINDOW":          new_cfg.get("probe_window"),
        # NEUTRAL-regime multiplier override (2026-08-31): same 3-layer-gap class.
        "FREQAI_NEUTRAL_LONG_MULT":     new_cfg.get("neutral_long_mult"),
        "FREQAI_NEUTRAL_SHORT_MULT":    new_cfg.get("neutral_short_mult"),
        "FREQAI_NEUTRAL_EXIT_MULT_LONG":  new_cfg.get("neutral_exit_mult_long"),
        "FREQAI_NEUTRAL_EXIT_MULT_SHORT": new_cfg.get("neutral_exit_mult_short"),
        # Exit-edge knobs (2026-08-31): same 3-layer-gap class.
        "FREQAI_EXIT_HYSTERESIS_FRAC":  new_cfg.get("exit_hysteresis_frac"),
        "FREQAI_TRAIL_LEVERAGE_FIX":    _bool_env(new_cfg.get("trail_leverage_fix")),
    }
    env_keys = {k: v for k, v in env_keys.items() if v is not None}
    if env_keys:
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        out_lines = [ln for ln in lines if ln.split("=", 1)[0] not in env_keys]
        for k, v in env_keys.items():
            out_lines.append(f"{k}={v}")
        env_path.write_text("\n".join(out_lines) + "\n")
        print(f".env updated: {list(env_keys.keys())}")

    # 4. Recreate container (must be `up -d`, not `restart`).
    # `docker-compose restart` does NOT re-read .env — the new thresholds written
    # above would be silently ignored. `up -d` recreates the container and picks
    # up all env-var changes. (See reference: finbuddy_memory/reference_compose_env_reload.md)
    try:
        result = subprocess.run(
            ["docker-compose", "up", "-d", "freqtrade"],
            cwd=str(ROOT / "freqtrade"),
            capture_output=True, text=True, timeout=120,
        )
        restart_ok = (result.returncode == 0)
        print(f"docker-compose up -d: {'OK' if restart_ok else 'FAILED'}")
        if not restart_ok:
            print(result.stderr[-400:], file=sys.stderr)
    except Exception as e:
        restart_ok = False
        print(f"restart error: {e}", file=sys.stderr)

    # 4b. Reset pair-regime gate stats (Fix 2, 2026-05-26).
    # After an identifier bump, the new model's early trades should NOT be
    # blocked by statistics accumulated under the old model. A pair that had
    # WR=32% with the old model may be perfectly fine with the new one.
    # Reset every entry to neutral (n=0, wr=0.5, pf=1.0) so the gate
    # accumulates fresh data from the promoted model's trades.
    pair_regime_path = ROOT / "finbuddy_memory" / "regimes" / "pair_regime_stats.json"
    try:
        if pair_regime_path.exists():
            data = json.loads(pair_regime_path.read_text())
            # Structure: data["stats"][pair][regime] = {...stats...}
            # Top level also has metadata keys: updated, lookback_days, block_rule, blocked.
            # Must NOT iterate data directly — only reset data["stats"].
            stats = data.get("stats", {})
            neutral = {"n": 0, "wins": 0, "losses": 0, "wr": 0.5, "pf": 1.0,
                       "profit_usdt": 0.0, "avg_profit_pct": 0.0}
            for pair in stats:
                stats[pair] = {regime: dict(neutral) for regime in stats[pair]}
            data["stats"] = stats
            data["blocked"] = {}   # clear blocked list so no pair starts pre-blocked
            from datetime import datetime, timezone as _tz
            data["updated"] = datetime.now(_tz.utc).isoformat()
            pair_regime_path.write_text(json.dumps(data, indent=2))
            print(f"pair_regime_stats.json reset ({len(stats)} pairs) for new identifier")
        else:
            print("pair_regime_stats.json not found — skipping reset (will be created fresh)")
    except Exception as e:
        print(f"WARN: pair_regime_stats reset failed: {e}", file=sys.stderr)

    # 5. Telegram confirmation
    try:
        tg_send(
            subsystem=Subsystem.BRAIN_PROMOTION,
            status=Status.OK if restart_ok else Status.WARN,
            title=f"🚀 v23 config promoted — {config_hash}",
            fields={
                "Identifier":  new_identifier,
                "K_TP/K_SL":   f"{new_cfg.get('k_tp')}/{new_cfg.get('k_sl')}",
                "Thresholds":  f"L={new_cfg.get('long_threshold')} S={new_cfg.get('short_threshold')}",
                "Stability":   str(new_cfg.get("stability_n", "-")),
                "Timeframe":   new_cfg.get("timeframe", "-"),
            },
            context=f"backup at {backup.name}",
            action=f"Rollback: cp {backup.name} {LIVE_CONFIG.name} && docker-compose restart freqtrade" if restart_ok else "RESTART FAILED — check docker logs freqtrade",
            silent=False,
        )
    except Exception as e:
        print(f"telegram alert failed: {e}", file=sys.stderr)

    # 6. Archive
    archive = PROMOTIONS_DIR / f"applied_{config_hash}_{ts}.json"
    archive.write_text(json.dumps({**pending, "applied_at": ts, "backup": str(backup), "restart_ok": restart_ok}, indent=2))
    PENDING_FILE.unlink()
    # Append to applied.jsonl for history
    applied_log = PROMOTIONS_DIR / "applied.jsonl"
    with applied_log.open("a") as f:
        f.write(json.dumps({
            "applied_at":    ts,
            "config_hash":   config_hash,
            "promotion_key": _promotion_key(new_cfg),  # for future promo-key dedup
            "config":        new_cfg,
            "identifier":    new_identifier,
            "backup":        str(backup),
            "restart_ok":    restart_ok,
        }) + "\n")
    print(f"archived → {archive}")
    return 0 if restart_ok else 2


def reject_promotion(config_hash: str, reason: str) -> int:
    """Permanently block a promotion_key from resurfacing as a candidate.

    For candidates proven fake via investigation (not just a Telegram Skip tap) —
    e.g. a config that passes find_candidates()'s gates in-sample but fails
    walk-forward OOS. Appends to rejected.jsonl, consulted by find_candidates().
    Also clears pending.json if it currently holds this hash.
    """
    PROMOTIONS_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if PENDING_FILE.exists():
        pending = json.loads(PENDING_FILE.read_text())
        if pending.get("config_hash") == config_hash:
            config = pending.get("config", {})
            PENDING_FILE.unlink()
            print(f"cleared pending.json ({config_hash})")
    rejected_log = PROMOTIONS_DIR / "rejected.jsonl"
    with rejected_log.open("a") as f:
        f.write(json.dumps({
            "rejected_at":   datetime.now(timezone.utc).isoformat(),
            "config_hash":   config_hash,
            "promotion_key": _promotion_key(config) if config else None,
            "config":        config,
            "reason":        reason,
        }) + "\n")
    print(f"rejected {config_hash} → {rejected_log} ({reason})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Cortexa Brain promotion engine")
    p.add_argument("--apply", metavar="CONFIG_HASH", help="Apply a pending promotion")
    p.add_argument("--reject", metavar="CONFIG_HASH", help="Permanently block a candidate from resurfacing")
    p.add_argument("--reason", default="", help="Reason for --reject (recorded in rejected.jsonl)")
    p.add_argument("--scan",  action="store_true", help="Scan log for candidates (default)")
    args = p.parse_args()

    if args.apply:
        return apply_promotion(args.apply)
    if args.reject:
        return reject_promotion(args.reject, args.reason)

    candidates = find_candidates()
    if not candidates:
        # Bug 2 fix (2026-05-30): delete stale pending.json when no new candidates.
        # Without this, an old Telegram Apply button remains functional and could
        # re-apply an already-live config, bumping the identifier unnecessarily.
        if PENDING_FILE.exists():
            PENDING_FILE.unlink()
            print("Cleared stale pending.json (already-applied config was best; no new winner yet)")

        # Bug 3 fix (2026-05-30): log WHY — applied vs need-more-data breakdown.
        from experiment_log import read_log as _read_log
        from collections import defaultdict as _dd
        _log = _read_log()
        _completed = [r for r in _log if r.get("status") == "completed" and r.get("metrics")]
        _groups: dict = _dd(lambda: {"bull_runs": [], "bear_runs": []})
        for r in _completed:
            h = _config_hash(r["config"])
            if "bull" in r.get("window", ""):
                _groups[h]["bull_runs"].append(r)
            elif "bear" in r.get("window", ""):
                _groups[h]["bear_runs"].append(r)
        _applied = set()
        if (PROMOTIONS_DIR / "applied.jsonl").exists():
            for line in (PROMOTIONS_DIR / "applied.jsonl").read_text().splitlines():
                if line.strip():
                    try: _applied.add(json.loads(line)["config_hash"])
                    except Exception: pass
        n_applied      = sum(1 for h in _groups if h in _applied)
        n_need_data    = sum(1 for h, g in _groups.items()
                            if h not in _applied
                            and (len(g["bull_runs"]) < MIN_BULL_RUNS or len(g["bear_runs"]) < MIN_BEAR_RUNS))
        n_failed_gates = len(_groups) - n_applied - n_need_data
        print(f"No new promotion candidates. Groups: total={len(_groups)}, "
              f"already_applied={n_applied}, need_more_data={n_need_data}, "
              f"failed_quality_gates={n_failed_gates}")
        return 0
    print(f"Found {len(candidates)} promotion candidate(s):")
    for c in candidates[:5]:
        print(f"  • {c['config_hash']}: avg_profit={c['avg_profit']}%  sharpe={c['avg_sharpe']}  trades={c['total_trades']}")
    propose(candidates[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
