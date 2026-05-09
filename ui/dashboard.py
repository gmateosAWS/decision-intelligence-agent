"""
ui/dashboard.py
----------------
Observability dashboard rendered inside the Dashboard tab.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from evaluation.metrics import compute_metrics, load_runs
from ui.styles import TOOL_COLORS


def render_dashboard() -> None:
    """Render the observability dashboard from evaluation/metrics.py."""
    st.caption("Dashboard de Observabilidad")

    runs = load_runs()
    metrics = compute_metrics(runs)

    if not metrics:
        st.info("No hay datos de ejecución todavía.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total ejecuciones", metrics["total_runs"])
    sr = metrics.get("success_rate", 0.0)
    c2.metric("Tasa de éxito", f"{sr * 100:.1f}%")
    avg_lat = metrics.get("avg_total_latency_ms")
    c3.metric("Latencia media", f"{avg_lat:,.0f} ms" if avg_lat is not None else "—")
    avg_conf = metrics.get("avg_confidence_score")
    c4.metric("Confianza media", f"{avg_conf:.2f}" if avg_conf is not None else "—")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        dist = metrics.get("tool_distribution", {})
        if dist:
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=[str(k) for k in dist.keys()],
                        values=[float(v) for v in dist.values()],
                        hole=0.5,
                        marker_colors=[
                            str(TOOL_COLORS.get(k, "#94a3b8")) for k in dist.keys()
                        ],
                    )
                ]
            )
            fig.update_layout(
                title="Distribución de herramientas",
                height=280,
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with col_r:
        _node_cfg = [
            ("Planner", "avg_planner_latency_ms", "#3b82f6"),
            ("Tool", "avg_tool_latency_ms", "#22c55e"),
            ("Synthesizer", "avg_synthesizer_latency_ms", "#f59e0b"),
            ("Judge", "avg_judge_latency_ms", "#ef4444"),
        ]
        valid = [(n, metrics.get(k), c) for n, k, c in _node_cfg if metrics.get(k)]
        if valid:
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=[str(v[0]) for v in valid],
                        y=[float(v[1]) for v in valid],
                        marker_color=[str(v[2]) for v in valid],
                    )
                ]
            )
            fig.update_layout(
                title="Latencia media por nodo (ms)",
                height=280,
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    st.divider()

    recent = metrics.get("recent_runs", [])
    if recent:
        st.markdown("**Últimas ejecuciones**")
        rows = []
        for r in reversed(recent):
            ts = (r.get("timestamp") or "")[:19].replace("T", " ")
            lat = r.get("total_latency_ms")
            judge = r.get("judge_score")
            rows.append(
                {
                    "Timestamp": ts,
                    "Query": (r.get("query") or "")[:60],
                    "Tool": r.get("action") or "—",
                    "Latencia (ms)": f"{lat:,.0f}" if lat is not None else "—",
                    "Judge": f"{judge:.2f}" if judge is not None else "—",
                    "OK": "✓" if r.get("success", True) else "✗",
                }
            )
        st.dataframe(rows, width="stretch", hide_index=True)
