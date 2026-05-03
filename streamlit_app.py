"""
streamlit_app.py
----------------
Streamlit web UI for the Decision Intelligence Agent.

Presentation layer only — invokes the same LangGraph graph as app.py without
modifying any agent code.  Sessions are persisted via PostgresSaver (or SqliteSaver
fallback) so multi-turn memory works identically to the REPL.

Run:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from scipy.stats import norm

load_dotenv()

# ---------------------------------------------------------------------------
# Page config — must be the first st.* call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="llull — Decision Intelligence Agent",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Agent imports (after set_page_config so Streamlit owns the page)
# ---------------------------------------------------------------------------

from agents.workflow import build_graph as build_agent_graph  # noqa: E402
from evaluation.metrics import compute_metrics, load_runs  # noqa: E402
from evaluation.observer import AgentObserver  # noqa: E402
from memory import SessionManager, get_checkpointer, register_turn  # noqa: E402
from spec.spec_loader import SPEC_PATH, get_spec  # noqa: E402
from system.system_graph import build_graph as build_causal_graph  # noqa: E402

# ---------------------------------------------------------------------------
# Cached resources (initialized once per process)
# ---------------------------------------------------------------------------


@st.cache_resource
def _seed_spec() -> str:
    """Auto-seed the spec into Postgres on first startup. Returns a status string."""
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
def _load_agent_graph():
    """Build and cache the LangGraph agent with the active checkpointer backend."""
    checkpointer = get_checkpointer()
    graph = build_agent_graph(checkpointer=checkpointer)
    return graph, checkpointer


@st.cache_resource
def _load_causal_graph():
    """Build and cache the causal NetworkX DiGraph from the spec."""
    return build_causal_graph()


# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------


def _dag_figure(G: nx.DiGraph) -> go.Figure:
    """Return a Plotly figure of the causal DAG, coloured by variable type."""
    spec = get_spec()
    decision_names = {v.name for v in spec.decision_variables}
    target_names = {v.name for v in spec.target_variables}

    # Hierarchical layout: decision(0) → intermediate(1) → target(2)
    layer: Dict[str, int] = {}
    for node in G.nodes():
        if node in decision_names:
            layer[node] = 0
        elif node in target_names:
            layer[node] = 2
        else:
            layer[node] = 1

    layer_buckets: Dict[int, List[str]] = {0: [], 1: [], 2: []}
    for node, lvl in layer.items():
        layer_buckets[lvl].append(node)

    pos: Dict[str, tuple] = {}
    for lvl, nodes in layer_buckets.items():
        nodes_sorted = sorted(nodes)
        n = len(nodes_sorted)
        for i, node in enumerate(nodes_sorted):
            pos[node] = (lvl * 3.0, (i - (n - 1) / 2) * 1.8)

    # Edge traces
    edge_x: List[Optional[float]] = []
    edge_y: List[Optional[float]] = []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line=dict(width=1.5, color="#64748b"),
        hoverinfo="none",
    )

    # Node traces by type
    _COLOURS = {"decision": "#3b82f6", "intermediate": "#94a3b8", "target": "#22c55e"}
    _LABELS = {
        "decision": "Variable de decisión",
        "intermediate": "Intermedia",
        "target": "Objetivo",
    }

    traces = [edge_trace]
    for ntype, colour in _COLOURS.items():
        if ntype == "decision":
            nodes_of_type = [n for n in G.nodes() if n in decision_names]
        elif ntype == "target":
            nodes_of_type = [n for n in G.nodes() if n in target_names]
        else:
            nodes_of_type = [
                n
                for n in G.nodes()
                if n not in decision_names and n not in target_names
            ]
        if not nodes_of_type:
            continue
        xs = [pos[n][0] for n in nodes_of_type]
        ys = [pos[n][1] for n in nodes_of_type]
        traces.append(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers+text",
                text=nodes_of_type,
                textposition="top center",
                textfont=dict(size=11),
                marker=dict(size=18, color=colour, line=dict(width=1.5, color="white")),
                name=_LABELS[ntype],
                hovertemplate="%{text}<extra></extra>",
            )
        )

    fig = go.Figure(data=traces)
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=30, b=10),
        height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    )
    return fig


def _simulation_figure(raw: Dict[str, Any]) -> go.Figure:
    """Approximate profit distribution plot from Monte Carlo summary stats."""
    mean = float(raw.get("expected_profit", 0))
    std = float(raw.get("profit_std", 1)) or 1.0
    p10 = float(raw.get("profit_p10", mean - 1.28 * std))
    p90 = float(raw.get("profit_p90", mean + 1.28 * std))

    x = np.linspace(mean - 3.8 * std, mean + 3.8 * std, 400)
    y = norm.pdf(x, mean, std)

    # P10–P90 confidence band mask
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


def _sanitize_markdown(text: str) -> str:
    """Close unclosed inline markdown delimiters to prevent style bleed."""
    # Close unclosed triple-backtick code fences first
    if len(re.findall(r"```", text)) % 2 == 1:
        text = text.rstrip() + "\n```"
    # Close unclosed inline backticks (excluding fence regions)
    no_fences = re.sub(r"```[\s\S]*?```", "", text)
    if no_fences.count("`") % 2 == 1:
        text += "`"
    # Close unclosed bold markers
    if len(re.findall(r"\*\*", text)) % 2 == 1:
        text += "**"
    return text


# Tool label map shared between history render and new response render
_TOOL_LABELS: Dict[str, str] = {
    "optimization": "🟢 Optimización",
    "simulation": "🔵 Simulación",
    "knowledge": "🟣 Conocimiento",
}

_TOOL_COLORS: Dict[str, str] = {
    "optimization": "#22c55e",
    "simulation": "#3b82f6",
    "knowledge": "#a855f7",
}


def _render_result_cards(action: str, raw_result: Dict[str, Any]) -> None:
    """Render result metrics and chart directly below the answer."""
    if not raw_result or action == "knowledge":
        return

    if action == "simulation":
        c1, c2, c3, c4 = st.columns(4)
        ep = raw_result.get("expected_profit")
        p10 = raw_result.get("profit_p10")
        p90 = raw_result.get("profit_p90")
        risk = raw_result.get("downside_risk_pct")
        if ep is not None:
            c1.metric("Beneficio esperado", f"€{ep:,.0f}")
        if p10 is not None:
            c2.metric("P10 (pesimista)", f"€{p10:,.0f}")
        if p90 is not None:
            c3.metric("P90 (optimista)", f"€{p90:,.0f}")
        if risk is not None:
            c4.metric("Riesgo a la baja", f"{risk:.1f}%")

        st.plotly_chart(
            _simulation_figure(raw_result),
            width="stretch",
            config={"displayModeBar": False},
        )

        ed = raw_result.get("expected_demand")
        ds = raw_result.get("demand_std")
        nr = raw_result.get("n_runs")
        if ed is not None:
            extra = f"  ·  σ demanda {ds:,.1f}" if ds is not None else ""
            nr_txt = f"  ·  {nr:,} simulaciones" if nr is not None else ""
            st.caption(f"Demanda esperada: {ed:,.1f} unidades{extra}{nr_txt}")

    elif action == "optimization":
        spec = get_spec()
        cols = st.columns(len(spec.decision_variables) + 1)
        for i, dv in enumerate(spec.decision_variables):
            val = raw_result.get(f"optimal_{dv.name}") or raw_result.get(dv.name)
            if val is not None:
                cols[i].metric(f"Óptimo {dv.name}", f"{val:,.2f} {dv.unit}")
        ep = raw_result.get("expected_profit")
        if ep is not None:
            cols[-1].metric("Beneficio esperado", f"€{ep:,.0f}")

        risk = raw_result.get("downside_risk_pct")
        if risk is not None:
            st.caption(f"Riesgo a la baja en el óptimo: {risk:.1f}%")


def _render_run_details(metadata: Dict[str, Any]) -> None:
    """Collapsible expander with per-node latency and judge verdict."""
    action = metadata.get("action", "—")
    reasoning = metadata.get("reasoning", "")
    judge_score = metadata.get("judge_score")
    judge_passed = metadata.get("judge_passed")
    judge_revised = metadata.get("judge_revised")
    total_ms = metadata.get("total_ms")
    latencies = metadata.get("latencies", {})

    with st.expander("Detalles técnicos", expanded=False):
        col1, col2 = st.columns([1, 2])
        with col1:
            _TOOL_ICONS = {
                "optimization": "🟢",
                "simulation": "🔵",
                "knowledge": "🟣",
            }
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


# ---------------------------------------------------------------------------
# Observability dashboard
# ---------------------------------------------------------------------------


def _render_dashboard() -> None:
    """Render the observability dashboard from evaluation/metrics.py."""
    st.caption("Dashboard de Observabilidad")

    runs = load_runs()
    metrics = compute_metrics(runs)

    if not metrics:
        st.info("No hay datos de ejecución todavía.")
        return

    # KPI cards
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

    # Tool distribution — donut chart
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
                            str(_TOOL_COLORS.get(k, "#94a3b8")) for k in dist.keys()
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

    # Latency breakdown — bar chart
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

    # Recent runs table
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


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------


def _new_session() -> None:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.is_new_session = True
    st.session_state.messages = []


def _resume_session(session_id: str) -> None:
    """Restore a session and populate display messages from graph state."""
    graph, _ = _load_agent_graph()
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


def _init_state() -> None:
    if "session_id" not in st.session_state:
        _new_session()
    if "observer" not in st.session_state:
        st.session_state.observer = AgentObserver(log_dir="logs")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "is_new_session" not in st.session_state:
        st.session_state.is_new_session = True


_init_state()
with st.spinner("Iniciando llull — cargando especificación y construyendo agente…"):
    _spec_source = _seed_spec()  # must run before any get_spec() call
    graph, _checkpointer = _load_agent_graph()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<span style="font-family: Georgia, serif; font-size: 28px; '
        'font-weight: 400; letter-spacing: -1px;">'
        '||<span style="font-weight: 700;">u</span>||</span>',
        unsafe_allow_html=True,
    )
    st.markdown("**llull**")
    st.caption("Inverence")
    if st.button("Inicio", use_container_width=True, type="secondary"):
        _new_session()
        st.rerun()
    st.divider()

    # --- Session management ---
    st.subheader("Sesión")

    if st.button("＋ Nueva sesión", use_container_width=True):
        _new_session()
        st.rerun()

    sessions = SessionManager.list_sessions()
    if sessions:
        opts = {}
        for s in sessions:
            label = f"{s['title'][:28]}…  ({s['turn_count']} turnos)"
            opts[label] = s["session_id"]

        chosen_label = st.selectbox(
            "Retomar una sesión anterior",
            options=["— seleccionar —"] + list(opts.keys()),
            key="resume_selector",
        )
        if chosen_label != "— seleccionar —":
            if st.button("↩ Retomar seleccionada", use_container_width=True):
                _resume_session(opts[chosen_label])
                st.rerun()

    # Session info
    sid = st.session_state.session_id
    session_row = SessionManager.get_session(sid)
    if session_row:
        st.info(
            f"**`{sid[:8]}…`**  \n"
            f"Turnos: {session_row['turn_count']}  \n"
            f"Activa: {session_row['last_active'][:10]}"
        )
    else:
        st.info(f"**`{sid[:8]}…`**  \n*Nueva — sin turnos aún*")

    st.divider()

    # --- LLM config ---
    with st.expander("Configuración LLM", expanded=False):
        _llm_nodes = [
            (
                "Planificador",
                "PLANNER_PROVIDER",
                "PLANNER_MODEL",
                "openai",
                "gpt-4o-mini",
            ),
            (
                "Sintetizador",
                "SYNTHESIZER_PROVIDER",
                "SYNTHESIZER_MODEL",
                "openai",
                "gpt-4o-mini",
            ),  # noqa: E501
            ("Juez", "JUDGE_PROVIDER", "JUDGE_MODEL", "openai", "gpt-4o-mini"),
        ]
        for label, prov_key, model_key, def_prov, def_model in _llm_nodes:
            prov = os.getenv(prov_key, def_prov)
            model = os.getenv(model_key, def_model)
            st.markdown(f"**{label}** · `{prov}` / `{model}`")
        fb_prov = os.getenv("FALLBACK_PROVIDER", "")
        fb_model = os.getenv("FALLBACK_MODEL", "")
        if fb_prov:
            st.divider()
            st.markdown(f"**Fallback** · `{fb_prov}` / `{fb_model}`")
        retries = os.getenv("LLM_MAX_RETRIES", "2")
        timeout = os.getenv("LLM_TIMEOUT", "30")
        st.caption(f"Reintentos: {retries} · Timeout: {timeout}s")

    # --- Domain info ---
    try:
        spec = get_spec()
        with st.expander("Dominio", expanded=False):
            st.markdown(f"**{spec.domain_name}**")
            st.caption(spec.domain_description)
            _src_label = "DB" if _spec_source == "db" else "YAML"
            st.caption(f"Spec v{spec.version} · {_src_label}")
            st.divider()
            st.markdown("**Variables de decisión**")
            for dv in spec.decision_variables:
                st.markdown(
                    f"- `{dv.name}` · {dv.bounds_min}–{dv.bounds_max} {dv.unit}"
                )
            if spec.target_variables:
                st.markdown("**Objetivos**")
                for tv in spec.target_variables:
                    st.markdown(f"- `{tv.name}`")
            # Model info
            st.divider()
            st.markdown("**Modelo predictivo**")
            try:
                import pickle

                import pandas as pd

                _model_path = "models/demand_model.pkl"
                _data_path = "data/sales.csv"
                if os.path.exists(_model_path):
                    with open(_model_path, "rb") as _f:
                        _mdl = pickle.load(_f)
                    _model_type = type(_mdl).__name__
                    _n_feat = getattr(_mdl, "n_features_in_", 2)
                    _feat_str = f"{_n_feat} variables"
                    _r2_str = ""
                    if os.path.exists(_data_path):
                        _df = pd.read_csv(_data_path)
                        _n_rows = len(_df)
                        _feat_cols = ["price", "marketing"] + (
                            ["month"] if "month" in _df.columns and _n_feat >= 3 else []
                        )
                        _X = _df[_feat_cols].values
                        _y = _df["demand"].values
                        from sklearn.metrics import r2_score as _r2_fn

                        _r2 = _r2_fn(_y, _mdl.predict(_X))
                        _r2_str = f" · R²={_r2:.3f}"
                    else:
                        _n_rows = None
                    st.caption(f"`{_model_type}` · {_feat_str}{_r2_str}")
                    if _n_rows is not None:
                        st.caption(f"{_n_rows:,} muestras de entrenamiento")
                else:
                    st.caption("Modelo no entrenado")
            except Exception:  # noqa: BLE001
                st.caption("Info no disponible")
    except Exception:  # noqa: BLE001
        pass

    # --- Causal DAG ---
    with st.expander("DAG causal", expanded=False):
        try:
            G = _load_causal_graph()
            fig_dag = _dag_figure(G)
            st.plotly_chart(fig_dag, width="stretch", config={"displayModeBar": False})
        except Exception as e:  # noqa: BLE001
            st.warning(f"DAG no disponible: {e}")

    # --- Ayuda inmersiva ---
    with st.expander("ℹ️ ¿Cómo funciona esta demo?", expanded=False):
        st.markdown(
            "#### Datos del modelo\n"
            "Los datos que alimentan las respuestas provienen de un modelo de negocio "
            "definido en el spec. Este modelo describe las variables de decisión "
            "(precio, marketing), las relaciones causales entre ellas (el DAG), y los "
            "rangos válidos. Los datos de entrenamiento del modelo de demanda son "
            "sintéticos en esta demo.\n\n"
            "#### DAG causal\n"
            "El grafo dirigido acíclico (DAG) representa cómo unas variables afectan "
            "a otras en el negocio. Por ejemplo: el precio afecta a la demanda, la "
            "demanda afecta a los ingresos, y los ingresos junto con los costes "
            "determinan el beneficio. El agente recorre este grafo para razonar sobre "
            "el impacto de las decisiones.\n\n"
            "#### Simulación Monte Carlo\n"
            "Cuando el agente simula, ejecuta cientos de escenarios con variaciones "
            "aleatorias (ruido) para estimar la distribución de resultados posibles. "
            "Esto permite evaluar no solo el resultado esperado, sino también el "
            "riesgo (¿cuánto puedo perder en el peor caso?).\n\n"
            "#### Optimización\n"
            "El optimizador busca los valores de las variables de decisión que "
            "maximizan el objetivo (beneficio) dentro de los rangos permitidos. Prueba "
            "combinaciones de precio y marketing para encontrar el punto óptimo.\n\n"
            "#### Knowledge base\n"
            "El agente tiene acceso a una base de conocimiento con documentos sobre el "
            "dominio del negocio. Cuando la pregunta es conceptual o no requiere "
            "cálculo, consulta estos documentos para responder."
        )

    # --- Admin controls ---
    with st.expander("⚙️ Administración", expanded=False):
        st.caption("Acciones de mantenimiento del sistema")

        if st.button("Regenerar datos", use_container_width=True):
            with st.spinner("Generando datos sintéticos..."):
                try:
                    from data.generate_data import generate
                    from spec.spec_loader import reload_spec

                    reload_spec()  # flush singleton — pick up latest spec from DB
                    df_gen = generate()
                    n_rows = len(df_gen)
                    temporal = "month" in df_gen.columns
                    _mode = (
                        "con temporalidad"
                        if temporal
                        else "datos estáticos, sin temporalidad"
                    )
                    st.success(f"Generados {n_rows:,} registros ({_mode}).")
                except Exception as _e:  # noqa: BLE001
                    st.warning(f"Error al regenerar datos: {_e}")

        if st.button("Reentrenar modelo ML", use_container_width=True):
            with st.spinner(
                "Entrenando modelo de demanda... (puede tardar unos segundos)"
            ):
                try:
                    from agents.tools import reload_system_model
                    from models.train_demand_model import train
                    from spec.spec_loader import reload_spec

                    reload_spec()  # flush singleton — pick up latest spec from DB
                    train()
                    reload_system_model()
                    st.cache_resource.clear()
                    st.success("Modelo reentrenado y recargado correctamente.")
                    st.rerun()
                except Exception as _e:  # noqa: BLE001
                    st.warning(f"Error al reentrenar el modelo: {_e}")

        if st.button("Recargar knowledge base", use_container_width=True):
            with st.spinner("Construyendo índice de conocimiento..."):
                try:
                    from knowledge.build_index import DOCUMENTS, build_knowledge_index
                    from spec.spec_loader import reload_spec

                    reload_spec()  # flush singleton — pick up latest spec from DB
                    build_knowledge_index()
                    n_docs = len(DOCUMENTS)
                    st.success(f"Knowledge base recargada ({n_docs} documentos).")
                except Exception as _e:  # noqa: BLE001
                    st.warning(f"Error al recargar knowledge base: {_e}")

# ---------------------------------------------------------------------------
# Example queries for the welcome block
# ---------------------------------------------------------------------------

_EXAMPLE_QUERIES = [
    (
        "¿Qué precio maximiza el beneficio?",
        "Optimización — busca el valor óptimo explorando combinaciones de precio y marketing",  # noqa: E501
        "¿Cuál es la combinación óptima de precio y marketing para maximizar el beneficio?",  # noqa: E501
    ),
    (
        "Simula el impacto de fijar precio a 25€",
        "Simulación Monte Carlo — ejecuta 500 escenarios con incertidumbre para ver la distribución de resultados",  # noqa: E501
        "Simula el beneficio con precio 25 € y marketing en 8.000 €",
    ),
    (
        "¿Cómo afecta el marketing a la demanda?",
        "Consulta al modelo causal — recorre el DAG para explicar relaciones entre variables",  # noqa: E501
        "¿Cómo afecta el nivel de marketing a la demanda según el modelo causal?",
    ),
]

# ---------------------------------------------------------------------------
# Main area — persistent header + tabs
# ---------------------------------------------------------------------------

# Header: full when no conversation, compact when active
_LOGO_FULL = (
    '<span style="font-family: Georgia, serif; font-size: 52px; '
    'font-weight: 400; letter-spacing: -2px; line-height: 1;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
)
_LOGO_COMPACT = (
    '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">'
    '<span style="font-family: Georgia, serif; font-size: 26px; '
    'font-weight: 400; letter-spacing: -1px;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
    '<span style="font-size: 15px; color: #6b7280;">Decision Intelligence Agent</span>'
    "</div>"
)

if st.session_state.messages:
    st.markdown(_LOGO_COMPACT, unsafe_allow_html=True)
    st.caption("Tu consejero de decisiones de negocio.")
else:
    st.markdown(_LOGO_FULL, unsafe_allow_html=True)
    st.markdown(
        "**Tu consejero de decisiones de negocio.**  \n"
        "Analiza el impacto de tus decisiones comerciales antes de tomarlas."
    )

# Tab styles — override Streamlit defaults with !important for specificity
st.markdown(
    """
<style>
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: transparent !important;
}
.stTabs button[role="tab"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 10px 28px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #9ca3af !important;
}
.stTabs button[role="tab"]:hover {
    color: #374151 !important;
    background: rgba(108,142,245,0.06) !important;
}
.stTabs button[role="tab"][aria-selected="true"] {
    color: #111827 !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #6c8ef5 !important;
    height: 2px !important;
}
.stTabs [data-baseweb="tab-border"] {
    background-color: #e5e7eb !important;
    height: 1px !important;
}
</style>
""",
    unsafe_allow_html=True,
)

tab_chat, tab_dashboard = st.tabs(["Chat", "Dashboard"])

with tab_chat:
    # Welcome cards — hidden once conversation starts or a card query is pending
    if not st.session_state.messages and not st.session_state.get("_pending_query"):
        st.divider()
        col1, col2, col3 = st.columns(3)
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
                    st.session_state["_pending_query"] = query
                    st.rerun()
        st.divider()

    # Conversation history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(_sanitize_markdown(msg["content"]))
            if msg["role"] == "assistant" and msg.get("metadata"):
                meta = msg["metadata"]
                action = meta.get("action", "")
                raw_result = meta.get("raw_result", {})
                total_ms = meta.get("total_ms")
                tool_label = _TOOL_LABELS.get(action, f"⚪ {action}" if action else "")
                if tool_label and total_ms:
                    st.caption(f"{tool_label}  ·  {total_ms:,.0f} ms")
                elif total_ms:
                    st.caption(f"{total_ms:,.0f} ms")
                _render_result_cards(action, raw_result)
                _render_run_details(meta)

with tab_dashboard:
    _render_dashboard()

# ---------------------------------------------------------------------------
# Chat input and agent invocation (outside tabs — always accessible)
# ---------------------------------------------------------------------------

_SPINNER_STEPS = [
    "Analizando tu pregunta…",
    "Consultando el modelo causal…",
    "Generando respuesta…",
]

_chat_input = st.chat_input("Pregunta sobre tu negocio…")

# Pick up pending query from example cards, or use typed input
if "_pending_query" in st.session_state:
    prompt = st.session_state["_pending_query"]
    del st.session_state["_pending_query"]
elif _chat_input:
    prompt = _chat_input
else:
    prompt = None

if prompt:
    # Show user message immediately
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "metadata": None}
    )
    with st.chat_message("user"):
        st.markdown(prompt)

    # Invoke the agent with staged status messages
    with st.chat_message("assistant"):
        _status = st.empty()
        _status.caption(f"⏳ {_SPINNER_STEPS[0]}")

        observer: AgentObserver = st.session_state.observer
        run_id = observer.start_run(prompt)
        t0 = time.perf_counter()

        _status.caption(f"⏳ {_SPINNER_STEPS[1]}")

        try:
            cfg = observer.langsmith_config()
            cfg["configurable"]["observer"] = observer
            cfg["configurable"]["thread_id"] = st.session_state.session_id

            result = graph.invoke(
                {"query": prompt, "run_id": run_id},
                config=cfg,
            )

            _status.caption(f"⏳ {_SPINNER_STEPS[2]}")
            total_ms = (time.perf_counter() - t0) * 1000
            run_record = observer.end_run(success=True) or {}

            answer = result.get("answer") or "*(no answer generated)*"

            metadata: Dict[str, Any] = {
                "action": result.get("action"),
                "reasoning": result.get("reasoning"),
                "raw_result": result.get("raw_result") or {},
                "judge_score": result.get("judge_score"),
                "judge_passed": result.get("judge_passed"),
                "judge_revised": result.get("judge_revised"),
                "total_ms": total_ms,
                "latencies": {
                    "planner": run_record.get("planner_latency_ms"),
                    "tool": run_record.get("tool_latency_ms"),
                    "synthesizer": run_record.get("synthesizer_latency_ms"),
                    "judge": run_record.get("judge_latency_ms"),
                },
            }

            register_turn(
                st.session_state.session_id,
                prompt,
                is_new=st.session_state.is_new_session,
            )
            st.session_state.is_new_session = False

        except Exception as exc:  # noqa: BLE001
            answer = f"⚠️ El agente encontró un error: {exc}"
            metadata = {
                "action": "error",
                "raw_result": {},
                "reasoning": str(exc),
                "total_ms": (time.perf_counter() - t0) * 1000,
                "latencies": {},
            }
            observer.end_run(success=False, error=str(exc))

        _status.empty()

        # Answer text
        st.markdown(_sanitize_markdown(answer))

        # Badge: tool used + latency
        action = metadata.get("action", "")
        total_ms = metadata.get("total_ms")
        tool_label = _TOOL_LABELS.get(action, f"⚪ {action}" if action else "")
        if tool_label and total_ms:
            st.caption(f"{tool_label}  ·  {total_ms:,.0f} ms")
        elif total_ms:
            st.caption(f"{total_ms:,.0f} ms")

        # Result cards (direct, outside expander)
        raw_result = metadata.get("raw_result", {})
        _render_result_cards(action, raw_result)

        # Technical details (collapsed)
        _render_run_details(metadata)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "metadata": metadata}
    )
    st.rerun()
