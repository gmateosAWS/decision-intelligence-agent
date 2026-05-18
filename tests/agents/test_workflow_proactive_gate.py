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
        "history": [],
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

    state = _state(action="simulation", history=[])
    assert _route_after_planner(state) == "proactive_confirmation_gate"


def test_route_tool_when_gate_bypassed() -> None:
    from agents.workflow import _route_after_planner

    state = _state(action="simulation", history=[], bypass_gate=True)
    assert _route_after_planner(state) == "tool"


def test_route_tool_for_cheap_action() -> None:
    from agents.workflow import _route_after_planner

    state = _state(action="knowledge", history=[])
    assert _route_after_planner(state) == "tool"


def test_route_synthesizer_when_requires_confirmation_and_no_gate() -> None:
    from agents.workflow import _route_after_planner

    # Cheap tool + requires_confirmation → synthesizer
    state = _state(
        action="knowledge",
        history=[{"query": "previous", "answer": "ok"}],
        requires_confirmation=True,
    )
    assert _route_after_planner(state) == "synthesizer"


# ── proactive_confirmation_gate node ─────────────────────────────────────────


def test_gate_node_returns_awaiting_true() -> None:
    from agents.workflow import proactive_confirmation_gate

    state = _state(action="simulation", history=[])
    result = proactive_confirmation_gate(state, config=None)
    assert result.get("awaiting_user_confirmation") is True
    assert result.get("proposal") is not None


def test_gate_node_passes_through_for_cheap_tool() -> None:
    from agents.workflow import proactive_confirmation_gate

    state = _state(action="knowledge", history=[])
    result = proactive_confirmation_gate(state, config=None)
    # No signals → empty dict returned (pass-through)
    assert not result.get("awaiting_user_confirmation")


def test_gate_node_includes_triggered_signals() -> None:
    from agents.workflow import proactive_confirmation_gate

    state = _state(action="optimization", history=[])
    result = proactive_confirmation_gate(state, config=None)
    proposal = result.get("proposal", {})
    assert "first_turn" in proposal.get("triggered_signals", [])
