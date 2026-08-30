"""One place that talks to an LLM.

Two providers, because the Anthropic key here is identity-linked and its
workspace could not be resolved, which blocked every LLM-dependent feature.
Gemini is the fallback so the app is usable while that is sorted out.

Selection is explicit and recorded. `LLM_PROVIDER` pins a provider; "auto" tries
Anthropic first and falls back. Every response reports which model produced it --
a run whose model silently changed partway would make its numbers unattributable,
which matters because these answers feed the eval harness.

temperature=0 on both: without it the Anthropic default is 1.0, and every metric
would be a single draw from an uncharacterised distribution.
"""
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = "claude-sonnet-4-6"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# gemini-2.5-flash spends output budget on thinking before it writes anything, so
# a caller's max_tokens is treated as an answer budget and given headroom on top.
GEMINI_THINKING_HEADROOM = 4096

_active_provider: Optional[str] = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str


def provider_order(preference: str, have_anthropic: bool, have_gemini: bool) -> List[str]:
    """Which providers to try, in order. Raises if the request cannot be honoured."""
    configured = {"anthropic": have_anthropic, "gemini": have_gemini}
    if preference in configured:
        if not configured[preference]:
            key = "ANTHROPIC_API_KEY" if preference == "anthropic" else "GEMINI_API_KEY"
            raise ValueError(f"LLM_PROVIDER={preference} but {key} is not set")
        return [preference]
    if preference != "auto":
        raise ValueError(f"unknown LLM_PROVIDER {preference!r}; use auto, anthropic or gemini")
    order = [name for name in ("anthropic", "gemini") if configured[name]]
    if not order:
        raise ValueError("No LLM configured: set ANTHROPIC_API_KEY or GEMINI_API_KEY")
    return order


def extract_gemini_text(body: dict) -> str:
    """Pull the answer out of a generateContent response, or say why there isn't one."""
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {str(body)[:200]}")
    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", []) or []
    text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
    if text:
        return text
    reason = candidate.get("finishReason", "unknown")
    if reason == "MAX_TOKENS":
        raise RuntimeError(
            "Gemini spent its whole output budget on thinking and wrote no answer; "
            "raise max_tokens"
        )
    raise RuntimeError(f"Gemini returned no text (finishReason={reason})")


def _call_anthropic(user: str, system: Optional[str], max_tokens: int) -> LLMResponse:
    import anthropic

    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    # Identity-linked keys are rejected without this header; it is harmless on
    # an ordinary key, so it is sent whenever configured.
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"), default_headers=headers
    )
    kwargs = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": user}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return LLMResponse(response.content[0].text, "anthropic", ANTHROPIC_MODEL)


def _call_gemini(user: str, system: Optional[str], max_tokens: int) -> LLMResponse:
    body = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_tokens + GEMINI_THINKING_HEADROOM,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    response = requests.post(
        f"{GEMINI_URL}/{GEMINI_MODEL}:generateContent",
        params={"key": os.environ.get("GEMINI_API_KEY")},
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    return LLMResponse(extract_gemini_text(response.json()), "gemini", GEMINI_MODEL)


_CALLERS = {"anthropic": _call_anthropic, "gemini": _call_gemini}


def complete(user: str, system: Optional[str] = None, max_tokens: int = 1024) -> LLMResponse:
    """Ask an LLM. Tries providers in order and reports which one answered."""
    global _active_provider

    order = provider_order(
        os.environ.get("LLM_PROVIDER", "auto"),
        bool(os.environ.get("ANTHROPIC_API_KEY")),
        bool(os.environ.get("GEMINI_API_KEY")),
    )
    # Once a provider has worked, keep using it rather than retrying a broken one
    # on every request.
    if _active_provider in order:
        order = [_active_provider] + [p for p in order if p != _active_provider]

    errors = []
    for provider in order:
        try:
            result = _CALLERS[provider](user, system, max_tokens)
            if provider != _active_provider:
                logger.info(f"LLM provider: {provider} ({result.model})")
                _active_provider = provider
            return result
        except Exception as exc:
            errors.append(f"{provider}: {type(exc).__name__}: {str(exc)[:200]}")
            logger.warning(f"LLM provider {provider} failed: {str(exc)[:200]}")

    raise RuntimeError("All LLM providers failed -- " + " | ".join(errors))


def active_model() -> Optional[str]:
    """Which model is currently answering, for reporting alongside results."""
    if _active_provider == "anthropic":
        return ANTHROPIC_MODEL
    if _active_provider == "gemini":
        return GEMINI_MODEL
    return None
