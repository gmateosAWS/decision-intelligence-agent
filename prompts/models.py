"""
prompts/models.py
─────────────────
Prompt Registry data model. First concrete instance of the
GovernableArtifact pattern (item 10.8).

When 10.8 lands, the common fields (id, version, status, owner,
created_at, changed_at, sunset_date, replacement_id, adr) will be
extracted to a shared GovernableArtifact base class. The current
PromptRecord is intentionally structured to make that extraction trivial:
all GovernableArtifact fields are at the top, prompt-specific fields below.

Stage vocabulary (extensible for item 4.3 skills):
  "planner"         — planner system prompt template
  "synthesizer"     — synthesizer system prompt template
  "judge"           — judge evaluation system prompt template
  "judge.revision"  — judge revision system prompt template
  "<skill>.<role>"  — future skill prompts
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PromptStatus(str, Enum):
    DRAFT = "draft"
    CERTIFIED = "certified"  # active, evaluated, approved for production
    DEPRECATED = "deprecated"


class PromptVariantStatus(str, Enum):
    DRAFT = "draft"  # being prepared, not yet in traffic
    CANDIDATE = "candidate"  # in A/B test, receiving rollout_percentage% of traffic
    CHAMPION = "champion"  # baseline, receives remaining traffic after candidates
    DEPRECATED = "deprecated"  # retired, receives 0% traffic


class PromptRecord(BaseModel):
    """
    A versioned prompt template. Follows GovernableArtifact contract (10.8).

    ``content`` stores the raw template string with Python-style {placeholders}.
    Callers render it with .format(**kwargs) using the variable names listed
    in ``variables``.

    Example:
        record = get_certified_prompt("planner")
        prompt = record.content.format(
            domain_name=..., vars_description=..., examples=...
        )
    """

    # ── GovernableArtifact fields (will become base class in 10.8) ──────────
    id: str  # human-readable: "planner", "synthesizer", "judge", "judge.revision"
    version: str  # semver: "1.0.0"
    status: PromptStatus = PromptStatus.DRAFT
    owner: str = ""
    created_at: datetime
    changed_at: datetime
    sunset_date: Optional[date] = None
    replacement_id: Optional[str] = None
    adr: Optional[str] = None

    # ── Prompt-specific fields ───────────────────────────────────────────────
    stage: str  # "planner", "synthesizer", "judge", "judge.revision"
    content: str  # prompt template text with {placeholders}
    variables: List[str] = []  # placeholder names used in content
    description: str = ""


class PromptVariant(BaseModel):
    """
    A traffic-routing entry for A/B testing a specific (prompt_id, version).

    Exactly one CHAMPION per stage (baseline, absorbs remaining traffic).
    CANDIDATEs share a slice of traffic; sum of their rollout_percentages must ≤ 100.

    Deterministic routing: sha256(f"{session_id}|{stage}") → bucket [0,100).
    Same session always receives the same variant, enabling quality measurement.
    """

    id: str  # UUID string
    stage: str  # "planner", "synthesizer", "judge", "judge.revision"
    prompt_id: str  # FK → prompts.id
    version: str  # FK → prompts.version
    variant_label: str = Field(
        ..., description="Human-readable: 'v1-control', 'v2-concise'"
    )
    status: PromptVariantStatus = PromptVariantStatus.DRAFT
    rollout_percentage: int = Field(0, ge=0, le=100)  # % of traffic; 100 for CHAMPION
    created_at: datetime
    changed_at: datetime
    owner: str = ""
    notes: str = ""
