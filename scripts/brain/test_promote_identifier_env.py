"""
Dry verification for the promote.py identifier→.env fix (2026-06-21).

Bug: apply_promotion() bumped freqai.identifier in config.json but did NOT write
FREQTRADE__FREQAI__IDENTIFIER to freqtrade/.env. docker-compose.yml forwards that
.env var (${FREQTRADE__FREQAI__IDENTIFIER:-}), which OVERRIDES config.json's
freqai.identifier. So after `up -d` the container kept the OLD model → promotion
silently had no effect. (.env identifier introduced 2026-06-06; promotions since
then may have been silently overridden.)

This test runs the REAL apply_promotion() against a temp sandbox (docker + Telegram
stubbed) and asserts the new identifier lands in BOTH config.json and .env, and the
two agree. No live config, no real container, no real promotion is touched.

Run: python scripts/brain/test_promote_identifier_env.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import promote  # noqa: E402


def run() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ud = root / "freqtrade" / "user_data"
        ud.mkdir(parents=True)
        (root / "freqtrade").mkdir(exist_ok=True)
        promotions = root / "finbuddy_memory" / "promotions"
        promotions.mkdir(parents=True)
        (root / "finbuddy_memory" / "regimes").mkdir(parents=True)

        live_config = ud / "config.json"
        env_path = root / "freqtrade" / ".env"
        OLD_ID = "finbuddy_v23_nosvm_OLD"

        live_config.write_text(json.dumps({
            "timeframe": "15m",
            "freqai": {"identifier": OLD_ID, "feature_parameters": {}},
        }, indent=4))
        # .env starts with the OLD identifier (as on the live server, line 22).
        env_path.write_text(
            "FREQTRADE__FREQAI__IDENTIFIER=" + OLD_ID + "\n"
            "FREQAI_LONG_THRESHOLD=0.7\n"
        )

        pending = {
            "config_hash": "deadbeef",
            "config": {
                "k_tp": 3.0, "k_sl": 2.0,
                "long_threshold": 0.7, "short_threshold": -0.6,
                "stability_n": 1, "timeframe": "15m",
            },
        }

        # Point the module at the sandbox.
        patches = {
            "ROOT": root,
            "LIVE_CONFIG": live_config,
            "PROMOTIONS_DIR": promotions,
            "PENDING_FILE": promotions / "pending.json",
        }
        (promotions / "pending.json").write_text(json.dumps(pending))

        with mock.patch.multiple(promote, **patches), \
             mock.patch("subprocess.run") as m_run, \
             mock.patch.object(promote, "tg_send", lambda *a, **k: None):
            m_run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            rc = promote.apply_promotion("deadbeef")

        # --- assertions ---
        cfg = json.loads(live_config.read_text())
        cfg_id = cfg["freqai"]["identifier"]

        env_id = None
        for line in env_path.read_text().splitlines():
            if line.startswith("FREQTRADE__FREQAI__IDENTIFIER="):
                env_id = line.split("=", 1)[1]

        ok = True
        if cfg_id == OLD_ID:
            print("FAIL: config.json identifier was not bumped")
            ok = False
        if env_id is None:
            print("FAIL: FREQTRADE__FREQAI__IDENTIFIER missing from .env")
            ok = False
        elif env_id == OLD_ID:
            print(f"FAIL: .env still has OLD identifier {env_id} (the bug)")
            ok = False
        elif env_id != cfg_id:
            print(f"FAIL: .env identifier {env_id} != config.json {cfg_id}")
            ok = False
        # exactly one identifier line (no duplicate/stale leftover)
        n_id_lines = sum(
            1 for ln in env_path.read_text().splitlines()
            if ln.startswith("FREQTRADE__FREQAI__IDENTIFIER=")
        )
        if n_id_lines != 1:
            print(f"FAIL: expected 1 identifier line in .env, found {n_id_lines}")
            ok = False

        if ok:
            print(f"PASS: rc={rc}; config.json and .env both = {cfg_id}")
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(run())
