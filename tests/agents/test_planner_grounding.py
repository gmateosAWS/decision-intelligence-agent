"""
tests/agents/test_planner_grounding.py
----------------------------------------
Tests that planner_node returns a clarification state dict when an ungrounded
param variable is detected (item 5.9 blocking check).

No LLM calls are made — invoke_with_fallback is mocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "healthcare_demo_spec.yaml"


@pytest.fixture(autouse=True)
def reset_planner_cache():
    import agents.planner as pm

    pm._llm = None
    pm._llm_structured = None
    pm._fallback_llm_structured = None
    yield
    pm._llm = None
    pm._llm_structured = None
    pm._fallback_llm_structured = None


def _make_selection(tool: str = "simulation", params: list[Any] | None = None):
    from agents.planner import ToolSelection

    selection = MagicMock(spec=ToolSelection)
    selection.tool = tool
    selection.reasoning = "test reasoning"
    selection.language = "en"
    selection.params = params or []
    return selection


def test_planner_returns_clarification_on_ungrounded_param():
    """planner_node must return clarification_needed=True for unknown variable."""
    from spec.spec_loader import load_spec

    spec = load_spec(FIXTURE_PATH)

    ungrounded_param = MagicMock()
    ungrounded_param.variable = "price"  # not in healthcare vocab
    ungrounded_param.value = 30.0

    selection = _make_selection("simulation", params=[ungrounded_param])
    mock_output = {"parsed": selection}

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=mock_output),
        patch("agents.planner.get_spec", return_value=spec),
        patch("system.grounded_tokens._vocab_cache", {}),
    ):
        from agents.planner import planner_node

        result = planner_node({"query": "simulate at price=30", "history": []})

    assert result["clarification_needed"] is True
    assert result["ungrounded_token"] == "price"
    assert "price" in result["clarification_message"]
    assert result["action"] is None


def test_planner_passes_for_grounded_param():
    """planner_node must pass normally when all params are in the vocabulary."""
    from spec.spec_loader import load_spec

    spec = load_spec(FIXTURE_PATH)

    grounded_param = MagicMock()
    grounded_param.variable = "bed_capacity"  # in healthcare vocab
    grounded_param.value = 100.0

    selection = _make_selection("simulation", params=[grounded_param])
    mock_output = {"parsed": selection}

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=mock_output),
        patch("agents.planner.get_spec", return_value=spec),
        patch("system.grounded_tokens._vocab_cache", {}),
    ):
        from agents.planner import planner_node

        result = planner_node({"query": "simulate at bed_capacity=100", "history": []})

    assert not result.get("clarification_needed")
    assert result["action"] == "simulation"


def test_planner_clarification_message_lists_valid_tokens():
    """The clarification message must include at least one valid vocab token."""
    from spec.spec_loader import load_spec

    spec = load_spec(FIXTURE_PATH)

    bad_param = MagicMock()
    bad_param.variable = "marketing_spend"  # retail name, not in healthcare
    bad_param.value = 5000.0

    selection = _make_selection("optimization", params=[bad_param])
    mock_output = {"parsed": selection}

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner.invoke_with_fallback", return_value=mock_output),
        patch("agents.planner.get_spec", return_value=spec),
        patch("system.grounded_tokens._vocab_cache", {}),
    ):
        from agents.planner import planner_node

        result = planner_node({"query": "optimize marketing_spend", "history": []})

    msg = result.get("clarification_message", "")
    # Message must mention at least one healthcare vocabulary token
    assert any(
        t in msg for t in ["bed_capacity", "staffing_ratio", "patient_throughput"]
    )
