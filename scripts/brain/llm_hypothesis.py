#!/usr/bin/env python3
"""
llm_hypothesis.py — LLM-driven hypothesis & feature generation (E1, 2026-06-11).

The evolutionary brain only mutates dials inside human-defined choice lists.
This module closes the self-evolution loop: a nightly LLM call reads a compact
dossier of what the system has LEARNED (experiment history, feature importance,
prediction IC, analyst patterns, regime) and proposes what to test NEXT:

  a) entry/param hypotheses — restricted to known config keys, clamped to valid
     ranges, then AUTO-QUEUED as normal brain experiments (safe: experiments
     are validation, not deployment; promotion gates still apply)
  b) feature proposals — formula + rationale, written to llm_proposals.jsonl
     and Telegram. NEVER auto-applied to code: a human (or a Claude session)
     implements approved ones behind env gates, then the brain validates.

Uses scripts/llm_client.py task="reasoning" chain (qwen3-coder → kimi-k2 → …,
all free-tier providers). Cron: nightly 02:30 UTC.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/ubuntu/var/www/html/trade")
BRAIN = ROOT / "scripts/brain"
sys.path.insert(0, str(BRAIN))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "freqtrade/user_data/scripts"))

from llm_client import call_llm                      # noqa: E402
from lib.telegram_template import Subsystem, Status, send  # noqa: E402
from experiment_log import read_log, queue_hypothesis      # noqa: E402
import hypothesis_gen as hg                          # noqa: E402

PROPOSALS_FILE = ROOT / "finbuddy_memory/experiments/llm_proposals.jsonl"
MAX_QUEUED_PER_NIGHT = 3
VALIDATION_WINDOWS = ["bull_2025Q4", "bear_2026Q1"]

# Params the LLM may set on an experiment, with sanitizers.
_ALLOWED_PARAMS = {
    "long_threshold": float, "short_threshold": float,
    "k_tp": float, "k_sl": float, "stability_n": int,
    "label_period_candles": int, "timeframe": str, "feature_set": str,
    "entry_mode": str, "entry_quantile": float, "bounce_guard": bool,
    "prune_indicators": bool, "num_leaves": int, "learning_rate": float,
}


def _dossier() -> str:
    """Compact system-state summary for the LLM."""
    parts = []
    # recent experiments
    recent = read_log()[-30:]
    lines = []
    for r in recent:
        c, m = r.get("config", {}), r.get("metrics") or {}
        lines.append(
            f"{r.get('status','?')[:12]} win={r.get('window','?')} "
            f"lt={c.get('long_threshold')} st={c.get('short_threshold')} "
            f"ktp={c.get('k_tp')} ksl={c.get('k_sl')} mode={c.get('entry_mode','absolute')} "
            f"profit={m.get('profit_pct')} wr={m.get('wr')} trades={m.get('trades')}"
        )
    parts.append("RECENT 30 EXPERIMENTS:\n" + "\n".join(lines))
    # feature importance
    try:
        fi = json.loads((ROOT / "finbuddy_memory/analytics/feature_importance.json").read_text())
        top = ", ".join(f"{d['feature']}({d['share_pct']}%)" for d in fi["top_50"][:15])
        parts.append(
            f"FEATURE IMPORTANCE: {fi['total_features']} features, 80% of gain in top "
            f"{fi['features_for_80pct']}, {fi['dead_features_lt_0.05pct']} dead. Top: {top}"
        )
    except Exception:
        pass
    # IC report
    try:
        ic = json.loads((ROOT / "finbuddy_memory/analytics/pair_ic.json").read_text())
        ranked = sorted(ic["pairs"].items(), key=lambda kv: -kv[1]["full"]["ic"])
        parts.append(
            f"PREDICTION IC (Spearman vs 12-candle fwd return): pooled "
            f"{ic.get('pooled',{}).get('ic')}; best {ranked[0][0]} {ranked[0][1]['full']['ic']}, "
            f"worst {ranked[-1][0]} {ranked[-1][1]['full']['ic']}"
        )
    except Exception:
        pass
    # analyst patterns
    try:
        ar = json.loads((ROOT / "finbuddy_memory/experiments/analyst_report.json").read_text())
        parts.append("ANALYST PATTERNS: " + json.dumps(ar)[:600])
    except Exception:
        pass
    # regime
    try:
        reg = json.loads((ROOT / "finbuddy_memory/regimes/current.json").read_text())
        parts.append(f"CURRENT REGIME: {reg.get('regime')} (conf {reg.get('confidence')})")
    except Exception:
        pass
    return "\n\n".join(parts)


_SYSTEM = """You are the research director of an autonomous crypto trading system
(LightGBM regressor on Binance USDT-M perp futures, 15m base timeframe, 26 pairs,
z-scored 12-candle future-return target, quantile/absolute entry thresholds,
ATR-based exits that already work well — DO NOT propose exit changes).
Known facts: entries are the weak link (38% of trades hit full stop-loss);
prediction IC ~0.05 concentrated in mid-cap alts, ~0 on BTC/ETH; 420+
threshold-only experiments found no profitable config on recent regimes.
Propose what to test NEXT. Respond with ONLY valid JSON, no markdown:
{
 "entry_hypotheses": [
   {"rationale": "<1 sentence>", "params": {<subset of: long_threshold, short_threshold,
    k_tp, k_sl, stability_n, label_period_candles, timeframe, feature_set, entry_mode
    ('absolute'|'quantile'), entry_quantile, bounce_guard, prune_indicators,
    num_leaves, learning_rate>}}
 ],
 "feature_proposals": [
   {"name": "<snake_case>", "formula": "<precise pandas-level description>",
    "rationale": "<why this should predict 3h returns>"}
 ]
}
Max 3 entry_hypotheses, max 3 feature_proposals. Prefer hypotheses that change
WHAT the model sees or HOW entries are selected — not another threshold tweak."""


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _sanitize_params(params: dict) -> dict | None:
    out = {}
    for k, v in params.items():
        if k not in _ALLOWED_PARAMS:
            continue
        try:
            out[k] = _ALLOWED_PARAMS[k](v)
        except Exception:
            return None
    if not out:
        return None
    for key in ("long_threshold", "short_threshold", "k_tp", "k_sl", "stability_n"):
        if key in out:
            hg._clamp(out, key)
    if not hg._in_current_scale(out):
        return None
    if out.get("entry_quantile") is not None:
        out["entry_quantile"] = min(0.98, max(0.80, out["entry_quantile"]))
    if out.get("timeframe") not in (None, "15m", "30m", "1h"):
        return None
    # feature_set must be a real mode — LLMs invent values like "base+conf";
    # an unknown mode would silently disable macro features in the strategy.
    if "feature_set" in out and out["feature_set"] not in ("all", "no_macro", "no_regime", "minimal"):
        del out["feature_set"]
    if out.get("entry_mode") not in (None, "absolute", "quantile"):
        del out["entry_mode"]
    return out


def main() -> int:
    dossier = _dossier()
    reply = call_llm(dossier, system=_SYSTEM, task="reasoning", max_tokens=1200, timeout=90)
    if not reply:
        print("[llm_hypothesis] all LLM providers failed")
        return 1
    data = _extract_json(reply)
    if not data:
        print(f"[llm_hypothesis] unparseable reply: {reply[:200]}")
        return 1

    ts = datetime.now(timezone.utc).isoformat()
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROPOSALS_FILE, "a") as f:
        f.write(json.dumps({"ts": ts, "raw": data}) + "\n")

    # a) auto-queue sanitized entry hypotheses as normal experiments
    queued = 0
    for h in (data.get("entry_hypotheses") or [])[:MAX_QUEUED_PER_NIGHT]:
        params = _sanitize_params(h.get("params") or {})
        if params is None:
            continue
        cfg = dict(hg.SEED_CONFIG_V23)
        cfg.update(params)
        cfg["target_version"] = "zscore"
        rationale = f"llm [v23]: {str(h.get('rationale', ''))[:140]}"
        for win in VALIDATION_WINDOWS:
            queue_hypothesis(config=cfg, band="aggressive", rationale=rationale,
                             window=win, timerange=hg.WINDOWS[win])
            queued += 1

    # b) feature proposals → Telegram for human review (never auto-applied)
    feats = data.get("feature_proposals") or []
    feat_lines = "\n".join(f"• <b>{p.get('name')}</b>: {p.get('formula','')[:160]}"
                           for p in feats[:3]) or "none"
    send(
        Subsystem.BRAIN_CYCLE, Status.INFO,
        "Nightly LLM research proposals",
        fields={"Experiments queued": queued, "Feature proposals": len(feats)},
        html_context=feat_lines,
        context=None if feats else "No feature proposals tonight.",
        silent=True,
    )
    print(f"[llm_hypothesis] queued {queued} experiments, "
          f"{len(feats)} feature proposals logged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
