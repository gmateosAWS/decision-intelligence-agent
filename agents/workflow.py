"""
agents/workflow.py
------------------
LangGraph 3-node workflow with integrated observability.

Graph:  planner_node → tool_node → synthesizer_node → END

Observability integration
-------------------------
The caller passes an AgentObserver via LangGraph's configurable dict:

    config = observer.langsmith_config()
    config["configurable"]["observer"] = observer
    graph.invoke({"query": query, "run_id": run_id}, config=config)

Each node reads the observer from config and calls the appropriate
record_* method.  The observer is optional: if absent, the graph runs
normally without any observability overhead.

LangSmith tracing
-----------------
Automatic when LANGCHAIN_TRACING_V2=true is set.  The run_name and tags
injected via observer.langsmith_config() make every invocation appear
with a meaningful name in the LangSmith UI.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from .planner import planner_node as _planner_node_impl
from .state import AgentState
from .tools import knowledge_tool, optimization_tool, simulation_tool

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

_TOOLS: Dict[str, Any] = {
    "optimization": optimization_tool,
    "simulation": simulation_tool,
    "knowledge": knowledge_tool,
}


# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------


def planner_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict:
    """
    Calls the LLM planner (structured output) and records timing via the observer.
    Returns: {action, reasoning}
    """
    obs = _get_observer(config)

    t0 = time.perf_counter()
    result = _planner_node_impl(state)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if obs:
        obs.record_planner(
            action=result.get("action", "knowledge"),
            reasoning=result.get("reasoning", ""),
            latency_ms=elapsed_ms,
        )
    return result


def tool_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict:
    """
    Executes the tool selected by the planner.
    Wraps execution in try/except so errors surface in the state
    rather than crashing the graph.
    Returns: {raw_result}
    """
    obs = _get_observer(config)
    action = state.get("action", "knowledge")
    tool_fn = _TOOLS.get(action, knowledge_tool)

    t0 = time.perf_counter()
    raw_result: Optional[Dict] = None
    error: Optional[str] = None

    try:
        raw_result = tool_fn(state)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        raw_result = {"error": error}

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if obs:
        obs.record_tool(
            tool_name=action,
            result=raw_result,
            latency_ms=elapsed_ms,
            error=error,
        )
    return {"raw_result": raw_result}


def synthesizer_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> Dict:
    """
    Uses the LLM to convert the raw tool output into a business-oriented
    natural-language answer.
    Returns: {answer}
    """
    from langchain_openai import ChatOpenAI

    obs = _get_observer(config)
    query = state.get("query", "")
    action = state.get("action", "unknown")
    raw = state.get("raw_result") or {}

    # Build a focused prompt from the raw result
    raw_text = "\n".join(f"  {k}: {v}" for k, v in raw.items())
    prompt = (
        "You are a business intelligence assistant.\n\n"
        f"The user asked: {query}\n\n"
        f"The {action} tool returned:\n{raw_text}\n\n"
        "Provide a clear, concise business interpretation:\n"
        "- What do the numbers mean?\n"
        "- What action should the decision-maker take?\n"
        "- What risks or caveats are relevant?\n"
        "Answer in 3-5 sentences. Be specific and quantitative."
    )

    t0 = time.perf_counter()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    try:
        response = llm.invoke(prompt)
        answer = response.content.strip()
    except Exception as exc:  # noqa: BLE001
        answer = f"[Synthesizer error: {exc}]\n\nRaw result:\n{raw_text}"

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if obs:
        obs.record_synthesizer(answer=answer, latency_ms=elapsed_ms)

    return {"answer": answer}


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """
    Build and compile the 3-node LangGraph workflow.

    Flow:
        planner_node → tool_node → synthesizer_node → END
    """
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("tool", tool_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "tool")
    builder.add_edge("tool", "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Private
# ---------------------------------------------------------------------------


def _get_observer(config: Optional[RunnableConfig]):
    """Extract the AgentObserver from the LangGraph configurable dict (if present)."""
    if config is None:
        return None
    return config.get("configurable", {}).get("observer")
