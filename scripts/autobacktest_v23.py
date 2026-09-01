#!/usr/bin/env python3
"""
autobacktest_v23.py — Cortexa v23 Regression Campaign Grid Runner
====================================================================
Runs a 48-combo × 2-window backtest grid for the Regression Conscious Brain:
  - long_threshold   (predicted % return to enter long: 0.5 / 1.0 / 1.5 / 2.0)
  - short_threshold  (predicted % return to enter short: same grid, negated)
  - label_period_candles (prediction horizon: 24 / 48 / 72 candles)

Architecture:
  LightGBMRegressor predicts continuous future_return (%).
  No class labels → no class imbalance → no base-rate short-bias.
  Dynamic thresholds adapt to regime + WR feedback in the live strategy.
  Grid searches the BASE threshold values (regime/WR multipliers apply on top).

Usage:
  cd /home/ubuntu/var/www/html/trade
  python scripts/autobacktest_v23.py [--dry-run] [--window bull|bear|both] [--no-download]

  # Re-read existing ZIPs and regenerate CSV:
  python scripts/autobacktest_v23.py --reparse

Results are written to _autobacktest_v23_results.csv and Telegram-notified.
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
GRID_JSON      = REPO_ROOT / "scripts" / "autobacktest_v23_grid.json"
BASE_CONFIG    = "/freqtrade/user_data/backtest_config.json"  # inside container
RESULTS_DIR    = REPO_ROOT / "freqtrade" / "user_data" / "backtest_results"
OVERLAY_HOST_DIR      = REPO_ROOT / "freqtrade" / "user_data"
OVERLAY_CONTAINER_DIR = "/freqtrade/user_data"
COMPOSE_DIR    = REPO_ROOT / "freqtrade"
BACKTEST_DIR   = REPO_ROOT / "backtests"
OUTPUT_CSV     = BACKTEST_DIR / "_autobacktest_v23_results.csv"

# ── Telegram ───────────────────────────────────────────────────────────────
def _load_telegram_token():
    # 2026-07-05: was a hardcoded literal (committed to git); read from freqtrade/.env instead.
    try:
        for _line in open("/home/ubuntu/var/www/html/trade/freqtrade/.env"):
            if _line.startswith("BRAIN_TELEGRAM_TOKEN="):
                return _line.strip().split("=", 1)[1]
    except Exception:
        pass
    return None

TELEGRAM_TOKEN = _load_telegram_token()
TELEGRAM_CHAT  = "5622292536"

def _tg(msg: str) -> None:
    try:
        import urllib.request, urllib.parse
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"}).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception as e:
        log.warning(f"[Telegram] send failed: {e}")

# ── Config overlay writer ──────────────────────────────────────────────────
def _write_overlay(label_period: int, identifier: str) -> tuple:
    """Minimal overlay — sets label_period_candles + unique identifier per combo."""
    overlay = {
        "freqai": {
            "identifier": identifier,
            "feature_parameters": {
                "label_period_candles": label_period
            }
        }
    }
    filename  = f"_v23_overlay_{identifier}.json"
    host_path = str(OVERLAY_HOST_DIR / filename)
    cont_path = f"{OVERLAY_CONTAINER_DIR}/{filename}"
    with open(host_path, "w") as f:
        json.dump(overlay, f)
    return host_path, cont_path

# ── Data download ──────────────────────────────────────────────────────────
def download_data(pairs: list, timeframes: list, windows: dict, dry_run: bool = False) -> bool:
    """Download historical data for all required timeframes (5m + 15m + 1h + 4h + 1d)."""
    from datetime import datetime as dt, timedelta

    starts = [w.split("-")[0] for w in windows.values()]
    ends   = [w.split("-")[1] for w in windows.values()]
    latest = max(ends)

    earliest_dt    = dt.strptime(min(starts), "%Y%m%d")
    download_start = (earliest_dt - timedelta(days=95)).strftime("%Y%m%d")
    timerange      = f"{download_start}-{latest}"

    log.info(f"[download] Timerange: {timerange}  Pairs: {pairs}  TFs: {timeframes}")

    cmd = [
        "docker-compose", "run", "--rm", "--no-deps",
        "freqtrade", "download-data",
        "--config", BASE_CONFIG,
        "--timerange", timerange,
        "--timeframes",
    ] + timeframes + ["--trading-mode", "futures", "--pairs"] + pairs

    if dry_run:
        log.info("[download] DRY RUN — skipping")
        return True

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(COMPOSE_DIR))
    out = (result.stdout + result.stderr)[-2000:]
    log.info(f"[download] exit={result.returncode}\n{out}")

    if result.returncode != 0:
        log.error(f"[download] FAILED — exit {result.returncode}")
        return False
    return True

# ── Result parser ──────────────────────────────────────────────────────────
def _find_latest_zip() -> Path | None:
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-1] if zips else None

def _parse_result_zip(zip_path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            json_names = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_names:
                return None
            with zf.open(json_names[0]) as jf:
                data = json.load(jf)

        strategy_data = data.get("strategy", {})
        if not strategy_data:
            return None

        strat_key = next(iter(strategy_data))
        s = strategy_data[strat_key]

        total_trades = s.get("total_trades", 0)
        if total_trades == 0:
            return {"win_rate": 0.0, "sharpe": 0.0, "max_drawdown": 100.0,
                    "profit_factor": 0.0, "trade_count": 0,
                    "long_count": 0, "short_count": 0}

        raw_wr = s.get("winrate", None)
        if raw_wr is not None:
            win_rate = round(float(raw_wr) * 100, 2)
        else:
            wins = s.get("wins", 0)
            win_rate = round((wins / total_trades * 100), 2) if total_trades > 0 else 0.0

        sharpe        = s.get("sharpe", s.get("sharpe_ratio", 0.0)) or 0.0
        dd_account    = s.get("max_drawdown_account", 0.0) or 0.0
        max_dd        = round(dd_account * 100, 2)
        profit_factor = round(float(s.get("profit_factor", 0.0) or 0.0), 3)

        # Count long vs short trades (key sanity check for regression — should have both)
        enter_reason  = s.get("enter_reason_summary", {})
        long_count  = sum(v.get("count", 0) for k, v in enter_reason.items() if "long" in k)
        short_count = sum(v.get("count", 0) for k, v in enter_reason.items() if "short" in k)

        return {
            "win_rate":      round(win_rate, 2),
            "sharpe":        round(float(sharpe), 3),
            "max_drawdown":  max_dd,
            "profit_factor": profit_factor,
            "trade_count":   total_trades,
            "long_count":    long_count,
            "short_count":   short_count,
        }
    except Exception as e:
        log.error(f"[parse] Exception parsing {zip_path}: {e}")
        return None

def _grade(metrics: dict, criteria: dict) -> bool:
    return (
        metrics["win_rate"]          >= criteria["win_rate"]
        and metrics["sharpe"]        >= criteria["sharpe"]
        and metrics["max_drawdown"]  <= criteria["max_drawdown"]
        and metrics["profit_factor"] >= criteria["profit_factor"]
    )

# ── Single backtest run ────────────────────────────────────────────────────
def run_one(
    long_threshold: float,
    short_threshold: float,
    label_period: int,
    window: str,
    timerange: str,
    dry_run: bool = False,
) -> dict | None:
    ts = int(time.time())
    identifier = f"v23_reg_lt{long_threshold}_st{short_threshold}_lp{label_period}_{ts}"

    overlay_host, overlay_container = _write_overlay(label_period, identifier)

    log.info(
        f"\n{'='*60}\n"
        f"  long_threshold={long_threshold}%  short_threshold=-{short_threshold}%\n"
        f"  label_period={label_period} candles ({label_period*5//60}h on 5m base)\n"
        f"  window={window}  identifier: {identifier}\n"
        f"{'='*60}"
    )

    before_zips = set(RESULTS_DIR.glob("backtest-result-*.zip")) if not dry_run else set()

    cmd = [
        "docker-compose", "run", "--rm", "--no-deps",
        "-e", f"FREQAI_LONG_THRESHOLD={long_threshold}",
        "-e", f"FREQAI_SHORT_THRESHOLD=-{short_threshold}",
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
        "freqtrade",
        "backtesting",
        "--config", BASE_CONFIG,
        "--config", overlay_container,
        "--strategy", "CortexaAI_v23",
        "--freqaimodel", "LightGBMRegressor",
        "--timerange", timerange,
        "--timeframe", "5m",
        "--export", "trades",
        "--cache", "none",
    ]

    log.info(f"[run] {' '.join(cmd)}")

    if dry_run:
        log.info("[run] DRY RUN — skipping")
        return {"win_rate": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "profit_factor": 0.0, "trade_count": 0,
                "long_count": 0, "short_count": 0, "_dry_run": True}

    t_start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(COMPOSE_DIR))
    elapsed = int(time.time() - t_start)

    out = (result.stdout + result.stderr)[-3000:]
    log.info(f"[run] exit={result.returncode}  elapsed={elapsed}s\n{out}")

    if result.returncode != 0:
        log.error(f"[run] FAILED (exit {result.returncode})")
        return None

    after_zips = set(RESULTS_DIR.glob("backtest-result-*.zip"))
    new_zips = sorted(after_zips - before_zips, key=lambda p: p.stat().st_mtime)
    if not new_zips:
        log.error("[run] No new backtest ZIP produced")
        return None

    zip_path = new_zips[-1]
    metrics  = _parse_result_zip(zip_path)
    if metrics is None:
        return None

    log.info(
        f"[result] WR={metrics['win_rate']}%  Sharpe={metrics['sharpe']}  "
        f"DD={metrics['max_drawdown']}%  PF={metrics['profit_factor']}  "
        f"Trades={metrics['trade_count']} (L={metrics['long_count']}/S={metrics['short_count']})"
    )

    try:
        os.remove(overlay_host)
    except Exception:
        pass

    return metrics

# ── Reparse ────────────────────────────────────────────────────────────────
def reparse_all(grid_cfg: dict) -> None:
    criteria   = grid_cfg["acceptance_criteria"]
    fieldnames = [
        "run", "window", "long_threshold", "short_threshold", "label_period",
        "win_rate", "sharpe", "max_drawdown", "profit_factor",
        "trade_count", "long_count", "short_count",
        "pass", "wr_pass", "sharpe_pass", "dd_pass", "pf_pass", "timestamp"
    ]

    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    v23_zips = []
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                jn = [n for n in zf.namelist() if n.endswith(".json")][0]
                with zf.open(jn) as jf:
                    d = json.load(jf)
            sk = next(iter(d.get("strategy", {})))
            ident = d["strategy"][sk].get("freqai_identifier", "")
            if not ident.startswith("v23_reg_"):
                continue
        except Exception:
            continue
        v23_zips.append((z, d))

    log.info(f"[reparse] Found {len(v23_zips)} v23 regression ZIPs")
    rows = []
    for z, d in v23_zips:
        sk    = next(iter(d["strategy"]))
        s     = d["strategy"][sk]
        ident = s.get("freqai_identifier", "")
        m = re.match(r"v23_reg_lt([\d.]+)_st([\d.]+)_lp(\d+)_(\d+)", ident)
        if not m:
            log.warning(f"[reparse] Could not parse identifier: {ident}")
            continue
        long_threshold  = float(m.group(1))
        short_threshold = float(m.group(2))
        label_period    = int(m.group(3))

        metrics = _parse_result_zip(z)
        if metrics is None:
            continue

        tr = s.get("timerange", "")
        window_name = "bull" if tr.startswith("20240101") else "bear" if tr.startswith("20250101") else tr

        passed = _grade(metrics, criteria)
        rows.append({
            "run":            len(rows) + 1,
            "window":         window_name,
            "long_threshold": long_threshold,
            "short_threshold":short_threshold,
            "label_period":   label_period,
            "win_rate":       metrics["win_rate"],
            "sharpe":         metrics["sharpe"],
            "max_drawdown":   metrics["max_drawdown"],
            "profit_factor":  metrics["profit_factor"],
            "trade_count":    metrics["trade_count"],
            "long_count":     metrics.get("long_count", 0),
            "short_count":    metrics.get("short_count", 0),
            "pass":           passed,
            "wr_pass":        metrics["win_rate"]      >= criteria["win_rate"],
            "sharpe_pass":    metrics["sharpe"]        >= criteria["sharpe"],
            "dd_pass":        metrics["max_drawdown"]  <= criteria["max_drawdown"],
            "pf_pass":        metrics["profit_factor"] >= criteria["profit_factor"],
            "timestamp":      datetime.utcnow().isoformat(),
        })

    rows.sort(key=lambda r: (r["window"], r["long_threshold"], r["short_threshold"], r["label_period"]))
    for i, r in enumerate(rows):
        r["run"] = i + 1

    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    passes = [r for r in rows if r["pass"]]
    log.info(f"[reparse] {len(passes)}/{len(rows)} PASS — CSV: {OUTPUT_CSV}")

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Cortexa v23 Regression backtest campaign")
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--window",      choices=["bull", "bear", "both"], default="both")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--reparse",     action="store_true")
    args = parser.parse_args()

    with open(GRID_JSON) as f:
        grid_cfg = json.load(f)

    if args.reparse:
        reparse_all(grid_cfg)
        return

    criteria        = grid_cfg["acceptance_criteria"]
    windows         = grid_cfg["windows"]
    pairs           = grid_cfg["pairs_download"]
    timeframes      = grid_cfg.get("timeframes_download", ["5m", "15m", "1h", "4h", "1d"])
    long_thresholds = grid_cfg["grid"]["long_threshold"]
    short_thresholds= grid_cfg["grid"]["short_threshold"]
    label_periods   = grid_cfg["grid"]["label_period_candles"]

    if args.window == "bull":
        run_windows = {"bull": windows["bull"]}
    elif args.window == "bear":
        run_windows = {"bear": windows["bear"]}
    else:
        run_windows = windows

    combos  = list(product(long_thresholds, short_thresholds, label_periods))
    n_total = len(combos) * len(run_windows)

    log.info(f"\n{'#'*60}")
    log.info(f"  Cortexa v23 Regression Backtest Campaign")
    log.info(f"  {len(combos)} combos × {len(run_windows)} window(s) = {n_total} runs")
    log.info(f"  long_threshold:  {long_thresholds}%")
    log.info(f"  short_threshold: {short_thresholds}%")
    log.info(f"  label_periods:   {label_periods} candles")
    log.info(f"  Model: LightGBMRegressor (no class imbalance)")
    log.info(f"{'#'*60}\n")

    _tg(
        f"🧠 <b>v23 Regression Campaign Started</b>\n"
        f"{len(combos)} combos × {len(run_windows)} window(s) = {n_total} runs\n"
        f"long_threshold: {long_thresholds}%\n"
        f"short_threshold: {short_thresholds}%\n"
        f"label_periods: {label_periods} candles\n"
        f"Model: LightGBMRegressor (no class bias)"
    )

    if not args.no_download:
        ok = download_data(pairs, timeframes, run_windows, dry_run=args.dry_run)
        if not ok:
            log.error("Data download failed — aborting campaign")
            _tg("❌ v23 campaign aborted: data download failed")
            sys.exit(1)

    all_results = []
    passes      = []
    run_idx     = 0

    fieldnames = [
        "run", "window", "long_threshold", "short_threshold", "label_period",
        "win_rate", "sharpe", "max_drawdown", "profit_factor",
        "trade_count", "long_count", "short_count",
        "pass", "wr_pass", "sharpe_pass", "dd_pass", "pf_pass", "timestamp"
    ]

    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    for window_name, timerange in run_windows.items():
        for long_thresh, short_thresh, label_period in combos:
            run_idx += 1
            log.info(
                f"\n[{run_idx}/{n_total}] window={window_name}  "
                f"lt={long_thresh}%  st=-{short_thresh}%  lp={label_period}"
            )

            metrics = run_one(
                long_threshold=long_thresh,
                short_threshold=short_thresh,
                label_period=label_period,
                window=window_name,
                timerange=timerange,
                dry_run=args.dry_run,
            )

            if metrics is None:
                row = {
                    "run": run_idx, "window": window_name,
                    "long_threshold": long_thresh, "short_threshold": short_thresh,
                    "label_period": label_period,
                    "win_rate": "ERROR", "sharpe": "ERROR", "max_drawdown": "ERROR",
                    "profit_factor": "ERROR", "trade_count": 0,
                    "long_count": 0, "short_count": 0,
                    "pass": False, "wr_pass": False, "sharpe_pass": False,
                    "dd_pass": False, "pf_pass": False,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                passed = _grade(metrics, criteria) and not metrics.get("_dry_run", False)
                row = {
                    "run":            run_idx,
                    "window":         window_name,
                    "long_threshold": long_thresh,
                    "short_threshold":short_thresh,
                    "label_period":   label_period,
                    "win_rate":       metrics["win_rate"],
                    "sharpe":         metrics["sharpe"],
                    "max_drawdown":   metrics["max_drawdown"],
                    "profit_factor":  metrics["profit_factor"],
                    "trade_count":    metrics["trade_count"],
                    "long_count":     metrics.get("long_count", 0),
                    "short_count":    metrics.get("short_count", 0),
                    "pass":           passed,
                    "wr_pass":        metrics["win_rate"]      >= criteria["win_rate"],
                    "sharpe_pass":    metrics["sharpe"]        >= criteria["sharpe"],
                    "dd_pass":        metrics["max_drawdown"]  <= criteria["max_drawdown"],
                    "pf_pass":        metrics["profit_factor"] >= criteria["profit_factor"],
                    "timestamp":      datetime.utcnow().isoformat(),
                }
                if passed:
                    passes.append(row)

            all_results.append(row)

            # Write CSV incrementally
            mode = "w" if run_idx == 1 else "a"
            with open(OUTPUT_CSV, mode, newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if run_idx == 1:
                    writer.writeheader()
                writer.writerow(row)

            # Progress Telegram every 6 runs
            if run_idx % 6 == 0 or run_idx == n_total:
                lc = row.get("long_count", "?")
                sc = row.get("short_count", "?")
                status = "✅" if row.get("pass") else "❌"
                _tg(
                    f"{status} [{run_idx}/{n_total}] lt={long_thresh}% st=-{short_thresh}% lp={label_period} [{window_name}]\n"
                    f"WR={row.get('win_rate')}% Sh={row.get('sharpe')} "
                    f"DD={row.get('max_drawdown')}% PF={row.get('profit_factor')}\n"
                    f"Trades: {row.get('trade_count')} (L={lc} / S={sc})"
                )

    # ── Final summary ──────────────────────────────────────────────────────
    log.info(f"\n{'#'*60}")
    log.info(f"  Campaign Complete — {len(passes)}/{n_total} PASS")
    log.info(f"{'#'*60}")

    if passes:
        log.info("\n🏆 PASSING COMBOS:")
        for r in passes:
            log.info(
                f"  [{r['window']}] lt={r['long_threshold']}% st={r['short_threshold']}% "
                f"lp={r['label_period']} → WR={r['win_rate']}% Sh={r['sharpe']} "
                f"DD={r['max_drawdown']}% PF={r['profit_factor']} "
                f"(L={r.get('long_count',0)}/S={r.get('short_count',0)})"
            )

        bull_passes = [r for r in passes if r["window"] == "bull"]
        bear_passes = [r for r in passes if r["window"] == "bear"]
        both_pass_keys = set(
            (r["long_threshold"], r["short_threshold"], r["label_period"]) for r in bull_passes
        ) & set(
            (r["long_threshold"], r["short_threshold"], r["label_period"]) for r in bear_passes
        )

        if both_pass_keys:
            log.info(f"\n✅ {len(both_pass_keys)} combo(s) pass BOTH windows")
            def combined_sharpe(key):
                lt, st, lp = key
                br = next((r for r in bull_passes if r["long_threshold"]==lt and r["short_threshold"]==st and r["label_period"]==lp), None)
                rr = next((r for r in bear_passes if r["long_threshold"]==lt and r["short_threshold"]==st and r["label_period"]==lp), None)
                return (br["sharpe"] if br else -999) + (rr["sharpe"] if rr else -999)
            best = max(both_pass_keys, key=combined_sharpe)
            log.info(f"\n🥇 WINNER (both windows): lt={best[0]}%  st=-{best[1]}%  lp={best[2]}")
            _tg(
                f"🏆 <b>v23 Regression Campaign Complete</b>\n"
                f"{len(passes)}/{n_total} PASS\n\n"
                f"✅ Winner (both windows):\n"
                f"long_threshold={best[0]}%  short_threshold=-{best[1]}%  label_period={best[2]}\n\n"
                f"Results: {OUTPUT_CSV.name}"
            )
        else:
            log.info("\n⚠️  No combo passes BOTH windows.")
            _tg(
                f"⚠️ <b>v23 Regression Campaign Complete</b>\n"
                f"{len(passes)}/{n_total} PASS\n"
                f"No combo passes BOTH windows — check CSV.\n"
                f"Results: {OUTPUT_CSV.name}"
            )
    else:
        log.info("\n❌ No combos passed.")
        valid = [r for r in all_results if isinstance(r.get("sharpe"), (int, float))]
        top3  = sorted(valid, key=lambda r: r.get("sharpe", -999), reverse=True)[:3]
        for r in top3:
            log.info(
                f"  Best: lt={r['long_threshold']}% st={r['short_threshold']}% lp={r['label_period']} "
                f"[{r['window']}] → WR={r['win_rate']}% Sh={r['sharpe']} "
                f"DD={r['max_drawdown']}% PF={r['profit_factor']} "
                f"(L={r.get('long_count',0)}/S={r.get('short_count',0)})"
            )
        _tg(
            f"❌ <b>v23 Regression Campaign: ALL FAIL</b>\n"
            f"0/{n_total} PASS\n"
            f"Best Sharpe: {top3[0].get('sharpe', 'N/A') if top3 else 'N/A'}\n"
            f"Results: {OUTPUT_CSV.name}"
        )

    log.info(f"\nFull results: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
