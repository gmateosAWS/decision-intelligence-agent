"""
tests/agents/test_llm_factory.py
---------------------------------
Unit tests for agents/llm_factory.py.

All tests are offline — no real LLM API calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from agents.llm_factory import (
    LLMUnavailableError,
    _extract_usage,
    get_chat_model,
    invoke_with_fallback,
)

# ---------------------------------------------------------------------------
# get_chat_model
# ---------------------------------------------------------------------------


def test_get_chat_model_openai():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-fake"}):
        llm = get_chat_model("openai", "gpt-4o-mini")
    assert isinstance(llm, ChatOpenAI)


def test_get_chat_model_anthropic():
    llm = get_chat_model("anthropic", "claude-haiku-4-5-20251001")
    assert isinstance(llm, ChatAnthropic)


def test_get_chat_model_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        get_chat_model("cohere", "command-r")


# ---------------------------------------------------------------------------
# invoke_with_fallback
# ---------------------------------------------------------------------------


def test_fallback_on_primary_failure():
    """When primary raises a non-rate-limit error, fallback is called once."""
    primary = MagicMock()
    primary.invoke.side_effect = RuntimeError("API connection error")
    fallback = MagicMock()
    fallback.invoke.return_value = "fallback response"

    result = invoke_with_fallback(primary, ["msg"], fallback=fallback)

    assert result == "fallback response"
    primary.invoke.assert_called_once()
    fallback.invoke.assert_called_once_with(["msg"])


def test_retry_on_rate_limit():
    """On a 429 rate-limit error the primary is retried; second call succeeds."""
    primary = MagicMock()
    primary.invoke.side_effect = [
        RuntimeError("Rate limit exceeded: 429 Too Many Requests"),
        "success response",
    ]

    with patch("agents.llm_factory.time.sleep"):
        result = invoke_with_fallback(primary, ["msg"])

    assert result == "success response"
    assert primary.invoke.call_count == 2


def test_graceful_error_on_total_failure():
    """When both primary and fallback fail, LLMUnavailableError is raised."""
    primary = MagicMock()
    primary.invoke.side_effect = RuntimeError("primary is down")
    fallback = MagicMock()
    fallback.invoke.side_effect = RuntimeError("fallback is also down")

    with pytest.raises(LLMUnavailableError):
        invoke_with_fallback(primary, ["msg"], fallback=fallback)


def test_no_fallback_raises_unavailable():
    """With no fallback configured, total primary failure raises LLMUnavailableError."""
    primary = MagicMock()
    primary.invoke.side_effect = RuntimeError("primary down")

    with pytest.raises(LLMUnavailableError):
        invoke_with_fallback(primary, ["msg"])


def test_rate_limit_exhausted_then_fallback():
    """Rate-limit retries exhausted → fallback is used next."""
    primary = MagicMock()
    primary.invoke.side_effect = RuntimeError("429 rate limit")
    fallback = MagicMock()
    fallback.invoke.return_value = "fallback ok"

    with patch("agents.llm_factory.time.sleep"):
        result = invoke_with_fallback(primary, ["msg"], fallback=fallback)

    assert result == "fallback ok"
    fallback.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# _extract_usage
# ---------------------------------------------------------------------------


def test_extract_usage_from_aimessage():
    """Pattern 1: direct AIMessage with usage_metadata (synthesizer path)."""
    response = MagicMock()
    response.usage_metadata = {"input_tokens": 120, "output_tokens": 45}
    inp, out = _extract_usage(response)
    assert inp == 120
    assert out == 45


def test_extract_usage_from_structured_dict():
    """Pattern 2: include_raw=True dict with 'raw' AIMessage (planner/judge path)."""
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 200, "output_tokens": 80}
    response = {"raw": raw, "parsed": MagicMock(), "parsing_error": None}
    inp, out = _extract_usage(response)
    assert inp == 200
    assert out == 80


def test_extract_usage_fallback_to_response_metadata():
    """Pattern 3: response_metadata.token_usage (older OpenAI shape)."""
    response = MagicMock(spec=[])  # no usage_metadata attribute
    response.response_metadata = {
        "token_usage": {"prompt_tokens": 50, "completion_tokens": 30}
    }
    inp, out = _extract_usage(response)
    assert inp == 50
    assert out == 30


def test_extract_usage_unknown_shape_returns_zeros():
    """Unknown response shape → (0, 0) with a warning logged."""
    response = MagicMock(spec=[])  # no relevant attributes
    inp, out = _extract_usage(response)
    assert inp == 0
    assert out == 0
