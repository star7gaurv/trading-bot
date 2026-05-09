# pragma pylint: disable=missing-docstring, invalid-name
"""
FinBuddyLLMModel — Custom FreqAI Model v3
==========================================
Architecture:
  1. LightGBM trains on OHLCV + TA indicators (inherited from LightGBMClassifier)
  2. predict() checks signal confidence (prob deviation from 0.5)
  3. High-confidence signals get LLM confirmation via central llm_client.py
     Task chain "signal": nvidia-deepseek-v4-flash → nvidia-glm-5 → nvidia-kimi-k2
                          → nvidia-llama-70b → openrouter-glm-free → raw LGBM
  4. LLM outcome: CONFIRM keeps class / REJECT or HOLD overrides to 'hold'

Keys required (in freqtrade/.env):
  NVIDIA_API_KEY      — primary, 10 free models on NVIDIA NIM
  OPENROUTER_API_KEY  — fallback, :free tier models

Rate limiting: per-pair cooldown (60 min). Resets on any successful LLM call.
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

        pair    = dk.pair if hasattr(dk, "pair") else "UNKNOWN"
        pred_col = "&-s_close"
        if pred_col not in pred_df.columns:
            return pred_df, do_predict

        last_class = pred_df[pred_col].iloc[-1]

        prob_col = next(
            (c for c in ("proba_long", "&-s_close_L") if c in pred_df.columns), None
        )
        last_prob  = float(pred_df[prob_col].iloc[-1]) if prob_col else 0.5
        confidence = abs(last_prob - 0.5)

        if hasattr(do_predict, "iloc"):
            last_do = do_predict.iloc[-1, 0] if not do_predict.empty else 0
        else:
            last_do = int(do_predict[-1]) if len(do_predict) > 0 else 0

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

            if outcome == "CONFIRM":
                logger.info(f"[FinBuddyLLMModel] {pair}: CONFIRM — keeping {last_class} (prob={last_prob:.3f})")
            elif outcome in ("REJECT", "HOLD"):
                pred_df.at[pred_df.index[-1], pred_col] = "hold"
                logger.info(
                    f"[FinBuddyLLMModel] {pair}: {outcome} — overriding {last_class}→hold (prob={last_prob:.3f})"
                )

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
