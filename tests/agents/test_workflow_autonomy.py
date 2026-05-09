"""
tests/agents/test_workflow_autonomy.py
----------------------------------------
Unit tests for autonomy-policy conditional routing in agents/workflow.py.

Tests the _route_after_planner() conditional edge and the synthesizer_node
short-circuit that emits the proposal message instead of a tool result.
No LLM or database required.
"""

from __future__ import annotations

from agents.workflow import _route_after_planner, synthesizer_node


def test_route_skips_tool_on_confirmation() -> None:
    state = {"requires_confirmation": True, "requires_approval": False}
    assert _route_after_planner(state) == "synthesizer"


def test_route_skips_tool_on_approval() -> None:
    state = {"requires_confirmation": False, "requires_approval": True}
    assert _route_after_planner(state) == "synthesizer"


def test_route_executes_tool_on_auto() -> None:
    state = {"requires_confirmation": False, "requires_approval": False}
    assert _route_after_planner(state) == "tool"


def test_route_executes_tool_when_no_flags() -> None:
    """Missing flags (state not set) default to tool execution."""
    assert _route_after_planner({}) == "tool"


def test_synthesizer_returns_confirmation_message() -> None:
    """When requires_confirmation=True, synthesizer returns the message directly."""
    state = {
        "requires_confirmation": True,
        "requires_approval": False,
        "confirmation_message": "Confirm running optimization?",
        "query": "optimize price",
        "action": "optimization",
    }
    result = synthesizer_node(state)
    assert result["answer"] == "Confirm running optimization?"


def test_synthesizer_returns_approval_message() -> None:
    """When requires_approval=True, synthesizer returns the proposal message."""
    state = {
        "requires_confirmation": False,
        "requires_approval": True,
        "confirmation_message": "Approval needed for simulation.",
        "query": "simulate price 30",
        "action": "simulation",
    }
    result = synthesizer_node(state)
    assert result["answer"] == "Approval needed for simulation."


def test_synthesizer_fallback_message_when_none() -> None:
    """When confirmation_message is None, a default message is returned."""
    state = {
        "requires_confirmation": True,
        "requires_approval": False,
        "confirmation_message": None,
    }
    result = synthesizer_node(state)
    assert "human" in result["answer"].lower() or "required" in result["answer"].lower()
