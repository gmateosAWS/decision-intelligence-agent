"""
memory/service.py
─────────────────
LocalMemoryService — concrete implementation of the MemoryService Protocol.

Wraps a MemoryCoordinator per session. Loads from DB lazily on first access,
persists on every mutation. Fail-open when DATABASE_URL is absent (matches
the dual-backend pattern throughout the system).

Consumers MUST NOT import this module directly — use `memory.get_memory_service()`
or type-hint against `core.protocols.memory.MemoryService`.
"""

from __future__ import annotations

from typing import Dict, List
from uuid import UUID

from memory.coordinator.coordinator import MemoryCoordinator
from memory.coordinator.intent_mapping import map_tool_to_intent
from memory.state.active import ActiveAnalyticalState
from memory.state.audit import StateTransition
from memory.state.types import ResolvedMetric


class LocalMemoryService:
    """Concrete MemoryService backed by per-session MemoryCoordinators.

    Coordinators are loaded from DB on first access and cached for the
    lifetime of this service instance (typically the process lifetime when
    used via get_memory_service()). Mutations are persisted synchronously
    with fail-open behaviour.
    """

    def __init__(self) -> None:
        self._coordinators: Dict[UUID, MemoryCoordinator] = {}

    def _get_or_load(self, session_id: UUID) -> MemoryCoordinator:
        if session_id not in self._coordinators:
            try:
                self._coordinators[session_id] = MemoryCoordinator.load_from_db(
                    session_id
                )
            except Exception:  # noqa: BLE001
                self._coordinators[session_id] = MemoryCoordinator(session_id)
        return self._coordinators[session_id]

    # ── Read API ─────────────────────────────────────────────────────────────

    def get_active_state(self, session_id: UUID) -> ActiveAnalyticalState:
        return self._get_or_load(session_id).get_state()

    def read_audit(
        self, session_id: UUID, since_turn: int = 0
    ) -> List[StateTransition]:
        return self._get_or_load(session_id).get_audit_log(since_turn=since_turn)

    # ── Implicit-mutation API ─────────────────────────────────────────────────

    def record_tool_selection(
        self,
        session_id: UUID,
        tool: str,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        coord = self._get_or_load(session_id)
        intent = map_tool_to_intent(tool)
        coord.set_intent(intent, turn_id=turn_id, cause=cause, evidence=evidence)
        self._persist_safe(coord)

    def record_metric(
        self,
        session_id: UUID,
        metric: ResolvedMetric,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        coord = self._get_or_load(session_id)
        coord.add_metric(metric, turn_id=turn_id, cause=cause, evidence=evidence)
        self._persist_safe(coord)

    def record_active_run(
        self,
        session_id: UUID,
        tool: str,
        run_id: str,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        coord = self._get_or_load(session_id)
        if tool == "simulation":
            coord.set_active_simulation_run(
                run_id, turn_id=turn_id, cause=cause, evidence=evidence
            )
        elif tool == "optimization":
            coord.set_active_optimization_run(
                run_id, turn_id=turn_id, cause=cause, evidence=evidence
            )
        # Other tools: no slot defined in v1; ignore gracefully.
        self._persist_safe(coord)

    # ── Explicit-mutation API (5.13 placeholders) ─────────────────────────────

    def propose_state_update(self, session_id: UUID, turn_id: int) -> object:
        # TODO(5.13): generate real StateProposal from turn delta.
        from core.protocols.memory import StateProposal

        return StateProposal()

    def commit_state_update(self, session_id: UUID, decision: object) -> object:
        # TODO(5.13): apply StateCommitDecision via coordinator with audit trail.
        from core.protocols.memory import StateCommitResult

        return StateCommitResult()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _persist_safe(self, coord: MemoryCoordinator) -> None:
        """Persist coordinator state; fail open if DB unavailable."""
        try:
            coord.persist_to_db()
        except Exception:  # noqa: BLE001
            pass
