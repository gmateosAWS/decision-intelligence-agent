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
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel

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

        return ChatAnthropic(
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

    Returns
    -------
    Any
        Whatever the successful ``.invoke()`` call returns.

    Raises
    ------
    LLMUnavailableError
        When all providers are exhausted.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            return primary.invoke(messages)
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
            return fallback.invoke(messages)
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallback LLM also failed (%s): %s", type(exc).__name__, exc)
            raise LLMUnavailableError("All LLM providers exhausted") from exc

    raise LLMUnavailableError(
        f"LLM unavailable and no fallback configured: {last_exc}"
    ) from last_exc
