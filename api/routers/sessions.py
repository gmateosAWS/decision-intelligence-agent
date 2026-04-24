"""api/routers/sessions.py — CRUD for /v1/sessions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas.sessions import SessionListResponse, SessionResponse

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
