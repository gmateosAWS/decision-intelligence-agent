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
        "decision": "Decision variable",
        "intermediate": "Intermediate",
        "target": "Target",
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
            name="Distribution",
            hovertemplate="Profit: %{x:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x[mask],
            y=y[mask],
            fill="tozeroy",
            mode="none",
            fillcolor="rgba(59,130,246,0.30)",
            name="P10–P90 range",
            hoverinfo="skip",
        )
    )
    fig.add_vline(
        x=mean,
        line=dict(color="#22c55e", width=2, dash="solid"),
        annotation_text=f"Mean {mean:,.0f}",
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
            title="Profit (EUR)", tickformat=",.0f", gridcolor="rgba(128,128,128,0.15)"
        ),
        yaxis=dict(showticklabels=False, gridcolor="rgba(128,128,128,0.1)"),
    )
    return fig


def _render_result_details(action: str, raw_result: Dict[str, Any]) -> None:
    """Render result visualizations inside an expander below the answer."""
    if not raw_result or action == "knowledge":
        return

    with st.expander("Results details", expanded=False):
        if action == "simulation":
            c1, c2, c3, c4 = st.columns(4)
            ep = raw_result.get("expected_profit")
            p10 = raw_result.get("profit_p10")
            p90 = raw_result.get("profit_p90")
            risk = raw_result.get("downside_risk_pct")
            if ep is not None:
                c1.metric("Expected profit", f"€{ep:,.0f}")
            if p10 is not None:
                c2.metric("P10 (pessimistic)", f"€{p10:,.0f}")
            if p90 is not None:
                c3.metric("P90 (optimistic)", f"€{p90:,.0f}")
            if risk is not None:
                c4.metric("Downside risk", f"{risk:.1f}%")

            st.plotly_chart(
                _simulation_figure(raw_result),
                width="stretch",
                config={"displayModeBar": False},
            )

            ed = raw_result.get("expected_demand")
            ds = raw_result.get("demand_std")
            nr = raw_result.get("n_runs")
            if ed is not None:
                extra = f"  ·  σ demand {ds:,.1f}" if ds is not None else ""
                nr_txt = f"  ·  {nr:,} simulation runs" if nr is not None else ""
                st.caption(f"Expected demand: {ed:,.1f} units{extra}{nr_txt}")

        elif action == "optimization":
            spec = get_spec()
            cols = st.columns(len(spec.decision_variables) + 1)
            for i, dv in enumerate(spec.decision_variables):
                val = raw_result.get(f"optimal_{dv.name}") or raw_result.get(dv.name)
                if val is not None:
                    cols[i].metric(f"Optimal {dv.name}", f"{val:,.2f} {dv.unit}")
            ep = raw_result.get("expected_profit")
            if ep is not None:
                cols[-1].metric("Expected profit", f"€{ep:,.0f}")

            risk = raw_result.get("downside_risk_pct")
            if risk is not None:
                st.caption(f"Downside risk at optimum: {risk:.1f}%")


def _render_run_details(metadata: Dict[str, Any]) -> None:
    """Collapsible expander with per-node latency and judge verdict."""
    action = metadata.get("action", "—")
    reasoning = metadata.get("reasoning", "")
    judge_score = metadata.get("judge_score")
    judge_passed = metadata.get("judge_passed")
    judge_revised = metadata.get("judge_revised")
    total_ms = metadata.get("total_ms")
    latencies = metadata.get("latencies", {})

    with st.expander("Run details", expanded=False):
        col1, col2 = st.columns([1, 2])
        with col1:
            _TOOL_COLOURS = {
                "optimization": "🟢",
                "simulation": "🔵",
                "knowledge": "🟣",
            }
            icon = _TOOL_COLOURS.get(action, "⚪")
            st.markdown(f"**Tool used:** {icon} `{action}`")
            if total_ms is not None:
                st.markdown(f"**Total latency:** `{total_ms:,.0f} ms`")
            if judge_score is not None:
                verdict = "✅ passed" if judge_passed else "✏️ revised"
                st.markdown(f"**Judge:** `{judge_score:.2f}` — {verdict}")
            elif judge_revised is not None:
                st.markdown(
                    f"**Judge:** {'✅ passed' if judge_passed else '✏️ revised'}"
                )

        with col2:
            if reasoning:
                st.markdown("**Planner reasoning:**")
                st.caption(reasoning)

        if latencies:
            lc = st.columns(len(latencies))
            for (node, ms), col in zip(latencies.items(), lc):
                if ms is not None:
                    col.metric(node.capitalize(), f"{ms:,.0f} ms")


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
graph, _checkpointer = _load_agent_graph()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

_spec_source = _seed_spec()  # idempotent — runs once per process

with st.sidebar:
    st.markdown("## ⚖️ llull")
    st.caption("Prototype v1 · Inverence")
    st.divider()

    # --- Session management ---
    st.subheader("Session")

    if st.button("＋ New session", use_container_width=True):
        _new_session()
        st.rerun()

    sessions = SessionManager.list_sessions()
    if sessions:
        # Build display labels; skip the current session
        opts = {}
        for s in sessions:
            label = f"{s['title'][:28]}…  ({s['turn_count']} turns)"
            opts[label] = s["session_id"]

        chosen_label = st.selectbox(
            "Resume a previous session",
            options=["— select —"] + list(opts.keys()),
            key="resume_selector",
        )
        if chosen_label != "— select —":
            if st.button("↩ Resume selected", use_container_width=True):
                _resume_session(opts[chosen_label])
                st.rerun()

    # Session info
    sid = st.session_state.session_id
    session_row = SessionManager.get_session(sid)
    if session_row:
        st.info(
            f"**`{sid[:8]}…`**  \n"
            f"Turns: {session_row['turn_count']}  \n"
            f"Active: {session_row['last_active'][:10]}"
        )
    else:
        st.info(f"**`{sid[:8]}…`**  \n*New — no turns yet*")

    st.divider()

    # --- LLM config ---
    with st.expander("LLM configuration", expanded=False):
        rows = [
            ("Planner", "PLANNER_PROVIDER", "PLANNER_MODEL"),
            ("Synthesizer", "SYNTHESIZER_PROVIDER", "SYNTHESIZER_MODEL"),
            ("Judge", "JUDGE_PROVIDER", "JUDGE_MODEL"),
        ]
        for node, pvar, mvar in rows:
            prov = os.getenv(pvar, "openai")
            model = os.getenv(mvar, "gpt-4o-mini")
            st.markdown(f"**{node}** · `{prov}` / `{model}`")
        fb_prov = os.getenv("FALLBACK_PROVIDER", "")
        fb_model = os.getenv("FALLBACK_MODEL", "")
        if fb_prov:
            st.caption(f"Fallback: `{fb_prov}` / `{fb_model}`")
        retries = os.getenv("LLM_MAX_RETRIES", "2")
        timeout = os.getenv("LLM_TIMEOUT", "30")
        st.caption(f"Retries: {retries} · Timeout: {timeout}s")

    # --- Domain info ---
    try:
        spec = get_spec()
        with st.expander("Domain", expanded=False):
            st.markdown(f"**{spec.domain_name}**")
            st.caption(spec.domain_description)
            _src_label = "DB" if _spec_source == "db" else "YAML"
            st.caption(f"Spec v{spec.version} · source: {_src_label}")
            st.markdown(
                f"- {len(spec.decision_variables)} decision variables  \n"
                f"- {len(spec.intermediate_variables)} intermediate  \n"
                f"- {len(spec.target_variables)} target"
            )
            for dv in spec.decision_variables:
                st.caption(f"`{dv.name}` [{dv.bounds_min}–{dv.bounds_max} {dv.unit}]")
    except Exception:  # noqa: BLE001
        pass

    # --- Causal DAG ---
    with st.expander("Causal DAG", expanded=False):
        try:
            G = _load_causal_graph()
            fig_dag = _dag_figure(G)
            st.plotly_chart(fig_dag, width="stretch", config={"displayModeBar": False})
        except Exception as e:  # noqa: BLE001
            st.warning(f"DAG unavailable: {e}")

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

st.title("llull — Decision Intelligence Agent")
st.caption("Ask business questions about pricing, marketing, and profitability.")

# Render conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("metadata"):
            meta = msg["metadata"]
            action = meta.get("action", "")
            raw_result = meta.get("raw_result", {})
            _render_result_details(action, raw_result)
            _render_run_details(meta)

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask a business question…"):
    # Show user message immediately
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "metadata": None}
    )
    with st.chat_message("user"):
        st.markdown(prompt)

    # Invoke the agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            observer: AgentObserver = st.session_state.observer
            run_id = observer.start_run(prompt)
            t0 = time.perf_counter()

            try:
                cfg = observer.langsmith_config()
                cfg["configurable"]["observer"] = observer
                cfg["configurable"]["thread_id"] = st.session_state.session_id

                result = graph.invoke(
                    {"query": prompt, "run_id": run_id},
                    config=cfg,
                )

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
                answer = f"⚠️ The agent encountered an error: {exc}"
                metadata = {
                    "action": "error",
                    "raw_result": {},
                    "reasoning": str(exc),
                    "total_ms": (time.perf_counter() - t0) * 1000,
                    "latencies": {},
                }
                observer.end_run(success=False, error=str(exc))

        st.markdown(answer)
        action = metadata.get("action", "")
        raw_result = metadata.get("raw_result", {})
        _render_result_details(action, raw_result)
        _render_run_details(metadata)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "metadata": metadata}
    )
