"""api/routers/sessions.py — CRUD for /v1/sessions."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.schemas.sessions import (
    AnalyticalStateResponse,
    CommitDecisionRequest,
    CommitResultResponse,
    ProposalCreateRequest,
    ProposalResponse,
    SessionListResponse,
    SessionResponse,
    SlotProposalSchema,
    StateAuditResponse,
    StateTransitionResponse,
)

router = APIRouter(tags=["sessions"])


def _get_graph() -> Any:
    """FastAPI dependency — returns the compiled LangGraph agent singleton."""
    from api.dependencies import get_graph  # noqa: PLC0415

    return get_graph()


def _row_to_response(row: dict) -> SessionResponse:
    return SessionResponse(
        session_id=str(row["session_id"]),
        title=row.get("title") or "",
        created_at=str(row.get("created_at") or ""),
        last_active=str(row.get("last_active") or ""),
        turn_count=int(row.get("turn_count") or 0),
    )


@router.get("/sessions", response_model=SessionListResponse, summary="List sessions")
def list_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> SessionListResponse:
    """Return all conversation sessions ordered by most-recently active."""
    from memory.session_manager import SessionManager

    rows = SessionManager.list_sessions()
    return SessionListResponse(
        sessions=[_row_to_response(r) for r in rows[skip : skip + limit]],
        total=len(rows),
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get session detail",
)
def get_session(session_id: str) -> SessionResponse:
    from memory.session_manager import SessionManager

    row = SessionManager.get_session(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _row_to_response(row)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session",
)
def delete_session(session_id: str) -> None:
    from memory.session_manager import SessionManager

    ok = SessionManager.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get(
    "/sessions/{session_id}/state",
    response_model=AnalyticalStateResponse,
    summary="Get analytical state snapshot for a session",
)
def get_session_state(session_id: str) -> AnalyticalStateResponse:
    """Return the current ActiveAnalyticalState for the given session.

    Backed by the MemoryService Protocol (item 5.11). The state is loaded from
    DB (Postgres) or returns an empty state when DATABASE_URL is not set.
    Read-only in v1 — mutations happen implicitly via the agent graph.
    Item 5.13 will add user-driven correction endpoints.
    """
    import uuid

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id UUID")

    from memory import get_memory_service

    state = get_memory_service().get_active_state(sid)

    return AnalyticalStateResponse(
        session_id=session_id,
        version=state.version,
        last_turn_id=state.last_turn_id,
        intent=state.intent.value if state.intent is not None else None,
        metrics=[m.model_dump() for m in state.metrics],
        active_simulation_run=state.active_simulation_run,
        active_optimization_run=state.active_optimization_run,
        active_scenarios=list(state.active_scenarios),
    )


@router.get(
    "/sessions/{session_id}/state/audit",
    response_model=StateAuditResponse,
    summary="Get analytical state audit log for a session",
)
def get_session_state_audit(
    session_id: str,
    since_turn: int = Query(
        0, ge=0, description="Return only transitions at or after this turn"
    ),
) -> StateAuditResponse:
    """Return the ordered list of state mutations for a session.

    Each entry corresponds to one mutation applied to ActiveAnalyticalState.
    Use ``since_turn`` to paginate or watch for new mutations.
    """
    import uuid

    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id UUID")

    from memory import get_memory_service

    transitions = get_memory_service().read_audit(sid, since_turn=since_turn)

    return StateAuditResponse(
        session_id=session_id,
        transitions=[
            StateTransitionResponse(
                turn_id=t.turn_id,
                version_before=t.version_before,
                version_after=t.version_after,
                slot=t.slot,
                op=t.op.value,
                before=t.before,
                after=t.after,
                cause=t.cause,
                evidence=t.evidence,
                timestamp=t.timestamp.isoformat(),
            )
            for t in transitions
        ],
        total=len(transitions),
    )


# ── State proposals & commits (item 5.13) ────────────────────────────────────


def _parse_session_uuid(session_id: str) -> Any:
    import uuid as _uuid

    try:
        return _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id UUID")


def _slot_proposal_to_schema(m: "Any") -> SlotProposalSchema:
    return SlotProposalSchema(
        slot=m.slot,
        current_value=m.current_value,
        proposed_value=m.proposed_value,
        reason=m.reason,
    )


@router.post(
    "/sessions/{session_id}/state/proposals",
    response_model=ProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a state-mutation proposal (proactive or reactive)",
)
def create_state_proposal(
    session_id: str,
    body: ProposalCreateRequest,
) -> ProposalResponse:
    """Generate a StateProposal for the given session.

    PROACTIVE_PLANNER: caller supplies ``pending_mutations`` (the planner's
    intended slot changes). REACTIVE_USER: ``pending_mutations`` is omitted;
    the current editable slots are packaged as identity proposals for the
    user to edit.
    """

    from core.protocols.memory import ProposalSource, SlotProposal
    from memory import get_memory_service

    sid = _parse_session_uuid(session_id)

    try:
        source = ProposalSource(body.source)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{body.source}'. "
            "Use 'proactive_planner' or 'reactive_user'.",
        )

    pending: list[SlotProposal] | None = None
    if body.pending_mutations is not None:
        pending = [
            SlotProposal(
                slot=m.slot,
                current_value=m.current_value,
                proposed_value=m.proposed_value,
                reason=m.reason,
            )
            for m in body.pending_mutations
        ]

    # turn_id: use last_turn_id + 1 from current state
    svc = get_memory_service()
    state = svc.get_active_state(sid)
    turn_id = state.last_turn_id + 1

    proposal = svc.propose_state_update(
        session_id=sid,
        turn_id=turn_id,
        source=source,
        pending_mutations=pending,
    )

    return ProposalResponse(
        session_id=str(proposal.session_id),
        turn_id=proposal.turn_id,
        source=proposal.source.value,
        mutations=[_slot_proposal_to_schema(m) for m in proposal.mutations],
        triggered_signals=proposal.triggered_signals,
        created_at=proposal.created_at.isoformat(),
    )


@router.post(
    "/sessions/{session_id}/state/commits",
    response_model=CommitResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Commit a state-mutation decision",
)
def commit_state_decision(
    session_id: str,
    body: CommitDecisionRequest,
    graph: Any = Depends(_get_graph),
) -> CommitResultResponse:
    """Apply the approved mutations from a StateProposal.

    Raises HTTP 400 when the ``proposal_turn_id`` does not correspond to an
    open proposal for this session. Frozen slots in ``approved_mutations``
    are silently skipped and returned in ``skipped_slots``.

    When ``resume_query=True`` (default) and the proposal stored an
    ``original_query``, the agent is re-invoked with ``bypass_gate=True``
    and the result is embedded in ``resumed_run``.
    """
    from core.protocols.memory import SlotProposal, StateCommitDecision
    from memory import get_memory_service

    sid = _parse_session_uuid(session_id)

    decision = StateCommitDecision(
        session_id=sid,
        proposal_turn_id=body.proposal_turn_id,
        approved_mutations=[
            SlotProposal(
                slot=m.slot,
                current_value=m.current_value,
                proposed_value=m.proposed_value,
                reason=m.reason,
            )
            for m in body.approved_mutations
        ],
        rejected_slots=body.rejected_slots,
        freeze_slots=body.freeze_slots,
        unfreeze_slots=body.unfreeze_slots,
    )

    svc = get_memory_service()
    try:
        result = svc.commit_state_update(session_id=sid, decision=decision)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    resumed_run: Optional[dict[str, Any]] = None
    if body.resume_query and result.original_query:
        try:
            from agents.runner import run_query  # noqa: PLC0415
            from evaluation.observer import AgentObserver  # noqa: PLC0415

            observer = AgentObserver()
            run_result = run_query(
                query=result.original_query,
                thread_id=session_id,
                observer=observer,
                graph=graph,
                bypass_gate=True,
            )
            resumed_run = {
                "answer": run_result.answer,
                "success": run_result.success,
                "tool_used": run_result.tool_used,
                "latency_ms": run_result.latency_ms,
                "total_cost_usd": run_result.total_cost_usd,
                "clarification_needed": run_result.clarification_needed,
                "error": run_result.error,
            }
        except Exception:  # noqa: BLE001
            pass  # resume is best-effort; commit result is always returned

    return CommitResultResponse(
        session_id=str(result.session_id),
        version_before=result.version_before,
        version_after=result.version_after,
        applied_mutations=[
            _slot_proposal_to_schema(m) for m in result.applied_mutations
        ],
        skipped_slots=result.skipped_slots,
        committed_at=result.committed_at.isoformat(),
        resumed_run=resumed_run,
    )
