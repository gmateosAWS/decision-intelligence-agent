"""
tests/memory/state/test_active_state.py
----------------------------------------
Unit tests for ActiveAnalyticalState and FrozenActiveAnalyticalState.
All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from memory.state.active import ActiveAnalyticalState, FrozenActiveAnalyticalState
from memory.state.types import Intent, ResolvedMetric


def _state() -> ActiveAnalyticalState:
    return ActiveAnalyticalState(session_id=uuid.uuid4())


def test_initial_state_is_empty() -> None:
    s = _state()
    assert s.version == 0
    assert s.intent is None
    assert s.metrics == []
    assert s.active_simulation_run is None
    assert s.active_optimization_run is None
    assert s.active_scenarios == []
    assert s.frozen_slots == set()


def test_frozen_is_immutable() -> None:
    s = _state()
    frozen = s.frozen()
    assert isinstance(frozen, FrozenActiveAnalyticalState)
    with pytest.raises(ValidationError):
        frozen.version = 99


def test_frozen_is_deep_copy() -> None:
    s = _state()
    s.metrics = [ResolvedMetric(id="m1", name="Metric 1", source_turn=0)]
    frozen = s.frozen()
    # Mutate original after freeze — frozen must be unaffected
    s.metrics = s.metrics + [ResolvedMetric(id="m2", name="Metric 2", source_turn=1)]
    assert len(frozen.metrics) == 1
    assert frozen.metrics[0].id == "m1"


def test_version_increments_on_mutation() -> None:
    """Version counter is append-only — each setattr in coordinator bumps it."""
    s = _state()
    assert s.version == 0
    s.version += 1
    assert s.version == 1
    s.version += 1
    assert s.version == 2


def test_metrics_appended_correctly() -> None:
    s = _state()
    m1 = ResolvedMetric(id="profit", name="Expected Profit", source_turn=1)
    m2 = ResolvedMetric(id="revenue", name="Revenue", source_turn=1)
    s.metrics = [m1]
    s.metrics = s.metrics + [m2]
    assert len(s.metrics) == 2
    assert s.metrics[0].id == "profit"
    assert s.metrics[1].id == "revenue"


def test_provenance_recorded_for_every_slot() -> None:
    from memory.state.types import SlotProvenance

    s = _state()
    prov = SlotProvenance(introduced_at_turn=1, introduced_by="planner")
    s.provenance["intent"] = prov
    assert s.provenance["intent"].introduced_by == "planner"
    assert s.provenance["intent"].introduced_at_turn == 1


def test_intent_set_records_transition() -> None:
    """Coordinator set_intent creates a StateTransition — tested via coordinator."""
    from memory.coordinator.coordinator import MemoryCoordinator

    c = MemoryCoordinator(session_id=uuid.uuid4())
    c.set_intent(Intent.SIMULATE, turn_id=1, cause="planner:tool_selection")
    frozen = c.get_state()
    assert frozen.intent == Intent.SIMULATE
    assert frozen.version == 1
    log = c.get_audit_log()
    assert len(log) == 1
    assert log[0].slot == "intent"


def test_frozen_slot_blocks_mutation() -> None:
    from memory.coordinator.coordinator import MemoryCoordinator

    c = MemoryCoordinator(session_id=uuid.uuid4())
    c._state.frozen_slots = {"intent"}
    c.set_intent(Intent.OPTIMIZE, turn_id=1, cause="planner:tool_selection")
    assert c.get_state().intent is None  # blocked
    assert len(c.get_audit_log()) == 0


def test_object_bus_fields_are_strings() -> None:
    # TODO(1.6/ObjectBus): when ObjectBus lands, these become ObjectId | None
    s = _state()
    assert s.active_simulation_run is None
    assert s.active_optimization_run is None
    assert isinstance(s.active_scenarios, list)
    # Verify they accept str
    s.active_simulation_run = "abc123"
    s.active_optimization_run = "def456"
    assert s.active_simulation_run == "abc123"
