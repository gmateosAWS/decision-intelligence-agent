"""
agents/llm_factory.py
---------------------
Factory for creating LLM instances with multi-provider support,
exponential-backoff retries, and provider fallback.

Public API
----------
get_chat_model(provider, model_name, temperature) -> BaseChatModel
    Instantiate a chat model for the given provider.

invoke_with_fallback(primary, messages, *, fallback) -> Any
    Call primary.invoke() with retry on rate limits; switch to fallback
    provider if primary is exhausted; raise LLMUnavailableError if both fail.

LLMUnavailableError
    Raised when all providers are exhausted so callers can return a
    structured error to the user instead of propagating a stack trace.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from evaluation.budget import BudgetTracker

logger = logging.getLogger(__name__)

_LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))


class LLMUnavailableError(RuntimeError):
    """All configured LLM providers are exhausted."""


def _is_rate_limit(exc: BaseException) -> bool:
    """Return True if the exception looks like an HTTP 429 / rate-limit error."""
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("rate limit", "ratelimit", "429", "too many requests")
    )


def get_chat_model(
    provider: str,
    model_name: str,
    temperature: float = 0,
) -> BaseChatModel:
    """
    Instantiate a LangChain chat model for the requested provider.

    Parameters
    ----------
    provider : str
        ``"openai"`` or ``"anthropic"``.
    model_name : str
        Provider-specific model identifier (e.g. ``"gpt-4o-mini"`` or
        ``"claude-haiku-4-5-20251001"``).
    temperature : float
        Sampling temperature passed to the model.

    Returns
    -------
    BaseChatModel

    Raises
    ------
    ValueError
        If *provider* is not one of the supported values.
    """
    provider = provider.lower().strip()
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            timeout=_LLM_TIMEOUT,
            max_retries=0,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(  # type: ignore[call-arg]  # langchain-anthropic stubs lag behind actual API; model= is valid
            model=model_name,
            temperature=temperature,
            timeout=_LLM_TIMEOUT,
            max_retries=0,
        )
    raise ValueError(
        f"Unsupported LLM provider: '{provider}'. Choose 'openai' or 'anthropic'."
    )


def invoke_with_fallback(
    primary: Any,
    messages: Any,
    *,
    fallback: Optional[Any] = None,
    tracker: Optional["BudgetTracker"] = None,
    model: str = "",
) -> Any:
    """
    Invoke *primary* with exponential-backoff retries on rate-limit errors.

    On rate-limit errors the call is retried up to ``LLM_MAX_RETRIES`` times
    with exponential backoff (2^attempt seconds, capped at 60 s).  Any other
    exception, or retries exhausted, causes an immediate switch to *fallback*
    (if provided).  If both providers fail, ``LLMUnavailableError`` is raised.

    Parameters
    ----------
    primary : Any
        A LangChain runnable with an ``.invoke(messages)`` method.
    messages : Any
        Input passed verbatim to ``.invoke()``.
    fallback : Any | None
        Optional second runnable tried once if primary is exhausted.
    tracker : BudgetTracker | None
        If provided, budget is checked before each call and usage is recorded
        after a successful call (item 8.7.b).
    model : str
        Model identifier used to look up pricing (item 8.7.a).

    Returns
    -------
    Any
        Whatever the successful ``.invoke()`` call returns.

    Raises
    ------
    LLMUnavailableError
        When all providers are exhausted.
    BudgetExceededError
        When the per-run budget ceiling is hit before the call (item 8.7.b).
    """
    if tracker is not None:
        tracker.raise_if_exceeded()

    last_exc: Optional[Exception] = None

    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            response = primary.invoke(messages)
            _record_usage(tracker, response, model)
            return response
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if _is_rate_limit(exc) and attempt < _LLM_MAX_RETRIES:
                wait_secs = min(2**attempt, 60)
                logger.warning(
                    "Rate limit on primary LLM (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    _LLM_MAX_RETRIES + 1,
                    wait_secs,
                    exc,
                )
                time.sleep(wait_secs)
            else:
                logger.warning("Primary LLM failed (%s): %s", type(exc).__name__, exc)
                break

    if fallback is not None:
        logger.info("Switching to fallback LLM provider")
        try:
            response = fallback.invoke(messages)
            _record_usage(tracker, response, model)
            return response
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallback LLM also failed (%s): %s", type(exc).__name__, exc)
            raise LLMUnavailableError("All LLM providers exhausted") from exc

    raise LLMUnavailableError(
        f"LLM unavailable and no fallback configured: {last_exc}"
    ) from last_exc


def _extract_usage(response: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from a LangChain response.

    Three patterns are handled, in priority order:

    1. Direct AIMessage — synthesizer and revision paths (plain `.invoke()`).
    2. Dict with ``"raw"`` key — planner and judge paths that use
       ``.with_structured_output(Schema, include_raw=True)``.
    3. ``response_metadata["token_usage"]`` — older OpenAI response shape.

    Returns (0, 0) and logs a warning for unknown shapes.
    """
    logger.warning(
        "[USAGE_DEBUG] type=%s is_dict=%s",
        type(response).__name__,
        isinstance(response, dict),
    )
    if isinstance(response, dict):
        logger.warning("[USAGE_DEBUG] dict_keys=%s", list(response.keys()))
        if "raw" in response:
            raw = response["raw"]
            logger.warning(
                "[USAGE_DEBUG] raw_type=%s has_usage_metadata=%s",
                type(raw).__name__,
                hasattr(raw, "usage_metadata"),
            )
            if hasattr(raw, "usage_metadata"):
                logger.warning(
                    "[USAGE_DEBUG] usage_metadata_value=%r", raw.usage_metadata
                )
    else:
        logger.warning(
            "[USAGE_DEBUG] direct response has_usage_metadata=%s",
            hasattr(response, "usage_metadata"),
        )
        if hasattr(response, "usage_metadata"):
            logger.warning(
                "[USAGE_DEBUG] usage_metadata_value=%r", response.usage_metadata
            )

    # Pattern 1: direct AIMessage / BaseChatModel response
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        input_tokens = int(um.get("input_tokens", 0) or 0)
        output_tokens = int(um.get("output_tokens", 0) or 0)
        logger.warning(
            "[USAGE_DEBUG] returning input=%d output=%d", input_tokens, output_tokens
        )
        return (input_tokens, output_tokens)
    # Pattern 2: structured output with include_raw=True → {"raw": AIMessage, ...}
    if isinstance(response, dict) and "raw" in response:
        raw = response["raw"]
        if hasattr(raw, "usage_metadata") and raw.usage_metadata:
            um = raw.usage_metadata
            input_tokens = int(um.get("input_tokens", 0) or 0)
            output_tokens = int(um.get("output_tokens", 0) or 0)
            logger.warning(
                "[USAGE_DEBUG] returning input=%d output=%d",
                input_tokens,
                output_tokens,
            )
            return (input_tokens, output_tokens)
    # Pattern 3: response_metadata.token_usage (older OpenAI shape)
    if hasattr(response, "response_metadata"):
        token_usage = response.response_metadata.get("token_usage", {})
        input_tokens = int(token_usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(token_usage.get("completion_tokens", 0) or 0)
        logger.warning(
            "[USAGE_DEBUG] returning input=%d output=%d", input_tokens, output_tokens
        )
        return (input_tokens, output_tokens)
    logger.warning(
        "[USAGE_DEBUG] unknown shape — type=%s returning (0, 0)",
        type(response).__name__,
    )
    return (0, 0)


def _record_usage(
    tracker: Optional["BudgetTracker"],
    response: Any,
    model: str,
) -> None:
    """Extract token counts from a LangChain response and record them in *tracker*."""
    if tracker is None:
        return
    try:
        from evaluation.cost import calculate_cost_usd

        input_tokens, output_tokens = _extract_usage(response)
        cost_usd = calculate_cost_usd(model, input_tokens, output_tokens)
        tracker.record_call(input_tokens, output_tokens, cost_usd)
    except Exception:  # noqa: BLE001
        tracker.record_call(0, 0, 0.0)
