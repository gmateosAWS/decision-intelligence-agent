"""
tests/agents/test_planner_bypass.py
-------------------------------------
Unit tests for the deterministic planner bypass introduced in item 5.13.c (R5 fix).

When bypass_gate=True AND active_state.intent is not None, workflow.planner_node
must short-circuit the LLM call and return an action derived from _INTENT_TO_ACTION.
All tests are offline — no DB, no LLM, no Streamlit runtime.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    session_id: str = "00000000-0000-0000-0000-000000000001",
    memory_service: Any = None,
) -> dict:
    """Return a minimal LangGraph-style config dict."""
    return {
        "configurable": {
            "thread_id": session_id,
            "memory_service": memory_service,
            "observer": None,
            "budget_tracker": None,
        }
    }


def _make_active_state(intent: Any) -> Any:
    """Return a mock active_state with the given intent."""
    state = MagicMock()
    state.intent = intent
    return state


def _make_agent_state(**kwargs: Any) -> dict:
    base: dict = {
        "query": "optimise now",
        "action": "knowledge",
        "params": {},
        "bypass_gate": False,
        "clarification_needed": False,
        "has_prior_turns": True,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Tests: bypass fires when bypass_gate=True + intent is set
# ---------------------------------------------------------------------------


def test_bypass_with_optimize_intent_skips_llm() -> None:
    """bypass_gate=True + OPTIMIZE intent → action=optimization, LLM not called."""
    from memory.state.types import Intent

    active_state = _make_active_state(Intent.OPTIMIZE)
    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = active_state

    config = _make_config(memory_service=mock_svc)
    state = _make_agent_state(bypass_gate=True)

    with patch("agents.workflow._planner_node_impl") as mock_impl:
        from agents.workflow import planner_node

        result = planner_node(state, config)

    mock_impl.assert_not_called()
    assert result["action"] == "optimization"
    assert "bypass_gate" in result.get("reasoning", "")


def test_bypass_with_simulate_intent_skips_llm() -> None:
    """bypass_gate=True + SIMULATE intent → action=simulation, LLM not called."""
    from memory.state.types import Intent

    active_state = _make_active_state(Intent.SIMULATE)
    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = active_state

    config = _make_config(memory_service=mock_svc)
    state = _make_agent_state(bypass_gate=True)

    with patch("agents.workflow._planner_node_impl") as mock_impl:
        from agents.workflow import planner_node

        result = planner_node(state, config)

    mock_impl.assert_not_called()
    assert result["action"] == "simulation"


def test_bypass_with_explain_intent_maps_to_knowledge() -> None:
    """bypass_gate=True + EXPLAIN intent → action=knowledge."""
    from memory.state.types import Intent

    active_state = _make_active_state(Intent.EXPLAIN)
    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = active_state

    config = _make_config(memory_service=mock_svc)
    state = _make_agent_state(bypass_gate=True)

    with patch("agents.workflow._planner_node_impl") as mock_impl:
        from agents.workflow import planner_node

        result = planner_node(state, config)

    mock_impl.assert_not_called()
    assert result["action"] == "knowledge"


def test_bypass_with_explore_intent_maps_to_knowledge() -> None:
    """bypass_gate=True + EXPLORE intent → action=knowledge."""
    from memory.state.types import Intent

    active_state = _make_active_state(Intent.EXPLORE)
    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = active_state

    config = _make_config(memory_service=mock_svc)
    state = _make_agent_state(bypass_gate=True)

    with patch("agents.workflow._planner_node_impl") as mock_impl:
        from agents.workflow import planner_node

        result = planner_node(state, config)

    mock_impl.assert_not_called()
    assert result["action"] == "knowledge"


# ---------------------------------------------------------------------------
# Tests: bypass does NOT fire on normal turns
# ---------------------------------------------------------------------------


def test_no_bypass_when_flag_is_false() -> None:
    """bypass_gate=False → LLM IS called even if intent is set."""
    from memory.state.types import Intent

    active_state = _make_active_state(Intent.OPTIMIZE)
    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = active_state

    config = _make_config(memory_service=mock_svc)
    state = _make_agent_state(bypass_gate=False)

    mock_result = {
        "action": "optimization",
        "reasoning": "llm said so",
        "params": {},
        "planner_prompt_version": None,
        "planner_variant_label": None,
    }
    with patch(
        "agents.workflow._planner_node_impl", return_value=mock_result
    ) as mock_impl:
        from agents.workflow import planner_node

        planner_node(state, config)

    mock_impl.assert_called_once()


def test_no_bypass_when_intent_is_none() -> None:
    """bypass_gate=True but intent=None → LLM IS called (intent unknown)."""
    active_state = _make_active_state(None)
    mock_svc = MagicMock()
    mock_svc.get_active_state.return_value = active_state

    config = _make_config(memory_service=mock_svc)
    state = _make_agent_state(bypass_gate=True)

    mock_result = {
        "action": "knowledge",
        "reasoning": "llm fallback",
        "params": {},
        "planner_prompt_version": None,
        "planner_variant_label": None,
    }
    with patch(
        "agents.workflow._planner_node_impl", return_value=mock_result
    ) as mock_impl:
        from agents.workflow import planner_node

        planner_node(state, config)

    mock_impl.assert_called_once()
