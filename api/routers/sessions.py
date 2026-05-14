"""api/routers/sessions.py — CRUD for /v1/sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.sessions import (
    AnalyticalStateResponse,
    SessionListResponse,
    SessionResponse,
    StateAuditResponse,
    StateTransitionResponse,
)

router = APIRouter(tags=["sessions"])


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
