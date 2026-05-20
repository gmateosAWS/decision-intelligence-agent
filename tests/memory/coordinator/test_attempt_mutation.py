"""
tests/memory/coordinator/test_attempt_mutation.py
--------------------------------------------------
Unit tests for MemoryCoordinator.attempt_mutation.
All offline — no DB, no LLM.
"""

from __future__ import annotations

import uuid

from core.protocols.memory import MutationApplied, MutationBlocked
from memory.coordinator.coordinator import MemoryCoordinator
from memory.state.audit import TransitionOp
from memory.state.types import Intent


def _coord() -> MemoryCoordinator:
    return MemoryCoordinator(session_id=uuid.uuid4())


def test_attempt_mutation_returns_applied_when_not_frozen() -> None:
    coord = _coord()
    outcome = coord.attempt_mutation(
        slot="intent",
        new_value=Intent.OPTIMIZE,
        op_hint=TransitionOp.SET,
        turn_id=1,
        cause="test",
        evidence="",
    )
    assert isinstance(outcome, MutationApplied)
    assert outcome.slot == "intent"
    assert outcome.after == Intent.OPTIMIZE
    assert outcome.version_after > 0


def test_attempt_mutation_returns_blocked_when_frozen() -> None:
    coord = _coord()
    coord.set_intent(Intent.OPTIMIZE, turn_id=1, cause="seed")
    coord.freeze_slot("intent", turn_id=2, cause="user:freeze")

    outcome = coord.attempt_mutation(
        slot="intent",
        new_value=Intent.SIMULATE,
        op_hint=TransitionOp.SET,
        turn_id=3,
        cause="test",
        evidence="",
    )
    assert isinstance(outcome, MutationBlocked)
    assert outcome.slot == "intent"
    assert outcome.blocked_value == Intent.SIMULATE
    assert outcome.reason == "frozen_by_user"
    assert outcome.current_value == Intent.OPTIMIZE


def test_attempt_mutation_blocked_preserves_current_value() -> None:
    coord = _coord()
    coord.set_intent(Intent.EXPLAIN, turn_id=1, cause="seed")
    coord.freeze_slot("intent", turn_id=2, cause="user:freeze")

    outcome = coord.attempt_mutation(
        slot="intent",
        new_value=Intent.OPTIMIZE,
        op_hint=TransitionOp.SET,
        turn_id=3,
        cause="test",
        evidence="",
    )
    assert isinstance(outcome, MutationBlocked)
    # State must be unchanged after a blocked attempt
    assert coord.get_state().intent == Intent.EXPLAIN


def test_attempt_mutation_identity_is_silent_noop() -> None:
    """Identity mutation returns MutationApplied without bumping version."""
    coord = _coord()
    coord.set_intent(Intent.OPTIMIZE, turn_id=1, cause="seed")
    version_before = coord.get_state().version

    outcome = coord.attempt_mutation(
        slot="intent",
        new_value=Intent.OPTIMIZE,  # same as current
        op_hint=TransitionOp.SET,
        turn_id=2,
        cause="test",
        evidence="",
    )
    assert isinstance(outcome, MutationApplied)
    assert outcome.before == outcome.after
    # Version must NOT change for identity mutations
    assert coord.get_state().version == version_before


def test_attempt_mutation_identity_on_frozen_slot_is_also_noop() -> None:
    """Identity mutation on a frozen slot returns MutationApplied (not blocked)."""
    coord = _coord()
    coord.set_intent(Intent.OPTIMIZE, turn_id=1, cause="seed")
    coord.freeze_slot("intent", turn_id=2, cause="user:freeze")

    outcome = coord.attempt_mutation(
        slot="intent",
        new_value=Intent.OPTIMIZE,  # same value — identity
        op_hint=TransitionOp.SET,
        turn_id=3,
        cause="test",
        evidence="",
    )
    # Identity check precedes freeze check — no MutationBlocked noise
    assert isinstance(outcome, MutationApplied)
    assert outcome.before == outcome.after
