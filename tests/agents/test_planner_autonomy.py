"""
tests/agents/test_planner_autonomy.py
---------------------------------------
Unit tests for autonomy-policy enforcement in agents/planner.py.

The LLM and spec singleton are mocked — no network or database required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.planner import ToolSelection, planner_node
from spec.autonomy import AutonomyLevel, AutonomyPolicy, ToolAutonomyPolicy


def _make_state(query: str = "test query") -> dict:
    return {"query": query, "history": []}


def _make_spec_mock(tool_levels: dict | None = None):
    """Return a mock OrganizationalModelSpec with the given autonomy levels."""
    tools = []
    if tool_levels:
        for tool_name, level in tool_levels.items():
            tools.append(ToolAutonomyPolicy(tool=tool_name, level=level))
    policy = AutonomyPolicy(tools=tools)

    dv = MagicMock()
    dv.name = "price"
    dv.description = "Unit price"
    dv.unit = "EUR"
    dv.bounds_min = 10.0
    dv.bounds_max = 50.0
    dv.default = 25.0

    spec = MagicMock()
    spec.autonomy_policy = policy
    spec.decision_variables = [dv]
    spec.domain_name = "test_domain"
    return spec


def test_planner_auto_no_flag() -> None:
    """Policy=auto → no confirmation/approval flags in result."""
    spec_mock = _make_spec_mock({"optimization": AutonomyLevel.AUTO})
    selection = ToolSelection(
        tool="optimization", reasoning="best tool", params=[], language="en"
    )

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner._get_system_prompt", return_value=("prompt", None)),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": selection, "raw": MagicMock()},
        ),
        patch("agents.planner.get_spec", return_value=spec_mock),
    ):
        result = planner_node(_make_state())

    assert result["action"] == "optimization"
    assert result["requires_confirmation"] is False
    assert result["requires_approval"] is False
    assert result["confirmation_message"] is None


def test_planner_human_confirms_flag() -> None:
    """Policy=human_confirms → requires_confirmation=True, message set."""
    spec_mock = _make_spec_mock({"optimization": AutonomyLevel.HUMAN_CONFIRMS})
    selection = ToolSelection(
        tool="optimization", reasoning="best tool", params=[], language="en"
    )

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner._get_system_prompt", return_value=("prompt", None)),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": selection, "raw": MagicMock()},
        ),
        patch("agents.planner.get_spec", return_value=spec_mock),
    ):
        result = planner_node(_make_state())

    assert result["action"] == "optimization"
    assert result["requires_confirmation"] is True
    assert result["requires_approval"] is False
    assert result["confirmation_message"] is not None
    assert "optimization" in result["confirmation_message"]


def test_planner_human_approves_flag() -> None:
    """Policy=human_approves → requires_approval=True, message set."""
    spec_mock = _make_spec_mock({"simulation": AutonomyLevel.HUMAN_APPROVES})
    selection = ToolSelection(
        tool="simulation", reasoning="best tool", params=[], language="es"
    )

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner._get_system_prompt", return_value=("prompt", None)),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": selection, "raw": MagicMock()},
        ),
        patch("agents.planner.get_spec", return_value=spec_mock),
    ):
        result = planner_node(_make_state())

    assert result["action"] == "simulation"
    assert result["requires_confirmation"] is False
    assert result["requires_approval"] is True
    assert result["confirmation_message"] is not None
    assert "simulation" in result["confirmation_message"]


def test_planner_unknown_tool_uses_default_policy() -> None:
    """Unknown tool name falls back to default policy (auto)."""
    spec_mock = _make_spec_mock()  # no tools configured → all default to auto
    selection = ToolSelection(
        tool="knowledge", reasoning="explain", params=[], language="en"
    )

    with (
        patch("agents.planner._init_planner_llms"),
        patch("agents.planner._get_system_prompt", return_value=("prompt", None)),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": selection, "raw": MagicMock()},
        ),
        patch("agents.planner.get_spec", return_value=spec_mock),
    ):
        result = planner_node(_make_state())

    assert result["requires_confirmation"] is False
    assert result["requires_approval"] is False
