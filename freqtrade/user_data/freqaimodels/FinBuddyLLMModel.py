# pragma pylint: disable=missing-docstring, invalid-name
"""
FinBuddyLLMModel — Custom FreqAI Model v2
==========================================
Architecture:
  1. LightGBM trains on OHLCV + TA indicators (inherited from LightGBMRegressor)
  2. predict() checks signal confidence (abs prediction > threshold)
  3. High-confidence signals get LLM confirmation via WATERFALL fallback chain:
       Primary  : xAI Grok   (GROK_MODEL env var, default grok-3-mini)
       Secondary: Groq Llama (GROQ_API_KEY env var, llama-3.3-70b-versatile — free 6000 req/day)
       Fallback : raw LightGBM signal (no LLM, signal unchanged)
  4. Final signal = LightGBM * 0.6 + LLM_factor * 0.4

Waterfall logic:
  - Try xAI Grok first. If XAI_API_KEY missing/fails → try Groq.
  - Try Groq next. If GROQ_API_KEY missing/fails → use raw LightGBM.
  - Any API call logs which provider was used or why it was skipped.

Rate limiting: per-pair cooldown (60 min) — shared across both providers.
The cooldown is reset after any SUCCESSFUL call (either provider).

TODO (Round 4 — after Round 3 completes):
  - Change set_freqai_targets() in FinBuddyFreqAI.py from .mean() to .max()
    to predict Max Favorable Excursion (MFE) instead of average future price.
    This directly targets the avg-loser > avg-winner problem identified in Rounds 1-3.

Activation:
  config.json  → "freqaimodel": "FinBuddyLLMModel"
  docker-compose.yml → environment:
    - XAI_API_KEY=xai_xxxx          (optional — Grok primary)
    - GROK_MODEL=grok-3-mini        (optional — default grok-3-mini)
    - GROQ_API_KEY=gsk_xxxx         (optional — Groq fallback, Llama 3.3 70B)
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from pandas import DataFrame

try:
    from freqtrade.freqai.prediction_models.LightGBMRegressor import LightGBMRegressor
    BASE_CLASS = LightGBMRegressor
except ImportError:
    from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
    BASE_CLASS = BaseRegressionModel

try:
    import requests
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)

# ── API endpoints ──────────────────────────────────────────────────────────────
XAI_API_URL   = "https://api.x.ai/v1/chat/completions"
GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"

# ── Defaults (overridden by env vars) ─────────────────────────────────────────
DEFAULT_XAI_MODEL  = "grok-3-mini"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Thresholds & weights ───────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.006   # abs prediction must exceed 0.6% to trigger LLM
LGBM_WEIGHT          = 0.60
LLM_WEIGHT           = 0.40
COOLDOWN_SECONDS     = 3600    # 60-min per-pair cooldown (shared, any provider resets it)
XAI_TIMEOUT          = 8       # seconds
GROQ_TIMEOUT         = 5       # Groq is faster (free tier, ~200ms confirmed)

# ── LLM outcome → signal multiplier ───────────────────────────────────────────
LLM_MULTIPLIERS = {
    "CONFIRM": 1.30,   # LLM agrees → amplify signal up to 30%
    "REJECT":  0.15,   # LLM disagrees → dampen to near-zero
    "HOLD":    0.50,   # LLM unsure → dampen moderately
}


class FinBuddyLLMModel(BASE_CLASS):
    """
    Custom FreqAI model: LightGBM + LLM confirmation with waterfall fallback.
    Inherits all training / feature-engineering from LightGBMRegressor.
    Only predict() is overridden to add the LLM confirmation layer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # ── API keys & model names from environment ────────────────────────────
        self._xai_api_key: str  = os.environ.get("XAI_API_KEY", "")
        self._xai_model: str    = os.environ.get("GROK_MODEL", DEFAULT_XAI_MODEL)
        self._groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
        self._groq_model: str   = DEFAULT_GROQ_MODEL

        # ── Per-pair state ─────────────────────────────────────────────────────
        self._last_llm_call: Dict[str, float] = {}   # pair → epoch_seconds of last successful call

        # ── Startup diagnostics ────────────────────────────────────────────────
        if not self._xai_api_key and not self._groq_api_key:
            logger.warning(
                "[FinBuddyLLMModel] ⚠️  Neither XAI_API_KEY nor GROQ_API_KEY is set. "
                "LLM confirmation fully disabled — LightGBM signal will be used as-is."
            )
        else:
            providers = []
            if self._xai_api_key:
                providers.append(f"xAI Grok ({self._xai_model}) [PRIMARY]")
            if self._groq_api_key:
                providers.append(f"Groq Llama ({self._groq_model}) [FALLBACK]")
            logger.info(
                f"[FinBuddyLLMModel] ✅ LLM waterfall chain ready: {' → '.join(providers)} → raw LGBM"
            )

        if requests is None:
            logger.warning(
                "[FinBuddyLLMModel] 'requests' library not available. "
                "All LLM calls disabled — LightGBM signal used as-is."
            )

    # ── Core predict override ──────────────────────────────────────────────────

    def predict(
        self, unfiltered_df: DataFrame, dk: Any, **kwargs
    ) -> Tuple[DataFrame, DataFrame]:
        """
        Step 1: LightGBM prediction (parent).
        Step 2: For high-confidence candles, call LLM waterfall.
        Step 3: Blend and return.
        """
        # 1. LightGBM prediction
        pred_df, do_predict = super().predict(unfiltered_df, dk, **kwargs)

        # 2. LLM confirmation gate
        if requests is None:
            return pred_df, do_predict

        llm_available = bool(self._xai_api_key or self._groq_api_key)
        if not llm_available:
            return pred_df, do_predict

        pair = dk.pair if hasattr(dk, "pair") else "UNKNOWN"
        target_col = "&-s_close"

        if target_col not in pred_df.columns:
            logger.debug(f"[FinBuddyLLMModel] {pair}: target col '{target_col}' not found")
            return pred_df, do_predict

        last_pred = pred_df[target_col].iloc[-1]
        if hasattr(do_predict, "iloc"):
            last_do_predict = do_predict.iloc[-1, 0] if not do_predict.empty else 0
        else:
            last_do_predict = int(do_predict[-1]) if len(do_predict) > 0 else 0

        # Gate: only call LLM if model is trained, signal is strong, cooldown elapsed
        if (
            last_do_predict == 1
            and abs(last_pred) >= CONFIDENCE_THRESHOLD
            and self._is_cooldown_elapsed(pair)
        ):
            market_context = self._build_market_context(unfiltered_df, pair, last_pred)
            llm_outcome, provider_used = self._call_llm_waterfall(pair, market_context)

            if llm_outcome in LLM_MULTIPLIERS:
                multiplier = LLM_MULTIPLIERS[llm_outcome]
                blended = last_pred * LGBM_WEIGHT + last_pred * multiplier * LLM_WEIGHT
                pred_df.at[pred_df.index[-1], target_col] = blended
                logger.info(
                    f"[FinBuddyLLMModel] {pair} | Provider={provider_used} | "
                    f"LGBM={last_pred:.4f} | LLM={llm_outcome} (x{multiplier}) | "
                    f"Blended={blended:.4f}"
                )
            else:
                logger.warning(
                    f"[FinBuddyLLMModel] {pair}: unexpected outcome '{llm_outcome}' from {provider_used}, "
                    f"using raw LGBM={last_pred:.4f}"
                )
        else:
            if last_do_predict != 1:
                reason = f"do_predict={last_do_predict}"
            elif abs(last_pred) < CONFIDENCE_THRESHOLD:
                reason = f"abs({last_pred:.4f}) < threshold={CONFIDENCE_THRESHOLD}"
            else:
                remaining = int(COOLDOWN_SECONDS - (time.time() - self._last_llm_call.get(pair, 0)))
                reason = f"cooldown active ({remaining}s remaining)"
            logger.debug(
                f"[FinBuddyLLMModel] {pair}: LLM skipped ({reason}), LGBM={last_pred:.4f}"
            )

        return pred_df, do_predict

    # ── Waterfall: try xAI → try Groq → return HOLD ───────────────────────────

    def _call_llm_waterfall(self, pair: str, context: str) -> Tuple[str, str]:
        """
        Try providers in order. Returns (outcome, provider_name).
        Falls back to ("HOLD", "none") if all providers fail.
        """
        # 1. xAI Grok (primary)
        if self._xai_api_key:
            outcome = self._call_provider(
                pair=pair,
                context=context,
                api_url=XAI_API_URL,
                api_key=self._xai_api_key,
                model=self._xai_model,
                provider_name="xAI-Grok",
                timeout=XAI_TIMEOUT,
            )
            if outcome != "__FAILED__":
                self._last_llm_call[pair] = time.time()
                return outcome, "xAI-Grok"
            logger.info(f"[FinBuddyLLMModel] {pair}: xAI Grok failed → trying Groq fallback")
        else:
            logger.debug(f"[FinBuddyLLMModel] {pair}: XAI_API_KEY not set, skipping Grok")

        # 2. Groq Llama (fallback)
        if self._groq_api_key:
            outcome = self._call_provider(
                pair=pair,
                context=context,
                api_url=GROQ_API_URL,
                api_key=self._groq_api_key,
                model=self._groq_model,
                provider_name="Groq-Llama",
                timeout=GROQ_TIMEOUT,
            )
            if outcome != "__FAILED__":
                self._last_llm_call[pair] = time.time()
                return outcome, "Groq-Llama"
            logger.warning(f"[FinBuddyLLMModel] {pair}: Groq also failed → using raw LGBM")
        else:
            logger.debug(f"[FinBuddyLLMModel] {pair}: GROQ_API_KEY not set, skipping Groq")

        # 3. Both failed — safe fallback, don't block trade
        return "HOLD", "none"

    # ── Generic provider caller ────────────────────────────────────────────────

    def _call_provider(
        self,
        pair: str,
        context: str,
        api_url: str,
        api_key: str,
        model: str,
        provider_name: str,
        timeout: int,
    ) -> str:
        """
        Call a single OpenAI-compatible API endpoint.
        Returns 'CONFIRM' / 'REJECT' / 'HOLD' on success, or '__FAILED__' on error.
        """
        prompt = (
            "You are FinBuddy, a crypto trading signal validator. "
            "A LightGBM ML model has generated a trading signal. "
            "Review the market context and decide if the signal is valid.\n\n"
            f"{context}\n\n"
            "Respond with EXACTLY one word:\n"
            "- CONFIRM: signal looks valid, market context supports it\n"
            "- REJECT: signal looks wrong, context contradicts it\n"
            "- HOLD: insufficient evidence, too uncertain\n\n"
            "Your response (one word only):"
        )

        try:
            response = requests.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip().upper()
            outcome = raw.split()[0] if raw else "HOLD"
            if outcome not in LLM_MULTIPLIERS:
                outcome = "HOLD"
            logger.info(
                f"[FinBuddyLLMModel] {pair} [{provider_name}] → {outcome} (raw: '{raw}')"
            )
            return outcome

        except requests.exceptions.Timeout:
            logger.warning(
                f"[FinBuddyLLMModel] {pair} [{provider_name}]: timeout after {timeout}s"
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            logger.warning(
                f"[FinBuddyLLMModel] {pair} [{provider_name}]: HTTP {status} error"
            )
            if status == 429:
                # Rate limited — extend cooldown by 2 hours for this pair
                self._last_llm_call[pair] = time.time() + COOLDOWN_SECONDS
                logger.warning(
                    f"[FinBuddyLLMModel] {pair} [{provider_name}]: rate limited, cooldown extended 2h"
                )
        except Exception as e:
            logger.warning(
                f"[FinBuddyLLMModel] {pair} [{provider_name}]: failed ({type(e).__name__}: {e})"
            )

        return "__FAILED__"

    # ── Market context builder ─────────────────────────────────────────────────

    def _build_market_context(self, df: DataFrame, pair: str, lgbm_pred: float) -> str:
        if df.empty:
            return f"Pair: {pair} | No candle data | ML prediction: {lgbm_pred:.4f}"

        last = df.iloc[-1]
        direction = "LONG (price expected to rise)" if lgbm_pred > 0 else "SHORT (price expected to fall)"
        strength = "STRONG" if abs(lgbm_pred) > 0.012 else "MODERATE"

        def safe_get(col, fmt=".2f", default="N/A"):
            try:
                val = last.get(col, None)
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return default
                return format(float(val), fmt)
            except Exception:
                return default

        close_val = safe_get("close")
        ema50_val = safe_get("ema_50")
        ema_trend = "ABOVE" if (
            close_val != "N/A" and ema50_val != "N/A"
            and float(close_val) > float(ema50_val)
        ) else "BELOW"

        lines = [
            "=== FinBuddy Signal Review ===",
            f"Pair:         {pair}",
            f"Timestamp:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Timeframe:    15m",
            "",
            "--- ML Signal ---",
            f"Direction:    {direction}",
            f"Strength:     {strength}",
            f"Predicted %:  {lgbm_pred * 100:.3f}% price change in next 45 min",
            "",
            "--- Market State ---",
            f"Price:        {close_val}",
            f"RSI(14):      {safe_get('rsi_14', '.1f')} (overbought >70, oversold <30)",
            f"MACD hist:    {safe_get('macd_hist')} (positive=bullish momentum)",
            f"EMA trend:    price {ema_trend} EMA50",
            f"BB position:  {safe_get('bb_pct', '.2f')} (0=lower band, 1=upper band)",
            f"ATR ratio:    {safe_get('atr_ratio', '.4f')} (volatility proxy)",
            "",
            f"Based on this context, should FinBuddy execute the {direction.split()[0]} signal?",
        ]
        return "\n".join(lines)

    # ── Cooldown helper ────────────────────────────────────────────────────────

    def _is_cooldown_elapsed(self, pair: str) -> bool:
        last_call = self._last_llm_call.get(pair, 0.0)
        elapsed = time.time() - last_call
        if elapsed < COOLDOWN_SECONDS:
            logger.debug(
                f"[FinBuddyLLMModel] {pair}: cooldown active "
                f"({int(COOLDOWN_SECONDS - elapsed)}s remaining)"
            )
            return False
        return True
