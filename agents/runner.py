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
    requires_confirmation: bool = False
    requires_approval: bool = False
    confirmation_message: Optional[str] = None
    # Cost tracking (item 8.7.a+b)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_calls_count: int = 0
    budget_exceeded: bool = False
    budget_exceeded_reason: Optional[str] = None
    # Analytical state snapshot after the run (item 5.11)
    active_state: Optional[Dict[str, Any]] = None
    # GroundedTokens clarification (item 5.9)
    clarification_needed: bool = False
    clarification_message: Optional[str] = None
    # Proactive confirmation gate (item 5.13)
    awaiting_user_confirmation: bool = False
    proposal: Optional[Dict[str, Any]] = None
    # Freeze enforcement (item 5.13.c): mutations blocked by frozen slots.
    # Each entry: {slot, blocked_value, current_value, reason, source}.
    # source is "planner" (intent-freeze) or "coordinator" (slot-freeze).
    # Both sources accumulate here; UI renders all blocks identically.
    blocked_mutations: list[Dict[str, Any]] = field(default_factory=list)


def run_query(
    query: str,
    thread_id: str,
    observer: "AgentObserver",
    graph: Any = None,
    bypass_gate: bool = False,
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

        graph = build_graph(checkpointer=get_checkpointer())  # type: ignore[no-untyped-call]  # memory.get_checkpointer not yet in strict zone

    # Bind the real session UUID so RunRecord.session_id matches agent_sessions.id
    observer.set_session_id(thread_id)

    # Resolve session UUID for MemoryService (item 5.11).
    import uuid as _uuid

    from memory import get_memory_service

    _sid: Optional[_uuid.UUID] = None
    try:
        _sid = _uuid.UUID(thread_id)
    except (ValueError, AttributeError):
        pass

    memory_svc = get_memory_service()

    run_id = observer.start_run(query)
    t0 = time.perf_counter()

    # Optional spec traceability — must come AFTER start_run() so self._run exists
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
                    active_row.version,  # type: ignore[arg-type, unused-ignore]  # SQLAlchemy Column[str] vs str | None
                )
        except Exception:  # noqa: BLE001
            pass

    from evaluation.budget import BudgetExceededError, BudgetTracker, RunBudget

    budget = RunBudget.from_env()
    tracker = BudgetTracker(budget=budget)

    try:
        cfg = observer.langsmith_config()
        cfg["configurable"]["observer"] = observer
        cfg["configurable"]["thread_id"] = thread_id
        cfg["configurable"]["budget_tracker"] = tracker
        cfg["configurable"]["memory_service"] = memory_svc

        # Determine whether prior turns exist for this session. We cannot use
        # graph.get_state() because PostgresSaver returns empty state values
        # for gate-only checkpoints, and state["history"] stays [] when the
        # graph ends early (gate → END). Instead, read agent_sessions.turn_count:
        # register_turn() is called by the UI/API before run_query() and has
        # already incremented turn_count for the current turn, so turn_count > 1
        # means at least one prior turn completed.
        has_prior_turns: bool = False
        try:
            from memory import SessionManager as _SM

            _session_row = _SM.get_session(thread_id)
            has_prior_turns = bool(
                _session_row is not None and _session_row.get("turn_count", 0) > 1
            )
        except Exception:  # noqa: BLE001
            has_prior_turns = False

        result = graph.invoke(
            {
                "query": query,
                "run_id": run_id,
                "bypass_gate": bypass_gate,
                "has_prior_turns": has_prior_turns,
                # Explicitly reset per-turn flags so LangGraph does not inherit
                # stale values from the previous checkpoint. Without this, a
                # gate-only turn (awaiting_user_confirmation=True in checkpoint)
                # would bleed into the next turn even after the tool has run.
                "awaiting_user_confirmation": False,
                "proposal": None,
                "clarification_needed": False,
                "clarification_message": None,
                "ungrounded_token": None,
                "blocked_mutations": [],
            },
            config=cfg,
        )

        # Capture typed state snapshot after the run (item 5.11).
        active_state_dict: Optional[Dict[str, Any]] = None
        if _sid is not None:
            try:
                snapshot = memory_svc.get_active_state(_sid)
                active_state_dict = snapshot.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                pass

        observer.set_raw_result(result.get("raw_result") or {})
        latency_ms = (time.perf_counter() - t0) * 1000

        # Attach cost fields to observer record before finalizing
        observer.record_cost(
            total_input_tokens=tracker.total_input_tokens,
            total_output_tokens=tracker.total_output_tokens,
            total_cost_usd=tracker.total_cost_usd,
            llm_calls_count=tracker.llm_calls,
        )

        # Proactive confirmation gate (item 5.13) — return early; no tool was run.
        # The client receives the proposal and must POST /commits to continue.
        if result.get("awaiting_user_confirmation"):
            observer.end_run(success=False) or {}
            return RunResult(
                answer="Please confirm the planned action before execution.",
                session_id=thread_id,
                run_id=run_id,
                success=False,
                latency_ms=(time.perf_counter() - t0) * 1000,
                error=None,
                error_type=None,
                latencies={},
                total_input_tokens=tracker.total_input_tokens,
                total_output_tokens=tracker.total_output_tokens,
                total_cost_usd=tracker.total_cost_usd,
                llm_calls_count=tracker.llm_calls,
                active_state=active_state_dict,
                awaiting_user_confirmation=True,
                proposal=result.get("proposal"),
            )

        # GroundedTokens clarification (item 5.9) — not a failure; return 200
        # with clarification fields populated and success=False so the UI/API
        # can distinguish clarification from a real error.
        if result.get("clarification_needed"):
            record = observer.end_run(success=False) or {}
            clarification_msg = result.get("clarification_message") or result.get(
                "answer", ""
            )
            return RunResult(
                answer=clarification_msg,
                session_id=thread_id,
                run_id=run_id,
                success=False,
                latency_ms=latency_ms,
                error=None,
                error_type=None,
                latencies={},
                total_input_tokens=tracker.total_input_tokens,
                total_output_tokens=tracker.total_output_tokens,
                total_cost_usd=tracker.total_cost_usd,
                llm_calls_count=tracker.llm_calls,
                active_state=active_state_dict,
                clarification_needed=True,
                clarification_message=clarification_msg,
            )

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
            requires_confirmation=bool(result.get("requires_confirmation", False)),
            requires_approval=bool(result.get("requires_approval", False)),
            confirmation_message=result.get("confirmation_message"),
            total_input_tokens=tracker.total_input_tokens,
            total_output_tokens=tracker.total_output_tokens,
            total_cost_usd=tracker.total_cost_usd,
            llm_calls_count=tracker.llm_calls,
            active_state=active_state_dict,
            blocked_mutations=result.get("blocked_mutations") or [],
        )

    except BudgetExceededError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        observer.record_cost(
            total_input_tokens=exc.tracker.total_input_tokens,
            total_output_tokens=exc.tracker.total_output_tokens,
            total_cost_usd=exc.tracker.total_cost_usd,
            llm_calls_count=exc.tracker.llm_calls,
        )
        observer.end_run(success=False, error=exc.reason)
        return RunResult(
            answer=f"⚠️ Budget ceiling reached: {exc.reason}",
            session_id=thread_id,
            run_id=run_id,
            success=False,
            latency_ms=latency_ms,
            error=exc.reason,
            error_type="BudgetExceededError",
            latencies={},
            total_input_tokens=exc.tracker.total_input_tokens,
            total_output_tokens=exc.tracker.total_output_tokens,
            total_cost_usd=exc.tracker.total_cost_usd,
            llm_calls_count=exc.tracker.llm_calls,
            budget_exceeded=True,
            budget_exceeded_reason=exc.reason,
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
