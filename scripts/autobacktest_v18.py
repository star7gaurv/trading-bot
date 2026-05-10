#!/usr/bin/env python3
"""
autobacktest_v18.py — FinBuddy v18 Campaign Grid Runner
=========================================================
Runs a 12-combo × 2-window backtest grid to find the optimal:
  - k_mult        (barrier multiplier + stoploss scale)
  - label_period  (triple-barrier resolution window, from config)
  - ml_threshold  (entry probability floor)

Key differences from v13/v14 campaigns:
  - Uses ENV VARs (FREQAI_K_MULT, FREQAI_ML_THRESHOLD) instead of regex patching
  - Writes a per-combo config overlay for label_period_candles
  - Both bull (20240101-20250101) and bear (20250101-20260401) windows
  - Correct 1h timeframe throughout (v17 bug: backtest_config had 15m)
  - BTC+ETH+SOL+XRP+DOGE (5 representative pairs; no BNB which is blacklisted)

Usage:
  cd /home/ubuntu/var/www/html/trade
  python scripts/autobacktest_v18.py [--dry-run] [--window bull|bear|both]

--dry-run: prints docker exec commands without running them
--window:  which time windows to run (default: both)

Results are written to _autobacktest_v18_results.csv and Telegram-notified.
"""

import argparse
import csv
import json
import logging
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from itertools import product
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT      = Path("/home/ubuntu/var/www/html/trade")
GRID_JSON      = REPO_ROOT / "scripts" / "autobacktest_v18_grid.json"
BASE_CONFIG    = "/freqtrade/user_data/backtest_config.json"  # inside container (user_data is mounted)
RESULTS_DIR    = REPO_ROOT / "freqtrade" / "user_data" / "backtest_results"
# Overlay configs go to user_data too (only mounted volume accessible inside container)
OVERLAY_HOST_DIR      = REPO_ROOT / "freqtrade" / "user_data"
OVERLAY_CONTAINER_DIR = "/freqtrade/user_data"
# docker-compose.yml is here; run docker-compose from this directory
COMPOSE_DIR = REPO_ROOT / "freqtrade"
OUTPUT_CSV     = REPO_ROOT / "_autobacktest_v18_results.csv"
CONTAINER      = "freqtrade"

# ── Telegram ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "REDACTED-FREQTRADE__TELEGRAM__TOKEN"
TELEGRAM_CHAT  = "5622292536"

def _tg(msg: str) -> None:
    """Fire-and-forget Telegram message."""
    try:
        import urllib.request, urllib.parse
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception as e:
        log.warning(f"[Telegram] send failed: {e}")

# ── Config overlay writer ──────────────────────────────────────────────────
def _write_overlay(label_period: int, identifier: str) -> tuple:
    """
    Write a minimal config overlay to user_data/ (the only mounted volume).
    Returns (host_path, container_path).
    """
    overlay = {
        "freqai": {
            "identifier": identifier,
            "feature_parameters": {
                "label_period_candles": label_period
            }
        }
    }
    filename   = f"_v18_overlay_{identifier}.json"
    host_path  = str(OVERLAY_HOST_DIR / filename)
    cont_path  = f"{OVERLAY_CONTAINER_DIR}/{filename}"
    with open(host_path, "w") as f:
        json.dump(overlay, f)
    return host_path, cont_path

# ── Data download ──────────────────────────────────────────────────────────
def download_data(pairs: list, windows: dict, dry_run: bool = False) -> bool:
    """
    Download all required historical data once before the grid starts.

    FreqAI needs train_period_days (90) of candles BEFORE the backtest window
    start date. We extend the earliest window start backward by 95 days (5 days
    buffer) to guarantee that warmup data exists.

    Uses docker-compose run --rm --no-deps (same as run_one) so the download
    runs in a clean isolated container — avoids conflicts with the live bot.
    """
    from datetime import datetime, timedelta

    all_timeranges = set(windows.values())

    # Earliest start and latest end across all selected windows
    starts = [w.split("-")[0] for w in all_timeranges]
    ends   = [w.split("-")[1] for w in all_timeranges]
    latest = max(ends)

    # Extend start backward by 95 days to cover train_period_days=90 warmup
    earliest_dt    = datetime.strptime(min(starts), "%Y%m%d")
    download_start = (earliest_dt - timedelta(days=95)).strftime("%Y%m%d")
    timerange      = f"{download_start}-{latest}"

    log.info(f"[download] Timerange: {timerange}  (windows: {min(starts)}–{latest}, "
             f"pre-period: {download_start}–{min(starts)})")
    log.info(f"[download] Pairs: {pairs}")

    # Use docker-compose run (NOT docker exec) — clean container, no conflicts
    cmd = [
        "docker-compose", "run", "--rm", "--no-deps",
        "freqtrade",
        "download-data",
        "--config", BASE_CONFIG,
        "--timerange", timerange,
        "--timeframes", "1h",
        "--trading-mode", "futures",
        "--pairs",
    ] + pairs

    log.info(f"[download] Command: {' '.join(cmd)}")
    if dry_run:
        log.info("[download] DRY RUN — skipping actual download")
        return True

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                            cwd=str(COMPOSE_DIR))
    out = (result.stdout + result.stderr)[-2000:]
    log.info(f"[download] exit={result.returncode}\n{out}")

    if result.returncode != 0:
        log.error(f"[download] FAILED — exit {result.returncode}")
        return False

    log.info("[download] Data download complete.")
    return True

# ── Result parser ──────────────────────────────────────────────────────────
def _find_latest_zip() -> Path | None:
    """Return the most recently modified backtest result ZIP."""
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-1] if zips else None

def _parse_result_zip(zip_path: Path) -> dict | None:
    """
    Extract key metrics from a FreqTrade backtest result ZIP.
    Returns dict with win_rate, sharpe, max_drawdown, profit_factor, trade_count.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            json_names = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_names:
                log.error(f"[parse] No JSON in {zip_path}")
                return None
            with zf.open(json_names[0]) as jf:
                data = json.load(jf)

        strategy_data = data.get("strategy", {})
        if not strategy_data:
            log.error(f"[parse] No 'strategy' key in backtest JSON")
            return None

        # FreqTrade stores per-strategy results
        strat_key = next(iter(strategy_data))
        s = strategy_data[strat_key]

        total_trades = s.get("total_trades", 0)
        if total_trades == 0:
            return {
                "win_rate": 0.0, "sharpe": 0.0, "max_drawdown": 100.0,
                "profit_factor": 0.0, "trade_count": 0
            }

        # winrate is reported directly (0.0–1.0); fall back to wins/total
        raw_wr = s.get("winrate", None)
        if raw_wr is not None:
            win_rate = round(float(raw_wr) * 100, 2)
        else:
            wins = s.get("wins", 0)
            win_rate = round((wins / total_trades * 100), 2) if total_trades > 0 else 0.0

        # Sharpe from summary (annualised)
        sharpe = s.get("sharpe", s.get("sharpe_ratio", 0.0)) or 0.0

        # Max drawdown — try account-level first (absolute %)
        dd_account = s.get("max_drawdown_account", 0.0) or 0.0
        max_dd = round(dd_account * 100, 2)

        # Profit factor — FreqTrade 2026 reports this directly in the summary.
        # Older approach (profit_sum / loss_sum) doesn't exist in this version.
        profit_factor = round(float(s.get("profit_factor", 0.0) or 0.0), 3)

        return {
            "win_rate":      round(win_rate, 2),
            "sharpe":        round(float(sharpe), 3),
            "max_drawdown":  max_dd,
            "profit_factor": profit_factor,
            "trade_count":   total_trades,
        }

    except Exception as e:
        log.error(f"[parse] Exception parsing {zip_path}: {e}")
        return None

def _grade(metrics: dict, criteria: dict) -> bool:
    """True if all 4 acceptance criteria pass."""
    return (
        metrics["win_rate"]      >= criteria["win_rate"]
        and metrics["sharpe"]    >= criteria["sharpe"]
        and metrics["max_drawdown"] <= criteria["max_drawdown"]
        and metrics["profit_factor"] >= criteria["profit_factor"]
    )

# ── Single backtest run ────────────────────────────────────────────────────
def run_one(
    k_mult: float,
    label_period: int,
    ml_threshold: float,
    window: str,
    timerange: str,
    dry_run: bool = False,
) -> dict | None:
    """Run one backtest combo. Returns parsed metrics dict or None on failure."""
    ts = int(time.time())
    identifier = f"v18_k{k_mult}_l{label_period}_m{ml_threshold}_{ts}"

    # Write label_period overlay (to user_data which is mounted in container)
    overlay_host, overlay_container = _write_overlay(label_period, identifier)

    log.info(
        f"\n{'='*60}\n"
        f"  k_mult={k_mult}  label_period={label_period}  ml_threshold={ml_threshold}  window={window}\n"
        f"  identifier: {identifier}\n"
        f"{'='*60}"
    )

    # Snapshot ZIP count before run
    before_zips = set(RESULTS_DIR.glob("backtest-result-*.zip")) if not dry_run else set()

    # Use `docker-compose run --rm` (fresh isolated container per run).
    # This matches the proven walk-forward approach and avoids conflicts with the
    # live bot running in the main container. `docker exec` on a live container
    # triggers a datasieve Pipeline.features_in AttributeError in FreqAI backtest.
    cmd = [
        "docker-compose", "run", "--rm", "--no-deps",
        # Pass ENV VARs for strategy configurable parameters
        "-e", f"FREQAI_K_MULT={k_mult}",
        "-e", f"FREQAI_ML_THRESHOLD={ml_threshold}",
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
        "freqtrade",
        "backtesting",
        "--config", BASE_CONFIG,
        "--config", overlay_container,
        "--strategy", "FinBuddyFreqAI",
        "--freqaimodel", "LightGBMClassifier",
        "--timerange", timerange,
        "--timeframe", "1h",
        "--export", "trades",
        "--cache", "none",
    ]

    log.info(f"[run] {' '.join(cmd)}")

    if dry_run:
        log.info("[run] DRY RUN — skipping execution")
        return {"win_rate": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "profit_factor": 0.0, "trade_count": 0, "_dry_run": True}

    t_start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                            cwd=str(COMPOSE_DIR))
    elapsed = int(time.time() - t_start)

    # Show last 60 lines of output
    out = (result.stdout + result.stderr)[-3000:]
    log.info(f"[run] exit={result.returncode}  elapsed={elapsed}s\n{out}")

    if result.returncode != 0:
        log.error(f"[run] FAILED (exit {result.returncode})")
        return None

    # Find new ZIP
    after_zips = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    new_zips = sorted(after_zips - before_zips, key=lambda p: p.stat().st_mtime)
    if not new_zips:
        log.error("[run] No new backtest ZIP produced")
        return None

    zip_path = new_zips[-1]
    log.info(f"[run] Result: {zip_path.name}")

    metrics = _parse_result_zip(zip_path)
    if metrics is None:
        log.error("[run] Parse failed")
        return None

    log.info(
        f"[result] WR={metrics['win_rate']}%  Sharpe={metrics['sharpe']}  "
        f"DD={metrics['max_drawdown']}%  PF={metrics['profit_factor']}  "
        f"Trades={metrics['trade_count']}"
    )

    # Cleanup overlay file
    try:
        os.remove(overlay_host)
    except Exception:
        pass

    return metrics

# ── Reparse ────────────────────────────────────────────────────────────────
def reparse_all(grid_cfg: dict) -> None:
    """
    Re-read all v18 backtest ZIPs, extract combo params from freqai_identifier,
    and regenerate _autobacktest_v18_results.csv with the fixed parser.
    Run this after the campaign completes to correct any parser bugs.
    """
    import re as _re
    criteria = grid_cfg["acceptance_criteria"]
    windows  = grid_cfg["windows"]

    fieldnames = [
        "run", "window", "k_mult", "label_period", "ml_threshold",
        "win_rate", "sharpe", "max_drawdown", "profit_factor",
        "trade_count", "pass", "wr_pass", "sharpe_pass", "dd_pass", "pf_pass",
        "timestamp"
    ]

    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    v18_zips = []
    for z in zips:
        # Quick check: only v18 results
        try:
            with zipfile.ZipFile(z) as zf:
                jn = [n for n in zf.namelist() if n.endswith(".json")][0]
                with zf.open(jn) as jf:
                    d = json.load(jf)
            sk = next(iter(d.get("strategy", {})))
            ident = d["strategy"][sk].get("freqai_identifier", "")
            if not ident.startswith("v18_"):
                continue
        except Exception:
            continue
        v18_zips.append((z, d))

    log.info(f"[reparse] Found {len(v18_zips)} v18 ZIPs")
    rows = []
    for z, d in v18_zips:
        sk  = next(iter(d["strategy"]))
        s   = d["strategy"][sk]
        ident = s.get("freqai_identifier", "")
        # Parse combo from identifier: v18_k{k}_l{l}_m{m}_{ts}
        m = _re.match(r"v18_k([\d.]+)_l(\d+)_m([\d.]+)_(\d+)", ident)
        if not m:
            log.warning(f"[reparse] Could not parse identifier: {ident}")
            continue
        k_mult        = float(m.group(1))
        label_period  = int(m.group(2))
        ml_threshold  = float(m.group(3))
        ts_val        = int(m.group(4))

        metrics = _parse_result_zip(z)
        if metrics is None:
            continue

        # Infer window from timerange
        tr = s.get("timerange", "")
        window_name = "bull" if tr.startswith("20240101") else "bear" if tr.startswith("20250101") else tr

        passed = _grade(metrics, criteria)
        rows.append({
            "run":            len(rows) + 1,
            "window":         window_name,
            "k_mult":         k_mult,
            "label_period":   label_period,
            "ml_threshold":   ml_threshold,
            "win_rate":       metrics["win_rate"],
            "sharpe":         metrics["sharpe"],
            "max_drawdown":   metrics["max_drawdown"],
            "profit_factor":  metrics["profit_factor"],
            "trade_count":    metrics["trade_count"],
            "pass":           passed,
            "wr_pass":        metrics["win_rate"]      >= criteria["win_rate"],
            "sharpe_pass":    metrics["sharpe"]        >= criteria["sharpe"],
            "dd_pass":        metrics["max_drawdown"]  <= criteria["max_drawdown"],
            "pf_pass":        metrics["profit_factor"] >= criteria["profit_factor"],
            "timestamp":      datetime.utcnow().isoformat(),
        })

    # Sort by window then combo
    rows.sort(key=lambda r: (r["window"], r["k_mult"], r["label_period"], r["ml_threshold"]))
    for i, r in enumerate(rows):
        r["run"] = i + 1

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    passes = [r for r in rows if r["pass"]]
    log.info(f"[reparse] {len(passes)}/{len(rows)} PASS — CSV rewritten: {OUTPUT_CSV}")
    for r in rows:
        status = "✅" if r["pass"] else "❌"
        log.info(
            f"  {status} [{r['window']}] k={r['k_mult']} l={r['label_period']} "
            f"m={r['ml_threshold']} → WR={r['win_rate']}% Sh={r['sharpe']} "
            f"DD={r['max_drawdown']}% PF={r['profit_factor']}"
        )


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="FinBuddy v18 backtest campaign")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running")
    parser.add_argument("--window", choices=["bull", "bear", "both"], default="both",
                        help="Which time window(s) to run")
    parser.add_argument("--no-download", action="store_true", help="Skip data download step")
    parser.add_argument("--reparse", action="store_true",
                        help="Re-read all v18 ZIPs and regenerate CSV (use after campaign completes)")
    args = parser.parse_args()

    # Load grid config
    with open(GRID_JSON) as f:
        grid_cfg = json.load(f)

    # Reparse mode — regenerate CSV from existing ZIPs with fixed parser
    if args.reparse:
        reparse_all(grid_cfg)
        return

    criteria    = grid_cfg["acceptance_criteria"]
    windows     = grid_cfg["windows"]
    pairs       = grid_cfg["pairs_download"]
    k_mults     = grid_cfg["grid"]["k_mult"]
    periods     = grid_cfg["grid"]["label_period_candles"]
    thresholds  = grid_cfg["grid"]["ml_threshold"]

    # Which windows to run
    if args.window == "bull":
        run_windows = {"bull": windows["bull"]}
    elif args.window == "bear":
        run_windows = {"bear": windows["bear"]}
    else:
        run_windows = windows

    combos = list(product(k_mults, periods, thresholds))
    n_total = len(combos) * len(run_windows)

    log.info(f"\n{'#'*60}")
    log.info(f"  FinBuddy v18 Backtest Campaign")
    log.info(f"  {len(combos)} combos × {len(run_windows)} window(s) = {n_total} runs")
    log.info(f"  Windows: {run_windows}")
    log.info(f"{'#'*60}\n")

    _tg(
        f"🔬 <b>v18 Backtest Campaign Started</b>\n"
        f"{len(combos)} combos × {len(run_windows)} window(s) = {n_total} runs\n"
        f"k_mult: {k_mults}  label_period: {periods}  ml_threshold: {thresholds}"
    )

    # Data download
    if not args.no_download:
        ok = download_data(pairs, run_windows, dry_run=args.dry_run)
        if not ok:
            log.error("Data download failed — aborting campaign")
            _tg("❌ v18 campaign aborted: data download failed")
            sys.exit(1)

    # Results accumulator
    all_results = []
    passes = []
    run_idx = 0

    fieldnames = [
        "run", "window", "k_mult", "label_period", "ml_threshold",
        "win_rate", "sharpe", "max_drawdown", "profit_factor",
        "trade_count", "pass", "wr_pass", "sharpe_pass", "dd_pass", "pf_pass",
        "timestamp"
    ]

    for window_name, timerange in run_windows.items():
        for k_mult, label_period, ml_threshold in combos:
            run_idx += 1
            log.info(f"\n[{run_idx}/{n_total}] window={window_name}  k={k_mult}  "
                     f"l={label_period}  m={ml_threshold}")

            metrics = run_one(
                k_mult=k_mult,
                label_period=label_period,
                ml_threshold=ml_threshold,
                window=window_name,
                timerange=timerange,
                dry_run=args.dry_run,
            )

            if metrics is None:
                row = {
                    "run": run_idx, "window": window_name,
                    "k_mult": k_mult, "label_period": label_period, "ml_threshold": ml_threshold,
                    "win_rate": "ERROR", "sharpe": "ERROR", "max_drawdown": "ERROR",
                    "profit_factor": "ERROR", "trade_count": 0,
                    "pass": False, "wr_pass": False, "sharpe_pass": False,
                    "dd_pass": False, "pf_pass": False,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                passed = _grade(metrics, criteria) and not metrics.get("_dry_run", False)
                row = {
                    "run":            run_idx,
                    "window":         window_name,
                    "k_mult":         k_mult,
                    "label_period":   label_period,
                    "ml_threshold":   ml_threshold,
                    "win_rate":       metrics["win_rate"],
                    "sharpe":         metrics["sharpe"],
                    "max_drawdown":   metrics["max_drawdown"],
                    "profit_factor":  metrics["profit_factor"],
                    "trade_count":    metrics["trade_count"],
                    "pass":           passed,
                    "wr_pass":        metrics["win_rate"] >= criteria["win_rate"],
                    "sharpe_pass":    metrics["sharpe"]   >= criteria["sharpe"],
                    "dd_pass":        metrics["max_drawdown"] <= criteria["max_drawdown"],
                    "pf_pass":        metrics["profit_factor"] >= criteria["profit_factor"],
                    "timestamp":      datetime.utcnow().isoformat(),
                }
                if passed:
                    passes.append(row)

            all_results.append(row)

            # Write CSV incrementally (so partial results survive a crash)
            mode = "w" if run_idx == 1 else "a"
            with open(OUTPUT_CSV, mode, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if run_idx == 1:
                    writer.writeheader()
                writer.writerow(row)

            # Progress Telegram every 6 runs
            if run_idx % 6 == 0 or run_idx == n_total:
                status = "✅" if row.get("pass") else "❌"
                _tg(
                    f"{status} [{run_idx}/{n_total}] k={k_mult} l={label_period} m={ml_threshold} "
                    f"{window_name}\n"
                    f"WR={row.get('win_rate')}% Sh={row.get('sharpe')} "
                    f"DD={row.get('max_drawdown')}% PF={row.get('profit_factor')}"
                )

    # ── Final summary ──────────────────────────────────────────────────────
    log.info(f"\n{'#'*60}")
    log.info(f"  Campaign Complete — {len(passes)}/{n_total} PASS")
    log.info(f"{'#'*60}")

    if passes:
        log.info("\n🏆 PASSING COMBOS:")
        for r in passes:
            log.info(
                f"  [{r['window']}] k={r['k_mult']} l={r['label_period']} m={r['ml_threshold']} "
                f"→ WR={r['win_rate']}% Sh={r['sharpe']} DD={r['max_drawdown']}% PF={r['profit_factor']}"
            )

        # Find best by Sharpe across both windows (prefer combo that passes BOTH)
        bull_passes = [r for r in passes if r["window"] == "bull"]
        bear_passes = [r for r in passes if r["window"] == "bear"]
        both_pass_keys = set(
            (r["k_mult"], r["label_period"], r["ml_threshold"]) for r in bull_passes
        ) & set(
            (r["k_mult"], r["label_period"], r["ml_threshold"]) for r in bear_passes
        )

        if both_pass_keys:
            log.info(f"\n✅ {len(both_pass_keys)} combo(s) pass BOTH windows: {both_pass_keys}")
            # Pick highest combined Sharpe
            def combined_sharpe(key):
                k, l, m = key
                bull_row = next((r for r in bull_passes if r["k_mult"]==k and r["label_period"]==l and r["ml_threshold"]==m), None)
                bear_row = next((r for r in bear_passes if r["k_mult"]==k and r["label_period"]==l and r["ml_threshold"]==m), None)
                b_sh = bull_row["sharpe"] if bull_row else -999
                r_sh = bear_row["sharpe"] if bear_row else -999
                return b_sh + r_sh
            best_key = max(both_pass_keys, key=combined_sharpe)
            log.info(f"\n🥇 WINNER (both windows): k={best_key[0]}  l={best_key[1]}  m={best_key[2]}")
            _tg(
                f"🏆 <b>v18 Campaign Complete</b>\n"
                f"{len(passes)}/{n_total} PASS\n\n"
                f"✅ Winner (both windows):\n"
                f"k_mult={best_key[0]}  label_period={best_key[1]}  ml_threshold={best_key[2]}\n\n"
                f"Results: {OUTPUT_CSV.name}"
            )
        else:
            log.info("\n⚠️  No combo passes BOTH windows. Best bull/bear candidates:")
            _tg(
                f"⚠️ <b>v18 Campaign Complete</b>\n"
                f"{len(passes)}/{n_total} PASS\n"
                f"No combo passes BOTH windows — check CSV for best candidates.\n"
                f"Results: {OUTPUT_CSV.name}"
            )
    else:
        log.info("\n❌ No combos passed. Check the CSV for the closest failures.")
        # Print top 3 by Sharpe
        valid = [r for r in all_results if isinstance(r.get("sharpe"), (int, float))]
        top3 = sorted(valid, key=lambda r: r.get("sharpe", -999), reverse=True)[:3]
        for r in top3:
            log.info(
                f"  Best: k={r['k_mult']} l={r['label_period']} m={r['ml_threshold']} "
                f"[{r['window']}] → WR={r['win_rate']}% Sh={r['sharpe']} "
                f"DD={r['max_drawdown']}% PF={r['profit_factor']}"
            )
        _tg(
            f"❌ <b>v18 Campaign: ALL FAIL</b>\n"
            f"0/{n_total} PASS\n"
            f"Best Sharpe: {top3[0].get('sharpe', 'N/A') if top3 else 'N/A'}\n"
            f"Results: {OUTPUT_CSV.name}"
        )

    log.info(f"\nFull results: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
