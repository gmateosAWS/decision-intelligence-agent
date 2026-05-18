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


# ── should_request_confirmation — cheap tools ─────────────────────────────────


def test_cheap_tool_never_triggers() -> None:
    """Cheap tools must never pause for confirmation regardless of signals."""
    should_pause, triggered = should_request_confirmation(
        tool="knowledge", query="short", params={}, is_first_session_turn=True
    )
    assert not should_pause
    assert triggered == []


# ── first_turn signal ─────────────────────────────────────────────────────────


def test_first_turn_signal_fires_when_is_first_turn_true() -> None:
    """first_turn fires when is_first_session_turn=True and tool is expensive."""
    should_pause, triggered = should_request_confirmation(
        tool="simulation",
        query="run a simulation",
        params={},
        is_first_session_turn=True,
    )
    assert should_pause
    assert "first_turn" in triggered


def test_first_turn_signal_does_not_fire_when_is_first_turn_false() -> None:
    """first_turn must NOT fire when the thread already has prior turns."""
    _, triggered = should_request_confirmation(
        tool="simulation",
        query="run a simulation",
        params={},
        is_first_session_turn=False,
    )
    # thin_context fires ("run a simulation" = 3 words, no params), not first_turn
    assert "first_turn" not in triggered


# ── thin_context signal ────────────────────────────────────────────────────────


def test_thin_context_alone_does_not_fire_under_and() -> None:
    """thin_context signal fires but gate does NOT fire when first_turn is absent.

    Under AND semantics with default env (both signals active), thin_context
    alone is insufficient — first_turn must also trigger. The signal is still
    returned so callers can inspect which signals fired.
    """
    should_pause, triggered = should_request_confirmation(
        tool="optimization",
        query="optimize",  # 1 word, < 8
        params={},
        is_first_session_turn=False,  # first_turn does not trigger
    )
    assert not should_pause  # AND: {thin_context} ≠ {first_turn, thin_context}
    assert "thin_context" in triggered  # signal fired; gate did not


def test_thin_context_does_not_fire_when_params_supplied() -> None:
    """Even with a short query, if params are supplied thin_context must NOT fire."""
    should_pause, triggered = should_request_confirmation(
        tool="optimization",
        query="optimize price",
        params={"price": 25.0},
        is_first_session_turn=False,
    )
    # No signals: not first turn; params supplied → no thin_context
    assert "thin_context" not in triggered


def test_thin_context_does_not_fire_for_long_query() -> None:
    """8+ word query must NOT trigger thin_context even without params."""
    should_pause, triggered = should_request_confirmation(
        tool="simulation",
        query="what happens if we set price to twenty five euros",  # 11 words
        params={},
        is_first_session_turn=False,
    )
    assert "thin_context" not in triggered


# ── combined signals ───────────────────────────────────────────────────────────


def test_both_signals_fire_on_first_turn_with_thin_context() -> None:
    """Short query + no params + first turn → both signals fire."""
    should_pause, triggered = should_request_confirmation(
        tool="simulation",
        query="simulate",  # 1 word, < 8
        params={},
        is_first_session_turn=True,
    )
    assert should_pause
    assert "first_turn" in triggered
    assert "thin_context" in triggered


def test_gate_does_not_retrigger_on_second_turn_after_gate_only_round() -> None:
    """Simulate what happens on the second turn after a gate-only first turn.

    Before the fix, state["history"] was always [] after a gate-only round
    (gate → END without writing history), causing first_turn to fire again.
    The fix passes is_first_session_turn=False when the checkpoint exists.
    """
    # Second turn: LangGraph checkpoint exists → has_prior_turns=True
    # → is_first_session_turn=False → first_turn must NOT fire.
    _, triggered = should_request_confirmation(
        tool="simulation",
        query="simulate",
        params={},
        is_first_session_turn=False,  # has_prior_turns=True → not first turn
    )
    assert "first_turn" not in triggered


def test_all_signals_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "")
    should_pause, triggered = should_request_confirmation(
        tool="simulation", query="short", params={}, is_first_session_turn=True
    )
    assert not should_pause
    assert triggered == []


# ── AND semantics — new tests ─────────────────────────────────────────────────


def test_and_semantics_first_turn_alone_does_not_fire() -> None:
    """first_turn fires but gate does NOT fire when thin_context is absent.

    Long query (≥8 words) with params → thin_context does not trigger.
    Under AND, first_turn alone is insufficient.
    """
    should_pause, triggered = should_request_confirmation(
        tool="optimization",
        query="optimiza el precio y el marketing para maximizar el beneficio esperado",
        params={"price": 30.0},
        is_first_session_turn=True,  # first_turn triggers
    )
    assert not should_pause  # AND: {first_turn} ≠ {first_turn, thin_context}
    assert triggered == ["first_turn"]


def test_and_semantics_thin_context_alone_does_not_fire() -> None:
    """thin_context fires but gate does NOT fire when first_turn is absent.

    Turn N>1 (is_first_session_turn=False), short query, no params.
    Under AND, thin_context alone is insufficient.
    """
    should_pause, triggered = should_request_confirmation(
        tool="simulation",
        query="simula",  # 1 word, no params
        params={},
        is_first_session_turn=False,  # first_turn does not trigger
    )
    assert not should_pause  # AND: {thin_context} ≠ {first_turn, thin_context}
    assert triggered == ["thin_context"]


def test_and_semantics_degenerates_with_single_active_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AND with a single active signal degenerates correctly.

    When STATE_CONFIRMATION_SIGNALS=first_turn (only), the gate fires as soon
    as that one signal triggers — {first_turn} == {first_turn}.
    """
    monkeypatch.setenv("STATE_CONFIRMATION_SIGNALS", "first_turn")
    should_pause, triggered = should_request_confirmation(
        tool="optimization",
        query="optimiza el precio y el marketing para maximizar el beneficio",
        params={"price": 30.0},  # thin_context would not fire anyway
        is_first_session_turn=True,
    )
    assert should_pause  # {first_turn} == {first_turn} → fires
    assert triggered == ["first_turn"]
