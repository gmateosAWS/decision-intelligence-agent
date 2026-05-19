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

import dataclasses
import logging
from typing import TYPE_CHECKING, Any, Dict, List
from uuid import UUID

# Deferred to break the circular import chain:
#   core.protocols.memory → memory.state.active → memory.__init__ → memory.service
# All symbols used only as runtime values are imported inside the methods that need
# them.
if TYPE_CHECKING:
    from core.protocols.memory import (
        ProposalSource,
        SlotProposal,
        StateCommitDecision,
        StateCommitResult,
        StateProposal,
    )
from memory.coordinator.coordinator import MemoryCoordinator
from memory.coordinator.intent_mapping import map_tool_to_intent
from memory.state.active import ActiveAnalyticalState
from memory.state.audit import StateTransition, TransitionOp
from memory.state.types import ResolvedMetric

logger = logging.getLogger(__name__)

# Slots exposed for reactive user correction.
_REACTIVE_EDITABLE_SLOTS = [
    "intent",
    "metrics",
    "active_simulation_run",
    "active_optimization_run",
    "active_scenarios",
]


class LocalMemoryService:
    """Concrete MemoryService backed by per-session MemoryCoordinators.

    Coordinators are loaded from DB on first access and cached for the
    lifetime of this service instance (typically the process lifetime when
    used via get_memory_service()). Mutations are persisted synchronously
    with fail-open behaviour.

    In-memory proposal store: proposals are kept in a dict keyed by
    (session_id, turn_id). In v1 this is process-local (no cross-process
    coordination). A future item (5.13.c) will persist proposals to the
    state_proposals table for audit; the DB models are ready in migration 010.
    """

    def __init__(self) -> None:
        self._coordinators: Dict[UUID, MemoryCoordinator] = {}
        # In-memory proposal store: (session_id, turn_id) → StateProposal
        self._proposals: Dict[tuple[UUID, int], StateProposal] = {}

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

    # ── Explicit-mutation API (item 5.13) ──────────────────────────────────

    def propose_state_update(
        self,
        session_id: UUID,
        turn_id: int,
        source: ProposalSource,
        pending_mutations: list[SlotProposal] | None = None,
        original_query: str = "",
    ) -> StateProposal:
        """Generate a proposal of mutations awaiting user decision.

        PROACTIVE_PLANNER: uses pending_mutations supplied by the workflow gate.
        REACTIVE_USER: packages current editable slots as identity proposals
        (current_value == proposed_value) so the user can edit them.
        """
        from core.protocols.memory import (  # noqa: PLC0415
            ProposalSource as _ProposalSource,
        )
        from core.protocols.memory import (
            StateProposal as _StateProposal,
        )

        coord = self._get_or_load(session_id)
        state = coord.get_state()

        if source == _ProposalSource.PROACTIVE_PLANNER:
            mutations = list(pending_mutations or [])
            candidate_runs: dict[str, list[dict]] = {}
        else:
            # Reactive: build SlotProposal for each editable slot
            mutations = self._build_reactive_mutations(state)
            candidate_runs = self._build_candidate_runs(session_id)

        proposal = _StateProposal(
            session_id=session_id,
            turn_id=turn_id,
            source=source,
            mutations=mutations,
            original_query=original_query,
            candidate_runs=candidate_runs,
        )
        self._proposals[(session_id, turn_id)] = proposal
        self._persist_proposal_safe(proposal)
        return proposal

    def commit_state_update(
        self,
        session_id: UUID,
        decision: StateCommitDecision,
    ) -> StateCommitResult:
        """Apply approved mutations via MemoryCoordinator. Persist with audit.

        Raises ValueError when proposal_turn_id does not correspond to a
        known open proposal (API converts to HTTP 400).
        """
        proposal = self._proposals.get((session_id, decision.proposal_turn_id))
        if proposal is None:
            raise ValueError(
                f"No open proposal for session {session_id} "
                f"at turn_id {decision.proposal_turn_id}"
            )

        coord = self._get_or_load(session_id)
        state_before = coord.get_state()
        version_before = state_before.version

        applied: list[SlotProposal] = []
        skipped: list[str] = []
        turn_id = decision.proposal_turn_id
        cause = "user:correction"

        for mutation in decision.approved_mutations:
            slot = mutation.slot
            # frozen_slots are silently skipped — the coordinator would also
            # reject them, but we log them explicitly in skipped_slots.
            if slot in state_before.frozen_slots:
                skipped.append(slot)
                continue
            self._apply_mutation(coord, mutation, turn_id, cause)
            applied.append(mutation)

        # Apply freeze / unfreeze regardless of approved_mutations
        for slot in decision.freeze_slots:
            coord.freeze_slot(slot, turn_id=turn_id, cause=cause)
        for slot in decision.unfreeze_slots:
            coord.unfreeze_slot(slot, turn_id=turn_id, cause=cause)

        self._persist_safe(coord)

        # Capture original_query before removing the proposal from the store.
        proposal_original_query = proposal.original_query

        # Remove proposal from in-memory store (mark resolved)
        del self._proposals[(session_id, decision.proposal_turn_id)]

        from core.protocols.memory import (
            StateCommitResult as _StateCommitResult,  # noqa: PLC0415
        )

        result = _StateCommitResult(
            session_id=session_id,
            version_before=version_before,
            version_after=coord.get_state().version,
            applied_mutations=applied,
            skipped_slots=skipped,
            original_query=proposal_original_query,
        )
        self._persist_commit_safe(result)
        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    def _persist_safe(self, coord: MemoryCoordinator) -> None:
        """Persist coordinator state; fail open if DB unavailable."""
        try:
            coord.persist_to_db()
        except Exception:  # noqa: BLE001
            pass

    def _persist_proposal_safe(self, proposal: StateProposal) -> None:
        """Persist proposal to DB for audit; fail open."""
        import os  # noqa: PLC0415

        if not os.getenv("DATABASE_URL", ""):
            return
        try:
            self._persist_proposal_postgres(proposal)
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist_proposal failed: %s", exc)

    def _persist_proposal_postgres(self, proposal: StateProposal) -> None:
        import json  # noqa: PLC0415

        from db.engine import get_session  # noqa: PLC0415
        from db.models import StateProposalRow  # noqa: PLC0415

        mutations_json = json.dumps(
            [dataclasses.asdict(m) for m in proposal.mutations],
            default=str,
        )
        signals_json = json.dumps(proposal.triggered_signals)

        with get_session() as db:
            row = StateProposalRow(
                session_id=proposal.session_id,
                turn_id=proposal.turn_id,
                source=proposal.source.value,
                mutations=mutations_json,
                triggered_signals=signals_json,
                original_query=proposal.original_query,
                created_at=proposal.created_at,
            )
            db.add(row)
            db.commit()

    def _persist_commit_safe(self, result: StateCommitResult) -> None:
        """Persist commit result to DB for audit; fail open."""
        import os  # noqa: PLC0415

        if not os.getenv("DATABASE_URL", ""):
            return
        try:
            self._persist_commit_postgres(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist_commit failed: %s", exc)

    def _persist_commit_postgres(self, result: StateCommitResult) -> None:
        import json  # noqa: PLC0415

        from db.engine import get_session  # noqa: PLC0415
        from db.models import StateCommitRow  # noqa: PLC0415

        applied_json = json.dumps(
            [dataclasses.asdict(m) for m in result.applied_mutations],
            default=str,
        )
        skipped_json = json.dumps(result.skipped_slots)

        with get_session() as db:
            row = StateCommitRow(
                session_id=result.session_id,
                version_before=result.version_before,
                version_after=result.version_after,
                applied_mutations=applied_json,
                skipped_slots=skipped_json,
                committed_at=result.committed_at,
            )
            db.add(row)
            db.commit()

    @staticmethod
    def _build_candidate_runs(session_id: UUID) -> dict[str, list[dict]]:
        """Query agent_runs for recent sim/opt runs in this session.

        Returns a dict keyed by slot name with up to 10 most-recent runs each.
        Each entry: {run_id, label (HH:MM), timestamp}. Fails open → returns {}.
        """
        import os  # noqa: PLC0415

        if not os.getenv("DATABASE_URL", ""):
            return {}
        try:
            from db.engine import get_session as _get_db_session  # noqa: PLC0415
            from db.models import AgentRun  # noqa: PLC0415

            slot_to_action = {
                "active_simulation_run": "simulation",
                "active_optimization_run": "optimization",
            }
            result: dict[str, list[dict]] = {}
            for slot, action_val in slot_to_action.items():
                with _get_db_session() as db:
                    rows = (
                        db.query(AgentRun)
                        .filter(
                            AgentRun.session_id == session_id,
                            AgentRun.action == action_val,
                        )
                        .order_by(AgentRun.timestamp.desc())
                        .limit(10)
                        .all()
                    )
                    candidates = []
                    for row in rows:
                        ts = (
                            row.timestamp.strftime("%H:%M")
                            if row.timestamp
                            else "??:??"
                        )
                        candidates.append(
                            {
                                "run_id": str(row.run_id),
                                "label": ts,
                                "timestamp": (
                                    row.timestamp.isoformat() if row.timestamp else ""
                                ),
                            }
                        )
                    if candidates:
                        result[slot] = candidates
            return result
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def _build_reactive_mutations(
        state: ActiveAnalyticalState,
    ) -> list[SlotProposal]:
        """Build identity SlotProposals for each user-editable slot."""
        from core.protocols.memory import SlotProposal as _SlotProposal  # noqa: PLC0415

        mutations: list[SlotProposal] = []
        for slot in _REACTIVE_EDITABLE_SLOTS:
            current = getattr(state, slot, None)
            mutations.append(
                _SlotProposal(
                    slot=slot,
                    current_value=current,
                    proposed_value=current,
                    reason="User-initiated reactive correction",
                )
            )
        return mutations

    @staticmethod
    def _apply_mutation(
        coord: MemoryCoordinator,
        mutation: SlotProposal,
        turn_id: int,
        cause: str,
    ) -> None:
        """Dispatch a SlotProposal to the appropriate coordinator method.

        Uses coord.attempt_mutation for all non-intent slots so that:
        - Identity mutations are silent no-ops (no log, no version bump).
        - Frozen slots return MutationBlocked (pre-filtered by caller, but
          the protocol remains consistent).
        """
        slot = mutation.slot
        value: Any = mutation.proposed_value

        if slot == "intent":
            from memory.state.types import Intent  # noqa: PLC0415

            if isinstance(value, str):
                try:
                    value = Intent(value)
                except ValueError:
                    return  # unknown intent string — skip silently
            if isinstance(value, Intent):
                coord.set_intent(value, turn_id=turn_id, cause=cause)
        elif slot == "metrics":
            # B4 fix: coerce list[dict] → list[ResolvedMetric] so Pydantic
            # does not warn about unexpected value types on serialization.
            from memory.state.types import (  # noqa: PLC0415
                ResolvedMetric as _ResolvedMetric,
            )

            raw_list: list[Any] = value if isinstance(value, list) else []
            coerced: list[ResolvedMetric] = []
            for item in raw_list:
                if isinstance(item, _ResolvedMetric):
                    coerced.append(item)
                elif isinstance(item, dict):
                    try:
                        coerced.append(_ResolvedMetric(**item))
                    except Exception:  # noqa: BLE001
                        pass  # skip malformed entries silently
            coord.attempt_mutation(
                slot="metrics",
                new_value=coerced,
                op_hint=TransitionOp.OVERWRITE,
                turn_id=turn_id,
                cause=cause,
                evidence="user:correction:metrics",
            )
        elif slot == "active_simulation_run":
            # B1(C) fix: normalize empty string → None (text input returns ""
            # when user clears the field; None means "no active run").
            norm_sim = value if (isinstance(value, str) and value.strip()) else None
            coord.attempt_mutation(
                slot="active_simulation_run",
                new_value=norm_sim,
                op_hint=TransitionOp.OVERWRITE,
                turn_id=turn_id,
                cause=cause,
                evidence="user:correction:active_simulation_run",
            )
        elif slot == "active_optimization_run":
            norm_opt = value if (isinstance(value, str) and value.strip()) else None
            coord.attempt_mutation(
                slot="active_optimization_run",
                new_value=norm_opt,
                op_hint=TransitionOp.OVERWRITE,
                turn_id=turn_id,
                cause=cause,
                evidence="user:correction:active_optimization_run",
            )
        elif slot == "active_scenarios":
            coord.attempt_mutation(
                slot="active_scenarios",
                new_value=value if isinstance(value, list) else [],
                op_hint=TransitionOp.OVERWRITE,
                turn_id=turn_id,
                cause=cause,
                evidence="user:correction:active_scenarios",
            )
        else:
            logger.warning(
                "commit_state_update: unknown slot %r in approved_mutations — skipped",
                slot,
            )
