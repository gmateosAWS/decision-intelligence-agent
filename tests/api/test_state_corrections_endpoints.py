"""
tests/api/test_state_corrections_endpoints.py
----------------------------------------------
Tests for the state proposals/commits API endpoints (item 5.13).
Offline — memory service uses in-memory store (no DB).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from memory import LocalMemoryService


@pytest.fixture()
def client_and_svc():
    """TestClient with a real (in-memory) LocalMemoryService injected."""
    from api.main import app

    svc = LocalMemoryService()

    with patch("memory._memory_service", svc):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, svc


# ── POST /sessions/{id}/state/proposals ──────────────────────────────────────


def test_create_reactive_proposal_returns_201(client_and_svc):
    client, svc = client_and_svc
    sid = str(uuid.uuid4())
    resp = client.post(
        f"/v1/sessions/{sid}/state/proposals",
        json={"source": "reactive_user"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_id"] == sid
    assert data["source"] == "reactive_user"
    assert len(data["mutations"]) > 0


def test_create_proactive_proposal_with_mutations_returns_201(client_and_svc):
    client, svc = client_and_svc
    sid = str(uuid.uuid4())
    resp = client.post(
        f"/v1/sessions/{sid}/state/proposals",
        json={
            "source": "proactive_planner",
            "pending_mutations": [
                {
                    "slot": "active_simulation_run",
                    "current_value": None,
                    "proposed_value": "run_abc",
                    "reason": "test",
                }
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["mutations"][0]["slot"] == "active_simulation_run"


def test_create_proposal_invalid_source_returns_422(client_and_svc):
    client, _ = client_and_svc
    sid = str(uuid.uuid4())
    resp = client.post(
        f"/v1/sessions/{sid}/state/proposals",
        json={"source": "invalid_source"},
    )
    assert resp.status_code == 422


# ── POST /sessions/{id}/state/commits ────────────────────────────────────────


def test_commit_decision_applies_mutation(client_and_svc):
    client, svc = client_and_svc
    sid_uuid = uuid.uuid4()
    sid = str(sid_uuid)

    # Create proposal first
    from core.protocols.memory import ProposalSource, SlotProposal

    proposal = svc.propose_state_update(
        sid_uuid,
        turn_id=1,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="active_optimization_run",
                current_value=None,
                proposed_value="run_opt_api",
                reason="API test",
            )
        ],
    )

    resp = client.post(
        f"/v1/sessions/{sid}/state/commits",
        json={
            "proposal_turn_id": proposal.turn_id,
            "approved_mutations": [
                {
                    "slot": "active_optimization_run",
                    "current_value": None,
                    "proposed_value": "run_opt_api",
                    "reason": "API test",
                }
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_after"] > data["version_before"]
    assert data["applied_mutations"][0]["slot"] == "active_optimization_run"


def test_commit_unknown_proposal_returns_400(client_and_svc):
    client, _ = client_and_svc
    sid = str(uuid.uuid4())
    resp = client.post(
        f"/v1/sessions/{sid}/state/commits",
        json={"proposal_turn_id": 9999},
    )
    assert resp.status_code == 400
