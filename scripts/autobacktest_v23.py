#!/usr/bin/env python3
"""
autobacktest_v21.py — FinBuddy v21 MTF Sniper Campaign Grid Runner
====================================================================
Runs an 18-combo × 2-window backtest grid for the MTF Sniper logic:
  - k_tp          (take-profit barrier: 1.5 / 2.0 / 2.5 × ATR)
  - k_sl          (stop-loss barrier:   0.8 / 1.0 × ATR)
  - ml_threshold  (entry probability floor: 0.60 / 0.65 / 0.70)

MTF Sniper (v22 strategy logic, campaign named v21 per plan):
  - Longs ONLY when pair's 4H close > 4H EMA50 (4H bullish trend)
  - Shorts ONLY when pair's 4H close < 4H EMA50 (4H bearish trend)
  This prevents fighting the macro 4H trend, eliminating the "all-shorts
  in ranging market" bias observed in live v21 at 40.4% WR.

Also includes:
  - ATR stoploss bug fix (commit 21796ea): first campaign with working ATR stops
  - RS-based dynamic ML thresholds from v21
  - Asymmetric barriers (K_TP > K_SL) from v19/v20

Usage:
  cd /home/ubuntu/var/www/html/trade
  python scripts/autobacktest_v21.py [--dry-run] [--window bull|bear|both] [--no-download]

  # Re-read existing ZIPs and regenerate CSV (use after campaign completes):
  python scripts/autobacktest_v21.py --reparse

Results are written to _autobacktest_v21_results.csv and Telegram-notified.
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
OUTPUT_CSV     = REPO_ROOT / "_autobacktest_v23_results.csv"

# ── Telegram ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "REDACTED-FREQTRADE__TELEGRAM__TOKEN"
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
    """
    Minimal config overlay — sets label_period_candles + unique identifier.
    Forces fresh model training per combo (no cross-contamination).
    """
    overlay = {
        "freqai": {
            "identifier": identifier,
            "feature_parameters": {
                "label_period_candles": label_period
            }
        }
    }
    filename  = f"_v21_overlay_{identifier}.json"
    host_path = str(OVERLAY_HOST_DIR / filename)
    cont_path = f"{OVERLAY_CONTAINER_DIR}/{filename}"
    with open(host_path, "w") as f:
        json.dump(overlay, f)
    return host_path, cont_path

# ── Data download ──────────────────────────────────────────────────────────
def download_data(pairs: list, timeframes: list, windows: dict, dry_run: bool = False) -> bool:
    """
    Download historical data for all required timeframes (1h + 4h for MTF).
    Extends start date back 95 days as FreqAI train_period_days buffer.
    """
    from datetime import datetime as dt, timedelta

    all_timeranges = set(windows.values())
    starts = [w.split("-")[0] for w in all_timeranges]
    ends   = [w.split("-")[1] for w in all_timeranges]
    latest = max(ends)

    earliest_dt    = dt.strptime(min(starts), "%Y%m%d")
    download_start = (earliest_dt - timedelta(days=95)).strftime("%Y%m%d")
    timerange      = f"{download_start}-{latest}"

    log.info(f"[download] Timerange: {timerange}  (windows: {min(starts)}–{latest})")
    log.info(f"[download] Pairs: {pairs}  Timeframes: {timeframes}")

    cmd = [
        "docker-compose", "run", "--rm", "--no-deps",
        "freqtrade",
        "download-data",
        "--config", BASE_CONFIG,
        "--timerange", timerange,
        "--timeframes",
    ] + timeframes + [
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
    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-1] if zips else None

def _parse_result_zip(zip_path: Path) -> dict | None:
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
            log.error("[parse] No 'strategy' key in backtest JSON")
            return None

        strat_key = next(iter(strategy_data))
        s = strategy_data[strat_key]

        total_trades = s.get("total_trades", 0)
        if total_trades == 0:
            return {
                "win_rate": 0.0, "sharpe": 0.0, "max_drawdown": 100.0,
                "profit_factor": 0.0, "trade_count": 0
            }

        raw_wr = s.get("winrate", None)
        if raw_wr is not None:
            win_rate = round(float(raw_wr) * 100, 2)
        else:
            wins = s.get("wins", 0)
            win_rate = round((wins / total_trades * 100), 2) if total_trades > 0 else 0.0

        sharpe       = s.get("sharpe", s.get("sharpe_ratio", 0.0)) or 0.0
        dd_account   = s.get("max_drawdown_account", 0.0) or 0.0
        max_dd       = round(dd_account * 100, 2)
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
    return (
        metrics["win_rate"]          >= criteria["win_rate"]
        and metrics["sharpe"]        >= criteria["sharpe"]
        and metrics["max_drawdown"]  <= criteria["max_drawdown"]
        and metrics["profit_factor"] >= criteria["profit_factor"]
    )

# ── Single backtest run ────────────────────────────────────────────────────
def run_one(
    k_tp: float,
    k_sl: float,
    ml_threshold: float,
    label_period: int,
    window: str,
    timerange: str,
    dry_run: bool = False,
) -> dict | None:
    ts = int(time.time())
    identifier = f"v23_ktp{k_tp}_ksl{k_sl}_m{ml_threshold}_{ts}"

    overlay_host, overlay_container = _write_overlay(label_period, identifier)

    log.info(
        f"\n{'='*60}\n"
        f"  k_tp={k_tp}  k_sl={k_sl}  ml_threshold={ml_threshold}  "
        f"label_period={label_period}  window={window}\n"
        f"  identifier: {identifier}\n"
        f"  theoretical PF at 62% WR: {(0.62*k_tp)/(0.38*k_sl):.2f}\n"
        f"{'='*60}"
    )

    before_zips = set(RESULTS_DIR.glob("backtest-result-*.zip")) if not dry_run else set()

    cmd = [
        "docker-compose", "run", "--rm", "--no-deps",
        "-e", f"FREQAI_K_TP={k_tp}",
        "-e", f"FREQAI_K_SL={k_sl}",
        "-e", f"FREQAI_ML_THRESHOLD={ml_threshold}",
        "-e", "FREQTRADE__DRY_RUN_WALLET=10000",
        "freqtrade",
        "backtesting",
        "--config", BASE_CONFIG,
        "--config", overlay_container,
        "--strategy", "FinBuddyFreqAI_v23",
        "--freqaimodel", "LightGBMClassifier",
        "--timerange", timerange,
        "--timeframe", "5m",
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

    try:
        os.remove(overlay_host)
    except Exception:
        pass

    return metrics

# ── Reparse ────────────────────────────────────────────────────────────────
def reparse_all(grid_cfg: dict) -> None:
    criteria = grid_cfg["acceptance_criteria"]

    fieldnames = [
        "run", "window", "k_tp", "k_sl", "ml_threshold",
        "win_rate", "sharpe", "max_drawdown", "profit_factor",
        "trade_count", "pass", "wr_pass", "sharpe_pass", "dd_pass", "pf_pass",
        "theoretical_pf", "timestamp"
    ]

    zips = sorted(RESULTS_DIR.glob("backtest-result-*.zip"), key=lambda p: p.stat().st_mtime)
    v21_zips = []
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                jn = [n for n in zf.namelist() if n.endswith(".json")][0]
                with zf.open(jn) as jf:
                    d = json.load(jf)
            sk = next(iter(d.get("strategy", {})))
            ident = d["strategy"][sk].get("freqai_identifier", "")
            if not ident.startswith("v23_"):
                continue
        except Exception:
            continue
        v21_zips.append((z, d))

    log.info(f"[reparse] Found {len(v21_zips)} v21 ZIPs")
    rows = []
    for z, d in v21_zips:
        sk    = next(iter(d["strategy"]))
        s     = d["strategy"][sk]
        ident = s.get("freqai_identifier", "")
        m = re.match(r"v23_ktp([\d.]+)_ksl([\d.]+)_m([\d.]+)_(\d+)", ident)
        if not m:
            log.warning(f"[reparse] Could not parse identifier: {ident}")
            continue
        k_tp         = float(m.group(1))
        k_sl         = float(m.group(2))
        ml_threshold = float(m.group(3))

        metrics = _parse_result_zip(z)
        if metrics is None:
            continue

        tr = s.get("timerange", "")
        window_name = "bull" if tr.startswith("20240101") else "bear" if tr.startswith("20250101") else tr

        passed = _grade(metrics, criteria)
        rows.append({
            "run":            len(rows) + 1,
            "window":         window_name,
            "k_tp":           k_tp,
            "k_sl":           k_sl,
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
            "theoretical_pf": round((0.62 * k_tp) / (0.38 * k_sl), 2),
            "timestamp":      datetime.utcnow().isoformat(),
        })

    rows.sort(key=lambda r: (r["window"], r["k_tp"], r["k_sl"], r["ml_threshold"]))
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
            f"  {status} [{r['window']}] ktp={r['k_tp']} ksl={r['k_sl']} "
            f"m={r['ml_threshold']} → WR={r['win_rate']}% Sh={r['sharpe']} "
            f"DD={r['max_drawdown']}% PF={r['profit_factor']} (theory={r['theoretical_pf']})"
        )


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="FinBuddy v21 MTF Sniper backtest campaign")
    parser.add_argument("--dry-run",     action="store_true", help="Print commands without running")
    parser.add_argument("--window",      choices=["bull", "bear", "both"], default="both")
    parser.add_argument("--no-download", action="store_true", help="Skip data download step")
    parser.add_argument("--reparse",     action="store_true",
                        help="Re-read all v21 ZIPs and regenerate CSV")
    args = parser.parse_args()

    with open(GRID_JSON) as f:
        grid_cfg = json.load(f)

    if args.reparse:
        reparse_all(grid_cfg)
        return

    criteria      = grid_cfg["acceptance_criteria"]
    windows       = grid_cfg["windows"]
    pairs         = grid_cfg["pairs_download"]
    timeframes    = grid_cfg.get("timeframes_download", ["1h", "4h"])
    k_tps         = grid_cfg["grid"]["k_tp"]
    k_sls         = grid_cfg["grid"]["k_sl"]
    thresholds    = grid_cfg["grid"]["ml_threshold"]
    label_period  = grid_cfg["label_period_candles"]

    if args.window == "bull":
        run_windows = {"bull": windows["bull"]}
    elif args.window == "bear":
        run_windows = {"bear": windows["bear"]}
    else:
        run_windows = windows

    combos  = list(product(k_tps, k_sls, thresholds))
    n_total = len(combos) * len(run_windows)

    log.info(f"\n{'#'*60}")
    log.info(f"  FinBuddy v21 MTF Sniper Backtest Campaign")
    log.info(f"  {len(combos)} combos × {len(run_windows)} window(s) = {n_total} runs")
    log.info(f"  k_tp: {k_tps}  k_sl: {k_sls}  ml_threshold: {thresholds}")
    log.info(f"  label_period: {label_period} (fixed)")
    log.info(f"  Timeframes: {timeframes}  (4h required for MTF filter)")
    log.info(f"  Theoretical PF range: {(0.62*min(k_tps))/(0.38*max(k_sls)):.2f}"
             f" – {(0.62*max(k_tps))/(0.38*min(k_sls)):.2f}")
    log.info(f"{'#'*60}\n")

    _tg(
        f"🎯 <b>v23 Omni-Timeframe Campaign Started</b>\n"
        f"{len(combos)} combos × {len(run_windows)} window(s) = {n_total} runs\n"
        f"k_tp: {k_tps}  k_sl: {k_sls}  ml_threshold: {thresholds}\n"
        f"label_period: {label_period} (fixed)\n"
        f"MTF: 4H EMA50 trend gate active (no trades against macro)\n"
        f"ATR stoploss: FIXED (first campaign with working stops)\n"
        f"Theoretical PF range: {(0.62*min(k_tps))/(0.38*max(k_sls)):.2f}"
        f"–{(0.62*max(k_tps))/(0.38*min(k_sls)):.2f}"
    )

    if not args.no_download:
        ok = download_data(pairs, timeframes, run_windows, dry_run=args.dry_run)
        if not ok:
            log.error("Data download failed — aborting campaign")
            _tg("❌ v21 MTF campaign aborted: data download failed")
            sys.exit(1)

    all_results = []
    passes      = []
    run_idx     = 0

    fieldnames = [
        "run", "window", "k_tp", "k_sl", "ml_threshold",
        "win_rate", "sharpe", "max_drawdown", "profit_factor",
        "trade_count", "pass", "wr_pass", "sharpe_pass", "dd_pass", "pf_pass",
        "theoretical_pf", "timestamp"
    ]

    for window_name, timerange in run_windows.items():
        for k_tp, k_sl, ml_threshold in combos:
            run_idx += 1
            theory_pf = round((0.62 * k_tp) / (0.38 * k_sl), 2)
            log.info(
                f"\n[{run_idx}/{n_total}] window={window_name}  "
                f"ktp={k_tp}  ksl={k_sl}  m={ml_threshold}  "
                f"theory_pf={theory_pf}"
            )

            metrics = run_one(
                k_tp=k_tp,
                k_sl=k_sl,
                ml_threshold=ml_threshold,
                label_period=label_period,
                window=window_name,
                timerange=timerange,
                dry_run=args.dry_run,
            )

            if metrics is None:
                row = {
                    "run": run_idx, "window": window_name,
                    "k_tp": k_tp, "k_sl": k_sl, "ml_threshold": ml_threshold,
                    "win_rate": "ERROR", "sharpe": "ERROR", "max_drawdown": "ERROR",
                    "profit_factor": "ERROR", "trade_count": 0,
                    "pass": False, "wr_pass": False, "sharpe_pass": False,
                    "dd_pass": False, "pf_pass": False,
                    "theoretical_pf": theory_pf,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                passed = _grade(metrics, criteria) and not metrics.get("_dry_run", False)
                row = {
                    "run":            run_idx,
                    "window":         window_name,
                    "k_tp":           k_tp,
                    "k_sl":           k_sl,
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
                    "theoretical_pf": theory_pf,
                    "timestamp":      datetime.utcnow().isoformat(),
                }
                if passed:
                    passes.append(row)

            all_results.append(row)

            # Write CSV incrementally (partial results survive a crash)
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
                    f"{status} [{run_idx}/{n_total}] ktp={k_tp} ksl={k_sl} m={ml_threshold} "
                    f"{window_name} (theory_pf={theory_pf})\n"
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
                f"  [{r['window']}] ktp={r['k_tp']} ksl={r['k_sl']} m={r['ml_threshold']} "
                f"→ WR={r['win_rate']}% Sh={r['sharpe']} DD={r['max_drawdown']}% "
                f"PF={r['profit_factor']} (theory={r['theoretical_pf']})"
            )

        bull_passes = [r for r in passes if r["window"] == "bull"]
        bear_passes = [r for r in passes if r["window"] == "bear"]
        both_pass_keys = set(
            (r["k_tp"], r["k_sl"], r["ml_threshold"]) for r in bull_passes
        ) & set(
            (r["k_tp"], r["k_sl"], r["ml_threshold"]) for r in bear_passes
        )

        if both_pass_keys:
            log.info(f"\n✅ {len(both_pass_keys)} combo(s) pass BOTH windows: {both_pass_keys}")
            def combined_sharpe(key):
                k_tp, k_sl, m = key
                br = next((r for r in bull_passes if r["k_tp"]==k_tp and r["k_sl"]==k_sl and r["ml_threshold"]==m), None)
                rr = next((r for r in bear_passes if r["k_tp"]==k_tp and r["k_sl"]==k_sl and r["ml_threshold"]==m), None)
                return (br["sharpe"] if br else -999) + (rr["sharpe"] if rr else -999)
            best = max(both_pass_keys, key=combined_sharpe)
            log.info(f"\n🥇 WINNER (both windows): ktp={best[0]}  ksl={best[1]}  m={best[2]}")
            _tg(
                f"🏆 <b>v23 Omni-Timeframe Campaign Complete</b>\n"
                f"{len(passes)}/{n_total} PASS\n\n"
                f"✅ Winner (both windows):\n"
                f"k_tp={best[0]}  k_sl={best[1]}  ml_threshold={best[2]}\n\n"
                f"Results: {OUTPUT_CSV.name}"
            )
        else:
            log.info("\n⚠️  No combo passes BOTH windows.")
            _tg(
                f"⚠️ <b>v23 Omni-Timeframe Campaign Complete</b>\n"
                f"{len(passes)}/{n_total} PASS\n"
                f"No combo passes BOTH windows — check CSV for best candidates.\n"
                f"Results: {OUTPUT_CSV.name}"
            )
    else:
        log.info("\n❌ No combos passed.")
        valid = [r for r in all_results if isinstance(r.get("sharpe"), (int, float))]
        top3  = sorted(valid, key=lambda r: r.get("sharpe", -999), reverse=True)[:3]
        for r in top3:
            log.info(
                f"  Best: ktp={r['k_tp']} ksl={r['k_sl']} m={r['ml_threshold']} "
                f"[{r['window']}] → WR={r['win_rate']}% Sh={r['sharpe']} "
                f"DD={r['max_drawdown']}% PF={r['profit_factor']}"
            )
        _tg(
            f"❌ <b>v23 Omni-Timeframe Campaign: ALL FAIL</b>\n"
            f"0/{n_total} PASS\n"
            f"Best Sharpe: {top3[0].get('sharpe', 'N/A') if top3 else 'N/A'}\n"
            f"Results: {OUTPUT_CSV.name}"
        )

    log.info(f"\nFull results: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
