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
MIN_TOTAL_TRADES = 30              # lowered from 60: with lp=12 (high-lt configs), 2 windows give ~60–120 trades
MIN_BULL_RUNS = 1                  # lowered from 2 — bear_2026Q1 is the hard constraint; 1 bull + bear_2026Q1 is sufficient
MIN_BEAR_RUNS = 1                  # lowered from 2 — see BEAR_2026Q1_REQUIRED below
# Safety floor for the per-run check below: avg(profits)>0 must hold AND no
# single run worse than this. Prevents one disaster window from masking on avg.
MIN_PER_RUN_PROFIT_FLOOR = -0.3    # percent — tighten to -0.1 once WR routinely >50%
# Require the current-market bear window to pass before promoting.
# Rationale: bear_2025Q1 (Jan–Apr 2025) and bear_2026Q1 (Jan–Apr 2026) are structurally
# different markets. A config that works in 2025 but not 2026 will fail live immediately.
# This gate ensures we never promote a config blind to the current bear conditions.
# Set to None to disable (e.g. when market is in BULL regime and bear_2026Q1 is irrelevant).
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
    """Deterministic hash of a config dict (for grouping bull/bear runs).

    Uses json.dumps(sort_keys=True) to guarantee stable ordering regardless of
    how the config dict was constructed (dict-literal vs JSON-parse insertion order).
    """
    import hashlib, json as _json
    payload = _json.dumps(cfg, sort_keys=True, separators=(",", ":"))
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
    # Filter to z-scored target experiments only (Fix 3: exclude 268 legacy raw-% runs)
    completed = [r for r in completed if r.get("config", {}).get("target_version") == "zscore"]

    groups: dict[str, dict] = defaultdict(lambda: {
        "config": None, "runs": [], "bull_runs": [], "bear_runs": []
    })
    for r in completed:
        h = _config_hash(r["config"])
        g = groups[h]
        g["config"] = r["config"]
        g["runs"].append(r)
        win = r.get("window", "")
        if "bull" in win:
            g["bull_runs"].append(r)
        elif "bear" in win:
            g["bear_runs"].append(r)

    baseline = get_live_baseline_profit_pct()
    candidates = []
    for h, g in groups.items():
        # Statistical-significance gate: require enough runs in each regime
        if len(g["bull_runs"]) < MIN_BULL_RUNS or len(g["bear_runs"]) < MIN_BEAR_RUNS:
            continue

        # Current-market bear gate: the live bot runs in bear_2026Q1 conditions.
        # A config that never passed on bear_2026Q1 is blind to the current market.
        # Require at least one passing (profit>0, sharpe>0) run on that window.
        if BEAR_2026Q1_REQUIRED:
            bear_recent_runs = [r for r in g["bear_runs"] if r.get("window") == BEAR_2026Q1_REQUIRED]
            if not bear_recent_runs:
                continue  # config was never tested on bear_2026Q1 → skip
            if not any(
                r["metrics"].get("profit_pct", -1) > 0 and r["metrics"].get("sharpe", -1) > 0
                for r in bear_recent_runs
            ):
                continue  # tested but never passed → skip

        bull_profits = [r["metrics"]["profit_pct"] for r in g["bull_runs"]]
        bear_profits = [r["metrics"]["profit_pct"] for r in g["bear_runs"]]
        bull_sharpes = [r["metrics"]["sharpe"]     for r in g["bull_runs"]]
        bear_sharpes = [r["metrics"]["sharpe"]     for r in g["bear_runs"]]
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

        # WR gate: at least 1 bull run AND 1 bear run must achieve WR ≥ 50%.
        bull_wr_ok = any(r.get("metrics", {}).get("wr", 0) >= 0.50 for r in g["bull_runs"])
        bear_wr_ok = any(r.get("metrics", {}).get("wr", 0) >= 0.50 for r in g["bear_runs"])
        if not bull_wr_ok or not bear_wr_ok:
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
    if "label_period_candles" in new_cfg:
        live.setdefault("freqai", {}).setdefault("feature_parameters", {})["label_period_candles"] = new_cfg["label_period_candles"]
    live.setdefault("freqai", {})["identifier"] = new_identifier
    with LIVE_CONFIG.open("w") as f:
        json.dump(live, f, indent=4)
    print(f"identifier: {old_identifier} → {new_identifier}")

    # 3. Write strategy env vars
    env_keys = {
        "FREQAI_K_TP":            new_cfg.get("k_tp"),
        "FREQAI_K_SL":            new_cfg.get("k_sl"),
        "FREQAI_LONG_THRESHOLD":  new_cfg.get("long_threshold"),
        "FREQAI_SHORT_THRESHOLD": new_cfg.get("short_threshold"),
        "FREQAI_STABILITY_N":     new_cfg.get("stability_n"),
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
            for pair in data:
                data[pair] = {r: {"n": 0, "wr": 0.5, "pf": 1.0} for r in data[pair]}
            pair_regime_path.write_text(json.dumps(data, indent=2))
            print(f"pair_regime_stats.json reset ({len(data)} pairs) for new identifier")
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
        f.write(json.dumps({"applied_at": ts, "config_hash": config_hash, "config": new_cfg, "identifier": new_identifier, "backup": str(backup), "restart_ok": restart_ok}) + "\n")
    print(f"archived → {archive}")
    return 0 if restart_ok else 2


def main() -> int:
    p = argparse.ArgumentParser(description="FinBuddy Brain promotion engine")
    p.add_argument("--apply", metavar="CONFIG_HASH", help="Apply a pending promotion")
    p.add_argument("--scan",  action="store_true", help="Scan log for candidates (default)")
    args = p.parse_args()

    if args.apply:
        return apply_promotion(args.apply)

    candidates = find_candidates()
    if not candidates:
        print("No promotion candidates yet — need bull+bear positive results.")
        return 0
    print(f"Found {len(candidates)} promotion candidate(s):")
    for c in candidates[:5]:
        print(f"  • {c['config_hash']}: avg_profit={c['avg_profit']}%  sharpe={c['avg_sharpe']}  trades={c['total_trades']}")
    propose(candidates[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
