"""
tests/agents/test_workflow_freeze_enforcement.py
-------------------------------------------------
Tests for B2 fix: frozen-intent enforcement in planner_node.

All offline — no DB, no LLM; planner_node is patched to return a controlled
ToolSelection so we can verify that the freeze override fires correctly.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from agents.state import AgentState
from agents.workflow import planner_node
from memory.state.types import Intent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frozen_active_state(intent: Intent) -> Any:
    """Build a mock frozen active state with intent frozen."""
    mock_state = MagicMock()
    mock_state.intent = intent
    mock_state.frozen_slots = {"intent"}
    mock_state.last_turn_id = 0
    return mock_state


def _unfrozen_active_state(intent: Intent) -> Any:
    mock_state = MagicMock()
    mock_state.intent = intent
    mock_state.frozen_slots = set()
    mock_state.last_turn_id = 0
    return mock_state


def _make_config(
    active_state: Any = None,
    session_id: uuid.UUID | None = None,
) -> dict:
    memory_svc = MagicMock()
    memory_svc.get_active_state.return_value = active_state or MagicMock(
        intent=None, frozen_slots=set(), last_turn_id=0
    )
    observer = MagicMock()
    tracker = MagicMock()
    tracker.total_input_tokens = 0
    tracker.total_output_tokens = 0
    tracker.total_cost_usd = 0.0
    tracker.llm_calls = 0
    return {
        "configurable": {
            "thread_id": str(session_id or uuid.uuid4()),
            "observer": observer,
            "budget_tracker": tracker,
            "memory_service": memory_svc,
        }
    }


# ---------------------------------------------------------------------------
# B2 tests: frozen-intent enforcement
# ---------------------------------------------------------------------------


def test_frozen_intent_overrides_llm_action() -> None:
    """Frozen intent=OPTIMIZE: LLM picks 'knowledge', action → 'optimization'."""
    active_state = _frozen_active_state(Intent.OPTIMIZE)
    config = _make_config(active_state=active_state)

    llm_result = {
        "action": "knowledge",  # LLM chose wrong tool
        "reasoning": "user asked about general info",
        "params": {},
        "planner_prompt_version": None,
        "planner_variant_label": None,
        "language": "en",
    }

    state: AgentState = {
        "query": "optimise price",
        "bypass_gate": False,
        "has_prior_turns": True,
        "blocked_mutations": [],
    }

    with patch("agents.workflow._planner_node_impl", return_value=llm_result):
        result = planner_node(state, config=config)

    # Action must be overridden to the frozen intent's tool
    assert result["action"] == "optimization"
    # blocked_mutations must contain one entry
    assert len(result.get("blocked_mutations", [])) == 1
    block = result["blocked_mutations"][0]
    assert block["slot"] == "intent"
    assert block["blocked_value"] == "knowledge"
    assert block["current_value"] == Intent.OPTIMIZE.value
    assert block["reason"] == "frozen_by_user"
    assert block["source"] == "planner"


def test_frozen_intent_no_override_when_llm_agrees() -> None:
    """If intent=OPTIMIZE is frozen and LLM also picks 'optimization', no block."""
    active_state = _frozen_active_state(Intent.OPTIMIZE)
    config = _make_config(active_state=active_state)

    llm_result = {
        "action": "optimization",
        "reasoning": "user wants optimization",
        "params": {},
        "planner_prompt_version": None,
        "planner_variant_label": None,
        "language": "en",
    }

    state: AgentState = {
        "query": "optimise price",
        "bypass_gate": False,
        "has_prior_turns": True,
        "blocked_mutations": [],
    }

    with patch("agents.workflow._planner_node_impl", return_value=llm_result):
        result = planner_node(state, config=config)

    assert result["action"] == "optimization"
    assert result.get("blocked_mutations", []) == []


def test_unfrozen_intent_does_not_block() -> None:
    """When intent is not frozen, LLM action is used as-is."""
    active_state = _unfrozen_active_state(Intent.OPTIMIZE)
    config = _make_config(active_state=active_state)

    llm_result = {
        "action": "knowledge",
        "reasoning": "user asked about general info",
        "params": {},
        "planner_prompt_version": None,
        "planner_variant_label": None,
        "language": "en",
    }

    state: AgentState = {
        "query": "what are the KPIs?",
        "bypass_gate": False,
        "has_prior_turns": True,
        "blocked_mutations": [],
    }

    with patch("agents.workflow._planner_node_impl", return_value=llm_result):
        result = planner_node(state, config=config)

    # Unfrozen → no override
    assert result["action"] == "knowledge"
    assert result.get("blocked_mutations", []) == []


# ---------------------------------------------------------------------------
# RunResult accumulation
# ---------------------------------------------------------------------------


def test_run_result_blocked_mutations_field_exists() -> None:
    """RunResult must have blocked_mutations as a list field (default empty)."""
    from agents.runner import RunResult

    rr = RunResult(answer="ok", session_id="s", run_id="r", success=True)
    assert hasattr(rr, "blocked_mutations")
    assert isinstance(rr.blocked_mutations, list)
    assert rr.blocked_mutations == []


# ---------------------------------------------------------------------------
# B3: intent serialized as .value in advanced mode
# ---------------------------------------------------------------------------


def test_intent_serialized_to_value_not_repr() -> None:
    """Intent enum in advanced mode must render as 'optimize', not 'Intent.OPTIMIZE'."""
    from memory.state.types import Intent

    intent_val = Intent.OPTIMIZE
    # This is the B3 bug: str(intent_val) → "Intent.OPTIMIZE"
    assert str(intent_val) != intent_val.value, "Precondition: Python str() of Enum"
    # The fix uses .value:
    rendered = intent_val.value if hasattr(intent_val, "value") else str(intent_val)
    assert rendered == "optimize"


# ---------------------------------------------------------------------------
# coordinator: freeze_block observer log (B2 integration)
# ---------------------------------------------------------------------------


def test_freeze_block_observer_called_when_intent_overridden() -> None:
    """obs.record_freeze_block must be called when LLM action is overridden."""
    active_state = _frozen_active_state(Intent.SIMULATE)
    config = _make_config(active_state=active_state)
    obs = config["configurable"]["observer"]

    llm_result = {
        "action": "optimization",  # diverges from frozen SIMULATE → knowledge
        "reasoning": "LLM reasoning",
        "params": {},
        "planner_prompt_version": None,
        "planner_variant_label": None,
        "language": "en",
    }

    state: AgentState = {
        "query": "simulación",
        "bypass_gate": False,
        "has_prior_turns": True,
        "blocked_mutations": [],
    }

    with patch("agents.workflow._planner_node_impl", return_value=llm_result):
        planner_node(state, config=config)

    obs.record_freeze_block.assert_called_once()
    call_kwargs = obs.record_freeze_block.call_args
    assert call_kwargs.kwargs["slot"] == "intent"
    assert call_kwargs.kwargs["source"] == "planner"
