"""api/routers/query.py — POST /v1/query: run one agent turn."""

from __future__ import annotations

import os
import time
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
def run_query(req: QueryRequest, graph=Depends(get_graph)) -> QueryResponse:
    """
    Submit a business question to the agent.

    - If `session_id` is provided the query continues that conversation thread.
    - If omitted a new session is created automatically.
    - Returns the answer plus observability fields (tool used, confidence, latency).
    """
    from agents.llm_factory import LLMUnavailableError
    from evaluation.observer import AgentObserver
    from memory.checkpointer import register_turn
    from memory.session_manager import SessionManager

    session_id = req.session_id or uuid.uuid4()
    observer = AgentObserver()
    run_id = observer.start_run(req.query)

    # Attach spec traceability when DB is available
    if os.getenv("DATABASE_URL", ""):
        try:
            from spec.spec_loader import get_spec
            from spec.spec_repository import get_active_spec

            spec = get_spec()
            active_row = get_active_spec(spec.domain_name)
            if active_row:
                observer.set_spec(str(active_row.id), active_row.version)
        except Exception:
            pass

    t0 = time.perf_counter()
    try:
        cfg = observer.langsmith_config()
        cfg["configurable"]["observer"] = observer
        cfg["configurable"]["thread_id"] = str(session_id)

        result = graph.invoke({"query": req.query, "run_id": run_id}, config=cfg)

        total_ms = (time.perf_counter() - t0) * 1000
        record = observer.end_run(success=True) or {}

        existing = SessionManager.get_session(str(session_id))
        register_turn(str(session_id), req.query, is_new=(existing is None))

        return QueryResponse(
            answer=result.get("answer") or "",
            session_id=session_id,
            run_id=run_id,
            tool_used=result.get("action"),
            confidence=record.get("confidence_score"),
            latency_ms=total_ms,
            fallback_triggered=bool(record.get("fallback_triggered", False)),
            spec_version=record.get("spec_version"),
        )

    except LLMUnavailableError as exc:
        observer.end_run(success=False, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "LLM service unavailable", "message": str(exc)},
        )
    except Exception as exc:
        observer.end_run(success=False, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Internal error", "message": str(exc)},
        )
