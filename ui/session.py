"""
ui/session.py
--------------
Session state management and query handling for the Streamlit UI.

run_agent_query() delegates graph invocation to agents.runner.run_query() so
the same code path is used by both the UI and the FastAPI service (Directive 3).

CRITICAL: run_agent_query() does NOT modify st.session_state.messages.
Message appending is the exclusive responsibility of ui/app.py to avoid
double-appends and race conditions with Streamlit's rerun cycle.

All imports of agents.*, evaluation.*, and memory.* are deferred inside
the functions that use them to prevent module-level import failures from
cascading into a blank Streamlit page (KeyError: 'ui.session' pattern).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

import streamlit as st

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    """Initialise all required session_state keys (idempotent)."""
    from evaluation.observer import AgentObserver

    if "session_id" not in st.session_state:
        handle_new_session()
    if "observer" not in st.session_state:
        st.session_state.observer = AgentObserver(log_dir="logs")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "is_new_session" not in st.session_state:
        st.session_state.is_new_session = True
    if "turn_count" not in st.session_state:
        st.session_state.turn_count = 0


# ---------------------------------------------------------------------------
# Session lifecycle helpers
# ---------------------------------------------------------------------------


def handle_new_session() -> None:
    """Reset state for a brand-new conversation."""
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.is_new_session = True
    st.session_state.messages = []
    st.session_state.turn_count = 0
    # Discard any pending proactive proposal or reactive correction state
    # from the previous session so stale panels do not ghost into the new one.
    st.session_state.pop("_pending_proposal", None)
    st.session_state.pop("_show_reactive_correction", None)
    st.session_state.pop("_reactive_proposal_cache", None)
    st.session_state.pop("_gate_bypass_prompt", None)
    st.session_state.pop("_pending_query", None)


def resume_session(session_id: str, graph: Any) -> None:
    """Restore a session and populate display messages from graph state."""
    st.session_state.session_id = session_id
    st.session_state.is_new_session = False
    # Discard any pending proactive proposal or reactive correction state
    # from the previous session so stale panels do not ghost into the new one.
    st.session_state.pop("_pending_proposal", None)
    st.session_state.pop("_show_reactive_correction", None)
    st.session_state.pop("_reactive_proposal_cache", None)
    st.session_state.pop("_gate_bypass_prompt", None)
    st.session_state.pop("_pending_query", None)
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
    st.session_state.turn_count = len([m for m in messages if m["role"] == "user"])


def get_or_create_graph() -> Any:
    """Return the cached LangGraph graph, building it on first call."""
    from agents.workflow import build_graph as build_agent_graph
    from memory import get_checkpointer

    checkpointer = get_checkpointer()
    return build_agent_graph(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Query handler — pure agent invocation, no session_state mutation
# ---------------------------------------------------------------------------


def run_agent_query(prompt: str, graph: Any, bypass_gate: bool = False) -> Any:
    """
    Run one agent turn and return the result.

    DOES NOT modify st.session_state.messages — that is the exclusive
    responsibility of ui/app.py to avoid double-appends and Streamlit
    rerun race conditions.

    DOES register the turn in the memory layer and invoke the agent via
    the shared runner (Directive 3 — same code as the API).
    """
    from agents.runner import run_query
    from memory import register_turn

    session_id: str = st.session_state.session_id
    observer = st.session_state.observer

    # Register session row before run_query so the FK exists when
    # PostgresSink INSERTs the agent_run row
    try:
        register_turn(session_id, prompt)
    except Exception:  # noqa: BLE001
        pass

    # Delegate to shared runner (Directive 3)
    result = run_query(prompt, session_id, observer, graph, bypass_gate=bypass_gate)

    return result
