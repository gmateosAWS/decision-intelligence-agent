"""
tests/agents/test_tools_registry.py
-------------------------------------
Unit tests for agents/tools_registry.py — tool cost classification (item 5.13).
All offline — no DB, no LLM.
"""

from __future__ import annotations

from agents.tools_registry import get_tool_cost_class, register_tool_cost_class


def test_expensive_tools_classified_correctly() -> None:
    assert get_tool_cost_class("simulation") == "expensive"
    assert get_tool_cost_class("optimization") == "expensive"


def test_cheap_tools_classified_correctly() -> None:
    assert get_tool_cost_class("knowledge") == "cheap"


def test_unknown_tool_defaults_to_cheap() -> None:
    """Unknown tools must default to 'cheap' to avoid unnecessary gate friction."""
    assert get_tool_cost_class("future_tool_xyz") == "cheap"


def test_register_new_tool_cost_class() -> None:
    """register_tool_cost_class must allow new tools to declare themselves expensive."""
    register_tool_cost_class("causal_inference", "expensive")
    assert get_tool_cost_class("causal_inference") == "expensive"
    # Cleanup — restore to cheap so other tests are not affected
    register_tool_cost_class("causal_inference", "cheap")


def test_proactive_gate_uses_registry_not_hardcoded() -> None:
    """The proactive gate must read cost class from the registry, not hardcode names.

    This test registers a new 'expensive' tool and verifies the gate fires for it.
    """
    from memory.proactive_confirmation import should_request_confirmation

    register_tool_cost_class("new_expensive_skill", "expensive")
    try:
        import os

        # Ensure signals are active for this test
        original = os.environ.get("STATE_CONFIRMATION_SIGNALS", None)
        os.environ["STATE_CONFIRMATION_SIGNALS"] = "first_turn,thin_context"

        # first_turn signal: is_first_session_turn=True → should fire
        should_pause, triggered = should_request_confirmation(
            tool="new_expensive_skill",
            query="short",
            params={},
            is_first_session_turn=True,
        )
        assert should_pause
        assert "first_turn" in triggered

        if original is None:
            del os.environ["STATE_CONFIRMATION_SIGNALS"]
        else:
            os.environ["STATE_CONFIRMATION_SIGNALS"] = original
    finally:
        register_tool_cost_class("new_expensive_skill", "cheap")
