"""
tests/memory/test_proposals_and_commits.py
-------------------------------------------
Unit tests for propose_state_update / commit_state_update on LocalMemoryService.
All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid

import pytest

from core.protocols.memory import (
    ProposalSource,
    SlotProposal,
    StateCommitDecision,
    StateProposal,
)
from memory import LocalMemoryService


def _svc() -> LocalMemoryService:
    return LocalMemoryService()


# ── Proposal tests ────────────────────────────────────────────────────────────


def test_propose_reactive_returns_editable_slots() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid, turn_id=1, source=ProposalSource.REACTIVE_USER
    )
    assert isinstance(proposal, StateProposal)
    slots = {m.slot for m in proposal.mutations}
    expected = {
        "intent",
        "metrics",
        "active_simulation_run",
        "active_optimization_run",
        "active_scenarios",
    }
    assert expected.issubset(slots)


def test_propose_reactive_identity_values() -> None:
    """Reactive mutations must have current_value == proposed_value (identity)."""
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid, turn_id=2, source=ProposalSource.REACTIVE_USER
    )
    for m in proposal.mutations:
        assert m.current_value == m.proposed_value


def test_propose_proactive_uses_supplied_mutations() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    mutation = SlotProposal(
        slot="active_optimization_run",
        current_value=None,
        proposed_value="run_abc",
        reason="Test proactive",
    )
    proposal = svc.propose_state_update(
        sid,
        turn_id=5,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[mutation],
    )
    assert len(proposal.mutations) == 1
    assert proposal.mutations[0].slot == "active_optimization_run"
    assert proposal.mutations[0].proposed_value == "run_abc"


def test_propose_stored_in_memory_store() -> None:
    """The proposal must be retrievable from the in-memory store until committed."""
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid, turn_id=3, source=ProposalSource.REACTIVE_USER
    )
    assert (sid, proposal.turn_id) in svc._proposals


def test_propose_proactive_empty_mutations() -> None:
    """pending_mutations=None for PROACTIVE_PLANNER must produce an empty list."""
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid, turn_id=1, source=ProposalSource.PROACTIVE_PLANNER, pending_mutations=None
    )
    assert proposal.mutations == []


# ── Commit tests ──────────────────────────────────────────────────────────────


def test_commit_applies_simulation_run() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid,
        turn_id=1,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="active_simulation_run",
                current_value=None,
                proposed_value="run_sim",
                reason="test",
            )
        ],
    )
    result = svc.commit_state_update(
        sid,
        StateCommitDecision(
            session_id=sid,
            proposal_turn_id=proposal.turn_id,
            approved_mutations=list(proposal.mutations),
        ),
    )
    state = svc.get_active_state(sid)
    assert state.active_simulation_run == "run_sim"
    assert result.version_after > result.version_before


def test_commit_removes_proposal_from_store() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid, turn_id=10, source=ProposalSource.REACTIVE_USER
    )
    svc.commit_state_update(
        sid,
        StateCommitDecision(
            session_id=sid,
            proposal_turn_id=proposal.turn_id,
        ),
    )
    assert (sid, proposal.turn_id) not in svc._proposals


def test_commit_missing_proposal_raises() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    with pytest.raises(ValueError, match="No open proposal"):
        svc.commit_state_update(
            sid,
            StateCommitDecision(session_id=sid, proposal_turn_id=999),
        )


def test_commit_frozen_slot_skipped() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    # Freeze intent slot via a commit decision
    svc.record_tool_selection(
        sid, tool="simulation", turn_id=1, cause="planner:tool_selection"
    )
    state_before = svc.get_active_state(sid)
    # Freeze intent manually via coordinator
    coord = svc._get_or_load(sid)
    coord.freeze_slot("intent", turn_id=2, cause="test:freeze")

    proposal = svc.propose_state_update(
        sid,
        turn_id=3,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="intent",
                current_value=state_before.intent,
                proposed_value=None,
                reason="try to clear intent",
            )
        ],
    )
    result = svc.commit_state_update(
        sid,
        StateCommitDecision(
            session_id=sid,
            proposal_turn_id=proposal.turn_id,
            approved_mutations=list(proposal.mutations),
        ),
    )
    assert "intent" in result.skipped_slots


def test_commit_freeze_and_unfreeze_slots() -> None:
    svc = _svc()
    sid = uuid.uuid4()
    proposal = svc.propose_state_update(
        sid, turn_id=1, source=ProposalSource.REACTIVE_USER
    )
    # Freeze metrics via decision
    svc.commit_state_update(
        sid,
        StateCommitDecision(
            session_id=sid,
            proposal_turn_id=proposal.turn_id,
            freeze_slots=["metrics"],
        ),
    )
    state = svc.get_active_state(sid)
    assert "metrics" in state.frozen_slots

    # Unfreeze via a second proposal+commit
    proposal2 = svc.propose_state_update(
        sid, turn_id=2, source=ProposalSource.REACTIVE_USER
    )
    svc.commit_state_update(
        sid,
        StateCommitDecision(
            session_id=sid,
            proposal_turn_id=proposal2.turn_id,
            unfreeze_slots=["metrics"],
        ),
    )
    state2 = svc.get_active_state(sid)
    assert "metrics" not in state2.frozen_slots
