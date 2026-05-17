"""
tests/agents/test_judge_grounding.py
--------------------------------------
Tests that judge_node performs a non-blocking observational scan and annotates
judge_feedback with [ungrounded: ...] prefix when raw_result keys are outside
the vocabulary (item 5.9).

No LLM calls are made — invoke_with_fallback is mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "healthcare_demo_spec.yaml"


def _make_verdict(overall_score: float = 0.9, verdict: str = "approved") -> MagicMock:
    from agents.judge import JudgeVerdict

    v = MagicMock(spec=JudgeVerdict)
    v.verdict = verdict
    v.overall_score = overall_score
    v.grounded_in_tool_output = True
    v.answers_user_question = True
    v.quantitative_consistency = True
    v.feedback = "Looks good."
    return v


def test_judge_annotates_feedback_for_ungrounded_result_keys():
    """Ungrounded raw_result keys cause [ungrounded: ...] prefix in judge_feedback."""
    from spec.spec_loader import load_spec

    spec = load_spec(FIXTURE_PATH)

    state = {
        "query": "simulate",
        "action": "simulation",
        "language": "en",
        "raw_result": {
            "expected_profit": 5000,  # retail key, ungrounded in healthcare
            "demand": 100,  # retail key, ungrounded in healthcare
        },
        "answer": "Expected profit is €5000.",
    }

    verdict = _make_verdict()
    mock_output = {"parsed": verdict}

    with (
        patch("agents.judge._init_llms"),
        patch("agents.judge.invoke_with_fallback", return_value=mock_output),
        patch("spec.spec_loader.get_spec", return_value=spec),
        patch("system.grounded_tokens._vocab_cache", {}),
    ):
        from agents.judge import judge_node

        result = judge_node(state)

    feedback = result.get("judge_feedback", "")
    assert "[ungrounded:" in feedback


def test_judge_does_not_annotate_feedback_for_grounded_result_keys():
    """When all raw_result keys are in the vocabulary, no [ungrounded:] prefix."""
    from spec.spec_loader import load_spec

    spec = load_spec(FIXTURE_PATH)

    state = {
        "query": "simulate",
        "action": "simulation",
        "language": "en",
        "raw_result": {
            "patient_throughput": 340,  # in healthcare vocab
            "bed_capacity": 80,  # in healthcare vocab
        },
        "answer": "Patient throughput is 340.",
    }

    verdict = _make_verdict()
    mock_output = {"parsed": verdict}

    with (
        patch("agents.judge._init_llms"),
        patch("agents.judge.invoke_with_fallback", return_value=mock_output),
        patch("spec.spec_loader.get_spec", return_value=spec),
        patch("system.grounded_tokens._vocab_cache", {}),
    ):
        from agents.judge import judge_node

        result = judge_node(state)

    feedback = result.get("judge_feedback", "")
    assert "[ungrounded:" not in feedback
