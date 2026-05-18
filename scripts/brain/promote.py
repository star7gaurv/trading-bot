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
from experiment_log import read_log

ROOT = Path("/home/ubuntu/var/www/html/trade")
LIVE_CONFIG = ROOT / "freqtrade" / "user_data" / "config.json"
PROMOTIONS_DIR = ROOT / "finbuddy_memory" / "promotions"
PENDING_FILE = PROMOTIONS_DIR / "pending.json"

# Improvement threshold over current baseline
MIN_AVG_PROFIT_IMPROVEMENT = 1.0   # percentage points
MIN_TOTAL_TRADES = 30
LIVE_BASELINE_PROFIT_PCT = -0.5    # current best-known (will be tracked over time)

TELEGRAM_TOKEN = "REDACTED-FREQTRADE__TELEGRAM__TOKEN"
TELEGRAM_CHAT  = "5622292536"


def _tg(msg: str) -> None:
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=8)
    except Exception:
        pass


# ── Aggregate experiments by config hash ──────────────────────────────────

def _config_hash(cfg: dict) -> str:
    """Deterministic hash of a config dict (for grouping bull/bear runs)."""
    import hashlib
    keys = sorted(cfg.keys())
    payload = "|".join(f"{k}={cfg[k]}" for k in keys)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def find_candidates() -> list[dict]:
    """
    Group completed experiments by config. Return configs that have ≥1 bull AND ≥1 bear result,
    and where all results are positive profit.
    """
    log = read_log()
    completed = [r for r in log if r.get("status") == "completed" and r.get("metrics")]

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

    candidates = []
    for h, g in groups.items():
        if not g["bull_runs"] or not g["bear_runs"]:
            continue
        bull_profits = [r["metrics"]["profit_pct"] for r in g["bull_runs"]]
        bear_profits = [r["metrics"]["profit_pct"] for r in g["bear_runs"]]
        bull_sharpes = [r["metrics"]["sharpe"]     for r in g["bull_runs"]]
        bear_sharpes = [r["metrics"]["sharpe"]     for r in g["bear_runs"]]
        total_trades = sum(r["metrics"]["trades"] for r in g["runs"])

        # Criteria: both windows profitable + sharpe positive on average
        bull_ok = min(bull_profits) > 0 and (sum(bull_sharpes) / len(bull_sharpes)) > 0
        bear_ok = min(bear_profits) > 0 and (sum(bear_sharpes) / len(bear_sharpes)) > 0
        if not (bull_ok and bear_ok):
            continue
        if total_trades < MIN_TOTAL_TRADES:
            continue

        avg_profit = (sum(bull_profits) + sum(bear_profits)) / (len(bull_profits) + len(bear_profits))
        improvement = avg_profit - LIVE_BASELINE_PROFIT_PCT
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

    _tg(
        f"🧠 <b>Brain Promotion Candidate</b>\n"
        f"Config hash: <code>{candidate['config_hash']}</code>\n"
        f"Avg profit: <b>{candidate['avg_profit']}%</b> (+{candidate['improvement']}pp vs baseline)\n"
        f"Avg Sharpe: {candidate['avg_sharpe']} | Trades: {candidate['total_trades']}\n"
        f"Bull windows: {len(candidate['bull_runs'])} | Bear windows: {len(candidate['bear_runs'])}\n\n"
        f"Config preview: tf={candidate['config'].get('timeframe')} "
        f"lt={candidate['config'].get('long_threshold')} "
        f"st={candidate['config'].get('short_threshold')} "
        f"ksl={candidate['config'].get('k_sl')} "
        f"N={candidate['config'].get('stability_n')}\n\n"
        f"To approve: <code>{proposal['approval_command']}</code>"
    )
    print(f"PROPOSAL written → {PENDING_FILE}")


def apply_promotion(config_hash: str) -> int:
    """Apply the pending promotion: update live config.json identifier + strategy params."""
    if not PENDING_FILE.exists():
        print("ERROR: no pending promotion to apply", file=sys.stderr)
        return 1
    pending = json.loads(PENDING_FILE.read_text())
    if pending["config_hash"] != config_hash:
        print(f"ERROR: pending hash {pending['config_hash']} != requested {config_hash}", file=sys.stderr)
        return 1

    # SAFETY: at this stage we only emit instructions. Actual config swap happens
    # only after human-readable diff confirmation by Gaurav. v1 keeps the live
    # bot completely untouched. Once trust is established, this method will
    # automate the JSON edit + identifier bump + bot restart.
    print("=" * 60)
    print(f"PROMOTION INSTRUCTIONS for {config_hash}:")
    print("=" * 60)
    print("v1 manual application (will automate after first 3 successful promotions):")
    print()
    print(json.dumps(pending["config"], indent=2))
    print()
    print(f"To apply manually:")
    print(f"  1. Update freqtrade/user_data/config.json to use these params")
    print(f"  2. Bump freqai.identifier to a fresh value")
    print(f"  3. docker-compose restart freqtrade")
    print()
    archive = PROMOTIONS_DIR / f"applied_{config_hash}_{int(datetime.now(timezone.utc).timestamp())}.json"
    archive.write_text(json.dumps(pending, indent=2))
    PENDING_FILE.unlink()
    print(f"Pending → archived at {archive}")
    return 0


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
