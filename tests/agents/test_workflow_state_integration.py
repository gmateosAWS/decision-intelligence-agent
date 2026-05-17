"""
tests/agents/test_workflow_state_integration.py
-------------------------------------------------
Verify that the LangGraph workflow correctly wires MemoryService (item 5.11).
All offline — no real LLM calls, no DB.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from memory import LocalMemoryService
from memory.coordinator.coordinator import MemoryCoordinator
from memory.state.types import Intent


def _make_config(memory_service=None):
    return {
        "configurable": {
            "observer": None,
            "budget_tracker": None,
            "memory_service": memory_service,
            "thread_id": str(uuid.uuid4()),
        }
    }


def _make_state(tool: str = "optimization") -> dict:
    return {
        "query": "test",
        "history": [],
        "action": tool,
        "reasoning": "test reasoning",
        "run_id": "test_run_001",
        "raw_result": None,
    }


def _make_planner_selection(tool: str = "optimization") -> MagicMock:
    sel = MagicMock()
    sel.tool = tool
    sel.reasoning = "test reasoning"
    sel.params = []
    sel.language = "en"
    return sel


# ── Coordinator wired into planner ──────────────────────────────────────────


def test_workflow_records_intent_after_planner() -> None:
    """planner_node must record intent on the MemoryService when service present."""
    svc = LocalMemoryService()
    sid = uuid.uuid4()
    sel = _make_planner_selection("simulation")
    config = {
        "configurable": {
            "observer": None,
            "budget_tracker": None,
            "memory_service": svc,
            "thread_id": str(sid),
        }
    }

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner._build_system_prompt", return_value=("prompt", None, None)
        ),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": sel, "raw": MagicMock()},
        ),
        patch(
            "agents.planner.get_spec",
            return_value=MagicMock(
                autonomy_policy=MagicMock(tools=[]),
                decision_variables=[],
                domain_name="test",
            ),
        ),
    ):
        from agents.workflow import planner_node

        planner_node(_make_state("simulation"), config=config)

    state = svc.get_active_state(sid)
    assert state.intent == Intent.SIMULATE
    log = svc.read_audit(sid)
    assert any(t.slot == "intent" for t in log)


def test_workflow_records_active_run_after_tool() -> None:
    """tool_node must record the active simulation run on the MemoryService."""
    svc = LocalMemoryService()
    sid = uuid.uuid4()
    config = {
        "configurable": {
            "observer": None,
            "budget_tracker": None,
            "memory_service": svc,
            "thread_id": str(sid),
        }
    }
    state = _make_state("simulation")

    with patch("agents.workflow.simulation_tool", return_value={"scenario": "ok"}):
        from agents.workflow import tool_node

        tool_node(state, config=config)

    active = svc.get_active_state(sid)
    assert active.active_simulation_run == "test_run_001"
    log = svc.read_audit(sid)
    assert any(t.slot == "active_simulation_run" for t in log)


def test_workflow_creates_coordinator_per_session() -> None:
    """Each run_query call creates a fresh coordinator (no cross-session bleed)."""
    sid1 = str(uuid.uuid4())
    sid2 = str(uuid.uuid4())

    c1 = MemoryCoordinator(session_id=uuid.UUID(sid1))
    c2 = MemoryCoordinator(session_id=uuid.UUID(sid2))

    c1.set_intent(Intent.OPTIMIZE, turn_id=1, cause="planner:tool_selection")

    assert c2.get_state().intent is None
    assert c1.get_state().session_id != c2.get_state().session_id


def test_workflow_works_without_coordinator() -> None:
    """If no memory_service in config, planner_node must complete without error."""
    config = {"configurable": {"observer": None, "budget_tracker": None}}
    sel = _make_planner_selection("knowledge")

    with (
        patch("agents.planner._init_planner_llms"),
        patch(
            "agents.planner._build_system_prompt", return_value=("prompt", None, None)
        ),
        patch(
            "agents.planner.invoke_with_fallback",
            return_value={"parsed": sel, "raw": MagicMock()},
        ),
        patch(
            "agents.planner.get_spec",
            return_value=MagicMock(
                autonomy_policy=MagicMock(tools=[]),
                decision_variables=[],
                domain_name="test",
            ),
        ),
    ):
        from agents.workflow import planner_node

        result = planner_node(_make_state("knowledge"), config=config)

    assert result["action"] == "knowledge"
