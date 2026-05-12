"""
ui/components.py
-----------------
Pure render functions.  Each function receives its data as arguments and does
not access st.session_state directly — keeping them testable and reusable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import norm

from ui.styles import TOOL_LABELS, sanitize_markdown

# ---------------------------------------------------------------------------
# Chat message rendering
# ---------------------------------------------------------------------------


def render_chat_message(msg: Dict[str, Any]) -> None:
    """Render a single chat message (user or assistant) from the history list."""
    with st.chat_message(msg["role"]):
        st.markdown(sanitize_markdown(msg["content"]))
        if msg["role"] == "assistant" and msg.get("metadata"):
            _render_assistant_extras(msg["metadata"])


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
