"""
tests/agents/test_workflow_clarification.py
---------------------------------------------
Tests for the clarification node and routing logic added in item 5.9.

No LLM calls are made.
"""

from __future__ import annotations

from agents.workflow import _route_after_planner, clarification_node


def test_route_after_planner_returns_clarification_when_needed():
    state = {
        "clarification_needed": True,
        "requires_confirmation": False,
        "requires_approval": False,
    }
    assert _route_after_planner(state) == "clarification"


def test_route_after_planner_clarification_takes_priority_over_policy():
    """clarification_needed must win over autonomy policy flags."""
    state = {
        "clarification_needed": True,
        "requires_confirmation": True,  # both set
        "requires_approval": False,
    }
    assert _route_after_planner(state) == "clarification"


def test_route_after_planner_returns_synthesizer_for_policy():
    state = {
        "clarification_needed": False,
        "requires_confirmation": True,
        "requires_approval": False,
    }
    assert _route_after_planner(state) == "synthesizer"


def test_route_after_planner_returns_tool_normally():
    state = {
        "clarification_needed": False,
        "requires_confirmation": False,
        "requires_approval": False,
    }
    assert _route_after_planner(state) == "tool"


def test_clarification_node_returns_message_as_answer():
    state = {
        "query": "simulate at price=30",
        "clarification_message": "I could not recognise 'price' in this domain.",
    }
    result = clarification_node(state)
    assert result["answer"] == "I could not recognise 'price' in this domain."


def test_clarification_node_appends_to_history():
    state = {
        "query": "simulate at price=30",
        "clarification_message": "Please use 'bed_capacity' instead.",
    }
    result = clarification_node(state)
    assert len(result["history"]) == 1
    assert result["history"][0]["query"] == "simulate at price=30"
    assert "bed_capacity" in result["history"][0]["answer"]


def test_clarification_node_fallback_when_no_message():
    state = {
        "query": "what is demand?",
    }
    result = clarification_node(state)
    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0
