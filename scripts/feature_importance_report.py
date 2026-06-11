#!/usr/bin/env python3
"""
feature_importance_report.py — weekly aggregated LightGBM feature importance.

Loads the most recent sub-train models (joblib lives only inside the freqtrade
container, so the model-loading step runs via `docker exec`), aggregates
normalized gain importance across pairs, and reports:
  - top features and families
  - how many features carry 80% of total importance
  - dead weight (<0.05% each) — pruning candidates for Phase B

Output:
  - finbuddy_memory/analytics/feature_importance.json
  - Telegram digest

Measured 2026-06-11 baseline: 1,322 expanded features, 80% of importance in
top 486, 756 features <0.05% each. Goal after Phase B pruning: <400 features.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from lib.telegram_template import Subsystem, Status, send  # noqa: E402

OUT_FILE = ROOT / "finbuddy_memory/analytics/feature_importance.json"
N_MODELS = 12  # most recent sub-train models to aggregate

# Runs inside the freqtrade container (has joblib + lightgbm).
_INNER = r"""
import glob, json
from collections import defaultdict
import joblib
dirs = sorted(glob.glob('/freqtrade/user_data/models/sub-train-*'))[-%(n_models)d:]
agg = defaultdict(float); nmodels = 0
for d in dirs:
    try:
        mfile = glob.glob(d + '/*_model.joblib')[0]
        model = joblib.load(mfile)
        est = model.estimators_[0] if hasattr(model, 'estimators_') else model
        names = est.booster_.feature_name()
        imp = est.feature_importances_.astype(float)
        s = imp.sum()
        if s <= 0:
            continue
        for n_, i_ in zip(names, imp / s):
            agg[n_] += i_
        nmodels += 1
    except Exception:
        continue
print(json.dumps({"n_models": nmodels, "importance": dict(agg)}))
"""


def main() -> int:
    proc = subprocess.run(
        ["docker", "exec", "freqtrade", "python3", "-c", _INNER % {"n_models": N_MODELS}],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        print(f"[feature_importance] docker exec failed: {proc.stderr[-500:]}")
        return 1
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    agg = data["importance"]
    total = sum(agg.values()) or 1.0
    ranked = sorted(agg.items(), key=lambda x: -x[1])

    cum, top80 = 0.0, len(ranked)
    for i, (_, v) in enumerate(ranked, 1):
        cum += v
        if cum / total >= 0.8:
            top80 = i
            break
    dead = sum(1 for v in agg.values() if v / total < 0.0005)

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "models_aggregated": data["n_models"],
        "total_features": len(ranked),
        "features_for_80pct": top80,
        "dead_features_lt_0.05pct": dead,
        "top_50": [
            {"feature": n, "share_pct": round(v / total * 100, 3)}
            for n, v in ranked[:50]
        ],
        "full_ranking": {n: round(v / total, 6) for n, v in ranked},
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(report, indent=2))

    top5 = ", ".join(n[:30] for n, _ in ranked[:5])
    send(
        Subsystem.BRAIN_CYCLE,
        Status.INFO,
        "Weekly feature-importance report",
        fields={
            "Features": len(ranked),
            "Carry 80%": top80,
            "Dead (<0.05%)": dead,
            "Top 5": top5,
        },
        context="Aggregated LightGBM gain importance across "
                f"{data['n_models']} recent pair models. "
                "Full ranking: finbuddy_memory/analytics/feature_importance.json",
        silent=True,
    )
    print(f"[feature_importance] wrote {OUT_FILE} — {len(ranked)} features, "
          f"80% in top {top80}, {dead} dead")
    return 0


if __name__ == "__main__":
    sys.exit(main())
