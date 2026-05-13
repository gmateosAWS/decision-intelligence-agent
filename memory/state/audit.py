"""
memory/state/audit.py
─────────────────────
StateTransition — typed audit log of every mutation on ActiveAnalyticalState.

Persisted per turn so any slot value can be traced back to the operation
that introduced it, with cause. Critical for debugging and for item 7.8
(regulated audit log).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TransitionOp(str, Enum):
    SET = "set"  # slot was empty, now has value
    OVERWRITE = "overwrite"  # slot had value, now different value
    APPEND = "append"  # for list slots
    CLEAR = "clear"  # slot reset to None / []
    FREEZE = "freeze"  # slot pinned by user (cannot be auto-overwritten)
    UNFREEZE = "unfreeze"


class StateTransition(BaseModel):
    """A single mutation applied to ActiveAnalyticalState.

    The audit_log on a session is the ordered list of these transitions.
    Reconstructing state at turn N = applying transitions 0..N to empty state.
    """

    turn_id: int
    version_before: int
    version_after: int
    slot: str  # "intent", "metrics", "active_simulation_run", ...
    op: TransitionOp
    before: Any = None  # value before mutation
    after: Any = None  # value after mutation
    cause: str  # "planner:tool_selection", "user:correction", "judge:revision"
    evidence: str = ""  # quote or short justification
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
