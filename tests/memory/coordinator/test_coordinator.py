"""
tests/memory/coordinator/test_coordinator.py
----------------------------------------------
Unit tests for MemoryCoordinator. All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid

import pytest

from memory.coordinator.coordinator import MemoryCoordinator
from memory.state.audit import TransitionOp
from memory.state.types import Intent, ResolvedMetric


def _coordinator() -> MemoryCoordinator:
    return MemoryCoordinator(session_id=uuid.uuid4())


def test_coordinator_creates_empty_state() -> None:
    c = _coordinator()
    state = c.get_state()
    assert state.version == 0
    assert state.intent is None
    assert state.metrics == []
    assert state.active_simulation_run is None


def test_set_intent_creates_transition() -> None:
    c = _coordinator()
    c.set_intent(
        Intent.OPTIMIZE,
        turn_id=1,
        cause="planner:tool_selection",
        evidence="user asked for max price",
    )
    state = c.get_state()
    assert state.intent == Intent.OPTIMIZE
    assert state.version == 1
    log = c.get_audit_log()
    assert len(log) == 1
    t = log[0]
    assert t.slot == "intent"
    assert t.op == TransitionOp.SET
    assert t.cause == "planner:tool_selection"
    assert t.turn_id == 1


def test_add_metric_appends_and_records_provenance() -> None:
    c = _coordinator()
    m = ResolvedMetric(id="expected_profit", name="Expected Profit", source_turn=1)
    c.add_metric(
        m,
        turn_id=1,
        cause="planner:metric_extraction",
        evidence="user mentioned profit",
    )
    state = c.get_state()
    assert len(state.metrics) == 1
    assert state.metrics[0].id == "expected_profit"
    assert state.provenance["metrics"].introduced_at_turn == 1
    log = c.get_audit_log()
    assert len(log) == 1
    assert log[0].op == TransitionOp.APPEND


def test_set_active_simulation_run_overwrites_if_exists() -> None:
    c = _coordinator()
    c.set_active_simulation_run("run_001", turn_id=1, cause="tool:simulation")
    c.set_active_simulation_run("run_002", turn_id=2, cause="tool:simulation")
    state = c.get_state()
    assert state.active_simulation_run == "run_002"
    log = c.get_audit_log()
    assert log[0].op == TransitionOp.SET
    assert log[1].op == TransitionOp.OVERWRITE


def test_audit_log_is_chronologically_ordered() -> None:
    c = _coordinator()
    c.set_intent(Intent.SIMULATE, turn_id=1, cause="planner:tool_selection")
    m = ResolvedMetric(id="profit", name="Profit", source_turn=2)
    c.add_metric(m, turn_id=2, cause="planner:metric_extraction")
    c.set_active_simulation_run("run_x", turn_id=2, cause="tool:simulation")
    log = c.get_audit_log()
    assert len(log) == 3
    assert log[0].turn_id == 1
    assert log[1].turn_id == 2
    assert log[2].turn_id == 2


def test_audit_log_filterable_by_turn() -> None:
    c = _coordinator()
    c.set_intent(Intent.EXPLAIN, turn_id=1, cause="planner:tool_selection")
    m = ResolvedMetric(id="profit", name="Profit", source_turn=3)
    c.add_metric(m, turn_id=3, cause="planner:metric_extraction")
    log_all = c.get_audit_log(since_turn=0)
    log_from_3 = c.get_audit_log(since_turn=3)
    assert len(log_all) == 2
    assert len(log_from_3) == 1
    assert log_from_3[0].slot == "metrics"


def test_persist_and_load_roundtrip(pytestmark=None) -> None:
    """Integration test — requires DATABASE_URL. Skipped in offline CI."""
    import os

    if not os.getenv("DATABASE_URL", ""):
        pytest.skip("DATABASE_URL not set — skipping DB roundtrip test")

    sid = uuid.uuid4()
    c = MemoryCoordinator(session_id=sid)
    c.set_intent(Intent.SIMULATE, turn_id=1, cause="planner:tool_selection")
    c.set_active_simulation_run("run_abc", turn_id=1, cause="tool:simulation")
    c.persist_to_db()

    loaded = MemoryCoordinator.load_from_db(session_id=sid)
    state = loaded.get_state()
    assert state.intent == Intent.SIMULATE
    assert state.active_simulation_run == "run_abc"
    assert len(loaded.get_audit_log()) == 2
