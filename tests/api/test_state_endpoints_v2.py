"""
tests/api/test_state_endpoints_v2.py
--------------------------------------
Verifies that GET /v1/sessions/{id}/state and /state/audit go through the
MemoryService Protocol facade (item 5.11) rather than touching MemoryCoordinator
or memory internals directly.

Complements test_state_endpoints.py which tests correctness of the response payload;
this file tests the architectural boundary: the endpoint must call get_memory_service().
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _make_frozen_state(
    intent_value: str | None = None,
    sim_run: str | None = None,
    version: int = 0,
) -> MagicMock:
    state = MagicMock()
    state.version = version
    state.last_turn_id = 0
    state.intent = MagicMock(value=intent_value) if intent_value else None
    state.metrics = []
    state.active_simulation_run = sim_run
    state.active_optimization_run = None
    state.active_scenarios = set()
    return state


def test_state_endpoint_uses_memory_service_not_coordinator() -> None:
    """GET /v1/sessions/{id}/state must call get_memory_service().get_active_state()
    and must NOT import or call MemoryCoordinator directly.

    If this test passes, the router is correctly delegating through the Protocol.
    """
    sid = str(uuid.uuid4())
    fake_state = _make_frozen_state(
        intent_value="simulate", sim_run="run_abc", version=2
    )

    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = fake_state

    with patch("memory.get_memory_service", return_value=mock_svc):
        resp = client.get(f"/v1/sessions/{sid}/state")

    assert resp.status_code == 200
    mock_svc.get_active_state.assert_called_once_with(uuid.UUID(sid))

    data = resp.json()
    assert data["intent"] == "simulate"
    assert data["active_simulation_run"] == "run_abc"
    assert data["version"] == 2


def test_audit_endpoint_uses_memory_service() -> None:
    """GET /v1/sessions/{id}/state/audit must call get_memory_service().read_audit()."""
    sid = str(uuid.uuid4())

    t = MagicMock()
    t.turn_id = 1
    t.version_before = 0
    t.version_after = 1
    t.slot = "intent"
    t.op = MagicMock(value="set")
    t.before = None
    t.after = "simulate"
    t.cause = "planner:tool_selection"
    t.evidence = ""
    t.timestamp = MagicMock()
    t.timestamp.isoformat.return_value = "2026-05-14T00:00:00+00:00"

    mock_svc = MagicMock()
    mock_svc.read_audit.return_value = [t]

    with patch("memory.get_memory_service", return_value=mock_svc):
        resp = client.get(f"/v1/sessions/{sid}/state/audit")

    assert resp.status_code == 200
    mock_svc.read_audit.assert_called_once_with(uuid.UUID(sid), since_turn=0)

    data = resp.json()
    assert data["total"] == 1
    assert data["transitions"][0]["slot"] == "intent"
