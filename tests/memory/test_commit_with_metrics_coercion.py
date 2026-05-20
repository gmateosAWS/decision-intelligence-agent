"""
tests/memory/test_commit_with_metrics_coercion.py
--------------------------------------------------
Verifies that committing metrics via the reactive form does NOT produce
PydanticSerializationUnexpectedValue warnings (B4 fix).

All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid
import warnings

from core.protocols.memory import ProposalSource, SlotProposal, StateCommitDecision
from memory import LocalMemoryService


def test_no_pydantic_warnings_on_commit_with_metrics() -> None:
    """Committing metrics as list[dict] must not trigger Pydantic warnings (B4)."""
    svc = LocalMemoryService()
    sid = uuid.uuid4()

    metrics_dicts = [
        {"id": "revenue", "name": "Revenue", "source_turn": 1, "confidence": 0.9},
        {"id": "margin", "name": "Margin", "source_turn": 1, "confidence": 0.8},
    ]

    proposal = svc.propose_state_update(
        sid,
        turn_id=1,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="metrics",
                current_value=[],
                proposed_value=metrics_dicts,
                reason="test B4",
            )
        ],
    )

    # Capture any warnings produced during commit
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        svc.commit_state_update(
            sid,
            StateCommitDecision(
                session_id=sid,
                proposal_turn_id=proposal.turn_id,
                approved_mutations=list(proposal.mutations),
            ),
        )

    pydantic_warnings = [
        w for w in caught if "PydanticSerializationUnexpectedValue" in str(w.message)
    ]
    assert (
        pydantic_warnings == []
    ), f"Unexpected Pydantic serialization warnings: {pydantic_warnings}"


def test_committed_metrics_are_typed_resolved_metric() -> None:
    """Committed metrics must be ResolvedMetric objects, not plain dicts."""
    from memory.state.types import ResolvedMetric

    svc = LocalMemoryService()
    sid = uuid.uuid4()

    proposal = svc.propose_state_update(
        sid,
        turn_id=1,
        source=ProposalSource.PROACTIVE_PLANNER,
        pending_mutations=[
            SlotProposal(
                slot="metrics",
                current_value=[],
                proposed_value=[
                    {"id": "cac", "name": "CAC", "source_turn": 2, "confidence": 1.0}
                ],
                reason="test",
            )
        ],
    )
    svc.commit_state_update(
        sid,
        StateCommitDecision(
            session_id=sid,
            proposal_turn_id=proposal.turn_id,
            approved_mutations=list(proposal.mutations),
        ),
    )
    state = svc.get_active_state(sid)
    assert len(state.metrics) == 1
    assert isinstance(state.metrics[0], ResolvedMetric)
    assert state.metrics[0].id == "cac"
