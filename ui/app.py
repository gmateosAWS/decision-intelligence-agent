"""
ui/app.py
----------
Main Streamlit orchestrator.  Composes sidebar, header, tabs, and chat
interaction.

Multi-turn rendering fix: all chat rendering (user message, processing
status, assistant response) happens INSIDE `with tab_chat:`.  The previous
bug rendered the current turn's messages below the tab panel, causing them
to disappear or misrender on subsequent reruns.
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
        handle_query,
        init_session_state,
        resume_session,
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

    from ui.components import render_chat_message, render_welcome_cards
    from ui.dashboard import render_dashboard

    with tab_chat:
        # Welcome cards — shown only when no messages and no pending query
        if not st.session_state.messages and not prompt:
            card_query = render_welcome_cards()
            if card_query:
                st.session_state["_pending_query"] = card_query
                st.rerun()

        # History loop — re-renders the complete conversation on every rerun
        for msg in st.session_state.messages:
            render_chat_message(msg)

        # Spinner blocks Streamlit's automatic reruns while the agent runs (~10-15 s).
        # When handle_query() returns, both user + assistant messages are in
        # session_state, so the subsequent st.rerun() renders them correctly.
        if prompt:
            with st.spinner("Analizando tu pregunta…"):
                handle_query(prompt, graph)
            st.rerun()

    with tab_dashboard:
        render_dashboard()
