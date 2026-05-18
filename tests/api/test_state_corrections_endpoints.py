"""
tests/api/test_state_corrections_endpoints.py
----------------------------------------------
Tests for the state proposals/commits API endpoints (item 5.13).
Offline — memory service uses in-memory store (no DB).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from memory import LocalMemoryService


def _mock_graph() -> MagicMock:
    """Return a MagicMock that satisfies the graph dependency without LLM calls."""
    g = MagicMock()
    g.get_state.return_value = MagicMock(values={})
    return g


@pytest.fixture()
def client_and_svc():
    """TestClient with a real (in-memory) LocalMemoryService injected.

    The graph dependency is overridden with a MagicMock so the commit endpoint
    can be called without building the full LangGraph workflow.
    """
    from api.main import app
    from api.routers.sessions import _get_graph

    svc = LocalMemoryService()
    mock_graph = _mock_graph()

    app.dependency_overrides[_get_graph] = lambda: mock_graph

    with patch("memory._memory_service", svc):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, svc, mock_graph

    app.dependency_overrides.clear()


# ── POST /sessions/{id}/state/proposals ──────────────────────────────────────


def test_create_reactive_proposal_returns_201(client_and_svc):
    client, svc, _ = client_and_svc
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
    client, svc, _ = client_and_svc
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
    client, _, _ = client_and_svc
    sid = str(uuid.uuid4())
    resp = client.post(
        f"/v1/sessions/{sid}/state/proposals",
        json={"source": "invalid_source"},
    )
    assert resp.status_code == 422


# ── POST /sessions/{id}/state/commits ────────────────────────────────────────


def test_commit_decision_applies_mutation(client_and_svc):
    client, svc, _ = client_and_svc
    sid_uuid = uuid.uuid4()
    sid = str(sid_uuid)

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
            "resume_query": False,  # no rerun needed for this test
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_after"] > data["version_before"]
    assert data["applied_mutations"][0]["slot"] == "active_optimization_run"


def test_commit_unknown_proposal_returns_400(client_and_svc):
    client, _, _ = client_and_svc
    sid = str(uuid.uuid4())
    resp = client.post(
        f"/v1/sessions/{sid}/state/commits",
        json={"proposal_turn_id": 9999, "resume_query": False},
    )
    assert resp.status_code == 400


# ── resume_query behaviour (hotfix 5.13 Bug 2) ────────────────────────────────


def test_commit_with_resume_query_false_does_not_set_resumed_run(client_and_svc):
    """When resume_query=False, resumed_run must be None."""
    client, svc, _ = client_and_svc
    sid_uuid = uuid.uuid4()
    sid = str(sid_uuid)

    from core.protocols.memory import ProposalSource, SlotProposal

    proposal = svc.propose_state_update(
        sid_uuid,
        turn_id=2,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="intent",
                current_value=None,
                proposed_value="optimization",
                reason="test",
            )
        ],
        original_query="optimiza el precio",
    )

    resp = client.post(
        f"/v1/sessions/{sid}/state/commits",
        json={
            "proposal_turn_id": proposal.turn_id,
            "approved_mutations": [
                {
                    "slot": "intent",
                    "current_value": None,
                    "proposed_value": "optimization",
                    "reason": "test",
                }
            ],
            "resume_query": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["resumed_run"] is None


def test_commit_with_no_original_query_does_not_resume(client_and_svc):
    """When original_query='', resume_query=True still skips re-invocation."""
    client, svc, _ = client_and_svc
    sid_uuid = uuid.uuid4()
    sid = str(sid_uuid)

    from core.protocols.memory import ProposalSource, SlotProposal

    proposal = svc.propose_state_update(
        sid_uuid,
        turn_id=3,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="intent",
                current_value=None,
                proposed_value="simulation",
                reason="test",
            )
        ],
        original_query="",  # no original query stored
    )

    resp = client.post(
        f"/v1/sessions/{sid}/state/commits",
        json={
            "proposal_turn_id": proposal.turn_id,
            "approved_mutations": [
                {
                    "slot": "intent",
                    "current_value": None,
                    "proposed_value": "simulation",
                    "reason": "test",
                }
            ],
            "resume_query": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["resumed_run"] is None


def test_original_query_stored_in_proposal(client_and_svc) -> None:
    """original_query passed to propose_state_update is stored in the proposal."""
    _, svc, _ = client_and_svc
    sid_uuid = uuid.uuid4()

    from core.protocols.memory import ProposalSource, SlotProposal

    proposal = svc.propose_state_update(
        sid_uuid,
        turn_id=4,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="intent",
                current_value=None,
                proposed_value="optimization",
                reason="",
            )
        ],
        original_query="optimiza el precio para maximizar el beneficio",
    )
    assert proposal.original_query == "optimiza el precio para maximizar el beneficio"


def test_commit_with_resume_query_true_calls_run_query(client_and_svc) -> None:
    """When resume_query=True and original_query is set, run_query is invoked."""
    client, svc, _ = client_and_svc
    sid_uuid = uuid.uuid4()
    sid = str(sid_uuid)

    from core.protocols.memory import ProposalSource, SlotProposal

    proposal = svc.propose_state_update(
        sid_uuid,
        turn_id=5,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="intent",
                current_value=None,
                proposed_value="optimization",
                reason="test",
            )
        ],
        original_query="optimiza el precio",
    )

    from agents.runner import RunResult

    mock_run_result = RunResult(
        answer="Precio óptimo: 28€",
        session_id=sid,
        run_id="run-test",
        success=True,
        tool_used="optimization",
        latency_ms=500.0,
    )

    with patch("agents.runner.run_query", return_value=mock_run_result) as mock_rq:
        resp = client.post(
            f"/v1/sessions/{sid}/state/commits",
            json={
                "proposal_turn_id": proposal.turn_id,
                "approved_mutations": [
                    {
                        "slot": "intent",
                        "current_value": None,
                        "proposed_value": "optimization",
                        "reason": "test",
                    }
                ],
                "resume_query": True,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    mock_rq.assert_called_once()
    assert mock_rq.call_args.kwargs.get("bypass_gate") is True
    assert data["resumed_run"] is not None
    assert data["resumed_run"]["answer"] == "Precio óptimo: 28€"
