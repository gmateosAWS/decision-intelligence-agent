"""
memory/state/types.py
─────────────────────
Typed slot components for ActiveAnalyticalState.

Each type is a closed contract — ResolvedMetric is what skills consume and
produce. Intent is a closed enum — extending it requires an ADR.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """High-level intent of the current analytical conversation.

    Closed enum — adding new intents requires an ADR
    (item 4.3 may add SKILL_INVOCATION).
    """

    OPTIMIZE = "optimize"  # user wants to find optimal values
    SIMULATE = "simulate"  # user wants to evaluate a specific scenario
    EXPLAIN = "explain"  # user wants to understand how the model works
    EXPLORE = "explore"  # user is exploring relationships / what-ifs


class ResolvedMetric(BaseModel):
    """A metric resolved against the spec — typed, not a raw string.

    This is the canonical typed reference to a business metric. Skills
    consume and produce ResolvedMetric (never raw strings). When the metric
    registry (item 10.8) lands, ``id`` will reference a MetricDefinition.
    """

    id: str  # canonical id from spec (e.g. "expected_profit")
    name: str  # human-readable name
    formula: Optional[str] = None  # for derived metrics (e.g. "revenue - cost")
    unit: Optional[str] = None
    source_turn: int  # turn that introduced this metric
    confidence: float = 1.0  # planner confidence at extraction


class SlotProvenance(BaseModel):
    """Records the origin of every slot value in ActiveAnalyticalState.

    Enables 'why is this metric in state?' queries critical for debugging
    and for regulated environments (item 7.8 audit log).
    """

    introduced_at_turn: int
    introduced_by: str  # node name: "planner", "judge", "user"
    evidence: str = ""  # quote from user message or tool output
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
