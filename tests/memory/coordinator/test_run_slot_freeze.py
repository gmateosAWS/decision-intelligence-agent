"""
tests/memory/coordinator/test_run_slot_freeze.py
-------------------------------------------------
Verifies that freezing active_simulation_run / active_optimization_run emits
MutationBlocked via set_active_simulation_run / set_active_optimization_run
and that the outcome propagates through LocalMemoryService.record_active_run.

All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid

from core.protocols.memory import MutationApplied, MutationBlocked
from memory import LocalMemoryService
from memory.coordinator.coordinator import MemoryCoordinator

# ---------------------------------------------------------------------------
# Coordinator-level tests
# ---------------------------------------------------------------------------


def _coord() -> MemoryCoordinator:
    return MemoryCoordinator(session_id=uuid.uuid4())


def test_set_active_simulation_run_returns_applied_when_not_frozen() -> None:
    coord = _coord()
    outcome = coord.set_active_simulation_run("run-abc", turn_id=1, cause="test")
    assert isinstance(outcome, MutationApplied)
    assert outcome.slot == "active_simulation_run"
    assert outcome.after == "run-abc"


def test_set_active_simulation_run_returns_blocked_when_frozen() -> None:
    coord = _coord()
    coord.set_active_simulation_run("run-original", turn_id=1, cause="seed")
    coord.freeze_slot("active_simulation_run", turn_id=2, cause="user:freeze")

    outcome = coord.set_active_simulation_run("run-new", turn_id=3, cause="test")

    assert isinstance(outcome, MutationBlocked)
    assert outcome.slot == "active_simulation_run"
    assert outcome.blocked_value == "run-new"
    assert outcome.reason == "frozen_by_user"
    assert outcome.current_value == "run-original"
    # State must be preserved
    assert coord.get_state().active_simulation_run == "run-original"


def test_set_active_optimization_run_returns_applied_when_not_frozen() -> None:
    coord = _coord()
    outcome = coord.set_active_optimization_run("opt-abc", turn_id=1, cause="test")
    assert isinstance(outcome, MutationApplied)
    assert outcome.slot == "active_optimization_run"
    assert outcome.after == "opt-abc"


def test_set_active_optimization_run_returns_blocked_when_frozen() -> None:
    coord = _coord()
    coord.set_active_optimization_run("opt-original", turn_id=1, cause="seed")
    coord.freeze_slot("active_optimization_run", turn_id=2, cause="user:freeze")

    outcome = coord.set_active_optimization_run("opt-new", turn_id=3, cause="test")

    assert isinstance(outcome, MutationBlocked)
    assert outcome.slot == "active_optimization_run"
    assert outcome.blocked_value == "opt-new"
    assert outcome.reason == "frozen_by_user"
    assert outcome.current_value == "opt-original"
    assert coord.get_state().active_optimization_run == "opt-original"


def test_run_slot_identity_is_noop() -> None:
    """Identity mutation on run slot: MutationApplied, no version bump."""
    coord = _coord()
    coord.set_active_simulation_run("run-same", turn_id=1, cause="seed")
    version_before = coord.get_state().version

    outcome = coord.set_active_simulation_run("run-same", turn_id=2, cause="test")

    assert isinstance(outcome, MutationApplied)
    assert coord.get_state().version == version_before


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_record_active_run_returns_applied() -> None:
    svc = LocalMemoryService()
    sid = uuid.uuid4()
    outcome = svc.record_active_run(
        sid, tool="simulation", run_id="run-x", turn_id=1, cause="test"
    )
    assert isinstance(outcome, MutationApplied)
    assert outcome.slot == "active_simulation_run"


def test_record_active_run_returns_blocked_when_frozen() -> None:
    svc = LocalMemoryService()
    sid = uuid.uuid4()

    # Seed and freeze via the proposal/commit path (direct coordinator access for test)
    coord = svc._get_or_load(sid)
    coord.set_active_simulation_run("run-original", turn_id=1, cause="seed")
    coord.freeze_slot("active_simulation_run", turn_id=2, cause="user:freeze")

    outcome = svc.record_active_run(
        sid, tool="simulation", run_id="run-new", turn_id=3, cause="test"
    )

    assert isinstance(outcome, MutationBlocked)
    assert outcome.slot == "active_simulation_run"
    assert outcome.blocked_value == "run-new"
    assert outcome.current_value == "run-original"
    assert svc.get_active_state(sid).active_simulation_run == "run-original"


def test_record_active_run_returns_none_for_unknown_tool() -> None:
    svc = LocalMemoryService()
    sid = uuid.uuid4()
    outcome = svc.record_active_run(
        sid, tool="knowledge", run_id="run-x", turn_id=1, cause="test"
    )
    assert outcome is None
