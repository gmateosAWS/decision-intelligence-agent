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

    # Resolve pending query from example-card buttons or gate bypass
    prompt: Optional[str] = None
    bypass_gate: bool = False
    if "_gate_bypass_prompt" in st.session_state:
        prompt = st.session_state.pop("_gate_bypass_prompt")
        bypass_gate = True
    elif "_pending_query" in st.session_state:
        prompt = st.session_state.pop("_pending_query")
    elif _chat_input:
        prompt = _chat_input

    # If the user submits a fresh prompt (not a gate bypass), any pending
    # proactive proposal becomes obsolete and is discarded.
    if prompt and not bypass_gate:
        st.session_state.pop("_pending_proposal", None)

    # ------------------------------------------------------------------
    # 7. Tabs
    # ------------------------------------------------------------------
    tab_chat, tab_dashboard = st.tabs(["Chat", "Dashboard"])

    from ui.components import (
        render_chat_message,
        render_clarification_message,
        render_proactive_confirmation,
        render_reactive_correction_form,
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
                    result = run_agent_query(prompt, graph, bypass_gate=bypass_gate)

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
                    "active_state": result.active_state,
                    "clarification_needed": result.clarification_needed,
                    "awaiting_user_confirmation": result.awaiting_user_confirmation,
                    "proposal": result.proposal,
                    # run_id used as unique key for per-message buttons (5.13.c)
                    "run_id": result.run_id,
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

                # Proactive confirmation gate (item 5.13): persist proposal so it
                # survives across reruns. The panel itself is rendered outside
                # this block (see below) so the button widgets are alive on the
                # rerun where the user clicks them, not just on the rerun where
                # the prompt was processed.
                if result.awaiting_user_confirmation and result.proposal:
                    st.session_state["_pending_proposal"] = {
                        "proposal": result.proposal,
                        "original_prompt": prompt,
                    }
                # GroundedTokens clarification (item 5.9): render with info style
                elif result.clarification_needed:
                    render_clarification_message(result.answer)
                else:
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

        # Render proactive confirmation panel — persistent across reruns while a
        # proposal is pending. Lives outside `if prompt:` so the button widgets
        # exist on the rerun where the user clicks them (Streamlit requires the
        # widget to be rendered in the same rerun where it receives a click).
        # Hidden while the reactive correction form is open (5.13.c) so both
        # panels are never visible simultaneously.
        _pending = st.session_state.get("_pending_proposal")
        if _pending and not st.session_state.get("_show_reactive_correction"):

            def _on_confirm() -> None:
                st.session_state["_gate_bypass_prompt"] = _pending["original_prompt"]
                st.session_state.pop("_pending_proposal", None)
                st.rerun()

            def _on_edit() -> None:
                st.session_state["_show_reactive_correction"] = True
                st.rerun()

            def _on_cancel() -> None:
                st.session_state.pop("_pending_proposal", None)
                st.rerun()

            render_proactive_confirmation(
                _pending["proposal"],
                on_confirm=_on_confirm,
                on_edit=_on_edit,
                on_cancel=_on_cancel,
            )

        # ── 5.13.c: Reactive correction form ─────────────────────────────────
        # Rendered when either:
        #   (a) "Corregir contexto" button is clicked from technical details
        #       (source="reactive" — _pending_proposal absent or irrelevant)
        #   (b) "Editar" is clicked from the proactive panel
        #       (source="proactive_edit" — _pending_proposal present, reused)
        #
        # The UI calls get_memory_service() and run_query() directly, mirroring
        # the existing pattern where run_agent_query() bypasses the HTTP API for
        # the in-process Streamlit deployment. The HTTP endpoints
        # (POST /v1/sessions/{id}/state/proposals and /commits) remain the
        # canonical path for non-Streamlit clients.
        if st.session_state.get("_show_reactive_correction"):
            _cached = st.session_state.get("_reactive_proposal_cache")

            # First render: build and cache the form data
            if _cached is None:
                try:
                    import uuid as _uuid

                    from core.protocols.memory import ProposalSource
                    from memory import get_memory_service

                    _msvc = get_memory_service()
                    _sid = _uuid.UUID(str(st.session_state.session_id))
                    _snap = _msvc.get_active_state(_sid)
                    _frozen = list(_snap.frozen_slots)

                    if _pending:
                        # Proactive edit — reuse the proposal already in session
                        _prop_dict = _pending["proposal"]
                        _src = "proactive_edit"
                    else:
                        # Reactive — fetch identity proposals for current state
                        _prop_obj = _msvc.propose_state_update(
                            session_id=_sid,
                            turn_id=_snap.last_turn_id + 1,
                            source=ProposalSource.REACTIVE_USER,
                        )
                        _prop_dict = {
                            "turn_id": _prop_obj.turn_id,
                            "session_id": str(_prop_obj.session_id),
                            "mutations": [
                                {
                                    "slot": m.slot,
                                    "current_value": m.current_value,
                                    "proposed_value": m.proposed_value,
                                    "reason": m.reason,
                                }
                                for m in _prop_obj.mutations
                            ],
                            "triggered_signals": _prop_obj.triggered_signals,
                            "original_query": _prop_obj.original_query,
                        }
                        _src = "reactive"

                    st.session_state["_reactive_proposal_cache"] = {
                        "proposal": _prop_dict,
                        "frozen_slots": _frozen,
                        "source": _src,
                    }
                    _cached = st.session_state["_reactive_proposal_cache"]

                except Exception as _exc:
                    st.error(f"Error preparando el formulario de corrección: {_exc}")
                    st.session_state.pop("_show_reactive_correction", None)
                    st.stop()

            _form_proposal = _cached["proposal"]
            _frozen_slots = _cached.get("frozen_slots", [])
            _form_source = _cached.get("source", "reactive")

            _FORM_SLOT_KEYS = [
                f"reactive_form_{s}"
                for s in (
                    "intent",
                    "metrics",
                    "active_simulation_run",
                    "active_optimization_run",
                    "active_scenarios",
                )
            ] + [
                f"reactive_form_freeze_{s}"
                for s in (
                    "intent",
                    "metrics",
                    "active_simulation_run",
                    "active_optimization_run",
                    "active_scenarios",
                )
            ]

            def _clear_form_state() -> None:
                """Remove reactive form widget keys from session_state."""
                for _k in _FORM_SLOT_KEYS:
                    st.session_state.pop(_k, None)

            def _form_on_save(
                approved_mutations: list,
                freeze_decisions: dict,
            ) -> None:
                import uuid as _uuid

                from core.protocols.memory import SlotProposal, StateCommitDecision
                from memory import get_memory_service

                _svc = get_memory_service()
                _sid2 = _uuid.UUID(str(st.session_state.session_id))
                _decision = StateCommitDecision(
                    session_id=_sid2,
                    proposal_turn_id=_form_proposal["turn_id"],
                    approved_mutations=[
                        SlotProposal(
                            slot=m["slot"],
                            current_value=m["current_value"],
                            proposed_value=m["proposed_value"],
                            reason=m.get("reason", "user edit"),
                        )
                        for m in approved_mutations
                    ],
                    freeze_slots=freeze_decisions.get("freeze", []),
                    unfreeze_slots=freeze_decisions.get("unfreeze", []),
                )
                try:
                    _svc.commit_state_update(session_id=_sid2, decision=_decision)
                except ValueError as _exc:
                    st.error(f"Error al guardar las correcciones: {_exc}")
                    return

                # Clear form UI state
                st.session_state.pop("_show_reactive_correction", None)
                st.session_state.pop("_reactive_proposal_cache", None)
                _clear_form_state()

                if _form_source == "proactive_edit" and _pending:
                    # Commit applied; now resume the original query with bypass_gate.
                    # Clears _pending_proposal so the proactive panel does not reappear.
                    st.session_state.pop("_pending_proposal", None)
                    _orig = _pending["original_prompt"]
                    try:
                        from agents.runner import run_query as _run_query

                        _rr = _run_query(
                            query=_orig,
                            thread_id=str(st.session_state.session_id),
                            observer=st.session_state.observer,
                            graph=graph,
                            bypass_gate=True,
                        )
                        _resume_meta = {
                            "action": _rr.tool_used,
                            "reasoning": _rr.reasoning,
                            "raw_result": _rr.raw_result,
                            "judge_score": _rr.judge_score,
                            "judge_passed": _rr.judge_passed,
                            "judge_revised": _rr.judge_revised,
                            "total_ms": _rr.latency_ms,
                            "latencies": _rr.latencies,
                            "requires_confirmation": _rr.requires_confirmation,
                            "requires_approval": _rr.requires_approval,
                            "confirmation_message": _rr.confirmation_message,
                            "total_cost_usd": _rr.total_cost_usd,
                            "total_input_tokens": _rr.total_input_tokens,
                            "total_output_tokens": _rr.total_output_tokens,
                            "llm_calls_count": _rr.llm_calls_count,
                            "budget_exceeded": _rr.budget_exceeded,
                            "budget_exceeded_reason": _rr.budget_exceeded_reason,
                            "active_state": _rr.active_state,
                            "clarification_needed": _rr.clarification_needed,
                            "awaiting_user_confirmation": (
                                _rr.awaiting_user_confirmation
                            ),
                            "proposal": _rr.proposal,
                            "run_id": _rr.run_id,
                        }
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": _rr.answer,
                                "metadata": _resume_meta,
                            }
                        )
                    except Exception as _exc:
                        st.error(
                            f"Correcciones guardadas. "
                            f"Error al reanudar la consulta: {_exc}"
                        )

                st.rerun()

            def _form_on_cancel() -> None:
                st.session_state.pop("_show_reactive_correction", None)
                st.session_state.pop("_reactive_proposal_cache", None)
                _clear_form_state()
                # _pending_proposal is intentionally NOT cleared here so the
                # proactive panel reappears and the user can choose again.
                st.rerun()

            render_reactive_correction_form(
                proposal=_form_proposal,
                frozen_slots=_frozen_slots,
                on_save=_form_on_save,
                on_cancel=_form_on_cancel,
                source=_form_source,
            )

    with tab_dashboard:
        render_dashboard()
