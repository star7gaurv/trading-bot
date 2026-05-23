"""
telegram_template.py — Unified Telegram message format for ALL FinBuddy subsystems.

The problem this solves: previously each script (brain runner, watchdog, postmortem,
daily summary, etc.) sent its own ad-hoc format. From the user's phone you couldn't
tell at a glance:
  - which subsystem sent it
  - is this success/failure/informational
  - do I need to act, or can I ignore it

This module provides a single source of truth:

    from telegram_template import send, Subsystem, Status

    send(
        subsystem=Subsystem.BRAIN_EXPERIMENT,
        status=Status.OK,
        title="experiment complete",
        fields={"WR": "43.2%", "Profit": "-0.16%", "Trades": "125 (99L/26S)"},
        context=f"{window} · {band} · {rationale}",
        action=None,   # None = info-only; string = "ACTION REQUIRED: …"
    )

Every message uses the same layout:

    [PREFIX_EMOJI] [SUBSYSTEM] · [STATUS_EMOJI] [STATUS_TEXT]
    ─────────────────────────────
    [field rows: key: value]
    ─────────────────────────────
    [context — one short line]
    [action line if any — bold, requires user action]

Subsystem prefixes are STABLE so users learn the visual shorthand:
    🧠 BRAIN      — autonomous hypothesis engine
    🚀 PROMOTION  — brain promotion candidate (needs approval)
    📊 TRADE      — live trade open/close
    🚨 WATCHDOG   — health/error alert
    ☀️ DIGEST     — daily morning summary
    🔬 CAMPAIGN   — multi-experiment campaign
    📈 WALK-FWD   — walk-forward result
    ⚠️ BIAS       — trade bias detector
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from enum import Enum
from typing import Any

# Telegram credentials — env vars take precedence over hardcoded fallback.
# To rotate the token: set TELEGRAM_TOKEN in environment (e.g. /etc/environment
# or freqtrade/.env) and remove the hardcoded fallback once verified.
import os as _os
TELEGRAM_TOKEN = (
    _os.getenv("BRAIN_TELEGRAM_TOKEN")
    or _os.getenv("TELEGRAM_TOKEN")
    or "REDACTED-BRAIN_TELEGRAM_TOKEN"
)
TELEGRAM_CHAT  = _os.getenv("TELEGRAM_CHAT_ID") or "5622292536"


class Subsystem(Enum):
    BRAIN_EXPERIMENT = ("🧠", "BRAIN · EXPERIMENT")
    BRAIN_PROMOTION  = ("🚀", "BRAIN · PROMOTION CANDIDATE")
    BRAIN_CYCLE      = ("🧠", "BRAIN · CYCLE")
    TRADE            = ("📊", "LIVE · TRADE")
    WATCHDOG         = ("🚨", "WATCHDOG")
    DIGEST           = ("☀️", "DAILY DIGEST")
    CAMPAIGN         = ("🔬", "CAMPAIGN")
    WALK_FORWARD     = ("📈", "WALK-FORWARD")
    BIAS             = ("⚠️", "BIAS DETECTOR")
    REGIME           = ("🌡️", "REGIME")


class Status(Enum):
    OK       = ("🟢", "OK")
    INFO     = ("ℹ️", "INFO")
    WARN     = ("🟡", "WARN")
    FAIL     = ("🔴", "FAIL")
    ACTION   = ("✋", "ACTION REQUIRED")
    RUNNING  = ("⏳", "RUNNING")


_DIVIDER = "━━━━━━━━━━━━━━━━━━━"


def format_message(
    subsystem: Subsystem,
    status: Status,
    title: str,
    fields: dict[str, Any] | None = None,
    context: str | None = None,
    action: str | None = None,
    html_context: str | None = None,
) -> str:
    """
    Build a consistent, scannable Telegram message.

    Args:
        subsystem: which FinBuddy subsystem is speaking
        status: OK / INFO / WARN / FAIL / ACTION / RUNNING
        title: one-line subject (lowercase imperative or noun phrase)
        fields: dict of key → value pairs. Values may contain HTML (<code>, <b>, etc.)
                — they are NOT escaped. Keys are always plain text.
        context: short plain-text sentence (wrapped in <i>, special chars escaped).
        action: if user must act, the action text (may contain HTML code spans).
        html_context: multi-line pre-formatted HTML block (NOT escaped, NOT wrapped in <i>).
                      Use for rich digest content. Takes precedence over `context`.

    Returns: HTML-formatted message ready for Telegram (parse_mode=HTML).

    NOTE: field VALUES and html_context are passed through unchanged — callers are
    responsible for either plain ASCII or valid Telegram HTML. Only field KEYS and
    the plain `context` argument are auto-escaped.
    """
    prefix_emoji, subsystem_label = subsystem.value
    status_emoji, status_label = status.value

    lines = [
        f"{prefix_emoji} <b>{subsystem_label}</b> · {status_emoji} <b>{status_label}</b>",
        f"<i>{_escape(title)}</i>",
        _DIVIDER,
    ]
    if fields:
        for k, v in fields.items():
            # Keys: always plain text → escape. Values: may be HTML → do NOT escape.
            lines.append(f"<b>{_escape(str(k))}</b>: {str(v)}")
        lines.append(_DIVIDER)
    if html_context:
        # Pre-formatted HTML block (digest rich content, etc.) — render as-is.
        lines.append(html_context)
    elif context:
        # Plain text sentence — escape special chars and italicise.
        lines.append(f"<i>{_escape(context)}</i>")
    if action:
        lines.append(f"<b>✋ ACTION</b>: {action}")  # action may contain HTML (code spans)
    return "\n".join(lines)


def send(
    subsystem: Subsystem,
    status: Status,
    title: str,
    fields: dict[str, Any] | None = None,
    context: str | None = None,
    action: str | None = None,
    *,
    silent: bool = False,
    buttons: list[list[dict]] | None = None,
    html_context: str | None = None,
) -> bool:
    """
    Build and send a formatted message. Returns True on success.

    Best-effort: errors are swallowed so callers don't break on Telegram outage.

    Args:
        silent: suppress phone-buzz (message still shown in chat)
        buttons: optional inline keyboard. List of rows; each row is a list of
                 button dicts: {"text": "🟢 Apply", "callback_data": "apply:abc123"}.
                 callback_data is opaque to Telegram but processed by our listener.
                 Max 64 bytes per callback_data.
    """
    text = format_message(subsystem, status, title, fields, context, action, html_context=html_context)
    payload: dict[str, Any] = {
        "chat_id":                  TELEGRAM_CHAT,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_notification":     "true" if silent else "false",
        "disable_web_page_preview": "true",
    }
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = urllib.parse.urlencode(payload).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        return True
    except Exception:
        return False


def answer_callback(callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
    """Acknowledge a button tap — clears the spinner on the user's button."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
        data = urllib.parse.urlencode({
            "callback_query_id": callback_query_id,
            "text":              text,
            "show_alert":        "true" if show_alert else "false",
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        return True
    except Exception:
        return False


def edit_message(message_id: int, chat_id: int | str, new_text: str,
                 parse_mode: str = "HTML", remove_buttons: bool = True) -> bool:
    """Edit a previously-sent message (used to update after Apply/Skip is tapped)."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
        payload = {
            "chat_id":    str(chat_id),
            "message_id": str(message_id),
            "text":       new_text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        }
        if remove_buttons:
            payload["reply_markup"] = json.dumps({"inline_keyboard": []})
        data = urllib.parse.urlencode(payload).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
        return True
    except Exception:
        return False


def get_updates(offset: int = 0, timeout_s: int = 0) -> list[dict]:
    """Poll Telegram for updates (long-polling). Returns list of update dicts."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        params = urllib.parse.urlencode({
            "offset":  str(offset),
            "timeout": str(timeout_s),
            "allowed_updates": json.dumps(["callback_query", "message"]),
        })
        with urllib.request.urlopen(f"{url}?{params}", timeout=timeout_s + 15) as r:
            data = json.loads(r.read())
        if not data.get("ok"):
            return []
        return data.get("result", [])
    except Exception:
        return []


def _escape(s: str) -> str:
    """Telegram HTML mode: escape <, >, & to prevent rendering issues."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
