#!/usr/bin/env python3
"""
brain_cleanup.py — Reclaim disk space by purging old brain artifacts.

Cron: 0 4 * * *  (daily 4am, after most overnight backtests finish)

What it removes:
1. Brain FreqAI model dirs (brain_* and wf_*) older than --max-age-days (default 2)
   (brain_scout_* alone generates ~15–20 GB/week; must prune aggressively)
2. Backtest result zips older than --max-age-days (default 14)
3. Brain log files older than --max-age-days (default 14)

What it preserves:
- finbuddy_memory/experiments/log.jsonl    (full brain history, append-only)
- finbuddy_memory/experiments/queue.jsonl  (pending hypotheses)
- finbuddy_memory/promotions/             (proposal/apply history)
- backtest zips referenced in pending promotions
- live (non-brain) freqai models (sub-train-* dirs)

Safe to run — never touches the live FreqTrade container's active model.
Uses sudo rm -rf for dirs owned by Docker root (ubuntu has passwordless sudo).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
MODELS_DIR = ROOT / "freqtrade" / "user_data" / "models"
BACKTEST_RESULTS = ROOT / "freqtrade" / "user_data" / "backtest_results"
BRAIN_LOG_DIR = ROOT / "backtests"


def _top_k_protected_dirs(keep_k: int) -> set[str]:
    """Return the set of brain_<hash>_<ts>-prefixed dir names tied to top-K
    experiments by profit_pct. These are preserved indefinitely as analyzable
    history (user instruction 2026-05-19: keep what's useful, delete garbage).
    Returns set of directory names (not full paths)."""
    log_file = ROOT / "finbuddy_memory" / "experiments" / "log.jsonl"
    if not log_file.exists():
        return set()
    import json
    completed = []
    try:
        for line in log_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("status") == "completed" and r.get("metrics", {}).get("trades", 0) >= 20:
                completed.append(r)
    except Exception:
        return set()
    completed.sort(key=lambda r: r["metrics"].get("profit_pct", -1e9), reverse=True)
    protected = set()
    for r in completed[:keep_k]:
        hid = r.get("hypothesis_id", "")
        if hid:
            # model dirs are named like brain_<hash>_<ts>; match by hash prefix
            for d in MODELS_DIR.glob(f"brain_{hid}_*"):
                protected.add(d.name)
    return protected


def _rmtree_sudo(d: Path) -> None:
    """Remove a directory tree, falling back to sudo rm -rf for Docker-owned (root) files."""
    try:
        shutil.rmtree(d)
    except PermissionError:
        subprocess.run(["sudo", "rm", "-rf", str(d)], check=True)


def cleanup_brain_models(max_age_days: int, keep_top_k: int, dry_run: bool = False) -> tuple[int, int]:
    """Remove brain_* and wf_* model dirs older than threshold.

    Covers both brain experiment dirs (brain_<hash>_*, brain_scout_<hash>_*) and
    walk-forward experiment dirs (wf_*). Both are created by Docker containers running
    as root, so falls back to sudo rm -rf when shutil.rmtree is denied.
    Preserves top-K best-profit experiment models indefinitely.
    Returns (count, bytes_freed).
    """
    cutoff = time.time() - max_age_days * 86400
    protected = _top_k_protected_dirs(keep_top_k)
    if protected:
        print(f"  preserving top-{keep_top_k} model dirs (by profit_pct): {len(protected)} dirs protected")
    count = 0
    freed = 0
    # fam_* are the shared model-cache families (2026-06-12): kept on a longer
    # leash (14d floor) because many experiments reuse one dir. runner.py
    # touches a family dir on every use, so an active family never expires.
    fam_cutoff = time.time() - max(max_age_days, 14) * 86400
    patterns = ["brain_*", "wf_*", "fam_*", "wfam_*"]
    for pattern in patterns:
        for d in MODELS_DIR.glob(pattern):
            if not d.is_dir():
                continue
            if d.name in protected:
                continue
            try:
                mtime = d.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime > (fam_cutoff if pattern in ("fam_*", "wfam_*") else cutoff):
                continue
            size = _dir_size(d)
            if dry_run:
                print(f"  [DRY-RUN] would remove {d.name} ({size/1024/1024:.1f}MB)")
            else:
                try:
                    _rmtree_sudo(d)
                    count += 1
                    freed += size
                except Exception as e:
                    print(f"  WARN: failed to remove {d.name}: {e}", file=sys.stderr)
    return count, freed


def cleanup_backtest_zips(max_age_days: int, dry_run: bool = False) -> tuple[int, int]:
    """Remove old backtest result zips + .meta.json files."""
    cutoff = time.time() - max_age_days * 86400
    count = 0
    freed = 0
    # Keep .last_result.json — it's the live pointer
    for f in list(BACKTEST_RESULTS.glob("backtest-result-*.zip")) + \
             list(BACKTEST_RESULTS.glob("backtest-result-*.meta.json")):
        try:
            if f.stat().st_mtime > cutoff:
                continue
            size = f.stat().st_size
        except FileNotFoundError:
            continue
        if dry_run:
            print(f"  [DRY-RUN] would remove {f.name} ({size/1024:.1f}KB)")
        else:
            try:
                f.unlink()
                count += 1
                freed += size
            except Exception as e:
                print(f"  WARN: failed to remove {f.name}: {e}", file=sys.stderr)
    return count, freed


def cleanup_brain_logs(max_age_days: int, dry_run: bool = False) -> tuple[int, int]:
    """Remove per-experiment brain log files (kept in backtests/brain_*.log)."""
    cutoff = time.time() - max_age_days * 86400
    count = 0
    freed = 0
    for f in BRAIN_LOG_DIR.glob("brain_*.log"):
        try:
            if f.stat().st_mtime > cutoff:
                continue
            size = f.stat().st_size
        except FileNotFoundError:
            continue
        if dry_run:
            print(f"  [DRY-RUN] would remove {f.name} ({size/1024:.1f}KB)")
        else:
            try:
                f.unlink()
                count += 1
                freed += size
            except Exception:
                pass
    return count, freed


def _dir_size(p: Path) -> int:
    total = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except FileNotFoundError:
                    pass
    except Exception:
        pass
    return total


def disk_usage_pct() -> int:
    """Return % used on root filesystem."""
    try:
        usage = shutil.disk_usage("/")
        return int((usage.used / usage.total) * 100)
    except Exception:
        return -1


def main() -> int:
    p = argparse.ArgumentParser(description="FinBuddy brain disk cleanup")
    p.add_argument("--max-age-days",     type=int, default=2,  help="brain/wf model dir age threshold (default 2 days — brain_scout alone generates ~15GB/week)")
    p.add_argument("--zip-max-age-days", type=int, default=14, help="backtest zip age threshold")
    p.add_argument("--log-max-age-days", type=int, default=14, help="brain log age threshold")
    p.add_argument("--keep-top-k",       type=int, default=10, help="preserve top-K best-profit model dirs indefinitely (analyzable history)")
    p.add_argument("--dry-run",          action="store_true",  help="print what would be deleted, don't delete")
    args = p.parse_args()

    before_pct = disk_usage_pct()
    print(f"== brain_cleanup ==  disk: {before_pct}%")

    print(f"Brain models  (older than {args.max_age_days}d, keeping top-{args.keep_top_k} best):")
    n1, f1 = cleanup_brain_models(args.max_age_days, args.keep_top_k, args.dry_run)
    print(f"  removed {n1} dirs / {f1/1024/1024:.1f}MB")

    print(f"Backtest zips (older than {args.zip_max_age_days}d):")
    n2, f2 = cleanup_backtest_zips(args.zip_max_age_days, args.dry_run)
    print(f"  removed {n2} files / {f2/1024/1024:.1f}MB")

    print(f"Brain logs    (older than {args.log_max_age_days}d):")
    n3, f3 = cleanup_brain_logs(args.log_max_age_days, args.dry_run)
    print(f"  removed {n3} files / {f3/1024/1024:.1f}MB")

    after_pct = disk_usage_pct()
    total_mb = (f1 + f2 + f3) / 1024 / 1024
    print(f"== done ==  disk: {after_pct}%  freed: {total_mb:.1f}MB")

    # Telegram alert if disk still > 80%
    if after_pct >= 80:
        sys.path.insert(0, str(ROOT / "scripts" / "lib"))
        from telegram_template import send, Subsystem, Status
        send(
            subsystem=Subsystem.WATCHDOG,
            status=Status.WARN,
            title=f"disk still {after_pct}% after cleanup",
            fields={
                "Before": f"{before_pct}%",
                "After":  f"{after_pct}%",
                "Freed":  f"{total_mb:.1f}MB",
            },
            context="brain_cleanup couldn't bring usage under 80% — investigate manually",
            action="<code>du -sh /home/ubuntu/var/www/html/trade/* | sort -h</code>",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
