"""
ui/components.py
-----------------
Pure render functions.  Each function receives its data as arguments and does
not access st.session_state directly — keeping them testable and reusable.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import norm

from memory import Intent
from ui.styles import TOOL_LABELS, sanitize_markdown

# ---------------------------------------------------------------------------
# Chat message rendering
# ---------------------------------------------------------------------------


def render_chat_message(msg: Dict[str, Any]) -> None:
    """Render a single chat message (user or assistant) from the history list."""
    with st.chat_message(msg["role"]):
        metadata = msg.get("metadata") or {}
        if msg["role"] == "assistant" and metadata.get("clarification_needed"):
            render_clarification_message(msg["content"])
        else:
            st.markdown(sanitize_markdown(msg["content"]))
            if msg["role"] == "assistant" and metadata:
                _render_assistant_extras(metadata)


def render_clarification_message(message: str) -> None:
    """Render a GroundedTokens clarification prompt (item 5.9).

    Displayed with an info callout so the user knows this is a vocabulary
    hint, not an error and not a normal analytical answer.
    """
    st.info(sanitize_markdown(message), icon="🔤")


def render_blocked_mutations_banner(blocked_mutations: list[Dict[str, Any]]) -> None:
    """Render a warning banner for mutations blocked by user-pinned frozen slots.

    Item 5.13.c. Displayed after a successful run when one or more slots were
    frozen by the user and the agent attempted to change them. Both sources of
    blocks (planner intent-freeze, coordinator slot-freeze) are shown here;
    the UI does not distinguish origin.
    """
    if not blocked_mutations:
        return
    lines = []
    for block in blocked_mutations:
        slot = block.get("slot", "?")
        attempted = block.get("blocked_value", "?")
        frozen = block.get("current_value", "?")
        lines.append(
            f"- **{slot}**: el agente habría elegido `{attempted}`, "
            f"pero está congelado en `{frozen}`."
        )
    banner = "**Acción bloqueada por valores congelados:**\n\n" + "\n".join(lines)
    st.warning(sanitize_markdown(banner), icon="🔒")


def render_proactive_confirmation(
    proposal: Dict[str, Any],
    on_confirm: Any,
    on_edit: Any,
    on_cancel: Any,
) -> None:
    """Render a proactive confirmation panel for the planner's proposed action.

    Item 5.13. Displayed when the proactive gate fires for an expensive tool
    and the agent pauses to ask the user to confirm before execution.

    Parameters
    ----------
    proposal  : JSON-serialisable StateProposal dict from RunResult.proposal.
    on_confirm: Callable — re-runs the original query with bypass_gate=True.
    on_edit   : Callable — opens the reactive correction form so the user can
                edit parameter values before confirming.
    on_cancel : Callable — discards the proposal and returns to idle state.
    """
    st.warning(
        "El agente quiere ejecutar un análisis costoso. "
        "Revisa los parámetros y confirma antes de continuar.",
        icon="⚠️",
    )
    mutations = proposal.get("mutations", [])
    triggered = proposal.get("triggered_signals", [])
    if triggered:
        signal_txt = ", ".join(f"`{s}`" for s in triggered)
        st.caption(f"Señales detectadas: {signal_txt}")

    if mutations:
        st.markdown("**Parámetros propuestos:**")
        for m in mutations:
            slot = m.get("slot", "")
            val = m.get("proposed_value")
            reason = m.get("reason", "")
            st.markdown(f"- **{slot}**: `{val}`")
            if reason:
                st.caption(f"  {reason}")

    # Compact button row: buttons grouped on the left with a wide spacer
    # on the right so they don't sprawl across the full width.
    col_confirm, col_edit, col_cancel, _spacer = st.columns([1.5, 1, 1, 5])
    with col_confirm:
        if st.button("Confirmar y ejecutar", type="primary", key="proactive_confirm"):
            on_confirm()
    with col_edit:
        if st.button("Editar", key="proactive_edit"):
            on_edit()
    with col_cancel:
        if st.button("Cancelar", key="proactive_cancel"):
            on_cancel()


def _render_assistant_extras(metadata: Dict[str, Any]) -> None:
    """Render tool badge, result cards, and technical details for an assistant msg."""
    try:
        action = metadata.get("action", "")
        raw_result = metadata.get("raw_result", {})
        total_ms = metadata.get("total_ms")

        tool_label = TOOL_LABELS.get(action, f"⚪ {action}" if action else "")
        if tool_label and total_ms:
            st.caption(f"{tool_label}  ·  {total_ms:,.0f} ms")
        elif total_ms:
            st.caption(f"{total_ms:,.0f} ms")

        render_result_cards(action, raw_result)
        render_blocked_mutations_banner(metadata.get("blocked_mutations") or [])
        render_technical_details(metadata)
    except Exception as e:  # noqa: BLE001
        st.caption(f"⚠️ Error en visualización: {e}")


# ---------------------------------------------------------------------------
# Result cards
# ---------------------------------------------------------------------------


def render_result_cards(action: str, raw_result: Dict[str, Any]) -> None:
    """Render metric cards and chart directly below the answer."""
    if not raw_result or action == "knowledge":
        return

    if action == "simulation":
        _render_simulation_cards(raw_result)
    elif action == "optimization":
        _render_optimization_cards(raw_result)


def _render_simulation_cards(raw: Dict[str, Any]) -> None:
    c1, c2, c3, c4 = st.columns(4)
    ep = raw.get("expected_profit")
    p10 = raw.get("profit_p10")
    p90 = raw.get("profit_p90")
    risk = raw.get("downside_risk_pct")
    if ep is not None:
        c1.metric("Beneficio esperado", f"€{ep:,.0f}")
    if p10 is not None:
        c2.metric("P10 (pesimista)", f"€{p10:,.0f}")
    if p90 is not None:
        c3.metric("P90 (optimista)", f"€{p90:,.0f}")
    if risk is not None:
        c4.metric("Riesgo a la baja", f"{risk:.1f}%")

    st.plotly_chart(
        _simulation_figure(raw),
        width="stretch",
        config={"displayModeBar": False},
    )

    ed = raw.get("expected_demand")
    ds = raw.get("demand_std")
    nr = raw.get("n_runs")
    if ed is not None:
        extra = f"  ·  σ demanda {ds:,.1f}" if ds is not None else ""
        nr_txt = f"  ·  {nr:,} simulaciones" if nr is not None else ""
        st.caption(f"Demanda esperada: {ed:,.1f} unidades{extra}{nr_txt}")


def _render_optimization_cards(raw: Dict[str, Any]) -> None:
    from spec.spec_loader import get_spec

    spec = get_spec()
    cols = st.columns(len(spec.decision_variables) + 1)
    for i, dv in enumerate(spec.decision_variables):
        val = raw.get(f"optimal_{dv.name}") or raw.get(dv.name)
        if val is not None:
            cols[i].metric(f"Óptimo {dv.name}", f"{val:,.2f} {dv.unit}")
    ep = raw.get("expected_profit")
    if ep is not None:
        cols[-1].metric("Beneficio esperado", f"€{ep:,.0f}")
    risk = raw.get("downside_risk_pct")
    if risk is not None:
        st.caption(f"Riesgo a la baja en el óptimo: {risk:.1f}%")


# ---------------------------------------------------------------------------
# Technical details expander
# ---------------------------------------------------------------------------


def render_technical_details(metadata: Dict[str, Any]) -> None:
    """Collapsible expander with per-node latency and judge verdict."""
    action = metadata.get("action", "—")
    reasoning = metadata.get("reasoning", "")
    judge_score = metadata.get("judge_score")
    judge_passed = metadata.get("judge_passed")
    judge_revised = metadata.get("judge_revised")
    total_ms = metadata.get("total_ms")
    latencies = metadata.get("latencies", {})

    _TOOL_ICONS = {"optimization": "🟢", "simulation": "🔵", "knowledge": "🟣"}

    with st.expander("Detalles técnicos", expanded=False):
        col1, col2 = st.columns([1, 2])
        with col1:
            icon = _TOOL_ICONS.get(action, "⚪")
            st.markdown(f"**Herramienta:** {icon} `{action}`")
            if total_ms is not None:
                st.markdown(f"**Latencia total:** `{total_ms:,.0f} ms`")
            if judge_score is not None:
                verdict = "✅ aprobado" if judge_passed else "✏️ revisado"
                st.markdown(f"**Juez:** `{judge_score:.2f}` — {verdict}")
            elif judge_revised is not None:
                st.markdown(
                    f"**Juez:** {'✅ aprobado' if judge_passed else '✏️ revisado'}"
                )
        with col2:
            if reasoning:
                st.markdown("**Razonamiento del planificador:**")
                st.caption(reasoning)

        if latencies:
            lc = st.columns(len(latencies))
            for (node, ms), col in zip(latencies.items(), lc):
                if ms is not None:
                    col.metric(node.capitalize(), f"{ms:,.0f} ms")

        cost_usd = metadata.get("total_cost_usd", 0.0)
        llm_calls = metadata.get("llm_calls_count", 0)
        tokens_in = metadata.get("total_input_tokens", 0)
        tokens_out = metadata.get("total_output_tokens", 0)
        budget_exceeded = metadata.get("budget_exceeded", False)
        if llm_calls or cost_usd:
            st.caption("**Coste LLM:**")
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("Llamadas LLM", llm_calls)
            cc2.metric("Tokens entrada", f"{tokens_in:,}")
            cc3.metric("Tokens salida", f"{tokens_out:,}")
            cc4.metric("Coste (USD)", f"${cost_usd:.4f}")
        if budget_exceeded:
            reason = metadata.get("budget_exceeded_reason", "")
            st.warning(f"⚠️ Budget ceiling reached: {reason}")

        active_state = metadata.get("active_state")
        if active_state:
            st.caption("**Estado analítico activo (item 5.11):**")
            intent_val = active_state.get("intent")
            sim_run = active_state.get("active_simulation_run")
            opt_run = active_state.get("active_optimization_run")
            version = active_state.get("version", 0)
            parts = [f"v{version}"]
            if intent_val:
                parts.append(f"intent: `{intent_val}`")
            if sim_run:
                parts.append(f"sim: `{sim_run}`")
            if opt_run:
                parts.append(f"opt: `{opt_run}`")
            st.caption("  ·  ".join(parts))
            # 5.13.c: button to open reactive correction form
            if version > 0:
                if st.button(
                    "Corregir contexto",
                    key=f"reactive_open_{metadata.get('run_id', 'current')}",
                    type="secondary",
                ):
                    st.session_state["_show_reactive_correction"] = True
                    st.rerun()


# ---------------------------------------------------------------------------
# Reactive correction form — pure helpers (item 5.13.c)
# ---------------------------------------------------------------------------

_REACTIVE_SLOTS: Tuple[str, ...] = (
    "intent",
    "metrics",
    "active_simulation_run",
    "active_optimization_run",
    "active_scenarios",
)

_REACTIVE_SLOT_LABELS: Dict[str, str] = {
    "intent": "Intención",
    "metrics": "Métricas",
    "active_simulation_run": "Simulación activa",
    "active_optimization_run": "Optimización activa",
    "active_scenarios": "Escenarios activos",
}

# Human-readable descriptions for the Intent selectbox.
_INTENT_DISPLAY: Dict[str, str] = {
    "optimize": "optimize — encontrar los valores óptimos",
    "simulate": "simulate — evaluar un escenario específico",
    "explain": "explain — entender el modelo causal",
    "explore": "explore — explorar relaciones entre variables",
}


def _normalize_metrics_list(value: Any) -> List[Dict[str, Any]]:
    """Convert any metrics representation (Pydantic models or raw dicts) to list[dict].

    Pure — no st.* calls, fully unit-testable.
    """
    if not value:
        return []
    result: List[Dict[str, Any]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            result.append(item.model_dump())
        elif isinstance(item, dict):
            result.append(dict(item))
        else:
            result.append(
                {
                    "id": str(item),
                    "name": str(item),
                    "source_turn": 0,
                    "confidence": 1.0,
                }
            )
    return result


def _assemble_metrics_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate and normalise structured metric rows.  Pure — no st.* calls.

    Rows with empty id are skipped.  confidence is clamped to [0.0, 1.0].
    """
    result: List[Dict[str, Any]] = []
    for row in rows:
        id_ = str(row.get("id", "")).strip()
        if not id_:
            continue
        result.append(
            {
                "id": id_,
                "name": str(row.get("name", "") or id_).strip() or id_,
                "confidence": max(0.0, min(1.0, float(row.get("confidence", 1.0)))),
                "source_turn": int(row.get("source_turn", 0)),
            }
        )
    return result


def _assemble_scenarios_from_rows(rows: List[str]) -> List[str]:
    """Strip and filter empty scenario strings.  Pure — no st.* calls."""
    return [s.strip() for s in rows if s.strip()]


def _parse_reactive_form_inputs(
    slot: str,
    raw_str: str,
    current_value: Any,
) -> Tuple[Any, Optional[str]]:
    """Parse and validate a raw form string for a state slot.  Pure — no st.* calls.

    Used by the Modo avanzado path.  Returns (parsed_value, error_message).
    error_message is None on success; on failure parsed_value is current_value.
    """
    if slot == "intent":
        valid = {e.value for e in Intent}
        if raw_str not in valid:
            return current_value, f"Valor inválido. Debe ser uno de: {sorted(valid)}"
        return raw_str, None
    elif slot in ("metrics", "active_scenarios"):
        stripped = raw_str.strip()
        try:
            parsed = json.loads(stripped) if stripped else []
        except json.JSONDecodeError as exc:
            return current_value, f"JSON inválido: {exc}"
        return parsed, None
    elif slot in ("active_simulation_run", "active_optimization_run"):
        val = raw_str.strip()
        return val if val else None, None
    return raw_str, None


def _compute_freeze_decisions(
    slot: str,
    was_frozen: bool,
    is_now_checked: bool,
) -> Tuple[List[str], List[str]]:
    """Return (freeze_slots, unfreeze_slots) for a single slot state transition.

    Pure — no st.* calls, fully unit-testable.
    """
    if is_now_checked and not was_frozen:
        return [slot], []
    if not is_now_checked and was_frozen:
        return [], [slot]
    return [], []


def render_reactive_correction_form(
    proposal: Dict[str, Any],
    frozen_slots: List[str],
    on_save: Any,
    on_cancel: Any,
    source: str,
) -> Dict[str, Any]:
    """Render the inline reactive-correction form (item 5.13.c).

    Accordion layout with four st.expander sections (Intención, Métricas,
    Simulación activa, Optimización activa, Escenarios).  A "Modo avanzado"
    toggle reveals raw JSON / UUID inputs for power users.

    Parameters
    ----------
    proposal     : dict — turn_id, mutations, candidate_runs (new), etc.
    frozen_slots : slots currently frozen in ActiveAnalyticalState.
    on_save      : Callable[(approved_mutations, freeze_decisions)].
    on_cancel    : Callable — discards edits.
    source       : "reactive" | "proactive_edit" — controls button labels.
    """
    title = "Editar parámetros" if source == "proactive_edit" else "Corregir contexto"
    save_label = "Guardar y ejecutar" if source == "proactive_edit" else "Guardar"

    mutations_by_slot: Dict[str, Dict[str, Any]] = {
        m["slot"]: m for m in proposal.get("mutations", [])
    }
    candidate_runs: Dict[str, List[Dict[str, Any]]] = proposal.get("candidate_runs", {})

    current_vals: Dict[str, Any] = {}
    save_clicked = False
    cancel_clicked = False

    with st.container(border=True):
        st.markdown(f"**{title}**")

        advanced_mode: bool = st.toggle(
            "Modo avanzado",
            key="reactive_form_advanced_mode",
            help="Muestra los campos en formato JSON/UUID para edición directa.",
        )

        # ── Section: Intent ───────────────────────────────────────────────
        intent_cv = mutations_by_slot.get("intent", {}).get("current_value")
        # B3 fix: Intent is an enum; use .value for display, not str() which
        # produces "Intent.OPTIMIZE" instead of "optimize".
        _intent_str = (
            (intent_cv.value if hasattr(intent_cv, "value") else str(intent_cv))
            if intent_cv is not None
            else ""
        )
        with st.expander("Intención", expanded=True):
            if advanced_mode:
                current_vals["intent"] = st.text_input(
                    "Valor (enum)",
                    value=_intent_str,
                    key="reactive_form_intent_adv",
                    placeholder="optimize | simulate | explain | explore",
                )
            else:
                _options = [e.value for e in Intent]
                _display = [_INTENT_DISPLAY.get(o, o) for o in _options]
                _def_idx = _options.index(_intent_str) if _intent_str in _options else 0
                _sel = st.selectbox(
                    "Intención analítica",
                    options=_display,
                    index=_def_idx,
                    key="reactive_form_intent",
                )
                current_vals["intent"] = _options[_display.index(_sel)]

            st.checkbox(
                "Congelar",
                value="intent" in frozen_slots,
                key="reactive_form_freeze_intent",
                help="Impide que el agente sobreescriba este valor automáticamente.",
            )

        # ── Section: Metrics ──────────────────────────────────────────────
        metrics_cv = mutations_by_slot.get("metrics", {}).get("current_value")
        norm_metrics = _normalize_metrics_list(metrics_cv)

        # Init structured keys on first render; cleared by _clear_form_state on close.
        if "reactive_form_metrics_count" not in st.session_state:
            st.session_state["reactive_form_metrics_count"] = len(norm_metrics)
            st.session_state["reactive_form_metrics_deleted"] = []
            for _i, _nm in enumerate(norm_metrics):
                st.session_state[f"reactive_form_metric_{_i}_id"] = _nm.get("id", "")
                st.session_state[f"reactive_form_metric_{_i}_name"] = _nm.get(
                    "name", ""
                )
                st.session_state[f"reactive_form_metric_{_i}_confidence"] = float(
                    _nm.get("confidence", 1.0)
                )

        with st.expander("Métricas", expanded=False):
            if advanced_mode:
                _def_json = (
                    json.dumps(norm_metrics, indent=2, ensure_ascii=False)
                    if norm_metrics
                    else "[]"
                )
                current_vals["metrics"] = st.text_area(
                    "Lista de métricas (JSON)",
                    value=_def_json,
                    key="reactive_form_metrics_adv",
                    height=120,
                )
            else:
                _m_count: int = st.session_state.get("reactive_form_metrics_count", 0)
                _m_deleted: List[int] = st.session_state.get(
                    "reactive_form_metrics_deleted", []
                )
                _m_deleted_set = set(_m_deleted)
                _rows_collected: List[Dict[str, Any]] = []

                if _m_count > 0:
                    _h1, _h2, _h3, _ = st.columns([3, 3, 2, 1])
                    _h1.caption("ID")
                    _h2.caption("Nombre")
                    _h3.caption("Conf.")

                for _i in range(_m_count):
                    if _i in _m_deleted_set:
                        continue
                    _c1, _c2, _c3, _c4 = st.columns([3, 3, 2, 1])
                    with _c1:
                        _id_v = st.text_input(
                            "id",
                            key=f"reactive_form_metric_{_i}_id",
                            label_visibility="collapsed",
                            placeholder="id métrica",
                        )
                    with _c2:
                        _nm_v = st.text_input(
                            "nombre",
                            key=f"reactive_form_metric_{_i}_name",
                            label_visibility="collapsed",
                            placeholder="nombre",
                        )
                    with _c3:
                        _cf_v = st.number_input(
                            "conf",
                            min_value=0.0,
                            max_value=1.0,
                            step=0.1,
                            key=f"reactive_form_metric_{_i}_confidence",
                            label_visibility="collapsed",
                        )
                    with _c4:
                        if st.button("✕", key=f"reactive_form_metric_{_i}_del"):
                            _m_deleted.append(_i)
                            st.session_state["reactive_form_metrics_deleted"] = (
                                _m_deleted
                            )
                            st.rerun()
                    _rows_collected.append(
                        {
                            "id": _id_v,
                            "name": _nm_v,
                            "confidence": _cf_v,
                            "source_turn": 0,
                        }
                    )

                if _m_count == 0 or _m_count == len(_m_deleted_set):
                    st.caption("Sin métricas activas.")

                if st.button("＋ Añadir métrica", key="reactive_form_metrics_add"):
                    _new_i = st.session_state.get("reactive_form_metrics_count", 0)
                    st.session_state["reactive_form_metrics_count"] = _new_i + 1
                    st.session_state[f"reactive_form_metric_{_new_i}_id"] = ""
                    st.session_state[f"reactive_form_metric_{_new_i}_name"] = ""
                    st.session_state[f"reactive_form_metric_{_new_i}_confidence"] = 1.0
                    st.rerun()

                current_vals["metrics"] = _rows_collected

            st.checkbox(
                "Congelar",
                value="metrics" in frozen_slots,
                key="reactive_form_freeze_metrics",
                help="Impide que el agente sobreescriba este valor automáticamente.",
            )

        # ── Helper: render a run slot (simulation or optimization) ────────
        def _render_run_expander(slot: str, label: str) -> None:
            """Render one run-selection expander, setting current_vals[slot]."""
            run_cv = mutations_by_slot.get(slot, {}).get("current_value")
            candidates: List[Dict[str, Any]] = candidate_runs.get(slot, [])

            with st.expander(label, expanded=False):
                if advanced_mode:
                    current_vals[slot] = st.text_input(
                        "ID de ejecución (UUID)",
                        value=str(run_cv) if run_cv else "",
                        key=f"reactive_form_{slot}_adv",
                        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                    )
                elif candidates:
                    _none_lbl = "— ninguna (borrar valor actual) —"
                    _drop_labels = [_none_lbl] + [
                        f"{c['label']}  ·  {c['run_id'][:8]}…" for c in candidates
                    ]
                    _def_idx = 0
                    if run_cv:
                        for _j, _c in enumerate(candidates):
                            if _c["run_id"] == str(run_cv):
                                _def_idx = _j + 1
                                break
                    _sel_lbl = st.selectbox(
                        "Seleccionar ejecución",
                        options=_drop_labels,
                        index=_def_idx,
                        key=f"reactive_form_{slot}_select",
                    )
                    if _sel_lbl == _none_lbl:
                        current_vals[slot] = None
                    else:
                        _sidx = _drop_labels.index(_sel_lbl) - 1
                        current_vals[slot] = candidates[_sidx]["run_id"]
                else:
                    current_vals[slot] = st.text_input(
                        "ID de ejecución",
                        value=str(run_cv) if run_cv else "",
                        key=f"reactive_form_{slot}",
                        placeholder="Pega aquí el ID de la ejecución",
                    )

                st.checkbox(
                    "Congelar",
                    value=slot in frozen_slots,
                    key=f"reactive_form_freeze_{slot}",
                    help="Impide que el agente sobreescriba este valor.",
                )

        _render_run_expander("active_simulation_run", "Simulación activa")
        _render_run_expander("active_optimization_run", "Optimización activa")

        # ── Section: Scenarios ────────────────────────────────────────────
        scen_cv_raw = mutations_by_slot.get("active_scenarios", {}).get("current_value")
        scen_cv: List[str] = (
            [str(s) for s in scen_cv_raw] if isinstance(scen_cv_raw, list) else []
        )

        if "reactive_form_scenarios_count" not in st.session_state:
            st.session_state["reactive_form_scenarios_count"] = len(scen_cv)
            st.session_state["reactive_form_scenarios_deleted"] = []
            for _i, _sc in enumerate(scen_cv):
                st.session_state[f"reactive_form_scenario_{_i}"] = _sc

        with st.expander("Escenarios activos", expanded=False):
            if advanced_mode:
                _def_scen = (
                    json.dumps(scen_cv, indent=2, ensure_ascii=False)
                    if scen_cv
                    else "[]"
                )
                current_vals["active_scenarios"] = st.text_area(
                    "Lista de escenarios (JSON)",
                    value=_def_scen,
                    key="reactive_form_active_scenarios_adv",
                    height=80,
                )
            else:
                _sc_count: int = st.session_state.get(
                    "reactive_form_scenarios_count", 0
                )
                _sc_deleted: List[int] = st.session_state.get(
                    "reactive_form_scenarios_deleted", []
                )
                _sc_deleted_set = set(_sc_deleted)
                _scen_rows: List[str] = []

                for _i in range(_sc_count):
                    if _i in _sc_deleted_set:
                        continue
                    _cv, _cd = st.columns([9, 1])
                    with _cv:
                        _sv = st.text_input(
                            "escenario",
                            key=f"reactive_form_scenario_{_i}",
                            label_visibility="collapsed",
                            placeholder="descripción del escenario",
                        )
                    with _cd:
                        if st.button("✕", key=f"reactive_form_scenario_{_i}_del"):
                            _sc_deleted.append(_i)
                            st.session_state["reactive_form_scenarios_deleted"] = (
                                _sc_deleted
                            )
                            st.rerun()
                    _scen_rows.append(_sv)

                if _sc_count == 0 or _sc_count == len(_sc_deleted_set):
                    st.caption("Sin escenarios activos.")

                if st.button("＋ Añadir escenario", key="reactive_form_scenarios_add"):
                    _new_sc = st.session_state.get("reactive_form_scenarios_count", 0)
                    st.session_state["reactive_form_scenarios_count"] = _new_sc + 1
                    st.session_state[f"reactive_form_scenario_{_new_sc}"] = ""
                    st.rerun()

                current_vals["active_scenarios"] = _scen_rows

            st.checkbox(
                "Congelar",
                value="active_scenarios" in frozen_slots,
                key="reactive_form_freeze_active_scenarios",
                help="Impide que el agente sobreescriba este valor automáticamente.",
            )

        # ── Footer buttons ────────────────────────────────────────────────
        st.markdown("---")
        col_save, col_cancel, _sp = st.columns([1.5, 1, 5])
        with col_save:
            save_clicked = st.button(
                save_label, key="reactive_form_save", type="primary"
            )
        with col_cancel:
            cancel_clicked = st.button("Cancelar", key="reactive_form_cancel")

    # ── Cancel ────────────────────────────────────────────────────────────
    if cancel_clicked:
        on_cancel()
        return current_vals

    # ── Save ──────────────────────────────────────────────────────────────
    if save_clicked:
        errors: List[str] = []
        approved: List[Dict[str, Any]] = []

        if advanced_mode:
            # Advanced path: read raw text/JSON inputs and validate.
            _adv_raw: Dict[str, str] = {
                "intent": str(st.session_state.get("reactive_form_intent_adv", "")),
                "metrics": str(st.session_state.get("reactive_form_metrics_adv", "[]")),
                "active_simulation_run": str(
                    st.session_state.get("reactive_form_active_simulation_run_adv", "")
                ),
                "active_optimization_run": str(
                    st.session_state.get(
                        "reactive_form_active_optimization_run_adv", ""
                    )
                ),
                "active_scenarios": str(
                    st.session_state.get("reactive_form_active_scenarios_adv", "[]")
                ),
            }
            for _slot in _REACTIVE_SLOTS:
                _m = mutations_by_slot.get(_slot, {})
                _raw = _adv_raw.get(_slot, "")
                _cv = _m.get("current_value")
                _parsed, _err = _parse_reactive_form_inputs(_slot, _raw, _cv)
                if _err:
                    errors.append(
                        f"**{_REACTIVE_SLOT_LABELS.get(_slot, _slot)}**: {_err}"
                    )
                else:
                    approved.append(
                        {
                            "slot": _slot,
                            "current_value": _cv,
                            "proposed_value": _parsed,
                            "reason": "user edit (advanced mode)",
                        }
                    )
        else:
            # Structured path: collect from widget values set during rendering.
            _intent_cv2 = mutations_by_slot.get("intent", {}).get("current_value")
            approved.append(
                {
                    "slot": "intent",
                    "current_value": _intent_cv2,
                    "proposed_value": current_vals.get("intent", _intent_cv2),
                    "reason": "user edit",
                }
            )
            _metrics_cv2 = mutations_by_slot.get("metrics", {}).get("current_value")
            approved.append(
                {
                    "slot": "metrics",
                    "current_value": _metrics_cv2,
                    "proposed_value": _assemble_metrics_from_rows(
                        current_vals.get("metrics") or []
                    ),
                    "reason": "user edit",
                }
            )
            for _rslot in ("active_simulation_run", "active_optimization_run"):
                approved.append(
                    {
                        "slot": _rslot,
                        "current_value": mutations_by_slot.get(_rslot, {}).get(
                            "current_value"
                        ),
                        "proposed_value": current_vals.get(_rslot),
                        "reason": "user edit",
                    }
                )
            _scen_cv2 = mutations_by_slot.get("active_scenarios", {}).get(
                "current_value"
            )
            approved.append(
                {
                    "slot": "active_scenarios",
                    "current_value": _scen_cv2,
                    "proposed_value": _assemble_scenarios_from_rows(
                        current_vals.get("active_scenarios") or []
                    ),
                    "reason": "user edit",
                }
            )

        if errors:
            for _emsg in errors:
                st.error(sanitize_markdown(_emsg))
        else:
            freeze_all: List[str] = []
            unfreeze_all: List[str] = []
            for _slot2 in _REACTIVE_SLOTS:
                _was = _slot2 in frozen_slots
                _chk = bool(
                    st.session_state.get(f"reactive_form_freeze_{_slot2}", False)
                )
                _f, _u = _compute_freeze_decisions(_slot2, _was, _chk)
                freeze_all.extend(_f)
                unfreeze_all.extend(_u)
            on_save(approved, {"freeze": freeze_all, "unfreeze": unfreeze_all})

    return current_vals


# ---------------------------------------------------------------------------
# Welcome cards
# ---------------------------------------------------------------------------

_EXAMPLE_QUERIES: List[Tuple[str, str, str]] = [
    (
        "¿Qué precio maximiza el beneficio?",
        "Optimización — busca el valor óptimo explorando combinaciones de precio y marketing",  # noqa: E501
        "¿Cuál es la combinación óptima de precio y marketing para maximizar el beneficio?",  # noqa: E501
    ),
    (
        "Simula el impacto de fijar precio a 25€",
        "Simulación Monte Carlo — 500 escenarios con incertidumbre, distribución de resultados",  # noqa: E501
        "Simula el beneficio con precio 25 € y marketing en 8.000 €",
    ),
    (
        "¿Cómo afecta el marketing a la demanda?",
        "Consulta al modelo causal — recorre el DAG para explicar relaciones entre variables",  # noqa: E501
        "¿Cómo afecta el nivel de marketing a la demanda según el modelo causal?",
    ),
]


def render_welcome_cards() -> Optional[str]:
    """
    Render three example-query cards.  Returns the query string if a card
    button was clicked, otherwise None.
    """
    st.divider()
    col1, col2, col3 = st.columns(3)
    pending: Optional[str] = None
    for col, (card_title, card_desc, query) in zip(
        [col1, col2, col3], _EXAMPLE_QUERIES
    ):
        with col:
            st.markdown(
                f'<div style="background: rgba(108,142,245,0.06); '
                f"border: 1px solid rgba(108,142,245,0.15); "
                f"border-radius: 10px; padding: 20px 20px 10px;"
                f'">'
                f'<p style="font-size: 16px; font-weight: bold; margin: 0 0 6px;">'
                f"{card_title}</p>"
                f'<p style="font-size: 13px; color: #888; margin: 0;">'
                f"{card_desc}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Preguntar",
                key=f"card_{card_title}",
                use_container_width=True,
                type="primary",
            ):
                pending = query
    st.divider()
    return pending


# ---------------------------------------------------------------------------
# Plotly figures (pure — no st.* calls)
# ---------------------------------------------------------------------------


def _simulation_figure(raw: Dict[str, Any]) -> go.Figure:
    mean = float(raw.get("expected_profit", 0))
    std = float(raw.get("profit_std", 1)) or 1.0
    p10 = float(raw.get("profit_p10", mean - 1.28 * std))
    p90 = float(raw.get("profit_p90", mean + 1.28 * std))

    x = np.linspace(mean - 3.8 * std, mean + 3.8 * std, 400)
    y = norm.pdf(x, mean, std)
    mask = (x >= p10) & (x <= p90)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            fill="tozeroy",
            mode="lines",
            line=dict(color="#3b82f6", width=1.5),
            fillcolor="rgba(59,130,246,0.12)",
            name="Distribución",
            hovertemplate="Beneficio: %{x:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x[mask],
            y=y[mask],
            fill="tozeroy",
            mode="none",
            fillcolor="rgba(59,130,246,0.30)",
            name="Rango P10–P90",
            hoverinfo="skip",
        )
    )
    fig.add_vline(
        x=mean,
        line=dict(color="#22c55e", width=2, dash="solid"),
        annotation_text=f"Media {mean:,.0f}",
        annotation_position="top right",
    )
    fig.add_vline(
        x=p10,
        line=dict(color="#f59e0b", width=1.2, dash="dot"),
        annotation_text="P10",
        annotation_position="top left",
    )
    fig.add_vline(
        x=p90,
        line=dict(color="#f59e0b", width=1.2, dash="dot"),
        annotation_text="P90",
        annotation_position="top right",
    )
    fig.update_layout(
        height=220,
        margin=dict(l=10, r=10, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(
            title="Beneficio (EUR)",
            tickformat=",.0f",
            gridcolor="rgba(128,128,128,0.15)",
        ),
        yaxis=dict(showticklabels=False, gridcolor="rgba(128,128,128,0.1)"),
    )
    return fig
