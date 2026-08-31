#!/usr/bin/env python3
"""apply_timeframe.py — switch the live trading timeframe + realign the whole system.

Single source of truth: finbuddy_memory/timeframe_profiles.json. This mirrors the proven
apply-live recipe in scripts/brain/promote.py:apply_promotion() (kept self-contained to avoid
regressing the promotion path). The strategy is already timeframe-safe (commit a4509b17), so
flipping config.json's timeframe + label_period + include_timeframes and recreating the
container is sufficient — every candle-count constant auto-scales.

Steps (apply <tf>):
  1. validate tf against profiles.available (strict allowlist)
  2. backup config.json (keep 3)
  3. json edit config.json: timeframe, label_period_candles, include_timeframes, bump identifier,
     + port feature-pipeline knobs from the per-TF config_file (like promote.py 2b)
  4. write per-TF thresholds/K_TP/K_SL/stability_n to freqtrade/.env
  5. docker-compose up -d freqtrade  (cwd freqtrade/, NOT restart)  [skip with --no-restart]
  6. reset pair_regime_stats.json (fresh model)
  7. update timeframe_profiles.json: active + history
  8. write timeframe_switch_status.json for the dashboard to poll

Usage:
  python3 scripts/apply_timeframe.py 1h          # switch live to 1h
  python3 scripts/apply_timeframe.py --rollback  # revert to previous tf (from history)
  python3 scripts/apply_timeframe.py 1h --dry-run     # print planned config, write nothing
  python3 scripts/apply_timeframe.py 1h --no-restart  # apply files but don't recreate container
"""
import argparse, json, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from ft_creds import read_freqtrade_env  # noqa: E402
LIVE_CONFIG = ROOT / "freqtrade" / "user_data" / "config.json"
ENV_PATH = ROOT / "freqtrade" / ".env"
PROFILES = ROOT / "finbuddy_memory" / "timeframe_profiles.json"
STATUS = ROOT / "finbuddy_memory" / "timeframe_switch_status.json"
PAIR_REGIME = ROOT / "finbuddy_memory" / "regimes" / "pair_regime_stats.json"
USER_DATA = ROOT / "freqtrade" / "user_data"
HYPOTHESIS_GEN = ROOT / "scripts" / "brain" / "hypothesis_gen.py"
BRAIN_CLI = ROOT / "scripts" / "brain" / "brain_cli.py"
DATA_DIR = ROOT / "freqtrade" / "user_data" / "data" / "binance" / "futures"


def load_profiles() -> dict:
    return json.loads(PROFILES.read_text())


def _write_status(d: dict):
    STATUS.write_text(json.dumps(d, indent=2))


def apply(tf: str, dry_run: bool = False, no_restart: bool = False) -> int:
    prof_doc = load_profiles()
    available = prof_doc.get("available", [])
    if tf not in available:
        print(f"ERROR: timeframe '{tf}' not in allowlist {available}", file=sys.stderr)
        return 2
    profile = prof_doc["profiles"][tf]
    prev_tf = prof_doc.get("active")
    ts = int(time.time())
    new_identifier = f"finbuddy_v23_tf{tf}_{ts}"

    # Build the planned config edits (load current live config)
    live = json.loads(LIVE_CONFIG.read_text())
    old_identifier = live.get("freqai", {}).get("identifier")
    planned = {
        "timeframe": tf,
        "label_period_candles": profile["label_period_candles"],
        "include_timeframes": profile["include_timeframes"],
        "identifier": new_identifier,
        "config_file": profile["config_file"],
    }
    # Gap 2 — data check: count feather files for the target TF
    feather_count = len(list(DATA_DIR.glob(f"*-{tf}-futures.feather")))
    data_warning = None if feather_count >= 10 else (
        f"Only {feather_count}/26 pairs have {tf} data — bot may stall on first startup. "
        f"Data downloads via cron at 04:30 UTC (download_data_daily.sh)."
    )
    if data_warning:
        print(f"WARN: {data_warning}", file=sys.stderr)
    else:
        print(f"data check: {feather_count} pairs have {tf} feathers ✓")

    if dry_run:
        print(json.dumps({
            "from": prev_tf, "to": tf, "old_identifier": old_identifier, "planned": planned,
            "data_check": f"{feather_count} pairs", "data_warning": data_warning,
            "seed_label_period_patch": profile["label_period_candles"],
            "brain_generate_queued": True,
            "env": {k: profile.get(k) for k in
                    ("long_threshold", "short_threshold", "k_tp", "k_sl", "stability_n")},
        }, indent=2))
        return 0

    # 1. status: starting
    _write_status({"state": "applying", "from": prev_tf, "to": tf,
                   "started_at": datetime.now(timezone.utc).isoformat(),
                   "identifier": new_identifier, "restart_ok": None,
                   "data_warning": data_warning})

    # 2. backup config.json (keep 3)
    shutil.copy(LIVE_CONFIG, LIVE_CONFIG.with_suffix(f".json.bak-{ts}"))
    for f in sorted(LIVE_CONFIG.parent.glob("config.json.bak-*"))[:-3]:
        try: f.unlink()
        except OSError: pass

    # 3. edit config.json
    feat = live.setdefault("freqai", {}).setdefault("feature_parameters", {})
    live["timeframe"] = tf
    feat["label_period_candles"] = profile["label_period_candles"]
    feat["include_timeframes"] = profile["include_timeframes"]
    live["freqai"]["identifier"] = new_identifier
    # Port feature-pipeline knobs from the per-TF config FILE (mirror promote.py 2b) so the live
    # feature set matches what the brain trains for that timeframe.
    try:
        exp_cfg = json.loads((USER_DATA / profile["config_file"]).read_text())
        exp_freqai = exp_cfg["freqai"]
        exp_feat = exp_freqai["feature_parameters"]
        for key in ("include_shifted_candles", "indicator_periods_candles",
                    "include_timeframes", "include_corr_pairlist"):
            if key in exp_feat:
                feat[key] = exp_feat[key]
        # Also port top-level freqai keys that are TF-specific (not just feature_parameters).
        # These were previously missed, causing live_retrain_hours to stay at the old TF's value.
        for key in ("live_retrain_hours", "purge_old_models", "backtest_period_days"):
            if key in exp_freqai:
                live["freqai"][key] = exp_freqai[key]
    except Exception as e:
        print(f"WARN: could not port feature_parameters from {profile['config_file']}: {e}", file=sys.stderr)
    # Set startup_candle_count from TF (25 days × candles-per-day). Null in config means FreqTrade
    # uses the class-level default (2400 at 15m) regardless of the actual timeframe.
    _secs = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}.get(tf, 3600)
    live["startup_candle_count"] = 25 * (86400 // _secs)
    LIVE_CONFIG.write_text(json.dumps(live, indent=4))
    print(f"config.json: timeframe={tf} label_period={feat['label_period_candles']} "
          f"include={feat['include_timeframes']} identifier {old_identifier} -> {new_identifier}")

    # 4. write strategy env vars (per-TF profile)
    # CRITICAL: FREQTRADE__FREQAI__IDENTIFIER lives in .env and docker-compose forwards it
    # (${FREQTRADE__FREQAI__IDENTIFIER:-}), which OVERRIDES config.json's freqai.identifier.
    # So the new identifier MUST be written here too, or the container keeps the OLD model
    # after `up -d` → strategy runs the new TF against a stale model (silent breakage).
    env_keys = {
        "FREQTRADE__FREQAI__IDENTIFIER": new_identifier,
        "FREQAI_LONG_THRESHOLD":  profile.get("long_threshold"),
        "FREQAI_SHORT_THRESHOLD": profile.get("short_threshold"),
        "FREQAI_K_TP":            profile.get("k_tp"),
        "FREQAI_K_SL":            profile.get("k_sl"),
        "FREQAI_STABILITY_N":     profile.get("stability_n"),
    }
    env_keys = {k: v for k, v in env_keys.items() if v is not None}
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    out = [ln for ln in lines if ln.split("=", 1)[0] not in env_keys]
    out += [f"{k}={v}" for k, v in env_keys.items()]
    ENV_PATH.write_text("\n".join(out) + "\n")
    print(f".env updated: {list(env_keys)}")

    # 5. recreate container (up -d, not restart — see reference_compose_env_reload.md)
    restart_ok = None
    if not no_restart:
        try:
            r = subprocess.run(["docker-compose", "up", "-d", "freqtrade"],
                               cwd=str(ROOT / "freqtrade"), capture_output=True, text=True, timeout=180)
            restart_ok = (r.returncode == 0)
            print(f"docker-compose up -d: {'OK' if restart_ok else 'FAILED'}")
            if not restart_ok:
                print(r.stderr[-400:], file=sys.stderr)
        except Exception as e:
            restart_ok = False
            print(f"restart error: {e}", file=sys.stderr)

    # 6. reset pair_regime_stats (fresh model)
    try:
        if PAIR_REGIME.exists():
            data = json.loads(PAIR_REGIME.read_text())
            stats = data.get("stats", {})
            neutral = {"n": 0, "wins": 0, "losses": 0, "wr": 0.5, "pf": 1.0,
                       "profit_usdt": 0.0, "avg_profit_pct": 0.0}
            for pair in stats:
                stats[pair] = {regime: dict(neutral) for regime in stats[pair]}
            data["stats"] = stats
            data["blocked"] = {}
            data["updated"] = datetime.now(timezone.utc).isoformat()
            PAIR_REGIME.write_text(json.dumps(data, indent=2))
            print(f"pair_regime_stats.json reset ({len(stats)} pairs)")
    except Exception as e:
        print(f"WARN: pair_regime_stats reset failed: {e}", file=sys.stderr)

    # 7. update profiles (active + history)
    prof_doc["active"] = tf
    prof_doc.setdefault("history", []).append(
        {"ts": ts, "at": datetime.now(timezone.utc).isoformat(),
         "from": prev_tf, "to": tf, "identifier": new_identifier})
    prof_doc["history"] = prof_doc["history"][-50:]
    PROFILES.write_text(json.dumps(prof_doc, indent=2))

    # 8. final status
    _write_status({"state": "training", "from": prev_tf, "to": tf,
                   "started_at": datetime.now(timezone.utc).isoformat(),
                   "identifier": new_identifier, "restart_ok": restart_ok,
                   "data_warning": data_warning})

    # Gap 1 — patch brain SEED label_period_candles so experiments start from the right horizon.
    # hypothesis_gen.py line 182: "label_period_candles": <int>,
    new_lp = profile["label_period_candles"]
    try:
        src = HYPOTHESIS_GEN.read_text()
        patched = re.sub(
            r'("label_period_candles"\s*:\s*)\d+(\s*,\s*#.*SEED)',
            lambda m: f'{m.group(1)}{new_lp}{m.group(2)}' if m.group(2) else m.group(0),
            src,
        )
        # Fallback: match without trailing comment (the actual format in the file)
        if patched == src:
            # Find SEED_CONFIG_V23 block and replace the first label_period_candles inside it
            patched = re.sub(
                r'(SEED_CONFIG_V23\s*=\s*\{[^}]*?"label_period_candles"\s*:\s*)\d+',
                lambda m: f'{m.group(1)}{new_lp}',
                src, flags=re.DOTALL,
            )
        if patched != src:
            HYPOTHESIS_GEN.write_text(patched)
            print(f"hypothesis_gen.py SEED label_period_candles patched → {new_lp}")
        else:
            print("WARN: could not patch hypothesis_gen.py SEED label_period_candles", file=sys.stderr)
    except Exception as e:
        print(f"WARN: SEED patch failed: {e}", file=sys.stderr)

    # Gap 3 — seed brain experiments for the new TF immediately (don't wait for midnight cron).
    try:
        subprocess.Popen(
            [sys.executable, str(BRAIN_CLI), "generate"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("brain_cli.py generate spawned in background → 1h experiments will queue shortly")
    except Exception as e:
        print(f"WARN: brain generate spawn failed: {e}", file=sys.stderr)

    # Regime → TF advisory: read current regime and send a Telegram advisory if the
    # chosen TF is suboptimal for the prevailing market regime (IC-evidence based).
    _REGIME_TF_ADVICE = {
        "CRASH":    ("4h", "4h reduces noise in crashes — IC 4h > 15m in stress regimes"),
        "BEAR":     ("1h", "1h IC 0.07 > 15m 0.03 in bear markets (measured Jun 2026)"),
        "NEUTRAL":  ("1h", "any TF valid; 1h is a balanced default"),
        "BULL":     ("15m", "15m fires more entries in bull — signal frequency is valuable"),
        "EUPHORIA": ("15m", "15m captures momentum in high-vol rallies"),
    }
    try:
        regime_file = ROOT / "finbuddy_memory" / "regimes" / "current.json"
        regime = json.loads(regime_file.read_text()).get("regime", "NEUTRAL")
        rec_tf, reason = _REGIME_TF_ADVICE.get(regime, ("1h", "default"))
        if rec_tf == tf:
            advisory = f"✅ TF switch to {tf} — optimal for current {regime} regime ({reason})"
        else:
            advisory = (
                f"⚠️ TF switched to {tf} (current regime: {regime})\n"
                f"Recommended: {rec_tf} — {reason}\n"
                f"You can switch via the dashboard TimeframeCard."
            )
        print(f"[RegimeAdvisory] {advisory}")
        # Send via Telegram. 2026-08-31: config.json's telegram.token is a placeholder
        # since the 2026-07-05 security pass (real value moved to freqtrade/.env) — this
        # call had been silently failing on every timeframe switch since then.
        cfg_tg = json.loads((ROOT / "freqtrade" / "user_data" / "config.json").read_text()).get("telegram", {})
        token = read_freqtrade_env().get("FREQTRADE__TELEGRAM__TOKEN")
        chat_id = cfg_tg.get("chat_id")
        if token and chat_id:
            import urllib.request as _ur
            _ur.urlopen(
                _ur.Request(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data=json.dumps({"chat_id": chat_id, "text": advisory, "parse_mode": "HTML"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ), timeout=10)
    except Exception as _e:
        print(f"WARN: regime advisory failed: {_e}", file=sys.stderr)

    print(f"DONE: active timeframe {prev_tf} -> {tf}")
    return 0 if (no_restart or restart_ok) else 1


def rollback(dry_run: bool = False, no_restart: bool = False) -> int:
    hist = load_profiles().get("history", [])
    if not hist:
        print("ERROR: no history to roll back to", file=sys.stderr)
        return 2
    target = hist[-1].get("from")
    if not target:
        print("ERROR: last history entry has no 'from'", file=sys.stderr)
        return 2
    print(f"rolling back to {target}")
    return apply(target, dry_run=dry_run, no_restart=no_restart)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("timeframe", nargs="?", help="target timeframe (e.g. 1h)")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    a = ap.parse_args()
    if a.rollback:
        return rollback(dry_run=a.dry_run, no_restart=a.no_restart)
    if not a.timeframe:
        ap.error("timeframe required (or --rollback)")
    return apply(a.timeframe, dry_run=a.dry_run, no_restart=a.no_restart)


if __name__ == "__main__":
    raise SystemExit(main())
