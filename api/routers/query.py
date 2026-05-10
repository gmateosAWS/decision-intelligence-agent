"""api/routers/query.py — POST /v1/query: run one agent turn."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_graph
from api.schemas.query import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Run an agent query",
)
def run_query_endpoint(req: QueryRequest, graph=Depends(get_graph)) -> QueryResponse:
    """
    Submit a business question to the agent.

    - If `session_id` is provided the query continues that conversation thread.
    - If omitted a new session is created automatically.
    - Returns the answer plus observability fields (tool used, confidence, latency).
    """
    from agents.runner import run_query
    from evaluation.observer import AgentObserver
    from memory.checkpointer import register_turn

    session_uuid = req.session_id or uuid.uuid4()
    session_id = str(session_uuid)
    observer = AgentObserver()

    # Create the agent_sessions row BEFORE run_query so the FK exists when
    # PostgresSink INSERTs the agent_run row.
    register_turn(session_id, req.query)

    # run_query() calls observer.start_run() and observer.end_run() internally
    result = run_query(req.query, session_id, observer, graph)

    if not result.success:
        if result.error_type == "LLMUnavailableError":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "LLM service unavailable", "message": result.error},
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Internal error", "message": result.error},
        )

    return QueryResponse(
        answer=result.answer,
        session_id=session_uuid,
        run_id=result.run_id,
        tool_used=result.tool_used,
        confidence=result.confidence,
        latency_ms=result.latency_ms,
        fallback_triggered=result.fallback_triggered,
        spec_version=result.spec_version,
        requires_confirmation=result.requires_confirmation,
        requires_approval=result.requires_approval,
        confirmation_message=result.confirmation_message,
    )
