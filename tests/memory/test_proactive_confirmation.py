"""
tests/memory/test_proactive_confirmation.py
--------------------------------------------
Unit tests for memory/proactive_confirmation.py (item 5.13).
All offline — no DB, no LLM. Env vars reset between tests.
"""

from __future__ import annotations

import pytest

from memory.proactive_confirmation import (
    get_active_signals,
    should_request_confirmation,
)


@pytest.fixture(autouse=True)
def reset_signals_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure STATE_CONFIRMATION_SIGNALS is always reset to default between tests."""
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "first_turn,thin_context")


# ── get_active_signals ────────────────────────────────────────────────────────


def test_default_signals_are_both_active() -> None:
    signals = get_active_signals()
    assert "first_turn" in signals
    assert "thin_context" in signals


def test_empty_env_disables_all_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "")
    signals = get_active_signals()
    assert len(signals) == 0


def test_single_signal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "first_turn")
    signals = get_active_signals()
    assert signals == {"first_turn"}


# ── should_request_confirmation ───────────────────────────────────────────────


def test_cheap_tool_never_triggers() -> None:
    """Cheap tools must never pause for confirmation regardless of signals."""
    should_pause, triggered = should_request_confirmation(
        tool="knowledge", query="short", params={}, history=[]
    )
    assert not should_pause
    assert triggered == []


def test_first_turn_signal_fires_for_expensive_tool_on_empty_history() -> None:
    should_pause, triggered = should_request_confirmation(
        tool="simulation", query="run a simulation", params={}, history=[]
    )
    assert should_pause
    assert "first_turn" in triggered


def test_first_turn_signal_does_not_fire_when_history_exists() -> None:
    should_pause, triggered = should_request_confirmation(
        tool="simulation",
        query="run a simulation",
        params={},
        history=[{"query": "previous", "answer": "answer"}],
    )
    # thin_context check: "run a simulation" = 3 words < 8, but params={} empty
    # So thin_context fires; first_turn does NOT because history is non-empty
    assert "first_turn" not in triggered


def test_thin_context_signal_fires_for_short_query_no_params() -> None:
    should_pause, triggered = should_request_confirmation(
        tool="optimization",
        query="optimize",  # 1 word, < 8
        params={},
        history=[{"query": "previous", "answer": "answer"}],
    )
    assert should_pause
    assert "thin_context" in triggered


def test_thin_context_does_not_fire_when_params_supplied() -> None:
    """Even with a short query, if params are supplied thin_context must NOT fire."""
    should_pause, triggered = should_request_confirmation(
        tool="optimization",
        query="optimize price",
        params={"price": 25.0},
        history=[{"query": "previous", "answer": "answer"}],
    )
    # No signals: history exists (no first_turn); params supplied (no thin_context)
    assert "thin_context" not in triggered


def test_thin_context_does_not_fire_for_long_query() -> None:
    """8+ word query must NOT trigger thin_context even without params."""
    should_pause, triggered = should_request_confirmation(
        tool="simulation",
        query="what happens if we set price to twenty five euros",  # 11 words
        params={},
        history=[{"query": "previous", "answer": "answer"}],
    )
    assert "thin_context" not in triggered


def test_all_signals_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "")
    should_pause, triggered = should_request_confirmation(
        tool="simulation", query="short", params={}, history=[]
    )
    assert not should_pause
    assert triggered == []
