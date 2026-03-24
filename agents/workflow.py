"""
agents/workflow.py  – Mejora 3
--------------------------------
Cambios respecto a Mejora 2:
  • build_graph() ahora acepta un checkpointer opcional (SqliteSaver).
    Si se pasa, el grafo se compila con persistencia: cada nodo escribe
    su estado parcial y LangGraph puede reanudar hilos por thread_id.
  • synthesizer_node devuelve un borrador de respuesta.
  • judge_node evalúa online la respuesta final, la aprueba o la revisa
    una vez antes de devolverla al usuario.
  • El historial se añade solo después del juez, para persistir la versión
    final y no el borrador previo.

Graph:  planner_node → tool_node → synthesizer_node → judge_node → END
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from .judge import judge_node as _judge_node_impl
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


def planner_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> Dict:
    """Calls the LLM planner and records timing via the observer."""
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


def tool_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> Dict:
    """Executes the tool selected by the planner."""
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
    Converts the raw tool output into a business-oriented answer.

    The answer is judged in a later node before it is appended to history,
    so this node only returns the synthesized draft answer.
    """
    from langchain_openai import ChatOpenAI

    obs = _get_observer(config)
    query = state.get("query", "")
    action = state.get("action", "unknown")
    raw = state.get("raw_result") or {}

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


def judge_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> Dict:
    """Evaluate and optionally revise the synthesized answer."""
    return _judge_node_impl(state, config)


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_graph(checkpointer=None):
    """
    Build and compile the 4-node LangGraph workflow.

    Parameters
    ----------
    checkpointer : SqliteSaver | None
        If provided, the graph persists state across invocations.
        Pass a thread_id in the config to resume a conversation.

    Flow:
        planner_node → tool_node → synthesizer_node → judge_node → END
    """
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("tool", tool_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("judge", judge_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "tool")
    builder.add_edge("tool", "synthesizer")
    builder.add_edge("synthesizer", "judge")
    builder.add_edge("judge", END)

    if checkpointer is not None:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()


# ---------------------------------------------------------------------------
# Private
# ---------------------------------------------------------------------------


def _get_observer(config: Optional[RunnableConfig]):
    """Extract the AgentObserver from the configurable dict."""
    if config is None:
        return None
    return config.get("configurable", {}).get("observer")
