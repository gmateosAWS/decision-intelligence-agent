"""
core/protocols/memory.py
────────────────────────
MemoryService Protocol — the only contract through which the rest of the
system may interact with analytical memory.

Design follows the Memory Architecture target (audit document, section 2.4):
- Readers consume frozen snapshots (immutability enforced by Pydantic)
- Mutations go through propose/commit (single-writer remains the coordinator)
- Audit log is first-class (regulated environments require this)

All implementations MUST be stateful per session_id and MUST guarantee that
get_active_state() returns a frozen() snapshot.

Consumers (agents, API, UI) import from here or from `memory` (the facade).
They MUST NOT import from `memory.coordinator.*` or `memory.state.*` directly —
that boundary is enforced by scripts/check_memory_boundary.py in CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Protocol, Union, runtime_checkable
from uuid import UUID

from memory.state.active import ActiveAnalyticalState
from memory.state.audit import StateTransition
from memory.state.types import ResolvedMetric

# ── Mutation outcome types (item 5.13.c) ─────────────────────────────────────


@dataclass
class MutationApplied:
    """A mutation that succeeded and was written to state."""

    slot: str
    before: Any
    after: Any
    version_after: int


@dataclass
class MutationBlocked:
    """A mutation that was rejected because the slot is frozen.

    Both sources of blocks (intent-freeze in planner_node, slot-freeze via
    attempt_mutation in the coordinator) produce this type and accumulate in
    RunResult.blocked_mutations. The UI does not distinguish origin.
    """

    slot: str
    blocked_value: Any  # the value that was attempted
    reason: str  # always "frozen_by_user" in v1
    current_value: Any  # the value that was preserved


MutationOutcome = Union[MutationApplied, MutationBlocked]


# ── Proposal / commit data model (item 5.13) ─────────────────────────────────


class ProposalSource(str, Enum):
    """Origin of a state proposal."""

    PROACTIVE_PLANNER = "proactive_planner"
    REACTIVE_USER = "reactive_user"


@dataclass
class SlotProposal:
    """A single proposed mutation on one slot."""

    slot: str
    current_value: Any
    proposed_value: Any
    reason: str


@dataclass
class StateProposal:
    """A bundle of proposed mutations awaiting user decision."""

    session_id: UUID
    turn_id: int
    source: ProposalSource
    mutations: list[SlotProposal]
    triggered_signals: list[str] = field(default_factory=list)
    original_query: str = ""  # query that triggered the gate; used for resume
    # Candidate historical runs per slot — populated for REACTIVE_USER proposals only.
    # Keys: "active_simulation_run", "active_optimization_run".
    # Each value: list of {run_id, label, timestamp} dicts, newest first.
    candidate_runs: dict[str, list[dict]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StateCommitDecision:
    """User's response to a StateProposal."""

    session_id: UUID
    proposal_turn_id: int
    approved_mutations: list[SlotProposal] = field(default_factory=list)
    rejected_slots: list[str] = field(default_factory=list)
    freeze_slots: list[str] = field(default_factory=list)
    unfreeze_slots: list[str] = field(default_factory=list)


@dataclass
class StateCommitResult:
    """Outcome of applying a StateCommitDecision."""

    session_id: UUID
    version_before: int
    version_after: int
    applied_mutations: list[SlotProposal]
    skipped_slots: list[str]
    original_query: str = ""  # propagated from the proposal for resume_query
    committed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class MemoryService(Protocol):
    """The only seam through which agents, API and UI interact with analytical memory.

    Implementations MUST be session-scoped (one coordinator per session_id,
    keyed internally) and MUST return frozen() snapshots from read methods.

    Follows the RunSink Protocol precedent established in item P2.3/1D —
    contract first, implementation behind, ObjectBus-ready seam.
    """

    # ── Read API (consumed by planner, judge, API endpoints, UI) ────────────

    def get_active_state(self, session_id: UUID) -> ActiveAnalyticalState:
        """Return a frozen snapshot of the analytical state for this session.

        Callers MUST treat the returned value as immutable. The boundary lint
        (scripts/check_memory_boundary.py) enforces this by blocking direct
        access to the coordinator outside memory/.
        """
        ...

    def read_audit(
        self, session_id: UUID, since_turn: int = 0
    ) -> List[StateTransition]:
        """Return ordered audit log of state transitions for this session."""
        ...

    # ── Implicit-mutation API (called by workflow nodes) ─────────────────────

    def record_tool_selection(
        self,
        session_id: UUID,
        tool: str,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        """Record the Intent derived from a planner tool selection.

        Maps tool name → Intent enum internally; callers do not need to know
        about the mapping. Called by planner_node after tool selection.
        """
        ...

    def record_metric(
        self,
        session_id: UUID,
        metric: ResolvedMetric,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> None:
        """Append a ResolvedMetric. Called by planner_node on metric extraction."""
        ...

    def record_active_run(
        self,
        session_id: UUID,
        tool: str,
        run_id: str,
        turn_id: int,
        cause: str,
        evidence: str = "",
    ) -> Optional[MutationOutcome]:
        """Record an active run reference after tool execution.

        Returns MutationBlocked when the target slot is frozen (so callers
        such as tool_node can surface the block to the user). Returns
        MutationApplied on success, or None for unsupported tool types.

        tool is 'simulation' or 'optimization'. run_id holds the agent_runs.run_id.

        TODO(1.6/ObjectBus): run_id will become ObjectId when bus lands.
        Interface signature stays — only the backing type changes.
        """
        ...

    # ── Explicit-mutation API (item 5.13) ─────────────────────────────────────

    def propose_state_update(
        self,
        session_id: UUID,
        turn_id: int,
        source: ProposalSource,
        pending_mutations: list[SlotProposal] | None = None,
        original_query: str = "",
    ) -> StateProposal:
        """Generate a proposal of mutations awaiting user decision.

        For PROACTIVE_PLANNER: pending_mutations is the planner's intended
        changes expressed as SlotProposals. The proposal is persisted for audit.

        For REACTIVE_USER: pending_mutations is None; the method returns the
        current state slots packaged as proposals (current_value == proposed_value)
        so the user can edit them. Slots covered: intent, metrics,
        active_simulation_run, active_optimization_run, active_scenarios.
        """
        ...

    def commit_state_update(
        self,
        session_id: UUID,
        decision: StateCommitDecision,
    ) -> StateCommitResult:
        """Apply approved mutations via MemoryCoordinator. Persist with audit.

        Raises ValueError when decision.proposal_turn_id does not correspond
        to an open proposal for this session (API layer converts to HTTP 400).

        Frozen slots in approved_mutations are silently skipped (logged in
        skipped_slots of the result). freeze_slots / unfreeze_slots in the
        decision are always applied regardless of the approved_mutations list.
        """
        ...
