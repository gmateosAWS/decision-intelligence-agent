"""
tests/api/test_state_endpoints.py
-----------------------------------
Unit tests for GET /v1/sessions/{id}/state and /state/audit.
No real DB — MemoryCoordinator.load_from_db is mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from memory.coordinator.coordinator import MemoryCoordinator
from memory.state.types import Intent

client = TestClient(app)


def _empty_coordinator(session_id: uuid.UUID) -> MemoryCoordinator:
    return MemoryCoordinator(session_id=session_id)


def _populated_coordinator(session_id: uuid.UUID) -> MemoryCoordinator:
    c = MemoryCoordinator(session_id=session_id)
    c.set_intent(
        Intent.SIMULATE, turn_id=1, cause="planner:tool_selection", evidence="test"
    )
    c.set_active_simulation_run("run_abc", turn_id=1, cause="tool:simulation")
    return c


def test_get_session_state_returns_serialized() -> None:
    sid = str(uuid.uuid4())
    expected_coordinator = _populated_coordinator(uuid.UUID(sid))

    with patch(
        "memory.coordinator.coordinator.MemoryCoordinator.load_from_db",
        return_value=expected_coordinator,
    ):
        resp = client.get(f"/v1/sessions/{sid}/state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sid
    assert data["intent"] == "simulate"
    assert data["active_simulation_run"] == "run_abc"
    assert data["version"] == 2


def test_get_session_state_empty_session() -> None:
    sid = str(uuid.uuid4())

    with patch(
        "memory.coordinator.coordinator.MemoryCoordinator.load_from_db",
        return_value=_empty_coordinator(uuid.UUID(sid)),
    ):
        resp = client.get(f"/v1/sessions/{sid}/state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] is None
    assert data["version"] == 0


def test_get_session_state_invalid_uuid() -> None:
    resp = client.get("/v1/sessions/not-a-uuid/state")
    assert resp.status_code == 422


def test_get_session_state_audit_with_since_filter() -> None:
    sid = str(uuid.uuid4())
    coordinator = _populated_coordinator(uuid.UUID(sid))

    with patch(
        "memory.coordinator.coordinator.MemoryCoordinator.load_from_db",
        return_value=coordinator,
    ):
        resp_all = client.get(f"/v1/sessions/{sid}/state/audit")
        resp_filtered = client.get(f"/v1/sessions/{sid}/state/audit?since_turn=2")

    assert resp_all.status_code == 200
    all_data = resp_all.json()
    assert all_data["total"] == 2

    assert resp_filtered.status_code == 200
    filtered_data = resp_filtered.json()
    # turn_id=1 for both transitions → since_turn=2 returns 0
    assert filtered_data["total"] == 0
