"""api/routers/runs.py — Read-only access to agent_runs history."""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_db
from api.schemas.runs import RunListResponse, RunResponse

router = APIRouter(tags=["runs"])


def _row_to_response(row, *, detail: bool = False) -> RunResponse:
    return RunResponse(
        id=row.id,
        run_id=row.run_id,
        session_id=row.session_id,
        timestamp=str(row.timestamp),
        query=row.query,
        action=row.action,
        success=bool(row.success),
        total_latency_ms=row.total_latency_ms,
        judge_score=row.judge_score,
        confidence_score=row.confidence_score,
        spec_version=row.spec_version,
        answer_length=row.answer_length if detail else None,
        reasoning=row.reasoning if detail else None,
        raw_result=row.raw_result if detail else None,
        error=row.error if detail else None,
    )


def _require_db() -> None:
    if not os.getenv("DATABASE_URL", ""):
        raise HTTPException(
            status_code=503,
            detail="Run history requires DATABASE_URL to be configured.",
        )


@router.get("/runs", response_model=RunListResponse, summary="List agent runs")
def list_runs(
    session_id: Optional[str] = Query(None, description="Filter by session UUID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
) -> RunListResponse:
    """Return agent runs ordered by most-recent first, filtered by session."""
    _require_db()
    from db.models import AgentRun

    q = db.query(AgentRun).order_by(AgentRun.timestamp.desc())
    if session_id:
        try:
            q = q.filter(AgentRun.session_id == uuid.UUID(session_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id UUID")

    total = q.count()
    rows = q.offset(skip).limit(limit).all()
    return RunListResponse(runs=[_row_to_response(r) for r in rows], total=total)


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Get run detail",
)
def get_run(run_id: str, db=Depends(get_db)) -> RunResponse:
    """Return full detail for one run, including raw tool output."""
    _require_db()
    from db.models import AgentRun

    row = db.query(AgentRun).filter(AgentRun.run_id == run_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _row_to_response(row, detail=True)
