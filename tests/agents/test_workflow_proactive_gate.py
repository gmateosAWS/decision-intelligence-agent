"""
tests/agents/test_workflow_proactive_gate.py
---------------------------------------------
Unit tests for the proactive_confirmation_gate node and _route_after_planner
4-way routing (item 5.13). All offline — no DB, no LLM.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def enable_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "first_turn,thin_context")


def _state(**kwargs: Any) -> dict:
    base: dict = {
        "query": "simulate",
        "action": "simulation",
        "params": {},
        "has_prior_turns": False,  # default: first session turn
        "clarification_needed": False,
        "bypass_gate": False,
    }
    base.update(kwargs)
    return base


# ── _route_after_planner routing ─────────────────────────────────────────────


def test_route_clarification_takes_priority() -> None:
    from agents.workflow import _route_after_planner

    state = _state(clarification_needed=True, action="simulation")
    assert _route_after_planner(state) == "clarification"


def test_route_proactive_gate_fires_for_expensive_tool_first_turn() -> None:
    from agents.workflow import _route_after_planner

    # has_prior_turns=False (default) → is_first_session_turn=True → gate fires
    state = _state(action="simulation")
    assert _route_after_planner(state) == "proactive_confirmation_gate"


def test_route_tool_on_second_turn_for_expensive_tool() -> None:
    """After the first turn, the gate must NOT fire for expensive tools.

    This is the core regression guard: before the fix, state["history"] was []
    after a gate-only round, so the gate would fire on every turn. Now we use
    has_prior_turns which is set from the LangGraph checkpoint.
    """
    from agents.workflow import _route_after_planner

    # has_prior_turns=True → is_first_session_turn=False
    # query="simulate" = 1 word, but thin_context won't fire because... wait,
    # "simulate" is < 8 words and params={}, so thin_context would fire.
    # Use a query with params or a long query to test no-gate on second turn.
    state = _state(
        action="simulation",
        has_prior_turns=True,
        query="what happens if we set price to twenty five euros",  # 11 words
        params={},
    )
    assert _route_after_planner(state) == "tool"


def test_route_tool_when_gate_bypassed() -> None:
    from agents.workflow import _route_after_planner

    state = _state(action="simulation", has_prior_turns=False, bypass_gate=True)
    assert _route_after_planner(state) == "tool"


def test_route_tool_for_cheap_action() -> None:
    from agents.workflow import _route_after_planner

    state = _state(action="knowledge")
    assert _route_after_planner(state) == "tool"


def test_route_synthesizer_when_requires_confirmation_and_no_gate() -> None:
    from agents.workflow import _route_after_planner

    # Cheap tool + requires_confirmation → synthesizer (gate doesn't fire for cheap)
    state = _state(
        action="knowledge",
        has_prior_turns=True,
        requires_confirmation=True,
    )
    assert _route_after_planner(state) == "synthesizer"


# ── proactive_confirmation_gate node ─────────────────────────────────────────


def test_gate_node_returns_awaiting_true() -> None:
    from agents.workflow import proactive_confirmation_gate

    state = _state(action="simulation", has_prior_turns=False)
    result = proactive_confirmation_gate(state, config=None)
    assert result.get("awaiting_user_confirmation") is True
    assert result.get("proposal") is not None


def test_gate_node_passes_through_for_cheap_tool() -> None:
    from agents.workflow import proactive_confirmation_gate

    state = _state(action="knowledge", has_prior_turns=False)
    result = proactive_confirmation_gate(state, config=None)
    # No signals → empty dict returned (pass-through)
    assert not result.get("awaiting_user_confirmation")


def test_gate_node_includes_triggered_signals() -> None:
    from agents.workflow import proactive_confirmation_gate

    state = _state(action="optimization", has_prior_turns=False)
    result = proactive_confirmation_gate(state, config=None)
    proposal = result.get("proposal", {})
    assert "first_turn" in proposal.get("triggered_signals", [])


def test_gate_node_does_not_pause_on_second_turn_long_query() -> None:
    """Gate must NOT fire when has_prior_turns=True and no thin_context."""
    from agents.workflow import proactive_confirmation_gate

    state = _state(
        action="simulation",
        has_prior_turns=True,
        query="what happens if we set price to twenty five euros",  # 11 words
        params={},
    )
    result = proactive_confirmation_gate(state, config=None)
    assert not result.get("awaiting_user_confirmation")
