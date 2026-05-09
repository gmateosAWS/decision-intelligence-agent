"""
agents/runner.py
-----------------
Shared graph invocation callable by the Streamlit UI, FastAPI service, and
future MCP clients.  Implements Directive 3 (API-first): every capability
must be internally callable as a typed Python function with a clear contract.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from evaluation.observer import AgentObserver


@dataclass
class RunResult:
    """Typed result of a single agent turn."""

    answer: str
    session_id: str
    run_id: str
    success: bool
    tool_used: Optional[str] = None
    confidence: Optional[float] = None
    latency_ms: float = 0.0
    fallback_triggered: bool = False
    spec_version: Optional[str] = None
    reasoning: Optional[str] = None
    raw_result: Dict[str, Any] = field(default_factory=dict)
    judge_score: Optional[float] = None
    judge_passed: Optional[bool] = None
    judge_revised: Optional[bool] = None
    latencies: Dict[str, Optional[float]] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None


def run_query(
    query: str,
    thread_id: str,
    observer: "AgentObserver",
    graph: Any = None,
) -> RunResult:
    """
    Invoke the LangGraph agent for one turn and return a typed RunResult.

    Parameters
    ----------
    query     : Natural-language question from the user.
    thread_id : LangGraph thread identifier (== session_id for Streamlit).
    observer  : AgentObserver instance; start_run() is called here.
    graph     : Compiled LangGraph graph.  Built and cached if None.

    Returns
    -------
    RunResult with success=True on success.  On any exception, returns a
    RunResult with success=False and error/error_type populated; never raises.
    """
    if graph is None:
        from agents.workflow import build_graph
        from memory import get_checkpointer

        graph = build_graph(checkpointer=get_checkpointer())

    # Optional spec traceability (no-op when DATABASE_URL is absent)
    import os

    if os.getenv("DATABASE_URL", ""):
        try:
            from spec.spec_loader import get_spec
            from spec.spec_repository import get_active_spec

            spec = get_spec()
            active_row = get_active_spec(spec.domain_name)
            if active_row:
                observer.set_spec(
                    str(active_row.id),
                    active_row.version,  # type: ignore[arg-type]
                )
        except Exception:  # noqa: BLE001
            pass

    run_id = observer.start_run(query)
    t0 = time.perf_counter()

    try:
        cfg = observer.langsmith_config()
        cfg["configurable"]["observer"] = observer
        cfg["configurable"]["thread_id"] = thread_id

        result = graph.invoke({"query": query, "run_id": run_id}, config=cfg)

        latency_ms = (time.perf_counter() - t0) * 1000
        record = observer.end_run(success=True) or {}

        return RunResult(
            answer=result.get("answer") or "",
            session_id=thread_id,
            run_id=run_id,
            success=True,
            tool_used=result.get("action"),
            confidence=record.get("confidence_score"),
            latency_ms=latency_ms,
            fallback_triggered=bool(record.get("fallback_triggered", False)),
            spec_version=record.get("spec_version"),
            reasoning=result.get("reasoning"),
            raw_result=result.get("raw_result") or {},
            judge_score=result.get("judge_score"),
            judge_passed=result.get("judge_passed"),
            judge_revised=result.get("judge_revised"),
            latencies={
                "planner": record.get("planner_latency_ms"),
                "tool": record.get("tool_latency_ms"),
                "synthesizer": record.get("synthesizer_latency_ms"),
                "judge": record.get("judge_latency_ms"),
            },
        )

    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - t0) * 1000
        observer.end_run(success=False, error=str(exc))
        return RunResult(
            answer=f"⚠️ El agente encontró un error: {exc}",
            session_id=thread_id,
            run_id=run_id,
            success=False,
            latency_ms=latency_ms,
            error=str(exc),
            error_type=type(exc).__name__,
            latencies={},
        )
