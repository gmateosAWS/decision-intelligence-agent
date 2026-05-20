"""
memory/coordinator/coordinator.py
─────────────────────────────────
MemoryCoordinator — the ONLY component allowed to mutate ActiveAnalyticalState.

Single-writer pattern from the Memory Architecture target. All other code
(agents, nodes, UI, API) consumes .frozen() snapshots. Boundary lint added
in item 5.11 enforces this rule at PR time via grep-based check in CI.

The coordinator records every mutation in the audit log so any state value
can be traced to its origin.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from core.protocols.memory import MutationOutcome

from memory.state.active import ActiveAnalyticalState
from memory.state.audit import StateTransition, TransitionOp
from memory.state.types import Intent, ResolvedMetric, SlotProvenance

logger = logging.getLogger(__name__)


class MemoryCoordinator:
    """Single mutator. Owns the audit log. Returns frozen snapshots to readers."""

    def __init__(self, session_id: UUID) -> None:
        self._state = ActiveAnalyticalState(session_id=session_id)
        self._audit_log: list[StateTransition] = []
        self._persisted_count: int = 0  # how many transitions already in DB

    # ── Read API ────────────────────────────────────────────────────────────

    def get_state(self) -> ActiveAnalyticalState:
        """Return frozen snapshot. Callers MUST NOT mutate."""
        return self._state.frozen()

    def get_audit_log(self, since_turn: int = 0) -> list[StateTransition]:
        return [t for t in self._audit_log if t.turn_id >= since_turn]

    # ── Mutation API (only called from workflow nodes or MemoryService) ─────

    def set_intent(
        self,
        intent: Intent,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        self._mutate(
            slot="intent",
            new_value=intent,
            op_hint=TransitionOp.SET,
            turn_id=turn_id,
            cause=cause,
            evidence=evidence,
        )

    def add_metric(
        self,
        metric: ResolvedMetric,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        new_metrics = list(self._state.metrics) + [metric]
        self._mutate(
            slot="metrics",
            new_value=new_metrics,
            op_hint=TransitionOp.APPEND,
            turn_id=turn_id,
            cause=cause,
            evidence=evidence,
        )

    def set_active_simulation_run(
        self,
        run_id: str,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> "MutationOutcome":
        # TODO(1.6/ObjectBus): change run_id type to ObjectId when bus lands.
        # See docs/tech_debt.md §"5.10 → 1.6".
        return self.attempt_mutation(
            slot="active_simulation_run",
            new_value=run_id,
            op_hint=(
                TransitionOp.SET
                if self._state.active_simulation_run is None
                else TransitionOp.OVERWRITE
            ),
            turn_id=turn_id,
            cause=cause,
            evidence=evidence,
        )

    def set_active_optimization_run(
        self,
        run_id: str,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> "MutationOutcome":
        # TODO(1.6/ObjectBus): same migration as above. See docs/tech_debt.md.
        return self.attempt_mutation(
            slot="active_optimization_run",
            new_value=run_id,
            op_hint=(
                TransitionOp.SET
                if self._state.active_optimization_run is None
                else TransitionOp.OVERWRITE
            ),
            turn_id=turn_id,
            cause=cause,
            evidence=evidence,
        )

    def freeze_slot(self, slot: str, turn_id: int, cause: str) -> None:
        """Add slot to frozen_slots. Frozen slots resist system mutations."""
        self._state.frozen_slots.add(slot)
        self._state.version += 1
        self._audit_log.append(
            StateTransition(
                turn_id=turn_id,
                version_before=self._state.version - 1,
                version_after=self._state.version,
                slot=slot,
                op=TransitionOp.SET,
                before=False,
                after=True,
                cause=cause,
                evidence=f"frozen_slots.add({slot!r})",
            )
        )

    def unfreeze_slot(self, slot: str, turn_id: int, cause: str) -> None:
        """Remove slot from frozen_slots, allowing system mutations again."""
        self._state.frozen_slots.discard(slot)
        self._state.version += 1
        self._audit_log.append(
            StateTransition(
                turn_id=turn_id,
                version_before=self._state.version - 1,
                version_after=self._state.version,
                slot=slot,
                op=TransitionOp.CLEAR,
                before=True,
                after=False,
                cause=cause,
                evidence=f"frozen_slots.discard({slot!r})",
            )
        )

    def attempt_mutation(
        self,
        *,
        slot: str,
        new_value: Any,
        op_hint: TransitionOp,
        turn_id: int,
        cause: str,
        evidence: str,
    ) -> "MutationOutcome":
        """Attempt a slot mutation; return typed MutationApplied or MutationBlocked.

        Identity mutations (new_value == current_value) are silent no-ops —
        they return MutationApplied without logging or incrementing version.
        This prevents spurious freeze_block noise when the planner re-sets a
        slot to the value it already holds (e.g. record_tool_selection after
        planner overrides a frozen action).

        Frozen slots return MutationBlocked with reason="frozen_by_user".
        All non-identity, non-frozen mutations delegate to _mutate and return
        MutationApplied.
        """
        from core.protocols.memory import (  # noqa: PLC0415
            MutationApplied as _MutationApplied,
        )
        from core.protocols.memory import (
            MutationBlocked as _MutationBlocked,
        )

        current_value = getattr(self._state, slot, None)

        # Identity check: no-op, return Applied without writing or logging.
        if new_value == current_value:
            return _MutationApplied(
                slot=slot,
                before=current_value,
                after=current_value,
                version_after=self._state.version,
            )

        if slot in self._state.frozen_slots:
            logger.info(
                "[memory] freeze_block: slot=%s attempted=%r current=%r",
                slot,
                new_value,
                current_value,
            )
            return _MutationBlocked(
                slot=slot,
                blocked_value=new_value,
                reason="frozen_by_user",
                current_value=current_value,
            )

        self._mutate(
            slot=slot,
            new_value=new_value,
            op_hint=op_hint,
            turn_id=turn_id,
            cause=cause,
            evidence=evidence,
        )
        return _MutationApplied(
            slot=slot,
            before=current_value,
            after=new_value,
            version_after=self._state.version,
        )

    # ── Persistence API ─────────────────────────────────────────────────────

    def persist_to_db(self) -> None:
        """Upsert state + insert new transitions into Postgres. Fail-open."""
        if not os.getenv("DATABASE_URL", ""):
            return
        try:
            self._persist_postgres()
        except Exception as exc:  # noqa: BLE001
            logger.warning("MemoryCoordinator.persist_to_db failed: %s", exc)

    @classmethod
    def load_from_db(cls, session_id: UUID) -> "MemoryCoordinator":
        """Load coordinator from DB; return empty coordinator on failure."""
        if not os.getenv("DATABASE_URL", ""):
            return cls(session_id=session_id)
        try:
            return cls._load_postgres(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MemoryCoordinator.load_from_db failed (%s), starting fresh", exc
            )
            return cls(session_id=session_id)

    # ── Internal mutation engine ─────────────────────────────────────────────

    def _mutate(
        self,
        *,
        slot: str,
        new_value: Any,
        op_hint: TransitionOp,
        turn_id: int,
        cause: str,
        evidence: str,
    ) -> None:
        if slot in self._state.frozen_slots:
            # User has pinned this slot — refuse to overwrite silently.
            # Future (5.11): expose this as a typed conflict event.
            return
        before = getattr(self._state, slot)
        setattr(self._state, slot, new_value)
        self._state.version += 1
        self._state.last_turn_id = turn_id
        self._state.provenance[slot] = SlotProvenance(
            introduced_at_turn=turn_id,
            introduced_by=cause.split(":")[0] if ":" in cause else cause,
            evidence=evidence,
        )
        self._audit_log.append(
            StateTransition(
                turn_id=turn_id,
                version_before=self._state.version - 1,
                version_after=self._state.version,
                slot=slot,
                op=op_hint,
                before=before,
                after=new_value,
                cause=cause,
                evidence=evidence,
            )
        )

    # ── Postgres helpers ─────────────────────────────────────────────────────

    def _persist_postgres(self) -> None:
        from datetime import datetime, timezone

        from db.engine import get_session
        from db.models import AgentSession, SessionStateTransition

        state_json = self._state.model_dump(mode="json")

        with get_session() as db:
            session_row = db.get(AgentSession, self._state.session_id)
            if session_row is None:
                # Create a minimal session row so analytical state can be FK-safe
                now = datetime.now(timezone.utc)
                session_row = AgentSession(
                    session_id=self._state.session_id,
                    title="",
                    created_at=now,
                    last_active=now,
                    turn_count=0,
                )
                db.add(session_row)
                db.flush()
            session_row.analytical_state = state_json  # type: ignore[assignment]
            session_row.analytical_state_version = self._state.version  # type: ignore[assignment]

            new_transitions = self._audit_log[self._persisted_count :]
            for t in new_transitions:
                t_data = t.model_dump(mode="json")
                db.add(
                    SessionStateTransition(
                        session_id=self._state.session_id,
                        turn_id=t.turn_id,
                        version_before=t.version_before,
                        version_after=t.version_after,
                        slot=t.slot,
                        op=t.op.value,
                        before=t_data.get("before"),
                        after=t_data.get("after"),
                        cause=t.cause,
                        evidence=t.evidence,
                        timestamp=t.timestamp,
                    )
                )
            self._persisted_count = len(self._audit_log)

    @classmethod
    def _load_postgres(cls, session_id: UUID) -> "MemoryCoordinator":
        from db.engine import get_session
        from db.models import AgentSession, SessionStateTransition

        coordinator = cls(session_id=session_id)

        with get_session() as db:
            session_row = db.get(AgentSession, session_id)
            if session_row is None or not session_row.analytical_state:
                return coordinator

            state_data = session_row.analytical_state
            if isinstance(state_data, str):
                import json as _json

                state_data = _json.loads(state_data)

            coordinator._state = ActiveAnalyticalState.model_validate(state_data)

            transitions = (
                db.query(SessionStateTransition)
                .filter(SessionStateTransition.session_id == session_id)
                .order_by(SessionStateTransition.version_after)
                .all()
            )
            from memory.state.audit import TransitionOp

            for row in transitions:
                coordinator._audit_log.append(
                    StateTransition(
                        turn_id=row.turn_id,
                        version_before=row.version_before,
                        version_after=row.version_after,
                        slot=row.slot,
                        op=TransitionOp(row.op),
                        before=row.before,
                        after=row.after,
                        cause=row.cause,
                        evidence=row.evidence or "",
                        timestamp=row.timestamp,
                    )
                )
            coordinator._persisted_count = len(coordinator._audit_log)

        return coordinator
