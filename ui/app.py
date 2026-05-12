"""
ui/app.py
----------
Main Streamlit orchestrator.  Composes sidebar, header, tabs, and chat
interaction.

Rendering pattern (official Streamlit chat pattern):
  1. History loop re-renders all past turns from session_state on every rerun.
  2. When a new prompt arrives, user message is rendered inline and appended
     to session_state.  Then the agent runs inside a spinner, and the
     assistant response is rendered inline and appended to session_state.
  3. No st.rerun() — the next user input triggers a natural rerun.
  4. handle_query() does NOT append messages — app.py owns the message list.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    """Entry point — called by the thin streamlit_app.py wrapper."""

    # ------------------------------------------------------------------
    # 1. Seed spec + build graph (cached across reruns)
    # ------------------------------------------------------------------
    from spec.spec_loader import SPEC_PATH

    @st.cache_resource
    def _seed_spec() -> str:
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            return "yaml"
        try:
            from db.engine import check_connection
            from spec.spec_repository import seed_from_yaml

            if check_connection():
                seed_from_yaml(SPEC_PATH)
                return "db"
        except Exception:  # noqa: BLE001
            pass
        return "yaml"

    @st.cache_resource
    def _load_agent_graph() -> Any:
        from ui.session import get_or_create_graph

        return get_or_create_graph()

    with st.spinner("Iniciando llull — cargando especificación y construyendo agente…"):
        spec_source = _seed_spec()
        graph = _load_agent_graph()

    # ------------------------------------------------------------------
    # 2. Session state
    # ------------------------------------------------------------------
    from ui.session import (
        handle_new_session,
        init_session_state,
        resume_session,
        run_agent_query,
    )

    init_session_state()

    # ------------------------------------------------------------------
    # 3. Sidebar
    # ------------------------------------------------------------------
    from ui.sidebar import render_sidebar

    render_sidebar(
        spec_source=spec_source,
        graph=graph,
        session_id=st.session_state.session_id,
        messages=st.session_state.messages,
        on_new_session=handle_new_session,
        on_resume_session=lambda sid: resume_session(sid, graph),
    )

    # ------------------------------------------------------------------
    # 4. Header (compact when conversation exists, full when empty)
    # ------------------------------------------------------------------
    from ui.styles import LOGO_COMPACT, LOGO_FULL

    if st.session_state.messages:
        st.markdown(LOGO_COMPACT, unsafe_allow_html=True)
        st.caption("Tu consejero de decisiones de negocio.")
    else:
        st.markdown(LOGO_FULL, unsafe_allow_html=True)
        st.markdown(
            "**Tu consejero de decisiones de negocio.**  \n"
            "Analiza el impacto de tus decisiones comerciales antes de tomarlas."
        )

    # ------------------------------------------------------------------
    # 5. Tab styles
    # ------------------------------------------------------------------
    from ui.styles import TAB_STYLE_CSS

    st.markdown(TAB_STYLE_CSS, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 6. Chat input — captured before tabs so prompt is available inside
    #    `with tab_chat:`.  st.chat_input() is always pinned to the bottom
    #    of the viewport regardless of its position in the script.
    # ------------------------------------------------------------------
    _chat_input = st.chat_input("Pregunta sobre tu negocio…")

    # Resolve pending query from example-card buttons
    prompt: Optional[str] = None
    if "_pending_query" in st.session_state:
        prompt = st.session_state.pop("_pending_query")
    elif _chat_input:
        prompt = _chat_input

    # ------------------------------------------------------------------
    # 7. Tabs
    # ------------------------------------------------------------------
    tab_chat, tab_dashboard = st.tabs(["Chat", "Dashboard"])

    from ui.components import (
        render_chat_message,
        render_result_cards,
        render_technical_details,
        render_welcome_cards,
    )
    from ui.dashboard import render_dashboard
    from ui.styles import TOOL_LABELS, sanitize_markdown

    with tab_chat:
        # Welcome cards — only when conversation is empty
        if not st.session_state.messages and not prompt:
            card_query = render_welcome_cards()
            if card_query:
                st.session_state["_pending_query"] = card_query
                st.rerun()

        # ── 1. Render full conversation history from session_state ────
        for msg in st.session_state.messages:
            render_chat_message(msg)

        # ── 2. Process current turn inline (no st.rerun) ─────────────
        #
        # This follows the official Streamlit chat pattern:
        # - Render user message inline AND append to session_state
        # - Run agent inside spinner
        # - Render assistant response inline AND append to session_state
        # - No st.rerun() — next user input triggers natural rerun
        #
        # CRITICAL: handle_query/run_agent_query does NOT append messages.
        # This function owns the message list exclusively.
        if prompt:
            # -- User message --
            st.session_state.messages.append(
                {"role": "user", "content": prompt, "metadata": None}
            )
            with st.chat_message("user"):
                st.markdown(prompt)

            # -- Agent execution + assistant message --
            with st.chat_message("assistant"):
                with st.spinner("Analizando tu pregunta…"):
                    result = run_agent_query(prompt, graph)

                # Build metadata
                metadata = {
                    "action": result.tool_used,
                    "reasoning": result.reasoning,
                    "raw_result": result.raw_result,
                    "judge_score": result.judge_score,
                    "judge_passed": result.judge_passed,
                    "judge_revised": result.judge_revised,
                    "total_ms": result.latency_ms,
                    "latencies": result.latencies,
                    "requires_confirmation": result.requires_confirmation,
                    "requires_approval": result.requires_approval,
                    "confirmation_message": result.confirmation_message,
                    "total_cost_usd": result.total_cost_usd,
                    "total_input_tokens": result.total_input_tokens,
                    "total_output_tokens": result.total_output_tokens,
                    "llm_calls_count": result.llm_calls_count,
                    "budget_exceeded": result.budget_exceeded,
                    "budget_exceeded_reason": result.budget_exceeded_reason,
                }

                # Append assistant to session_state
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": result.answer,
                        "metadata": metadata,
                    }
                )
                st.session_state.turn_count = len(
                    [m for m in st.session_state.messages if m["role"] == "user"]
                )
                st.session_state.is_new_session = False

                # Render assistant response inline — always safe
                st.markdown(sanitize_markdown(result.answer))

                # Render extras — resilient to component errors
                try:
                    action = result.tool_used or ""
                    total_ms = result.latency_ms
                    tool_label = TOOL_LABELS.get(
                        action, f"⚪ {action}" if action else ""
                    )
                    if tool_label and total_ms:
                        st.caption(f"{tool_label}  ·  {total_ms:,.0f} ms")
                    elif total_ms:
                        st.caption(f"{total_ms:,.0f} ms")
                    render_result_cards(action, result.raw_result or {})
                    render_technical_details(metadata)
                except Exception as e:  # noqa: BLE001
                    st.caption(f"⚠️ Error rendering details: {e}")

    with tab_dashboard:
        render_dashboard()
