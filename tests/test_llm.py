import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from api.llm import provider_order, extract_gemini_text


# --- provider selection -----------------------------------------------------

def test_auto_prefers_anthropic_when_both_configured():
    assert provider_order("auto", True, True) == ["anthropic", "gemini"]

def test_auto_falls_back_to_gemini_alone():
    assert provider_order("auto", False, True) == ["gemini"]

def test_auto_uses_anthropic_alone():
    assert provider_order("auto", True, False) == ["anthropic"]

def test_explicit_preference_wins_and_does_not_fall_back():
    """Pinning a provider must be honoured exactly -- a run whose model silently
    changed partway would make its numbers unattributable."""
    assert provider_order("gemini", True, True) == ["gemini"]
    assert provider_order("anthropic", True, True) == ["anthropic"]

def test_explicit_preference_for_unconfigured_provider_raises():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        provider_order("gemini", True, False)

def test_no_provider_configured_raises():
    with pytest.raises(ValueError, match="No LLM"):
        provider_order("auto", False, False)

def test_unknown_preference_raises():
    with pytest.raises(ValueError, match="unknown"):
        provider_order("llama", True, True)


# --- Gemini response parsing ------------------------------------------------

def test_extracts_plain_text():
    body = {"candidates": [{"finishReason": "STOP",
                            "content": {"parts": [{"text": "hello"}]}}]}
    assert extract_gemini_text(body) == "hello"

def test_joins_multiple_text_parts():
    body = {"candidates": [{"finishReason": "STOP",
                            "content": {"parts": [{"text": "a"}, {"text": "b"}]}}]}
    assert extract_gemini_text(body) == "ab"

def test_skips_thought_parts():
    """gemini-2.5-flash is a thinking model; thought parts are not the answer."""
    body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "internal reasoning", "thought": True}, {"text": "the answer"}]}}]}
    assert extract_gemini_text(body) == "the answer"

def test_budget_exhausted_by_thinking_raises_clearly():
    """A thinking model can spend the whole output budget before writing an
    answer. Returning '' would look like a refusal instead of a config problem."""
    body = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}
    with pytest.raises(RuntimeError, match="max_tokens"):
        extract_gemini_text(body)

def test_safety_block_raises():
    body = {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}
    with pytest.raises(RuntimeError, match="SAFETY"):
        extract_gemini_text(body)

def test_no_candidates_raises():
    with pytest.raises(RuntimeError, match="no candidates"):
        extract_gemini_text({"candidates": []})
