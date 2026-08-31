#!/usr/bin/env python3
"""ic_advisor.py — weekly Telegram advisory: which TF has the best entry-signal IC?

Reads feature_ic_by_tf.json (written by feature_ic.py --all-tf, Monday 06:55 cron) and
sends a one-line Telegram summary with the best TF's IC score and whether the current live
TF is already optimal. Zero-commitment — just information, no auto-switching.

Usage: python3 scripts/brain/ic_advisor.py
Cron:  Mon 06:59 UTC  (after feature_ic.py --all-tf at 06:55)
"""
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IC_BY_TF = ROOT / "finbuddy_memory/analytics/feature_ic_by_tf.json"
PROFILES = ROOT / "finbuddy_memory/timeframe_profiles.json"
CONFIG = ROOT / "freqtrade/user_data/config.json"

sys.path.insert(0, str(ROOT / "scripts" / "lib"))
from ft_creds import read_freqtrade_env  # noqa: E402

BEAR_WINDOWS = ["bear_2025Q1", "bear_2026Q1"]
IC_GATE = 0.05
MIN_SWITCH_GAIN = 0.015   # only suggest a switch if best TF is this much better than current


def _telegram_creds() -> tuple[str, str]:
    # 2026-07-05: config.json's telegram.token is now a placeholder (real value
    # moved to freqtrade/.env FREQTRADE__TELEGRAM__TOKEN) — read from there instead.
    # (2026-08-31: this script was missed in the original 07-05 pass — every
    # weekly send had been silently failing against the placeholder since then.)
    try:
        cfg = json.loads(CONFIG.read_text())
        chat_id = str((cfg.get("telegram") or {}).get("chat_id", ""))
        token = read_freqtrade_env().get("FREQTRADE__TELEGRAM__TOKEN", "")
        return token, chat_id
    except Exception:
        return "", ""


def _send(msg: str) -> None:
    token, chat_id = _telegram_creds()
    if not token or not chat_id:
        print("[ic_advisor] no Telegram creds — printing only")
        print(msg)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15)
    except Exception as e:
        print(f"[ic_advisor] Telegram send failed: {e}")


def best_ic_per_tf(by_tf: dict) -> dict[str, float]:
    """Return {tf: best_generalized_ic} — the highest MIN bear IC across features.

    Uses MIN across bear windows (conservative generalization) rather than MAX,
    so a feature that spikes in only one bear window doesn't inflate the score.
    Example: 4h btc_accel (0.138/0.019) → min=0.019 < gate; 1h btc_vol_12
    (0.083/0.056) → min=0.056 > gate. The correct recommendation is 1h.
    """
    result = {}
    for tf, r in by_tf.items():
        report = r.get("report", {})
        best_min_ic = 0.0
        for feat, wdata in report.items():
            bear_ics = [abs((wdata.get(w) or {}).get("ic") or 0.0) for w in BEAR_WINDOWS]
            if len(bear_ics) >= 2:
                min_ic = min(bear_ics)  # conservative: must be robust across ALL bear windows
            else:
                min_ic = max(bear_ics, default=0.0)
            best_min_ic = max(best_min_ic, min_ic)
        result[tf] = round(best_min_ic, 4)
    return result


def main() -> int:
    if not IC_BY_TF.exists():
        print("[ic_advisor] feature_ic_by_tf.json not found — run feature_ic.py --all-tf first")
        return 1

    try:
        data = json.loads(IC_BY_TF.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ic_advisor] cannot read IC file: {e}")
        return 1

    by_tf = data.get("by_tf", {})
    if not by_tf:
        print("[ic_advisor] by_tf is empty")
        return 1

    scores = best_ic_per_tf(by_tf)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    best_tf, best_ic = ranked[0]

    # Current active TF
    active_tf = None
    try:
        active_tf = json.loads(PROFILES.read_text()).get("active")
    except Exception:
        pass
    active_ic = scores.get(active_tf, 0.0)

    generated = data.get("generated_at", "")[:10]

    lines = [f"📡 <b>Weekly IC Advisor</b> ({generated})"]
    lines.append("")
    lines.append(f"<b>TF ranking by max |bear IC|:</b>")
    for tf, ic in ranked:
        marker = " ← active" if tf == active_tf else ""
        gate = " ✅" if ic > IC_GATE else ""
        lines.append(f"  {tf}: {ic:.3f}{gate}{marker}")

    lines.append("")
    gain = best_ic - active_ic
    if best_tf == active_tf:
        lines.append(f"✓ Active TF (<b>{active_tf}</b>) already has the best IC ({active_ic:.3f}).")
    elif best_ic > IC_GATE and gain >= MIN_SWITCH_GAIN:
        lines.append(
            f"⚡ Consider switching: <b>{best_tf}</b> has IC {best_ic:.3f} "
            f"vs current {active_tf} at {active_ic:.3f} (+{gain:.3f}).\n"
            f"  Switch via dashboard Settings → Trading Timeframe."
        )
    elif best_ic > IC_GATE:
        lines.append(
            f"✓ Active TF (<b>{active_tf}</b>) IC {active_ic:.3f} is close to best "
            f"{best_tf} ({best_ic:.3f}, gap {gain:.3f} < {MIN_SWITCH_GAIN} threshold). No switch needed."
        )
    else:
        lines.append(
            f"No TF clears the IC gate ({IC_GATE}). Best is {best_tf} at {best_ic:.3f}. "
            f"Entry-signal is weak across all TFs — market-neutral modules may be the better path."
        )

    msg = "\n".join(lines)
    print(msg)
    _send(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
