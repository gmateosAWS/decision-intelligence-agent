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

from typing import List, Protocol, runtime_checkable
from uuid import UUID

from memory.state.active import ActiveAnalyticalState
from memory.state.audit import StateTransition
from memory.state.types import ResolvedMetric


class StateProposal:
    """A proposed mutation to ActiveAnalyticalState.

    v1: intentionally minimal placeholder — the full proposal/decision flow
    lands with item 5.13 (user-driven state corrections).

    TODO(5.13): expand with proposed_slot, proposed_value, proposed_op,
    justification, requires_user_confirmation.
    """


class StateCommitDecision:
    """A user's decision on a StateProposal.

    TODO(5.13): expand with accept: bool, alternative_value, justification.
    """


class StateCommitResult:
    """The result of applying a StateCommitDecision.

    TODO(5.13): expand with version_before, version_after, applied: bool.
    """


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
    ) -> None:
        """Record an active run reference after tool execution.

        tool is 'simulation' or 'optimization'. run_id holds the agent_runs.run_id.

        TODO(1.6/ObjectBus): run_id will become ObjectId when bus lands.
        Interface signature stays — only the backing type changes.
        """
        ...

    # ── Explicit-mutation API (5.13 placeholder) ─────────────────────────────

    def propose_state_update(self, session_id: UUID, turn_id: int) -> StateProposal:
        """Generate a proposed mutation for user review.

        v1 returns an empty StateProposal — the full proposal/decision flow
        lands with item 5.13 (user-driven state corrections).
        """
        ...

    def commit_state_update(
        self,
        session_id: UUID,
        decision: StateCommitDecision,
    ) -> StateCommitResult:
        """Apply a user-approved StateProposal.

        v1 is a no-op — the full implementation comes with item 5.13.
        """
        ...
