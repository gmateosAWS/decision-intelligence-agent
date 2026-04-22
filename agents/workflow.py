"""
agents/workflow.py
------------------
LangGraph workflow for the Decision Intelligence Agent.

Defines the four pipeline nodes and compiles them into a directed graph:

    planner_node → tool_node → synthesizer_node → judge_node → END

Nodes
-----
- ``planner_node``    -- wraps the LLM planner; records timing via observer.
- ``tool_node``       -- dispatches to the tool selected by the planner
                         (optimization / simulation / knowledge); errors are
                         captured and propagated in state rather than raised.
- ``synthesizer_node``-- converts raw tool output into a business-oriented
                         draft answer using an LLM (``SYNTHESIZER_MODEL``).
- ``judge_node``      -- delegates to ``agents/judge.py`` for online quality
                         evaluation and optional single-pass revision.

``build_graph(checkpointer=None)`` compiles the graph with optional SQLite
persistence: when a checkpointer is provided, LangGraph writes partial state
after each node and can resume a thread by ``thread_id``.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from .judge import judge_node as _judge_node_impl
from .llm_factory import LLMUnavailableError, get_chat_model, invoke_with_fallback
from .planner import planner_node as _planner_node_impl
from .state import AgentState
from .tools import knowledge_tool, optimization_tool, simulation_tool

load_dotenv()

_PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
_SYNTHESIZER_PROVIDER = os.getenv("SYNTHESIZER_PROVIDER", "openai")
_SYNTHESIZER_MODEL = os.getenv("SYNTHESIZER_MODEL", "gpt-4o-mini")
_FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "")
_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

_synthesizer_llm = get_chat_model(
    _SYNTHESIZER_PROVIDER, _SYNTHESIZER_MODEL, temperature=0.2
)
_synthesizer_fallback_llm = (
    get_chat_model(_FALLBACK_PROVIDER, _FALLBACK_MODEL, temperature=0.2)
    if _FALLBACK_PROVIDER and _FALLBACK_MODEL
    else None
)

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
    result = _sanitize_for_state(_planner_node_impl(state))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if obs:
        obs.record_planner(
            action=result.get("action", "knowledge"),
            reasoning=result.get("reasoning", ""),
            latency_ms=elapsed_ms,
            model=_PLANNER_MODEL,
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
        raw_result = _sanitize_for_state(tool_fn(state))
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

    obs = _get_observer(config)
    query = state.get("query", "")
    action = state.get("action", "unknown")
    raw = _sanitize_for_state(state.get("raw_result") or {})

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
    try:
        response = invoke_with_fallback(
            _synthesizer_llm,
            prompt,
            fallback=_synthesizer_fallback_llm,
        )
        answer = response.content.strip()
    except (LLMUnavailableError, Exception):  # noqa: BLE001
        answer = (
            "The synthesis service is temporarily unavailable. "
            f"Raw result:\n{raw_text}"
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if obs:
        obs.record_synthesizer(
            answer=answer, latency_ms=elapsed_ms, model=_SYNTHESIZER_MODEL
        )

    return _sanitize_for_state({"answer": answer})


def judge_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> Dict:
    """Evaluate and optionally revise the synthesized answer."""
    return _sanitize_for_state(_judge_node_impl(state, config))


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


def _sanitize_for_state(value: Any) -> Any:
    """Convert NumPy and other non-msgpack-friendly values to plain Python."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _sanitize_for_state(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_state(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _sanitize_for_state(item_method())
        except Exception:  # noqa: BLE001
            pass

    tolist_method = getattr(value, "tolist", None)
    if callable(tolist_method):
        try:
            return _sanitize_for_state(tolist_method())
        except Exception:  # noqa: BLE001
            pass

    return str(value)


def _get_observer(config: Optional[RunnableConfig]):
    """Extract the AgentObserver from the configurable dict."""
    if config is None:
        return None
    return config.get("configurable", {}).get("observer")
