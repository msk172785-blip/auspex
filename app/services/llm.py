"""Optional LLM enhancement layer.

If an API key is configured, the analyst conclusion + executive summary are
rewritten by an LLM for a more natural, senior-analyst voice. If no key is set
or the call fails, callers fall back to the deterministic template (zero cost).
"""
from __future__ import annotations
from typing import Optional
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger("llm")

SYSTEM_PROMPT = (
    "You are a senior equity research analyst writing concise, balanced, "
    "investment-grade commentary. You never give personalised financial advice "
    "and you always ground statements in the metrics provided. Avoid hype."
)


def enhance(prompt: str, max_tokens: int = 900) -> Optional[str]:
    provider = settings.llm_provider
    try:
        if provider == "openai":
            return _openai(prompt, max_tokens)
        if provider == "anthropic":
            return _anthropic(prompt, max_tokens)
    except Exception as e:
        logger.warning("LLM enhancement failed (%s): %s", provider, e)
    return None


def _openai(prompt: str, max_tokens: int) -> Optional[str]:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": max_tokens,
        },
        timeout=40,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _anthropic(prompt: str, max_tokens: int) -> Optional[str]:
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=40,
    )
    r.raise_for_status()
    data = r.json()
    return "".join(block.get("text", "") for block in data.get("content", [])).strip()


def anthropic_complete(system: str, prompt: str, max_tokens: int = 900):
    """Generic Anthropic call returning text, or None if no key / failure.
    Used by the decomposition engine (V0.4)."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
            json={"model": settings.ANTHROPIC_MODEL, "max_tokens": max_tokens,
                  "system": system, "messages": [{"role": "user", "content": prompt}]},
            timeout=40,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except Exception as e:
        logger.warning("anthropic_complete failed: %s", e)
        return None


def anthropic_json(system: str, prompt: str, max_tokens: int = 900):
    """Returns (text, error). error is None on success; otherwise a short reason
    string (no_key, api_<status>: <body>, exception: <msg>). Used to make the
    decomposition path observable instead of failing silently."""
    if not settings.ANTHROPIC_API_KEY:
        return None, "no_key"
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
            json={"model": settings.ANTHROPIC_MODEL, "max_tokens": max_tokens,
                  "system": system, "messages": [{"role": "user", "content": prompt}]},
            timeout=40,
        )
        if r.status_code >= 400:
            return None, "api_%d: %s" % (r.status_code, (r.text or "")[:220])
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
        return text, None
    except Exception as e:
        return None, "exception: %s" % (str(e)[:200])
