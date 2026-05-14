"""
tests/agents/test_planner_uses_typed_state.py
---------------------------------------------
Unit tests verifying that planner_node correctly reads and uses
frozen ActiveAnalyticalState snapshots from the MemoryService (item 5.11).

All offline — no LLM calls, no DB, no spec IO.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.planner import ToolSelection, planner_node
from agents.state import AgentState

# ── Helpers ───────────────────────────────────────────────────────────────────


def _minimal_state(query: str = "What should I do?") -> AgentState:
    return AgentState(
        query=query,
        history=[],
        action=None,
        reasoning=None,
        params={},
        language="en",
        answer=None,
        requires_confirmation=False,
        requires_approval=False,
        confirmation_message=None,
        planner_prompt_version=None,
        synthesizer_prompt_version=None,
        judge_prompt_version=None,
    )


def _make_invoke_return(tool: str = "simulation") -> dict:
    """Return a minimal structured-output result that planner_node can unwrap."""
    selection = ToolSelection(tool=tool, reasoning="test", params=[], language="en")
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}
    return {"parsed": selection, "raw": raw}


def _capture_messages_invoke(captured: list):
    """Factory for a side_effect that records messages then returns a fake result."""

    def _invoke(chain, messages, **kwargs):
        captured.extend(messages)
        return _make_invoke_return()

    return _invoke


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_planner_works_without_service() -> None:
    """planner_node must work normally when active_state is None (no service wired)."""
    state = _minimal_state()

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value=_make_invoke_return("knowledge"),
        ),
    ):
        result = planner_node(state, active_state=None)

    assert result["action"] == "knowledge"
    assert "requires_confirmation" in result


def test_planner_reads_active_state_when_service_present() -> None:
    """planner_node must accept and consume an active_state snapshot without error."""
    from memory.state.types import Intent

    active_state = MagicMock()
    active_state.intent = Intent.OPTIMIZE
    active_state.active_simulation_run = None
    active_state.active_optimization_run = None
    active_state.metrics = []

    state = _minimal_state()

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value=_make_invoke_return("optimization"),
        ),
    ):
        result = planner_node(state, active_state=active_state)

    assert result["action"] == "optimization"


def test_planner_prompt_includes_intent_when_present_in_state() -> None:
    """When active_state carries an intent, a TYPED ANALYTICAL STATE system message
    is injected before the history so the LLM has structured context."""
    from memory.state.types import Intent

    active_state = MagicMock()
    active_state.intent = Intent.SIMULATE
    active_state.active_simulation_run = None
    active_state.active_optimization_run = None
    active_state.metrics = []

    state = _minimal_state()
    captured: list = []

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner.invoke_with_fallback",
            side_effect=_capture_messages_invoke(captured),
        ),
    ):
        planner_node(state, active_state=active_state)

    system_msgs = [m for m in captured if m.get("role") == "system"]
    assert (
        len(system_msgs) >= 2
    ), "Expected at least two system messages (prompt + state context)"

    context_msg = system_msgs[1]["content"]
    assert "TYPED ANALYTICAL STATE" in context_msg
    assert Intent.SIMULATE.value in context_msg


def test_planner_prompt_includes_active_run_when_present() -> None:
    """When active_state has an active simulation run, the run_id appears in context."""
    active_state = MagicMock()
    active_state.intent = None
    active_state.active_simulation_run = "run_test_xyz"
    active_state.active_optimization_run = None
    active_state.metrics = []

    state = _minimal_state()
    captured: list = []

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner.invoke_with_fallback",
            side_effect=_capture_messages_invoke(captured),
        ),
    ):
        planner_node(state, active_state=active_state)

    system_msgs = [m for m in captured if m.get("role") == "system"]
    assert len(system_msgs) >= 2

    context_content = system_msgs[1]["content"]
    assert "run_test_xyz" in context_content
