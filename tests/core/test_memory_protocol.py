"""
tests/core/test_memory_protocol.py
------------------------------------
Unit tests for the MemoryService Protocol and LocalMemoryService.
All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from core.protocols.memory import MemoryService
from memory import LocalMemoryService
from memory.state.types import Intent


def _service() -> LocalMemoryService:
    return LocalMemoryService()


def test_local_memory_service_implements_protocol() -> None:
    """LocalMemoryService must satisfy the MemoryService Protocol structurally."""
    svc = _service()
    assert isinstance(svc, MemoryService)


def test_get_active_state_returns_frozen() -> None:
    """get_active_state must return a frozen (immutable) snapshot."""
    from pydantic import ValidationError

    svc = _service()
    sid = uuid.uuid4()
    state = svc.get_active_state(sid)
    assert state.version == 0
    # Frozen state must reject direct attribute mutation.
    with pytest.raises((ValidationError, TypeError)):
        state.version = 99  # type: ignore[misc]


def test_multiple_sessions_isolated() -> None:
    """Two session_ids must not share any coordinator state."""
    svc = _service()
    sid1, sid2 = uuid.uuid4(), uuid.uuid4()

    svc.record_tool_selection(
        sid1, tool="optimization", turn_id=1, cause="planner:tool_selection"
    )

    s1 = svc.get_active_state(sid1)
    s2 = svc.get_active_state(sid2)

    assert s1.intent == Intent.OPTIMIZE
    assert s2.intent is None


def test_service_loads_from_db_lazily() -> None:
    """_get_or_load must call load_from_db on first access, not before."""
    from memory.coordinator.coordinator import MemoryCoordinator

    svc = _service()
    sid = uuid.uuid4()

    with patch.object(
        MemoryCoordinator, "load_from_db", wraps=MemoryCoordinator.load_from_db
    ) as mock_load:
        # First access triggers load.
        svc.get_active_state(sid)
        assert mock_load.call_count == 1
        # Second access uses the cache — no second load.
        svc.get_active_state(sid)
        assert mock_load.call_count == 1


def test_service_fail_open_without_db() -> None:
    """Service must return a fresh empty coordinator when DB is unreachable."""
    from memory.coordinator.coordinator import MemoryCoordinator

    svc = _service()
    sid = uuid.uuid4()

    with patch.object(
        MemoryCoordinator, "load_from_db", side_effect=RuntimeError("no DB")
    ):
        state = svc.get_active_state(sid)

    assert state.version == 0
    assert state.intent is None


def test_record_tool_selection_sets_intent() -> None:
    svc = _service()
    sid = uuid.uuid4()

    svc.record_tool_selection(
        sid, tool="simulation", turn_id=1, cause="planner:tool_selection"
    )

    state = svc.get_active_state(sid)
    assert state.intent == Intent.SIMULATE
    assert state.version == 1


def test_record_active_run_simulation() -> None:
    svc = _service()
    sid = uuid.uuid4()

    svc.record_active_run(
        sid, tool="simulation", run_id="run_xyz", turn_id=1, cause="tool:simulation"
    )

    state = svc.get_active_state(sid)
    assert state.active_simulation_run == "run_xyz"


def test_record_active_run_optimization() -> None:
    svc = _service()
    sid = uuid.uuid4()

    svc.record_active_run(
        sid, tool="optimization", run_id="run_opt", turn_id=1, cause="tool:optimization"
    )

    state = svc.get_active_state(sid)
    assert state.active_optimization_run == "run_opt"


def test_record_active_run_unknown_tool_is_ignored() -> None:
    svc = _service()
    sid = uuid.uuid4()

    svc.record_active_run(
        sid, tool="knowledge", run_id="run_k", turn_id=1, cause="tool:knowledge"
    )

    state = svc.get_active_state(sid)
    assert state.active_simulation_run is None
    assert state.active_optimization_run is None


def test_read_audit_returns_transitions() -> None:
    svc = _service()
    sid = uuid.uuid4()

    svc.record_tool_selection(sid, tool="optimization", turn_id=1, cause="planner")
    svc.record_active_run(
        sid, tool="optimization", run_id="r", turn_id=1, cause="tool:optimization"
    )

    log = svc.read_audit(sid)
    assert len(log) == 2

    log_filtered = svc.read_audit(sid, since_turn=2)
    assert len(log_filtered) == 0


def test_propose_commit_return_placeholders() -> None:
    """v1 placeholder methods must return without raising."""
    from core.protocols.memory import (
        StateCommitDecision,
        StateCommitResult,
        StateProposal,
    )

    svc = _service()
    sid = uuid.uuid4()

    proposal = svc.propose_state_update(sid, turn_id=1)
    assert isinstance(proposal, StateProposal)

    result = svc.commit_state_update(sid, decision=StateCommitDecision())
    assert isinstance(result, StateCommitResult)
