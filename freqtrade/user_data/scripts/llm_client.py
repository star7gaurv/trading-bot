#!/usr/bin/env python3
"""
FinBuddy central LLM client.

Two providers, one key each:
  NVIDIA_API_KEY     → https://integrate.api.nvidia.com/v1  (50+ models, free tier)
  OPENROUTER_API_KEY → https://openrouter.ai/api/v1         (:free models, zero cost)

Both use the OpenAI-compatible /chat/completions endpoint.
Keys are read from freqtrade/.env (or environment).

Usage:
    from llm_client import call_llm

    text = call_llm("Analyse this snapshot...", task="research")
    text = call_llm("Generate hypotheses...",   task="reasoning")
    text = call_llm("Is this signal valid?",    task="signal")
    text = call_llm("...", model="nvidia-deepseek-v4-pro")

Supported model aliases:
    nvidia-deepseek-v4-pro     deepseek-ai/deepseek-v4-pro          (NVIDIA)
    nvidia-deepseek-v4-flash   deepseek-ai/deepseek-v4-flash        (NVIDIA)
    nvidia-kimi-k2             moonshotai/kimi-k2-instruct           (NVIDIA)
    nvidia-kimi-k2-thinking    moonshotai/kimi-k2-thinking           (NVIDIA, reasoning)
    nvidia-qwen3-coder         qwen/qwen3-coder-480b-a35b-instruct   (NVIDIA)
    nvidia-mistral-medium      mistralai/mistral-medium-3.5-128b     (NVIDIA)
    nvidia-llama-70b           meta/llama-3.3-70b-instruct           (NVIDIA)
    nvidia-glm-5               z-ai/glm-5.1                          (NVIDIA)
    openrouter-glm-free        z-ai/glm-4.5-air:free                 (OpenRouter)
    openrouter-llama-free      meta-llama/llama-3.1-8b-instruct:free (OpenRouter)
"""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Works on host (/home/ubuntu/...) and inside Docker container (/freqtrade/)
_ENV_CANDIDATES = [
    Path("/home/ubuntu/var/www/html/trade/freqtrade/.env"),
    Path("/freqtrade/user_data/../../../.env"),  # won't exist but safe
]

_NVIDIA_URL     = "https://integrate.api.nvidia.com/v1/chat/completions"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# (url, key_env_var, model_id)
# All providers below VERIFIED working as of 2026-05-09.
# Removed: deepseek-v4-pro/flash (downloadable-only, never respond via API),
#          kimi-k2-thinking (thinking tokens overflow 30s timeout),
#          glm-4.5-air:free (null content), llama-8b:free (404 deprecated),
#          qwen:free (429 provider rate-cap on OpenRouter free tier).
_PROVIDERS: dict[str, tuple[str, str, str]] = {
    # ── NVIDIA NIM (verified working) ───────────────────────────────────────
    "nvidia-kimi-k2":        (_NVIDIA_URL, "NVIDIA_API_KEY", "moonshotai/kimi-k2-instruct"),       # 0.5s
    "nvidia-mistral-medium": (_NVIDIA_URL, "NVIDIA_API_KEY", "mistralai/mistral-medium-3.5-128b"), # 0.3s fastest
    "nvidia-llama-70b":      (_NVIDIA_URL, "NVIDIA_API_KEY", "meta/llama-3.3-70b-instruct"),       # 0.4s
    "nvidia-qwen3-coder":    (_NVIDIA_URL, "NVIDIA_API_KEY", "qwen/qwen3-coder-480b-a35b-instruct"), # ~20s, best JSON
    # ── OpenRouter free tier (verified working 2026-05-09) ───────────────────
    "openrouter-gpt-oss-20b":   (_OPENROUTER_URL, "OPENROUTER_API_KEY", "openai/gpt-oss-20b:free"),              # 1.9s
    "openrouter-gpt-oss-120b":  (_OPENROUTER_URL, "OPENROUTER_API_KEY", "openai/gpt-oss-120b:free"),             # 2.0s best quality
    "openrouter-nemotron-120b": (_OPENROUTER_URL, "OPENROUTER_API_KEY", "nvidia/nemotron-3-super-120b-a12b:free"), # 3.2s
}

# Per-task fallback chains — first available provider wins
_TASK_CHAINS: dict[str, list[str]] = {
    # Research: large context, broad analysis — kimi-k2 strongest general model
    "research": [
        "nvidia-kimi-k2",
        "openrouter-gpt-oss-120b",
        "nvidia-mistral-medium",
        "nvidia-llama-70b",

        "openrouter-gpt-oss-20b",
        "openrouter-nemotron-120b",

    ],
    # Reasoning: structured JSON output — qwen3-coder first (best at JSON despite slow)
    "reasoning": [
        "nvidia-qwen3-coder",
        "nvidia-kimi-k2",
        "openrouter-gpt-oss-120b",
        "nvidia-llama-70b",

        "openrouter-gpt-oss-20b",
        "openrouter-nemotron-120b",

    ],
    # Signal: speed critical — mistral fastest (0.3s), then llama (0.4s)
    "signal": [
        "nvidia-mistral-medium",
        "nvidia-llama-70b",
        "nvidia-kimi-k2",
        "openrouter-gpt-oss-20b",


        "openrouter-gpt-oss-120b",
        "openrouter-nemotron-120b",
    ],
    "general": [
        "nvidia-kimi-k2",
        "nvidia-mistral-medium",
        "nvidia-llama-70b",
        "openrouter-gpt-oss-20b",


        "openrouter-gpt-oss-120b",
        "openrouter-nemotron-120b",
    ],
}


def _load_env() -> dict[str, str]:
    """Load keys: .env file candidates first, then environment overrides."""
    keys: dict[str, str] = {}
    for env_path in _ENV_CANDIDATES:
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip()
        except Exception:
            pass
    # Environment variables always override file values (docker passes keys via env)
    keys.update({k: v for k, v in os.environ.items()})
    return keys


def _call_provider(
    url: str,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
) -> Optional[str]:
    """Single OpenAI-compatible chat/completions call via urllib (no dependencies)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model":      model,
        "messages":   messages,
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }).encode()

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    # OpenRouter requires these for attribution
    if "openrouter.ai" in url:
        headers["HTTP-Referer"] = "https://github.com/star7gaurv/trading-bot"
        headers["X-Title"]      = "FinBuddy"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        if content is None:
            return None
        return content.strip()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if e.code == 429:
            logger.info(f"[llm_client] 429 rate-limit: {model} @ {url[:40]}")
        elif e.code == 403:
            logger.info(f"[llm_client] 403 forbidden: {model} — check key/credits. {body}")
        else:
            logger.info(f"[llm_client] HTTP {e.code}: {model}: {body}")
        return None
    except Exception as e:
        logger.info(f"[llm_client] {type(e).__name__} calling {model}: {e}")
        return None


def _try_alias(
    alias: str,
    system: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
    keys: dict[str, str],
) -> Optional[str]:
    if alias not in _PROVIDERS:
        logger.warning(f"[llm_client] Unknown model alias '{alias}'")
        return None
    url, key_var, model_id = _PROVIDERS[alias]
    api_key = keys.get(key_var, "")
    if not api_key:
        logger.debug(f"[llm_client] Skipping {alias}: {key_var} not configured")
        return None
    logger.debug(f"[llm_client] Trying {alias} ({model_id})")
    return _call_provider(url, api_key, model_id, system, prompt, max_tokens, timeout)


def call_llm(
    prompt: str,
    system: str = "",
    model: str = "auto",
    max_tokens: int = 800,
    task: str = "general",
    timeout: int = 45,
) -> str:
    """
    Call an LLM with automatic provider routing and fallback.

    Args:
        prompt:     User message.
        system:     Optional system prompt.
        model:      Alias from _PROVIDERS or "auto" (uses task chain).
        max_tokens: Max tokens in the response.
        task:       "research" | "reasoning" | "signal" | "general"
        timeout:    Per-call HTTP timeout in seconds.

    Returns:
        Model response text, or "" if all providers fail.
    """
    keys = _load_env()

    if model != "auto":
        result = _try_alias(model, system, prompt, max_tokens, timeout, keys)
        if result:
            logger.info(f"[llm_client] {model} OK ({len(result)} chars)")
            return result
        logger.info(f"[llm_client] {model} failed — falling through {task} chain")

    chain = _TASK_CHAINS.get(task, _TASK_CHAINS["general"])
    for alias in chain:
        if model != "auto" and alias == model:
            continue
        result = _try_alias(alias, system, prompt, max_tokens, timeout, keys)
        if result:
            logger.info(f"[llm_client] {alias} OK ({len(result)} chars) [task={task}]")
            return result

    logger.warning(f"[llm_client] All providers exhausted for task={task}")
    return ""


def available_providers() -> list[str]:
    """Return model aliases that have a key configured."""
    keys = _load_env()
    return [alias for alias, (_, key_var, _) in _PROVIDERS.items() if keys.get(key_var)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    avail = available_providers()
    print(f"Configured providers ({len(avail)}):", avail)
    resp = call_llm(
        "In one sentence, what is the main risk of trading crypto futures?",
        task="general",
        max_tokens=80,
    )
    print("Response:", resp or "(no response)")
