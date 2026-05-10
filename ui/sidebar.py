"""
ui/sidebar.py
--------------
Full sidebar including session management, LLM config, domain info, causal
DAG, help, and admin controls.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from ui.styles import LOGO_SIDEBAR


def render_sidebar(
    spec_source: str,
    graph: Any,
    session_id: str,
    messages: List[Dict],
    on_new_session: Any,
    on_resume_session: Any,
) -> None:
    """
    Render the complete sidebar.

    Parameters
    ----------
    spec_source      : "db" or "yaml" — shown in the Dominio expander.
    graph            : Compiled LangGraph graph (used for session resume).
    session_id       : Current session UUID string.
    messages         : Current session messages list (for session info).
    on_new_session   : Zero-arg callable to trigger a new session.
    on_resume_session: Callable(session_id: str) to restore an old session.
    """
    with st.sidebar:
        st.markdown(LOGO_SIDEBAR, unsafe_allow_html=True)
        st.markdown("**llull**")
        st.caption("Inverence")

        if st.button("Inicio", use_container_width=True, type="secondary"):
            on_new_session()
            st.rerun()

        st.divider()

        # --- Session management ---
        st.subheader("Sesión")

        if st.button("＋ Nueva sesión", use_container_width=True):
            on_new_session()
            st.rerun()

        from memory import SessionManager

        sessions = SessionManager.list_sessions()
        if sessions:
            opts: Dict[str, str] = {}
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
                    on_resume_session(opts[chosen_label])
                    st.rerun()

        session_row = SessionManager.get_session(session_id)
        if session_row:
            st.info(
                f"**`{session_id[:8]}…`**  \n"
                f"Turnos: {session_row['turn_count']}  \n"
                f"Activa: {session_row['last_active'][:10]}"
            )
        else:
            st.info(f"**`{session_id[:8]}…`**  \n*Nueva — sin turnos aún*")

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
                ),
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
            from spec.spec_loader import get_spec

            spec = get_spec()
            with st.expander("Dominio", expanded=False):
                st.markdown(f"**{spec.domain_name}**")
                st.caption(spec.domain_description)
                _src_label = "DB" if spec_source == "db" else "YAML"
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
                st.divider()
                st.markdown("**Modelo predictivo**")
                _render_model_info()
        except Exception:  # noqa: BLE001
            pass

        # --- Causal DAG ---
        with st.expander("DAG causal", expanded=False):
            try:
                from system.system_graph import build_graph as build_causal_graph

                G = build_causal_graph()
                fig_dag = _dag_figure(G)
                st.plotly_chart(
                    fig_dag, use_container_width=True, config={"displayModeBar": False}
                )
            except Exception as e:  # noqa: BLE001
                st.warning(f"DAG no disponible: {e}")

        # --- Help ---
        with st.expander("ℹ️ ¿Cómo funciona esta demo?", expanded=False):
            st.markdown(
                "#### Datos del modelo\n"
                "Los datos provienen de un modelo de negocio definido en el spec. "
                "Describe variables de decisión (precio, marketing), las relaciones "
                "causales entre ellas (el DAG) y los rangos válidos. Los datos de "
                "entrenamiento del modelo de demanda son sintéticos en esta demo.\n\n"
                "#### DAG causal\n"
                "El grafo dirigido acíclico (DAG) representa cómo unas variables "
                "afectan a otras en el negocio. El agente recorre este grafo para "
                "razonar sobre el impacto de las decisiones.\n\n"
                "#### Simulación Monte Carlo\n"
                "Cuando el agente simula, ejecuta cientos de escenarios aleatorios "
                "para estimar la distribución de resultados posibles. "
                "Permite evaluar el riesgo (¿cuánto puedo perder en el peor caso?).\n\n"
                "#### Optimización\n"
                "El optimizador busca los valores de las variables de decisión que "
                "maximizan el objetivo (beneficio) dentro de los rangos permitidos.\n\n"
                "#### Knowledge base\n"
                "El agente accede a una base de conocimiento con documentos sobre el "
                "dominio del negocio. Cuando la pregunta es conceptual, consulta "
                "estos documentos para responder."
            )

        # --- Admin controls ---
        with st.expander("⚙️ Administración", expanded=False):
            st.caption("Acciones de mantenimiento del sistema")
            render_admin_controls()


# ---------------------------------------------------------------------------
# Admin controls (extracted for testability)
# ---------------------------------------------------------------------------


def render_admin_controls() -> None:
    """Render the admin action buttons and handle clicks."""
    if st.button("Regenerar datos", use_container_width=True):
        with st.spinner("Generando datos sintéticos..."):
            try:
                from data.generate_data import generate
                from spec.spec_loader import reload_spec

                reload_spec()
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
        with st.spinner("Entrenando modelo de demanda... (puede tardar unos segundos)"):
            try:
                from agents.tools import reload_system_model
                from models.train_demand_model import train
                from spec.spec_loader import reload_spec

                reload_spec()
                train()
                reload_system_model()
                st.success("Modelo reentrenado y recargado correctamente.")
                st.rerun()
            except Exception as _e:  # noqa: BLE001
                st.warning(f"Error al reentrenar el modelo: {_e}")

    if st.button("Recargar knowledge base", use_container_width=True):
        with st.spinner("Construyendo índice de conocimiento..."):
            try:
                from knowledge.build_index import DOCUMENTS, build_knowledge_index
                from spec.spec_loader import reload_spec

                reload_spec()
                build_knowledge_index()
                n_docs = len(DOCUMENTS)
                st.success(f"Knowledge base recargada ({n_docs} documentos).")
            except Exception as _e:  # noqa: BLE001
                st.warning(f"Error al recargar knowledge base: {_e}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _render_model_info() -> None:
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


def _dag_figure(G: nx.DiGraph) -> go.Figure:
    from spec.spec_loader import get_spec

    spec = get_spec()
    decision_names = {v.name for v in spec.decision_variables}
    target_names = {v.name for v in spec.target_variables}

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
