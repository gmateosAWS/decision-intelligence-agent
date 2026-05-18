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
    result = run_query(
        req.query, session_id, observer, graph, bypass_gate=req.bypass_gate
    )

    # Proactive confirmation gate (item 5.13) — not a failure; return 200 with
    # awaiting_user_confirmation=True and the proposal so the client can render
    # a confirmation dialog and POST /commits when the user approves.
    if result.awaiting_user_confirmation:
        return QueryResponse(
            answer=result.answer,
            session_id=session_uuid,
            run_id=result.run_id,
            total_input_tokens=result.total_input_tokens,
            total_output_tokens=result.total_output_tokens,
            total_cost_usd=result.total_cost_usd,
            llm_calls_count=result.llm_calls_count,
            awaiting_user_confirmation=True,
            proposal=result.proposal,
        )

    # GroundedTokens clarification (item 5.9) — not a server error; return 200
    # with clarification fields so the client can prompt the user to rephrase.
    if result.clarification_needed:
        return QueryResponse(
            answer=result.clarification_message or result.answer,
            session_id=session_uuid,
            run_id=result.run_id,
            total_input_tokens=result.total_input_tokens,
            total_output_tokens=result.total_output_tokens,
            total_cost_usd=result.total_cost_usd,
            llm_calls_count=result.llm_calls_count,
            clarification_needed=True,
            clarification_message=result.clarification_message,
        )

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
        total_input_tokens=result.total_input_tokens,
        total_output_tokens=result.total_output_tokens,
        total_cost_usd=result.total_cost_usd,
        llm_calls_count=result.llm_calls_count,
        budget_exceeded=result.budget_exceeded,
        budget_exceeded_reason=result.budget_exceeded_reason,
    )
