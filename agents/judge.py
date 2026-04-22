"""
agents/judge.py
----------------
Online LLM judge for the final user-facing answer.

Responsibilities
----------------
1. Evaluate whether the synthesizer answer is:
   - grounded in the raw tool output,
   - responsive to the user's query,
   - quantitatively consistent.
2. Approve the answer or request a single revision.
3. If revision is needed, rewrite the answer in-place so the graph still
   returns a single final answer to the caller.

This keeps the architecture simple while introducing a production-relevant
quality gate before returning the final response.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .llm_factory import LLMUnavailableError, get_chat_model, invoke_with_fallback
from .state import AgentState

load_dotenv()

_JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "openai")
_JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4o-mini")
_JUDGE_THRESHOLD = float(os.getenv("JUDGE_THRESHOLD", "0.75"))
_FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "")
_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

_judge_llm = get_chat_model(_JUDGE_PROVIDER, _JUDGE_MODEL, temperature=0)
_revision_llm = get_chat_model(_JUDGE_PROVIDER, _JUDGE_MODEL, temperature=0.1)

_fallback_judge_llm = None
_fallback_revision_llm = None
if _FALLBACK_PROVIDER and _FALLBACK_MODEL:
    _fallback_judge_llm = get_chat_model(
        _FALLBACK_PROVIDER, _FALLBACK_MODEL, temperature=0
    )
    _fallback_revision_llm = get_chat_model(
        _FALLBACK_PROVIDER, _FALLBACK_MODEL, temperature=0.1
    )


class JudgeVerdict(BaseModel):
    """Structured quality assessment for a generated answer."""

    verdict: Literal["approved", "revise"]
    overall_score: float = Field(ge=0.0, le=1.0)
    grounded_in_tool_output: bool
    answers_user_question: bool
    quantitative_consistency: bool
    feedback: str


_judge_structured = _judge_llm.with_structured_output(JudgeVerdict)
_fallback_judge_structured = (
    _fallback_judge_llm.with_structured_output(JudgeVerdict)
    if _fallback_judge_llm is not None
    else None
)


def judge_node(state: AgentState, config: Optional[dict] = None) -> Dict[str, Any]:
    """
    Evaluate the synthesized answer and optionally revise it once.

    Returns updated state fields including the final answer, judge metadata,
    and the turn appended to conversation history.
    """
    obs = _get_observer(config)

    query = state.get("query", "")
    action = state.get("action", "unknown")
    raw_result = state.get("raw_result") or {}
    answer = (state.get("answer") or "").strip()

    raw_text = _format_raw_result(raw_result)
    t0 = time.perf_counter()

    judge_messages = [
        {
            "role": "system",
            "content": (
                "You are an online quality judge for a Decision Intelligence "
                "assistant.\n"
                "Evaluate the assistant answer strictly against the user"
                "'s query and the raw tool output.\n"
                "Do not reward style alone. Prefer factual grounding, "
                "quantitative consistency, and decision usefulness.\n"
                "Approve only if the answer is clearly grounded in the tool "
                "result and directly answers the user.\n"
                f"Use a strict approval threshold of {_JUDGE_THRESHOLD:.2f}."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User query:\n{query}\n\n"
                f"Selected tool: {action}\n\n"
                f"Raw tool output:\n{raw_text}\n\n"
                f"Assistant answer to evaluate:\n{answer}\n\n"
                "Return a structured verdict. If the answer omits key "
                "quantitative findings, overstates certainty, or adds claims "
                "not supported by the tool output, request revision."
            ),
        },
    ]
    try:
        verdict = invoke_with_fallback(
            _judge_structured,
            judge_messages,
            fallback=_fallback_judge_structured,
        )
    except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
        # Fail open: preserve the original answer, but log that the judge failed.
        elapsed_ms = (time.perf_counter() - t0) * 1000
        feedback = f"Judge unavailable: {type(exc).__name__}: {exc}"
        if obs:
            obs.record_judge(
                score=None,
                approved=True,
                feedback=feedback,
                latency_ms=elapsed_ms,
                revised=False,
                final_answer=answer,
                error=str(exc),
                model=_JUDGE_MODEL,
            )
        return {
            "judge_score": None,
            "judge_passed": True,
            "judge_feedback": feedback,
            "judge_revised": False,
            "history": [{"query": query, "answer": answer}],
        }

    final_answer = answer
    revised = False
    approved = (
        verdict.verdict == "approved" and verdict.overall_score >= _JUDGE_THRESHOLD
    )

    if not approved:
        revised = True
        final_answer = _revise_answer(
            query=query,
            action=action,
            raw_text=raw_text,
            original_answer=answer,
            feedback=verdict.feedback,
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    if obs:
        obs.record_judge(
            score=verdict.overall_score,
            approved=approved,
            feedback=verdict.feedback,
            latency_ms=elapsed_ms,
            revised=revised,
            final_answer=final_answer,
            model=_JUDGE_MODEL,
        )

    return {
        "answer": final_answer,
        "judge_score": verdict.overall_score,
        "judge_passed": approved,
        "judge_feedback": verdict.feedback,
        "judge_revised": revised,
        "history": [{"query": query, "answer": final_answer}],
    }


def _revise_answer(
    *,
    query: str,
    action: str,
    raw_text: str,
    original_answer: str,
    feedback: str,
) -> str:
    """Generate one grounded revision using the judge feedback."""
    revision_messages = [
        {
            "role": "system",
            "content": (
                "You revise answers for a Decision Intelligence assistant.\n"
                "Rewrite the answer so it is strictly grounded in the tool "
                "output, directly answers the user's question, and stays "
                "concise.\n"
                "Do not introduce facts not present in the raw tool output.\n"
                "If numbers exist, use them. If uncertainty exists, mention "
                "it.\n"
                "Answer in 3-5 sentences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User query:\n{query}\n\n"
                f"Selected tool: {action}\n\n"
                f"Raw tool output:\n{raw_text}\n\n"
                f"Original answer:\n{original_answer}\n\n"
                f"Judge feedback:\n{feedback}\n\n"
                "Rewrite the answer now."
            ),
        },
    ]
    try:
        response = invoke_with_fallback(
            _revision_llm,
            revision_messages,
            fallback=_fallback_revision_llm,
        )
        revised = (response.content or "").strip()
        return revised or original_answer
    except (LLMUnavailableError, Exception):  # noqa: BLE001
        return original_answer


def _format_raw_result(raw_result: Dict[str, Any]) -> str:
    if not raw_result:
        return "(empty result)"
    return "\n".join(f"- {k}: {v}" for k, v in raw_result.items())


def _get_observer(config: Optional[dict]):
    if config is None:
        return None
    return config.get("configurable", {}).get("observer")
