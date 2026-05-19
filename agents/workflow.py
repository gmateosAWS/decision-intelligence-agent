"""
agents/workflow.py
------------------
LangGraph workflow for the Decision Intelligence Agent.

Defines the pipeline nodes and compiles them into a directed graph:

    planner_node → [proactive_gate] → tool_node → synthesizer_node → judge_node → END

Nodes
-----
- ``planner_node``              -- wraps the LLM planner; records timing via observer.
- ``proactive_confirmation_gate``-- pauses flow when structural signals fire for an
                                    expensive tool (item 5.13). Returns a StateProposal
                                    to the client instead of executing the tool.
- ``tool_node``                 -- dispatches to the tool selected by the planner
                                    (optimization / simulation / knowledge); errors are
                                    captured and propagated in state rather than raised.
- ``synthesizer_node``          -- converts raw tool output into a business-oriented
                                    draft answer using an LLM (``SYNTHESIZER_MODEL``).
- ``judge_node``                -- delegates to ``agents/judge.py`` for online quality
                                    evaluation and optional single-pass revision.
- ``clarification_node``        -- vocabulary clarification message (item 5.9).

``build_graph(checkpointer=None)`` compiles the graph with optional SQLite
persistence: when a checkpointer is provided, LangGraph writes partial state
after each node and can resume a thread by ``thread_id``.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from prompts.registry import SYNTHESIZER_SYSTEM_TEMPLATE, get_prompt_template

from .i18n import get_synth_instructions, get_system_language_directive
from .judge import judge_node as _judge_node_impl
from .llm_factory import LLMUnavailableError, get_chat_model, invoke_with_fallback
from .planner import planner_node as _planner_node_impl
from .state import AgentState
from .tools import knowledge_tool, optimization_tool, simulation_tool

load_dotenv()

logger = logging.getLogger(__name__)

_PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gpt-4o-mini")
_SYNTHESIZER_PROVIDER = os.getenv("SYNTHESIZER_PROVIDER", "openai")
_SYNTHESIZER_MODEL = os.getenv("SYNTHESIZER_MODEL", "gpt-4o-mini")
_FALLBACK_PROVIDER = os.getenv("FALLBACK_PROVIDER", "")
_FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "")

_synthesizer_llm = None
_synthesizer_fallback_llm = None


def _get_synthesizer_llms() -> tuple[Any, Any]:
    global _synthesizer_llm, _synthesizer_fallback_llm
    if _synthesizer_llm is None:
        _synthesizer_llm = get_chat_model(
            _SYNTHESIZER_PROVIDER, _SYNTHESIZER_MODEL, temperature=0.2
        )
        if _FALLBACK_PROVIDER and _FALLBACK_MODEL:
            _synthesizer_fallback_llm = get_chat_model(
                _FALLBACK_PROVIDER, _FALLBACK_MODEL, temperature=0.2
            )
    return _synthesizer_llm, _synthesizer_fallback_llm


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

_TOOLS: Dict[str, Any] = {
    "optimization": optimization_tool,
    "simulation": simulation_tool,
    "knowledge": knowledge_tool,
}

# Deterministic mapping from a known user-corrected Intent to the tool action string.
# Used by the planner bypass when bypass_gate=True (item 5.13.c / R5 fix).
# Raise ValueError on unknown variant so new Intent values are caught at dev time.
from memory import Intent as _Intent  # noqa: E402

_INTENT_TO_ACTION: Dict[_Intent, str] = {
    _Intent.OPTIMIZE: "optimization",
    _Intent.SIMULATE: "simulation",
    _Intent.EXPLAIN: "knowledge",
    _Intent.EXPLORE: "knowledge",
}


# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------


def planner_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """Calls the LLM planner and records timing via the observer."""
    obs = _get_observer(config)
    tracker = _get_tracker(config)
    memory = _get_memory_service(config)
    session_id = _get_session_id(config)

    # Read typed state before planning so planner can use it as context (item 5.11).
    active_state = None
    if memory is not None and session_id is not None:
        try:
            active_state = memory.get_active_state(session_id)
        except Exception:  # noqa: BLE001
            pass

    session_id_str = _session_id_as_str(config)
    t0 = time.perf_counter()

    # Deterministic bypass when resuming after a gate confirmation with a known intent.
    # Skips the LLM entirely to honour the user-corrected intent (R5 fix, 5.13.c).
    _blocked_mutations: list[dict[str, Any]] = []
    if (
        state.get("bypass_gate")
        and active_state is not None
        and active_state.intent is not None
    ):
        _action = _INTENT_TO_ACTION.get(active_state.intent)
        if _action is None:
            raise ValueError(
                f"No _INTENT_TO_ACTION mapping for intent {active_state.intent!r}"
            )
        result: dict[str, Any] = _sanitize_for_state(
            {
                "action": _action,
                "reasoning": (
                    f"bypass_gate: intent={active_state.intent.value} → {_action}"
                ),
                "params": state.get("params") or {},
                "planner_prompt_version": None,
                "planner_variant_label": "bypass_gate",
            }
        )
    else:
        result = _sanitize_for_state(
            _planner_node_impl(
                state,
                tracker=tracker,
                active_state=active_state,
                session_id=session_id_str,
            )
        )
        # B2 fix: enforce frozen intent after the LLM has run.
        # If the user pinned intent to X but the LLM chose a different action,
        # override the action to preserve the frozen intent. The LLM output is
        # still used for notification (blocked_value = what LLM would have done).
        if (
            active_state is not None
            and "intent" in active_state.frozen_slots
            and active_state.intent is not None
        ):
            _frozen_action = _INTENT_TO_ACTION.get(active_state.intent)
            _llm_action = result.get("action")
            if _frozen_action and _llm_action != _frozen_action:
                if obs:
                    obs.record_freeze_block(
                        slot="intent",
                        attempted=_llm_action,
                        frozen=active_state.intent.value,
                        source="planner",
                    )
                _blocked_mutations.append(
                    {
                        "slot": "intent",
                        "blocked_value": _llm_action,
                        "current_value": active_state.intent.value,
                        "reason": "frozen_by_user",
                        "source": "planner",
                    }
                )
                result["action"] = _frozen_action

    elapsed_ms = (time.perf_counter() - t0) * 1000
    if obs:
        obs.record_planner(
            action=result.get("action", "knowledge"),
            reasoning=result.get("reasoning", ""),
            latency_ms=elapsed_ms,
            model=_PLANNER_MODEL,
            prompt_version=result.get("planner_prompt_version"),
            variant_label=result.get("planner_variant_label"),
        )
    # Record tool selection in analytical state — fail-open (item 5.11).
    # Intent-frozen sessions: record_tool_selection will call set_intent which
    # calls _mutate — the coordinator silently returns for frozen slots, so
    # memory is consistent. No double-block logged because attempt_mutation
    # identity check returns MutationApplied when value == current.
    if memory is not None and session_id is not None:
        try:
            current = memory.get_active_state(session_id)
            next_turn = current.last_turn_id + 1
            memory.record_tool_selection(
                session_id=session_id,
                tool=result.get("action", "knowledge"),
                turn_id=next_turn,
                cause="planner:tool_selection",
                evidence=result.get("reasoning", "")[:200],
            )
        except Exception:  # noqa: BLE001
            pass
    if _blocked_mutations:
        result["blocked_mutations"] = _blocked_mutations
    return result


def tool_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """Executes the tool selected by the planner."""
    obs = _get_observer(config)
    action: str = state.get("action") or "knowledge"
    tool_fn = _TOOLS.get(action, knowledge_tool)

    t0 = time.perf_counter()
    raw_result: Optional[dict[str, Any]] = None
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
    # Record active run via MemoryService — fail-open (item 5.11).
    memory = _get_memory_service(config)
    session_id = _get_session_id(config)
    if memory is not None and session_id is not None and not error:
        try:
            run_id = state.get("run_id") or ""
            turn_id = memory.get_active_state(session_id).last_turn_id
            memory.record_active_run(
                session_id=session_id,
                tool=action,
                run_id=run_id,
                turn_id=turn_id,
                cause=f"tool:{action}",
            )
        except Exception:  # noqa: BLE001
            pass
    return {"raw_result": raw_result}


def synthesizer_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """
    Converts the raw tool output into a business-oriented answer.

    The answer is judged in a later node before it is appended to history,
    so this node only returns the synthesized draft answer.
    """

    # When autonomy policy requires human intervention, skip tool synthesis
    if state.get("requires_confirmation") or state.get("requires_approval"):
        answer = state.get("confirmation_message") or (
            "Human review required before this action can be executed."
        )
        return {"answer": answer}

    obs = _get_observer(config)
    query = state.get("query", "")
    action = state.get("action", "unknown")
    language = state.get("language", "en")
    raw = _sanitize_for_state(state.get("raw_result") or {})

    session_id_str = _session_id_as_str(config)
    raw_text = "\n".join(f"  {k}: {v}" for k, v in raw.items())
    synth_template, synth_version, synth_variant_label = get_prompt_template(
        "synthesizer", SYNTHESIZER_SYSTEM_TEMPLATE, session_id=session_id_str
    )
    messages = [
        {
            "role": "system",
            "content": synth_template.format(
                language_directive=get_system_language_directive(language)
            ),
        },
        {
            "role": "user",
            "content": (
                f"User query: {query}\n\n"
                f"Tool used: {action}\n"
                f"Tool output:\n{raw_text}\n\n"
                f"{get_synth_instructions(language)}"
            ),
        },
    ]

    _syn_llm, _syn_fallback = _get_synthesizer_llms()
    tracker = _get_tracker(config)
    t0 = time.perf_counter()
    try:
        response = invoke_with_fallback(
            _syn_llm,
            messages,
            fallback=_syn_fallback,
            tracker=tracker,
            model=_SYNTHESIZER_MODEL,
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
            answer=answer,
            latency_ms=elapsed_ms,
            model=_SYNTHESIZER_MODEL,
            prompt_version=synth_version,
            variant_label=synth_variant_label,
        )

    raw = {
        "answer": answer,
        "synthesizer_prompt_version": synth_version,
        "synthesizer_variant_label": synth_variant_label,
    }
    sanitized: dict[str, Any] = _sanitize_for_state(raw)
    return sanitized


def judge_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """Evaluate and optionally revise the synthesized answer."""
    sanitized: dict[str, Any] = _sanitize_for_state(_judge_node_impl(state, config))
    return sanitized


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def proactive_confirmation_gate(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """Proactive-gate node (item 5.13).

    Generates a StateProposal when structural signals fire for an expensive tool,
    stores it in AgentState as a JSON-serialisable dict, and sets
    `awaiting_user_confirmation=True` so the runner returns early to the client.
    The client must POST /proposals → /commits to resume.
    """
    from core.protocols.memory import ProposalSource, SlotProposal  # noqa: PLC0415
    from memory.proactive_confirmation import (  # noqa: PLC0415
        should_request_confirmation,
    )

    action: str = state.get("action") or "knowledge"
    query: str = state.get("query", "")
    params: dict[str, Any] = state.get("params") or {}
    is_first_session_turn: bool = not state.get("has_prior_turns", False)

    should_pause, triggered = should_request_confirmation(
        tool=action,
        query=query,
        params=params,
        is_first_session_turn=is_first_session_turn,
    )
    if not should_pause:
        return {}

    memory = _get_memory_service(config)
    session_id = _get_session_id(config)

    # Mutations: intent (applied by commit) + params (UI display, no-op in service).
    from memory import map_tool_to_intent  # noqa: PLC0415

    proposed_intent = map_tool_to_intent(action)
    pending_mutations: list[SlotProposal] = [
        SlotProposal(
            slot="intent",
            current_value=None,
            proposed_value=proposed_intent.value,
            reason=f"Planner selected '{action}' tool. Committing this proposal "
            "will record the intent in analytical state.",
        ),
        SlotProposal(
            slot="params",
            current_value=params,
            proposed_value=params,
            reason=f"Parameters for '{action}' tool. Inspect before confirming.",
        ),
    ]

    proposal_dict: dict[str, Any] = {}
    if memory is not None and session_id is not None:
        try:
            active = memory.get_active_state(session_id)
            turn_id = active.last_turn_id + 1
            proposal = memory.propose_state_update(
                session_id=session_id,
                turn_id=turn_id,
                source=ProposalSource.PROACTIVE_PLANNER,
                pending_mutations=pending_mutations,
                original_query=query,
            )
            import dataclasses  # noqa: PLC0415
            import json  # noqa: PLC0415

            proposal_dict = json.loads(
                json.dumps(dataclasses.asdict(proposal), default=str)
            )
            proposal_dict["triggered_signals"] = triggered
        except Exception:  # noqa: BLE001
            # Fall-back: build a minimal dict without DB persistence

            proposal_dict = {
                "session_id": str(session_id) if session_id else "",
                "turn_id": 0,
                "source": ProposalSource.PROACTIVE_PLANNER.value,
                "mutations": (
                    [dataclasses.asdict(m) for m in pending_mutations]
                    if "dataclasses" in dir()
                    else []
                ),
                "triggered_signals": triggered,
            }
    else:
        proposal_dict = {
            "session_id": "",
            "turn_id": 0,
            "source": ProposalSource.PROACTIVE_PLANNER.value,
            "mutations": [],
            "triggered_signals": triggered,
        }

    return {
        "awaiting_user_confirmation": True,
        "proposal": proposal_dict,
    }


def _route_after_planner(state: AgentState) -> str:
    """Route after planner: clarification > proactive gate > autonomy policy > tool."""
    if state.get("clarification_needed"):
        return "clarification"
    # bypass_gate=True: user confirmed via UI/API, skip the proactive check.
    if not state.get("bypass_gate", False):
        # Proactive gate: check if expensive tool + signals warrant pausing.
        from memory.proactive_confirmation import (  # noqa: PLC0415
            should_request_confirmation,
        )

        action: str = state.get("action") or "knowledge"
        query: str = state.get("query", "")
        params: dict[str, Any] = state.get("params") or {}
        is_first: bool = not state.get("has_prior_turns", False)
        should_pause, _ = should_request_confirmation(
            tool=action,
            query=query,
            params=params,
            is_first_session_turn=is_first,
        )
        if should_pause:
            return "proactive_confirmation_gate"
    if state.get("requires_confirmation") or state.get("requires_approval"):
        return "synthesizer"
    return "tool"


def clarification_node(
    state: AgentState,
    config: Optional[RunnableConfig] = None,
) -> dict[str, Any]:
    """
    Return the clarification message as the final answer (item 5.9).

    Reached when planner catches an UngroundedTokenError.  No tool is run;
    the agent asks the user to rephrase using valid vocabulary.
    """
    query = state.get("query", "")
    message = state.get("clarification_message") or (
        "I could not identify the variable you mentioned. "
        "Please use a variable name from the domain model."
    )
    return {
        "answer": message,
        "history": [{"query": query, "answer": message}],
    }


def build_graph(checkpointer: Any = None) -> Any:
    """
    Build and compile the 6-node LangGraph workflow.

    Parameters
    ----------
    checkpointer : SqliteSaver | None
        If provided, the graph persists state across invocations.
        Pass a thread_id in the config to resume a conversation.

    Flow (auto):          planner → tool → synthesizer → judge → END
    Flow (policy):        planner → synthesizer → judge → END
    Flow (clarification): planner → clarification → END  (item 5.9)
    Flow (proactive):     planner → proactive_gate → END  (item 5.13)
    """
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("proactive_confirmation_gate", proactive_confirmation_gate)
    builder.add_node("tool", tool_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("judge", judge_node)
    builder.add_node("clarification", clarification_node)

    builder.set_entry_point("planner")
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {
            "tool": "tool",
            "synthesizer": "synthesizer",
            "clarification": "clarification",
            "proactive_confirmation_gate": "proactive_confirmation_gate",
        },
    )
    builder.add_edge("proactive_confirmation_gate", END)
    builder.add_edge("tool", "synthesizer")
    builder.add_edge("synthesizer", "judge")
    builder.add_edge("judge", END)
    builder.add_edge("clarification", END)

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


def _get_observer(config: Optional[RunnableConfig]) -> Any:
    """Extract the AgentObserver from the configurable dict."""
    if config is None:
        return None
    return config.get("configurable", {}).get("observer")


def _get_tracker(config: Optional[RunnableConfig]) -> Any:
    """Extract the BudgetTracker from the configurable dict."""
    if config is None:
        return None
    return config.get("configurable", {}).get("budget_tracker")


def _get_memory_service(config: Optional[RunnableConfig]) -> Any:
    """Extract the LocalMemoryService from the configurable dict (item 5.11)."""
    if config is None:
        return None
    return config.get("configurable", {}).get("memory_service")


def _get_session_id(config: Optional[RunnableConfig]) -> Any:
    """Extract and parse the session UUID from the configurable thread_id."""
    if config is None:
        return None
    raw = config.get("configurable", {}).get("thread_id")
    if not raw:
        return None
    try:
        import uuid as _uuid

        return _uuid.UUID(raw)
    except (ValueError, AttributeError):
        return None


def _session_id_as_str(config: Optional[RunnableConfig]) -> Optional[str]:
    """Return the session thread_id as a plain string for variant routing."""
    if config is None:
        return None
    raw = config.get("configurable", {}).get("thread_id")
    return str(raw) if raw else None
