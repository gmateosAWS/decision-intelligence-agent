"""
spec/autonomy.py
────────────────
Autonomy policy model for tools and future skills.

Three levels of autonomy:
- auto: agent executes without human intervention
- human_confirms: agent shows what it will do and waits for OK
- human_approves: agent proposes but does not execute until explicit approval

Policies are declared per tool/skill in the spec YAML.  The planner consults
the policy before executing.  This is the foundation for:
- Item 7.3 (runtime policy enforcement, I3)
- Item 5.3.b (Capability Graph per-agent policies, I3)
- CEO's "Human-in-the-loop" transversal principle
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class AutonomyLevel(str, Enum):
    AUTO = "auto"
    HUMAN_CONFIRMS = "human_confirms"
    HUMAN_APPROVES = "human_approves"


class ToolAutonomyPolicy(BaseModel):
    """Policy for a single tool or future skill."""

    tool: str
    level: AutonomyLevel = AutonomyLevel.AUTO
    # Placeholder for item 7.3: conditions under which autonomy escalates.
    # e.g. ["params.price > 100", "params.marketing_spend > 50000"]
    conditions: List[str] = Field(default_factory=list)
    reason: str = ""


class AutonomyPolicy(BaseModel):
    """Aggregate policy for all tools declared in a spec."""

    default_level: AutonomyLevel = AutonomyLevel.AUTO
    tools: List[ToolAutonomyPolicy] = Field(default_factory=list)

    def get_level(self, tool_name: str) -> AutonomyLevel:
        """Return the autonomy level for a tool, falling back to default."""
        for t in self.tools:
            if t.tool == tool_name:
                return t.level
        return self.default_level
