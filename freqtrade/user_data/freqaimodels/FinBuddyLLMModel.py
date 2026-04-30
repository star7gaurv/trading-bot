# pragma pylint: disable=missing-docstring, invalid-name
"""
FinBuddyLLMModel — Custom FreqAI Model (Task 1.2)
==================================================
Architecture:
  1. LightGBM trains on OHLCV + TA indicators (inherited from LightGBMRegressor)
  2. predict() checks signal confidence (abs prediction > threshold)
  3. High-confidence signals get Groq Llama 3.3 70B confirmation
  4. Final signal = LightGBM * 0.6 + LLM_factor * 0.4

Rate limiting: per-pair cooldown (60 min) to stay inside Groq free tier (6000 req/day).
Fallback: if Groq fails or times out, LightGBM signal is used unchanged.

Activation:
  config.json → "freqaimodel": "FinBuddyLLMModel"
  docker-compose.yml → environment: - GROQ_API_KEY=gsk_xxxx
"""

import logging
import os
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from pandas import DataFrame

try:
    from freqtrade.freqai.prediction_models.LightGBMRegressor import LightGBMRegressor
    BASE_CLASS = LightGBMRegressor
except ImportError:
    # Fallback if LightGBMRegressor path differs across versions
    from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
    BASE_CLASS = BaseRegressionModel

try:
    import requests
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"
CONFIDENCE_THRESHOLD = 0.006   # 0.6% predicted move to trigger LLM call
LGBM_WEIGHT  = 0.60            # LightGBM contribution to blended signal
LLM_WEIGHT   = 0.40            # LLM contribution to blended signal
COOLDOWN_SECONDS = 3600        # 60 min per-pair cooldown (rate limiting)
GROQ_TIMEOUT = 4               # seconds — never block a trade decision

# ── LLM outcome → signal multiplier ───────────────────────────────────────────
LLM_MULTIPLIERS = {
    "CONFIRM": 1.30,   # LLM agrees → amplify signal
    "REJECT":  0.15,   # LLM disagrees → dampen hard (near-zero)
    "HOLD":    0.50,   # LLM unsure → dampen moderately
}


class FinBuddyLLMModel(BASE_CLASS):
    """
    Custom FreqAI model: LightGBM + Groq LLM confirmation.
    Inherits all training/feature-engineering from LightGBMRegressor.
    Only predict() is overridden to add the LLM layer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
        # Per-pair last Groq call timestamp {pair: epoch_seconds}
        self._last_groq_call: Dict[str, float] = {}
        # Per-pair last LLM outcome cache {pair: (outcome_str, epoch_seconds)}
        self._llm_cache: Dict[str, Tuple[str, float]] = {}

        if not self._groq_api_key:
            logger.warning(
                "[FinBuddyLLMModel] GROQ_API_KEY not set. "
                "LLM confirmation disabled — LightGBM signal used as-is."
            )
        if requests is None:
            logger.warning(
                "[FinBuddyLLMModel] 'requests' library not available. "
                "LLM confirmation disabled."
            )

    # ── Core predict override ─────────────────────────────────────────────────

    def predict(
        self, unfiltered_df: DataFrame, dk: Any, **kwargs
    ) -> Tuple[DataFrame, DataFrame]:
        """
        Step 1: Run LightGBM prediction (parent class).
        Step 2: For high-confidence candles, call Groq for confirmation.
        Step 3: Blend signals and return.
        """
        # ── 1. LightGBM prediction ────────────────────────────────────────────
        pred_df, do_predict = super().predict(unfiltered_df, dk, **kwargs)

        # ── 2. LLM confirmation (only if key present + requests available) ────
        if not self._groq_api_key or requests is None:
            return pred_df, do_predict

        pair = dk.pair if hasattr(dk, "pair") else "UNKNOWN"
        target_col = "&-s_close"  # standard FreqAI target column name

        if target_col not in pred_df.columns:
            logger.debug(f"[FinBuddyLLMModel] {pair}: target col '{target_col}' not found")
            return pred_df, do_predict

        # Work on last candle (most recent prediction)
        last_pred = pred_df[target_col].iloc[-1]
        last_do_predict = do_predict.iloc[-1, 0] if not do_predict.empty else 0

        # Only call LLM if:
        #   a) model is trained (do_predict == 1)
        #   b) signal is above confidence threshold (not a weak prediction)
        #   c) per-pair cooldown has elapsed
        if (
            last_do_predict == 1
            and abs(last_pred) >= CONFIDENCE_THRESHOLD
            and self._is_cooldown_elapsed(pair)
        ):
            market_context = self._build_market_context(
                unfiltered_df, pair, last_pred
            )
            llm_outcome = self._call_groq(pair, market_context)

            if llm_outcome in LLM_MULTIPLIERS:
                multiplier = LLM_MULTIPLIERS[llm_outcome]
                # Blended signal = LightGBM contribution + LLM-scaled contribution
                # When LLM CONFIRMS: signal grows (max 30% boost)
                # When LLM REJECTS: signal is almost nullified
                blended = (
                    last_pred * LGBM_WEIGHT
                    + last_pred * multiplier * LLM_WEIGHT
                )
                pred_df.at[pred_df.index[-1], target_col] = blended
                logger.info(
                    f"[FinBuddyLLMModel] {pair} | "
                    f"LGBM={last_pred:.4f} | LLM={llm_outcome} (x{multiplier}) | "
                    f"Blended={blended:.4f}"
                )
            else:
                logger.warning(
                    f"[FinBuddyLLMModel] {pair}: Groq returned unexpected outcome '{llm_outcome}', "
                    f"using raw LightGBM signal {last_pred:.4f}"
                )
        else:
            reason = (
                f"do_predict={last_do_predict}"
                if last_do_predict != 1
                else f"abs({last_pred:.4f}) < threshold={CONFIDENCE_THRESHOLD}"
                if abs(last_pred) < CONFIDENCE_THRESHOLD
                else "cooldown active"
            )
            logger.debug(
                f"[FinBuddyLLMModel] {pair}: LLM skipped ({reason}), "
                f"LGBM={last_pred:.4f}"
            )

        return pred_df, do_predict

    # ── Groq API call ─────────────────────────────────────────────────────────

    def _call_groq(self, pair: str, context: str) -> str:
        """
        Call Groq Llama 3.3 70B with market context.
        Returns: 'CONFIRM', 'REJECT', or 'HOLD'.
        Falls back to 'HOLD' on any error.
        """
        prompt = (
            f"You are FinBuddy, a crypto trading signal validator. "
            f"A LightGBM ML model has generated a trading signal. "
            f"Your job: review the market context and decide if the signal is valid.\n\n"
            f"{context}\n\n"
            f"Respond with EXACTLY one word:\n"
            f"- CONFIRM: signal looks valid, market context supports it\n"
            f"- REJECT: signal looks wrong, context contradicts it\n"
            f"- HOLD: insufficient evidence, too uncertain\n\n"
            f"Your response (one word only):"
        )

        try:
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {self._groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1,
                },
                timeout=GROQ_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip().upper()
            # Extract first word (defensive parsing)
            outcome = raw.split()[0] if raw else "HOLD"
            if outcome not in LLM_MULTIPLIERS:
                outcome = "HOLD"

            # Update cooldown timer
            self._last_groq_call[pair] = time.time()
            logger.info(
                f"[FinBuddyLLMModel] Groq call for {pair} → {outcome} "
                f"(raw: '{raw}')"
            )
            return outcome

        except requests.exceptions.Timeout:
            logger.warning(
                f"[FinBuddyLLMModel] {pair}: Groq timeout after {GROQ_TIMEOUT}s — using HOLD"
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            logger.warning(
                f"[FinBuddyLLMModel] {pair}: Groq HTTP {status} error — using HOLD"
            )
            if status == 429:
                # Rate limited — extend cooldown to 2 hours
                self._last_groq_call[pair] = time.time() + COOLDOWN_SECONDS
                logger.warning(
                    f"[FinBuddyLLMModel] {pair}: Rate limited by Groq, "
                    f"extending cooldown to 2 hours"
                )
        except Exception as e:
            logger.warning(
                f"[FinBuddyLLMModel] {pair}: Groq call failed ({type(e).__name__}: {e}) — using HOLD"
            )

        return "HOLD"  # Safe fallback — never block a trade on API failure

    # ── Market context builder ────────────────────────────────────────────────

    def _build_market_context(self, df: DataFrame, pair: str, lgbm_pred: float) -> str:
        """
        Build a concise market context string for the LLM prompt.
        Uses last available candle data.
        """
        if df.empty:
            return f"Pair: {pair} | No candle data available | ML prediction: {lgbm_pred:.4f}"

        last = df.iloc[-1]
        direction = "LONG (price expected to rise)" if lgbm_pred > 0 else "SHORT (price expected to fall)"
        strength = "STRONG" if abs(lgbm_pred) > 0.012 else "MODERATE"

        # Safely get indicator values with fallbacks
        def safe_get(col, fmt=".2f", default="N/A"):
            try:
                val = last.get(col, None)
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    return default
                return format(float(val), fmt)
            except Exception:
                return default

        context_lines = [
            f"=== FinBuddy Signal Review ===",
            f"Pair:         {pair}",
            f"Timestamp:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Timeframe:    15m",
            f"",
            f"--- ML Signal ---",
            f"Direction:    {direction}",
            f"Strength:     {strength}",
            f"Predicted %:  {lgbm_pred * 100:.3f}% price change in next 45 min",
            f"",
            f"--- Market State ---",
            f"Price:        {safe_get('close')}",
            f"RSI(14):      {safe_get('rsi_14', '.1f')} (overbought >70, oversold <30)",
            f"MACD hist:    {safe_get('macd_hist')} (positive=bullish momentum)",
            f"EMA trend:    price {'ABOVE' if safe_get('ema_50') != 'N/A' and float(safe_get('close')) > float(safe_get('ema_50')) else 'BELOW'} EMA50",
            f"BB position:  {safe_get('bb_pct', '.2f')} (0=lower band, 1=upper band)",
            f"Volume:       {safe_get('volume_change', '.2f')}x average",
            f"Price 24h:    {safe_get('price_position', '.2f')} (0=24h low, 1=24h high)",
            f"",
            f"Based on this context, should FinBuddy execute the {direction.split()[0]} signal?",
        ]
        return "\n".join(context_lines)

    # ── Rate limiting helpers ─────────────────────────────────────────────────

    def _is_cooldown_elapsed(self, pair: str) -> bool:
        """Returns True if enough time has passed since last Groq call for this pair."""
        last_call = self._last_groq_call.get(pair, 0.0)
        elapsed = time.time() - last_call
        if elapsed < COOLDOWN_SECONDS:
            logger.debug(
                f"[FinBuddyLLMModel] {pair}: Groq cooldown active "
                f"({int(COOLDOWN_SECONDS - elapsed)}s remaining)"
            )
            return False
        return True
