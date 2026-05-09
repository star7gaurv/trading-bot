#!/usr/bin/env python3
"""Reasoning agent — generates de-duplicated strategy hypotheses from research text.
Uses Grok-3-Mini when available; falls back to context-driven rules.
Hypothesis IDs always include a date suffix so they are never duplicates across runs.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT     = Path("/home/ubuntu/var/www/html/trade")
REGISTRY = ROOT / "strategies/registry.json"
XAI_API_URL = "https://api.x.ai/v1/chat/completions"


def _load_xai_key() -> str:
    key = os.environ.get("XAI_API_KEY", "")
    if key:
        return key
    try:
        for line in (ROOT / "freqtrade/.env").read_text().splitlines():
            if line.startswith("XAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def _call_grok(prompt: str, system: str = "", max_tokens: int = 700) -> str | None:
    key = _load_xai_key()
    if not key:
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": "grok-3-mini",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.5,
    }).encode()
    req = urllib.request.Request(
        XAI_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"[reasoning] XAI 403 — no credits. Using rule-based fallback.")
        else:
            print(f"[reasoning] XAI HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[reasoning] XAI error: {e}")
        return None


def _rule_based_hypotheses(research_text: str, today: str) -> list:
    """Generate context-driven hypotheses with date-unique IDs."""
    text_lower = research_text.lower()
    suffix = today.replace("-", "")
    hypotheses = []

    if "fear" in text_lower and ("extreme" in text_lower or "fg=" in text_lower):
        hypotheses.append({
            "strategy_id": f"fear_greed_contrarian_{suffix}",
            "hypothesis": "Extreme fear reading is historically a mean-reversion long signal; test longs on 15m oversold with tight 1×ATR stop.",
            "timeframe": "15m",
            "indicators": ["RSI_14", "ATR_14", "EMA_20"],
            "entry_long": "fear_greed < 30 AND RSI < 28 AND close > EMA_20",
            "entry_short": "fear_greed > 75 AND RSI > 72 AND close < EMA_20",
            "exit_rule": "RSI mean-reverts to 50 or 1×ATR stop",
            "regime_filter": ["NEUTRAL", "BEAR"],
        })

    if "btc dominance" in text_lower and ("elevated" in text_lower or "high" in text_lower):
        hypotheses.append({
            "strategy_id": f"btc_dom_threshold_adjust_{suffix}",
            "hypothesis": "During high BTC dominance periods, raise ml_threshold to 0.65 on alt pairs to filter noise-driven signals.",
            "timeframe": "1h",
            "indicators": ["BTC_DOM_SMA20", "ml_pred_proba"],
            "entry_long": "ml_pred_proba_long > 0.65 AND BTC_DOM < BTC_DOM_SMA20",
            "entry_short": "ml_pred_proba_short > 0.65 AND BTC_DOM > BTC_DOM_SMA20",
            "exit_rule": "exit_signal or 6h time_limit",
            "regime_filter": ["NEUTRAL", "BULL"],
        })

    if "neutral" in text_lower and "flat" in text_lower:
        hypotheses.append({
            "strategy_id": f"range_time_limit_{suffix}",
            "hypothesis": "Low volatility + NEUTRAL regime → shorten time_limit to 4 candles to avoid drift losing in range-bound markets.",
            "timeframe": "1h",
            "indicators": ["ATR_14", "BB_width_20"],
            "entry_long": "ml_pred_proba_long > 0.60 AND ATR_14 < ATR_14_SMA50",
            "entry_short": "ml_pred_proba_short > 0.60 AND ATR_14 < ATR_14_SMA50",
            "exit_rule": "exit_signal or 4h time_limit",
            "regime_filter": ["NEUTRAL"],
        })

    # Always generate at least one hypothesis
    if not hypotheses:
        hypotheses.append({
            "strategy_id": f"stop_loss_audit_{suffix}",
            "hypothesis": "Hard stop_loss exits drive 15-50% of trades at 0% WR; test raising ml_threshold to 0.65 to reduce false entries that immediately hit the stop.",
            "timeframe": "1h",
            "indicators": ["ml_pred_proba_long", "ml_pred_proba_short"],
            "entry_long": "ml_pred_proba_long > 0.65",
            "entry_short": "ml_pred_proba_short > 0.65",
            "exit_rule": "exit_signal or custom_stoploss",
            "regime_filter": ["NEUTRAL", "BULL", "BEAR"],
        })

    return hypotheses


def _load_registry() -> dict:
    try:
        with open(REGISTRY) as f:
            return json.load(f)
    except Exception:
        return {"strategies": []}


def run_reasoning(research_text: str) -> list:
    registry  = _load_registry()
    existing  = {s["strategy_id"] for s in registry.get("strategies", [])}
    today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    suffix    = today.replace("-", "")

    # Try LLM first
    system_prompt = (
        "You are FinBuddy's strategy designer for a FreqAI LightGBM futures bot (long+short, 1h TF, 25 pairs). "
        "Based on the research text, propose exactly 2 NEW trading hypotheses. "
        "Reply ONLY with a JSON array of objects, each with: "
        "strategy_id (must end with _" + suffix + " and not be in this list: " + json.dumps(sorted(existing)) + "), "
        "hypothesis, timeframe, indicators (list), entry_long, entry_short, exit_rule, regime_filter (list)."
    )
    raw = _call_grok(research_text, system=system_prompt, max_tokens=700)

    hypotheses = []
    if raw:
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:]).rsplit("```", 1)[0]
            parsed = json.loads(clean)
            if isinstance(parsed, list):
                hypotheses = parsed
        except Exception as e:
            print(f"[reasoning] JSON parse failed ({e}), using rule-based fallback")

    if not hypotheses:
        hypotheses = _rule_based_hypotheses(research_text, today)

    # Deduplicate: never add an id that's already in the registry
    new_hypotheses = [h for h in hypotheses if h.get("strategy_id") not in existing]

    for h in new_hypotheses:
        h["status"] = "in_development"
        h["proposed_at"] = today
        h["proposed_by"] = "reasoning_agent"
        registry["strategies"].append(h)

    with open(REGISTRY, "w") as f:
        json.dump(registry, f, indent=2)

    skipped = len(hypotheses) - len(new_hypotheses)
    print(f"Added {len(new_hypotheses)} hypotheses (skipped {skipped} duplicates)")
    return new_hypotheses


if __name__ == "__main__":
    run_reasoning("test")
