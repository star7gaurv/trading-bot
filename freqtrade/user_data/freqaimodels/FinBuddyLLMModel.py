# pragma pylint: disable=missing-docstring, invalid-name
"""
FinBuddyLLMModel — Custom FreqAI Model v4
==========================================
Architecture:
  1. LightGBM trains on OHLCV + TA indicators (inherited from LightGBMClassifier)
  2. predict() checks signal confidence (prob deviation from 0.5)
  3. High-confidence signals get LLM confirmation via central llm_client.py
     Task chain "signal": nvidia-mistral-medium → nvidia-llama-70b → nvidia-kimi-k2
                          → openrouter-gpt-oss-20b → ... → raw LGBM if all fail
  4. LLM outcome:
     - CONFIRM → signal passes (LightGBM raw used for subsequent candles in cooldown)
     - REJECT / HOLD → signal suppressed AND verdict cached for full cooldown window
       so subsequent candles for this pair are also blocked (sticky veto)

Keys required (in freqtrade/.env):
  NVIDIA_API_KEY      — primary, 10 free models on NVIDIA NIM
  OPENROUTER_API_KEY  — fallback, :free tier models

Rate limiting: per-pair cooldown (60 min). Resets on any successful LLM call.
Bug fix v4 (2026-05-10): REJECT/HOLD verdicts now sticky for full cooldown period.
  v3 bug: LLM rejection only suppressed pred_df at the moment of the call; the
  NEXT candle's predict() would bypass the filter (cooldown active but no cached
  verdict applied) and fire raw LightGBM — allowing trades the LLM just blocked.
"""

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from pandas import DataFrame

try:
    from freqtrade.freqai.prediction_models.LightGBMClassifier import LightGBMClassifier
    BASE_CLASS = LightGBMClassifier
except ImportError:
    from freqtrade.freqai.base_models.BaseClassifierModel import BaseClassifierModel
    BASE_CLASS = BaseClassifierModel

# Central LLM client — lives at /freqtrade/user_data/scripts/llm_client.py
sys.path.insert(0, "/freqtrade/user_data/scripts")
try:
    from llm_client import call_llm, available_providers
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.05   # prob must deviate >5% from 0.5 to trigger LLM
COOLDOWN_SECONDS     = 3600   # 60-min per-pair cooldown

_SIGNAL_SYSTEM = (
    "You are FinBuddy's trade validator for a 25-pair crypto futures bot "
    "(FreqAI LightGBM 1h TF). A ML model flagged a trade. "
    "Review the market context and respond with EXACTLY one word: "
    "CONFIRM (signal valid), REJECT (signal wrong), or HOLD (uncertain)."
)


class FinBuddyLLMModel(BASE_CLASS):
    """
    LightGBM classifier with LLM signal confirmation layer.
    Inherits all training from LightGBMClassifier; overrides predict() only.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_llm_call: Dict[str, float] = {}
        # Sticky veto cache: pair → (verdict, timestamp). REJECT/HOLD verdicts
        # are re-applied on every predict() call for this pair until cooldown elapses,
        # even though the LLM itself is not re-called (rate limiting still applies).
        self._llm_verdict_cache: Dict[str, Tuple[str, float]] = {}

        if not _LLM_AVAILABLE:
            logger.warning("[FinBuddyLLMModel] llm_client not found — LLM confirmation disabled.")
        else:
            providers = available_providers()
            if providers:
                logger.info(f"[FinBuddyLLMModel] LLM ready via {len(providers)} providers: {providers}")
            else:
                logger.warning(
                    "[FinBuddyLLMModel] No LLM keys configured. "
                    "Add NVIDIA_API_KEY or OPENROUTER_API_KEY to freqtrade/.env"
                )

    def fit(self, data_dictionary: Dict, dk: Any, **kwargs) -> Any:
        return super().fit(data_dictionary, dk, **kwargs)

    def predict(self, unfiltered_df: DataFrame, dk: Any, **kwargs) -> Tuple[DataFrame, DataFrame]:
        pred_df, do_predict = super().predict(unfiltered_df, dk, **kwargs)

        if not _LLM_AVAILABLE:
            return pred_df, do_predict

        pair = dk.pair if hasattr(dk, "pair") else "UNKNOWN"
        # FreqAI classifier stores prediction in "&-s_label" (matches strategy's
        # set_freqai_targets target column). Probabilities are in "L" and "S".
        pred_col = "&-s_label"
        if pred_col not in pred_df.columns:
            return pred_df, do_predict

        last_class = pred_df[pred_col].iloc[-1]

        # Probability of the "L" class — matches strategy class_names = ["L", "S"]
        prob_col = next((c for c in ("L", "proba_long", "&-s_label_L") if c in pred_df.columns), None)
        last_prob  = float(pred_df[prob_col].iloc[-1]) if prob_col else 0.5
        confidence = abs(last_prob - 0.5)

        if hasattr(do_predict, "iloc"):
            last_do = do_predict.iloc[-1, 0] if not do_predict.empty else 0
        else:
            last_do = int(do_predict[-1]) if len(do_predict) > 0 else 0

        # ── Sticky veto check ─────────────────────────────────────────────────
        # If a REJECT/HOLD was issued in the last COOLDOWN_SECONDS, apply it to
        # ALL high-confidence signals during the veto window — even across new
        # candles.  (v3 bug: rejection only applied to the prediction at the
        # moment of the LLM call; next candle bypassed the filter via raw LGBM.)
        cached = self._llm_verdict_cache.get(pair)
        if cached is not None:
            cached_verdict, cached_ts = cached
            elapsed = time.time() - cached_ts
            if elapsed < COOLDOWN_SECONDS:
                if (
                    cached_verdict in ("REJECT", "HOLD")
                    and last_do == 1
                    and last_class in ("L", "S")
                    and confidence >= CONFIDENCE_THRESHOLD
                ):
                    pred_df.at[pred_df.index[-1], pred_col] = "hold"
                    for prob_c in ("L", "S"):
                        if prob_c in pred_df.columns:
                            pred_df.at[pred_df.index[-1], prob_c] = 0.5
                    remaining = int(COOLDOWN_SECONDS - elapsed)
                    logger.debug(
                        f"[FinBuddyLLMModel] {pair}: sticky {cached_verdict} applied "
                        f"({remaining}s remaining in veto window)"
                    )
                return pred_df, do_predict
            # Veto window expired — clear cache
            del self._llm_verdict_cache[pair]

        # ── Fresh LLM call ────────────────────────────────────────────────────
        if (
            last_do == 1
            and last_class in ("L", "S")
            and confidence >= CONFIDENCE_THRESHOLD
            and self._is_cooldown_elapsed(pair)
        ):
            lgbm_proxy = (last_prob - 0.5) * 2.0
            if last_class == "S":
                lgbm_proxy = -abs(lgbm_proxy)
            context = self._build_market_context(unfiltered_df, pair, lgbm_proxy)
            outcome = self._confirm_via_llm(pair, context)

            # Cache REJECT/HOLD so the veto sticks for the full cooldown window.
            # CONFIRM is NOT cached: subsequent candles can fire on raw LightGBM
            # (we confirmed the direction; no need to block the pair for 60 min).
            if outcome in ("REJECT", "HOLD"):
                self._llm_verdict_cache[pair] = (outcome, time.time())
                pred_df.at[pred_df.index[-1], pred_col] = "hold"
                # Also zero out the probability columns so the strategy's 0.60 threshold is not met.
                # The strategy gates on "L"/"S" proba columns, not on the label — setting
                # the label to "hold" alone does nothing without this.
                for prob_c in ("L", "S"):
                    if prob_c in pred_df.columns:
                        pred_df.at[pred_df.index[-1], prob_c] = 0.5
                logger.info(
                    f"[FinBuddyLLMModel] {pair}: {outcome} — suppressed {last_class} signal "
                    f"(prob reset to 0.5, was {last_prob:.3f})"
                )
            else:
                logger.info(f"[FinBuddyLLMModel] {pair}: CONFIRM — keeping {last_class} (prob={last_prob:.3f})")

        return pred_df, do_predict

    def _confirm_via_llm(self, pair: str, context: str) -> str:
        """Call central llm_client with task=signal. Returns CONFIRM/REJECT/HOLD."""
        raw = call_llm(
            context,
            system=_SIGNAL_SYSTEM,
            task="signal",
            model="auto",
            max_tokens=10,
            timeout=15,
        )
        if not raw:
            return "HOLD"
        outcome = raw.strip().upper().split()[0]
        if outcome not in ("CONFIRM", "REJECT", "HOLD"):
            outcome = "HOLD"
        self._last_llm_call[pair] = time.time()
        return outcome

    def _build_market_context(self, df: DataFrame, pair: str, lgbm_pred: float) -> str:
        if df.empty:
            return f"Pair: {pair} | No candle data | ML prediction: {lgbm_pred:.4f}"
        last = df.iloc[-1]
        direction = "LONG (price expected to rise)" if lgbm_pred > 0 else "SHORT (price expected to fall)"
        strength  = "STRONG" if abs(lgbm_pred) > 0.012 else "MODERATE"

        def safe(col, fmt=".2f"):
            try:
                v = last.get(col)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return "N/A"
                return format(float(v), fmt)
            except Exception:
                return "N/A"

        close_v = safe("close")
        ema50_v = safe("ema_50")
        ema_pos = "ABOVE" if (
            close_v != "N/A" and ema50_v != "N/A" and float(close_v) > float(ema50_v)
        ) else "BELOW"

        return "\n".join([
            "=== FinBuddy Signal Review ===",
            f"Pair: {pair}  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Direction: {direction}  |  Strength: {strength}",
            f"Price: {close_v}  |  EMA50: {ema50_v} ({ema_pos})",
            f"RSI: {safe('rsi_14', '.1f')}  |  MACD hist: {safe('macd_hist')}",
            f"BB pct: {safe('bb_pct')}  |  ATR ratio: {safe('atr_ratio', '.4f')}",
            f"ML pred: {lgbm_pred*100:.3f}% expected change",
            f"Should FinBuddy execute the {direction.split()[0]} signal?",
        ])

    def _is_cooldown_elapsed(self, pair: str) -> bool:
        elapsed = time.time() - self._last_llm_call.get(pair, 0.0)
        if elapsed < COOLDOWN_SECONDS:
            logger.debug(f"[FinBuddyLLMModel] {pair}: cooldown {int(COOLDOWN_SECONDS-elapsed)}s remaining")
            return False
        return True
