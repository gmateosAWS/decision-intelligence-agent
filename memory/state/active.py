"""
memory/state/active.py
──────────────────────
ActiveAnalyticalState — the typed analytical context that lives between turns.

Design follows the Memory Architecture target (audit document):
- Single-writer: only MemoryCoordinator may mutate this object
- Readers get .frozen() snapshots (immutable)
- Append-only versioning: every mutation increments `version`
- Provenance per slot: any slot value can be traced to the turn that
  introduced it

V1 SCOPE (this PR):
Implemented slots:
  - session_id, last_turn_id, version (always)
  - intent (Intent enum)
  - metrics (list[ResolvedMetric])
  - active_simulation_run, active_optimization_run (str | None — see TODO)
  - active_scenarios (list[str] — see TODO)
  - provenance (dict per slot)
  - frozen_slots (set — empty by default; user freeze/unfreeze in 5.11+)

Placeholder slots (typed but unused in v1, populated by future items):
  - dimensions, period, geography (5.10 v2 + text2sql)
  - comparisons, transformations (5.10 v2)
  - pending_confirmations (5.13)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from memory.state.types import Intent, ResolvedMetric, SlotProvenance


class ActiveAnalyticalState(BaseModel):
    """Single source of truth for the analytical context of a session.

    IMMUTABILITY: callers outside memory/coordinator/ MUST use frozen()
    before reading. Direct mutation is enforced-against by the boundary lint
    (added in item 5.11).
    """

    model_config = ConfigDict(frozen=False)  # mutable for the coordinator only

    # Identity & versioning ─────────────────────────────────────────
    session_id: UUID
    last_turn_id: int = 0
    version: int = 0  # append-only; ++ on every commit

    # Analytical context (v1 implemented) ───────────────────────────
    intent: Intent | None = None
    metrics: list[ResolvedMetric] = Field(default_factory=list)

    # Decisional context (v1 implemented, DEUDA TÉCNICA con 1.6) ────
    # TODO(1.6/ObjectBus): change type to `ObjectId | None`. See docs/tech_debt.md.
    # Current backing: agent_runs.run_id (str). Future: ObjectBus entry id.
    active_simulation_run: str | None = None
    active_optimization_run: str | None = None
    # TODO(1.6/ObjectBus): change type to `list[ObjectId]`. See docs/tech_debt.md.
    active_scenarios: list[str] = Field(default_factory=list)

    # Provenance & governance ────────────────────────────────────────
    provenance: dict[str, SlotProvenance] = Field(default_factory=dict)
    frozen_slots: set[str] = Field(default_factory=set)

    # Placeholder slots (v2 — populated when text2sql/dimensions land) ─
    # These fields exist so the contract is stable; downstream code can
    # reference them safely even before they hold data.
    dimensions: list[Any] = Field(default_factory=list)  # v2: list[ResolvedDimension]
    period: Any | None = None  # v2: TemporalScope
    geography: list[Any] = Field(default_factory=list)  # v2: list[ResolvedGeo]
    comparisons: list[Any] = Field(default_factory=list)  # v2: list[Comparison]
    transformations: list[Any] = Field(default_factory=list)  # v2: list[Transformation]
    pending_confirmations: list[Any] = Field(
        default_factory=list
    )  # v2: list[PendingConfirmation]

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def frozen(self) -> "FrozenActiveAnalyticalState":
        """Return an immutable deep-copy for read-only consumption.

        Callers outside memory/coordinator/ MUST call this before reading.
        The boundary lint (item 5.11) will enforce this at PR time.
        """
        return FrozenActiveAnalyticalState.model_validate(self.model_dump(mode="json"))


class FrozenActiveAnalyticalState(ActiveAnalyticalState):
    """Immutable snapshot of ActiveAnalyticalState.

    Returned by ActiveAnalyticalState.frozen().  Any attempt to assign a
    field raises pydantic.ValidationError so violations are caught early.
    """

    model_config = ConfigDict(frozen=True)
