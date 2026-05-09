"""
ui/session.py
--------------
Session state management and query handling for the Streamlit UI.

handle_query() delegates graph invocation to agents.runner.run_query() so the
same code path is used by both the UI and the FastAPI service (Directive 3).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

import streamlit as st

from agents.runner import RunResult, run_query
from evaluation.observer import AgentObserver
from memory import get_checkpointer, register_turn

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    """Initialise all required session_state keys (idempotent)."""
    if "session_id" not in st.session_state:
        handle_new_session()
    if "observer" not in st.session_state:
        st.session_state.observer = AgentObserver(log_dir="logs")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "is_new_session" not in st.session_state:
        st.session_state.is_new_session = True


# ---------------------------------------------------------------------------
# Session lifecycle helpers
# ---------------------------------------------------------------------------


def handle_new_session() -> None:
    """Reset state for a brand-new conversation."""
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.is_new_session = True
    st.session_state.messages = []


def resume_session(session_id: str, graph: Any) -> None:
    """Restore a session and populate display messages from graph state."""
    st.session_state.session_id = session_id
    st.session_state.is_new_session = False
    messages: List[Dict] = []
    try:
        cfg = {"configurable": {"thread_id": session_id}}
        state = graph.get_state(cfg)
        if state and state.values:
            for turn in state.values.get("history", []):
                messages.append(
                    {"role": "user", "content": turn.get("query", ""), "metadata": None}
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": turn.get("answer", ""),
                        "metadata": None,
                    }
                )
    except Exception:  # noqa: BLE001
        pass
    st.session_state.messages = messages


def get_or_create_graph() -> Any:
    """Return the cached LangGraph graph, building it on first call."""
    from agents.workflow import build_graph as build_agent_graph

    checkpointer = get_checkpointer()
    return build_agent_graph(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Query handler — core of the multi-turn fix
# ---------------------------------------------------------------------------

_SPINNER_STEPS = [
    "Analizando tu pregunta…",
    "Consultando el modelo causal…",
    "Generando respuesta…",
]


def handle_query(prompt: str, graph: Any) -> RunResult:
    """
    Run one agent turn and update session_state.

    Flow (multi-turn bug fix):
    1. Append user message FIRST so the next render shows it immediately.
    2. Call agents.runner.run_query() — the same function the API uses.
    3. Build metadata dict from RunResult.
    4. Append assistant message to session_state.messages.
    5. Register the turn in the memory layer.
    6. Return the RunResult (caller decides when to st.rerun()).

    The caller (ui/app.py) is responsible for rendering the in-progress
    status and for calling st.rerun() after this function returns.
    """
    session_id: str = st.session_state.session_id
    observer: AgentObserver = st.session_state.observer

    # Step 1 — append user message before processing
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "metadata": None}
    )

    # Step 2 — delegate to shared runner (Directive 3)
    result = run_query(prompt, session_id, observer, graph)

    # Step 3 — build metadata for display
    metadata: Dict[str, Any] = {
        "action": result.tool_used,
        "reasoning": result.reasoning,
        "raw_result": result.raw_result,
        "judge_score": result.judge_score,
        "judge_passed": result.judge_passed,
        "judge_revised": result.judge_revised,
        "total_ms": result.latency_ms,
        "latencies": result.latencies,
    }

    # Step 4 — append assistant message
    st.session_state.messages.append(
        {"role": "assistant", "content": result.answer, "metadata": metadata}
    )
    st.session_state.turn_count = len(
        [m for m in st.session_state.messages if m["role"] == "user"]
    )

    # Step 5 — register turn in memory layer (no-op on failure)
    try:
        register_turn(session_id, prompt)
    except Exception:  # noqa: BLE001
        pass
    st.session_state.is_new_session = False

    return result
