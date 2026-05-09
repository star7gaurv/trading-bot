#!/usr/bin/env python3
"""
FinBuddy central LLM client.

Single import point for all AI calls in the project.  Handles:
  - provider routing (pass a specific model name or "auto")
  - per-task fallback chains (research → reasoning → signal → general)
  - key loading from env vars and freqtrade/.env
  - unified logging

Usage:
    from llm_client import call_llm

    text = call_llm("Analyse this data...", task="research")
    text = call_llm("Is this signal valid?", model="grok-3-mini", task="signal")

Supported model aliases:
    grok-3-mini       xAI Grok-3-Mini       (XAI_API_KEY)
    gemini-2.5-flash  Google Gemini Flash   (GEMINI_API_KEY)
    deepseek-chat     DeepSeek Chat         (DEEPSEEK_API_KEY)
    deepseek-r1       DeepSeek Reasoner     (DEEPSEEK_API_KEY)
    nvidia-llama      NVIDIA NIM Llama-70B  (NVIDIA_API_KEY)
    groq-llama        Groq Llama-3.3-70B    (GROQ_API_KEY)
    openrouter-free   OpenRouter :free tier (OPENROUTER_API_KEY)

To add a new provider key, add it to freqtrade/.env:
    GEMINI_API_KEY=AIza...
    DEEPSEEK_API_KEY=sk-...
    NVIDIA_API_KEY=nvapi-...
    GROQ_API_KEY=gsk_...
    OPENROUTER_API_KEY=sk-or-...
"""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT = Path("/home/ubuntu/var/www/html/trade")
_ENV_FILE = _ROOT / "freqtrade/.env"

# ── Provider definitions ───────────────────────────────────────────────────────
# Each entry: (api_url, key_env_var, model_id, api_style)
# api_style: "openai" (standard ChatCompletion) or "gemini" (Google REST)
_PROVIDERS = {
    "grok-3-mini": (
        "https://api.x.ai/v1/chat/completions",
        "XAI_API_KEY",
        "grok-3-mini",
        "openai",
    ),
    "gemini-2.5-flash": (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-latest:generateContent",
        "GEMINI_API_KEY",
        "",  # key passed as query param for Gemini
        "gemini",
    ),
    "deepseek-chat": (
        "https://api.deepseek.com/v1/chat/completions",
        "DEEPSEEK_API_KEY",
        "deepseek-chat",
        "openai",
    ),
    "deepseek-r1": (
        "https://api.deepseek.com/v1/chat/completions",
        "DEEPSEEK_API_KEY",
        "deepseek-reasoner",
        "openai",
    ),
    "nvidia-llama": (
        "https://integrate.api.nvidia.com/v1/chat/completions",
        "NVIDIA_API_KEY",
        "meta/llama-3.1-70b-instruct",
        "openai",
    ),
    "groq-llama": (
        "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY",
        "llama-3.3-70b-versatile",
        "openai",
    ),
    "openrouter-free": (
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        "meta-llama/llama-3.1-8b-instruct:free",
        "openai",
    ),
}

# ── Per-task fallback chains ───────────────────────────────────────────────────
# Order = preference.  Providers with missing keys are silently skipped.
_TASK_CHAINS: dict[str, list[str]] = {
    # Gemini Flash: huge free context window, great for summarising research text
    "research":  ["gemini-2.5-flash", "deepseek-chat", "nvidia-llama", "grok-3-mini", "groq-llama", "openrouter-free"],
    # DeepSeek-R1: dedicated reasoning model → ideal for hypothesis generation
    "reasoning": ["deepseek-r1", "grok-3-mini", "nvidia-llama", "gemini-2.5-flash", "groq-llama", "openrouter-free"],
    # Grok-3-Mini: project default for low-latency signal confirmation
    "signal":    ["grok-3-mini", "deepseek-chat", "gemini-2.5-flash", "nvidia-llama", "groq-llama", "openrouter-free"],
    "general":   ["grok-3-mini", "gemini-2.5-flash", "deepseek-chat", "nvidia-llama", "groq-llama", "openrouter-free"],
}


# ── Key loader ─────────────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    """Load API keys: environment first, then freqtrade/.env as supplement."""
    keys: dict[str, str] = {}
    # Read .env file
    try:
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
    except Exception:
        pass
    # Environment overrides file
    keys.update({k: v for k, v in os.environ.items()})
    return keys


# ── OpenAI-compatible call ─────────────────────────────────────────────────────

def _call_openai_compat(
    url: str,
    api_key: str,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
) -> Optional[str]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:200]
        except Exception:
            pass
        if e.code == 403:
            logger.info(f"[llm_client] 403 from {url} — account likely needs credits. body={body}")
        elif e.code == 429:
            logger.info(f"[llm_client] 429 rate-limit from {url}")
        else:
            logger.info(f"[llm_client] HTTP {e.code} from {url}: {body}")
        return None
    except Exception as e:
        logger.info(f"[llm_client] {type(e).__name__} calling {url}: {e}")
        return None


# ── Gemini call ────────────────────────────────────────────────────────────────

def _call_gemini(
    api_key: str,
    system: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
) -> Optional[str]:
    base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-latest:generateContent"
    url = f"{base_url}?key={api_key}"

    body: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4},
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}

    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        body_txt = ""
        try:
            body_txt = e.read().decode()[:200]
        except Exception:
            pass
        logger.info(f"[llm_client] Gemini HTTP {e.code}: {body_txt}")
        return None
    except Exception as e:
        logger.info(f"[llm_client] Gemini {type(e).__name__}: {e}")
        return None


# ── Single provider dispatcher ─────────────────────────────────────────────────

def _try_provider(
    model_alias: str,
    system: str,
    prompt: str,
    max_tokens: int,
    timeout: int,
    keys: dict[str, str],
) -> Optional[str]:
    if model_alias not in _PROVIDERS:
        logger.warning(f"[llm_client] Unknown model alias '{model_alias}'")
        return None

    url, key_var, model_id, style = _PROVIDERS[model_alias]
    api_key = keys.get(key_var, "")
    if not api_key:
        logger.debug(f"[llm_client] Skipping {model_alias}: {key_var} not set")
        return None

    logger.debug(f"[llm_client] Trying {model_alias} ({model_id or 'gemini'})")

    if style == "gemini":
        return _call_gemini(api_key, system, prompt, max_tokens, timeout)
    else:
        return _call_openai_compat(url, api_key, model_id, system, prompt, max_tokens, timeout)


# ── Public API ─────────────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    system: str = "",
    model: str = "auto",
    max_tokens: int = 800,
    task: str = "general",
    timeout: int = 30,
) -> str:
    """
    Call an LLM with automatic provider routing and fallback.

    Args:
        prompt:     The user message / question.
        system:     Optional system prompt.
        model:      Model alias (see module docstring) or "auto".
                    "auto" uses the per-task fallback chain.
        max_tokens: Maximum tokens in the response.
        task:       "research" | "reasoning" | "signal" | "general"
                    Used to pick the fallback chain when model="auto".
        timeout:    Per-provider HTTP timeout in seconds.

    Returns:
        The model's text response, or "" if all providers fail.
    """
    keys = _load_env()

    if model != "auto":
        # Caller specified a model — try it, then fall through the task chain
        result = _try_provider(model, system, prompt, max_tokens, timeout, keys)
        if result:
            logger.info(f"[llm_client] {model} responded ({len(result)} chars)")
            return result
        logger.info(f"[llm_client] {model} failed, falling through {task} chain")

    chain = _TASK_CHAINS.get(task, _TASK_CHAINS["general"])
    for alias in chain:
        if model != "auto" and alias == model:
            continue  # already tried above
        result = _try_provider(alias, system, prompt, max_tokens, timeout, keys)
        if result:
            logger.info(f"[llm_client] {alias} responded ({len(result)} chars) [task={task}]")
            return result

    logger.warning(f"[llm_client] All providers exhausted for task={task}. Returning empty string.")
    return ""


def available_providers() -> list[str]:
    """Return list of model aliases that have a key configured."""
    keys = _load_env()
    return [alias for alias, (_, key_var, _, _) in _PROVIDERS.items() if keys.get(key_var)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("Configured providers:", available_providers())
    resp = call_llm("Say hello in one sentence.", task="general", max_tokens=50)
    print("Response:", resp or "(no response — all providers failed or no keys configured)")
