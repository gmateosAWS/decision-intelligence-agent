"""api/schemas/prompts.py — Prompt Registry request/response models."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PromptResponse(BaseModel):
    id: str
    version: str
    status: str
    stage: str
    content: str
    variables: List[str] = []
    owner: str = ""
    description: str = ""
    created_at: datetime
    changed_at: datetime
    sunset_date: Optional[date] = None
    replacement_id: Optional[str] = None
    adr: Optional[str] = None


class PromptListResponse(BaseModel):
    total: int
    prompts: List[PromptResponse]


class PromptCreateRequest(BaseModel):
    id: str = Field(..., description="Human-readable stage key, e.g. 'planner'")
    stage: str = Field(
        ...,
        description="Agent stage: 'planner', 'synthesizer', 'judge', 'judge.revision'",
    )
    content: str = Field(..., description="Prompt template text with {placeholders}")
    version: str = Field("1.0.0", description="Semver string")
    variables: List[str] = Field(
        default_factory=list, description="Placeholder names used in content"
    )
    owner: str = ""
    description: str = ""
    adr: Optional[str] = None


class PromptDeprecateRequest(BaseModel):
    replacement_id: Optional[str] = Field(
        None, description="ID of the prompt that replaces this one"
    )


# ---------------------------------------------------------------------------
# Variant schemas (item 10.2)
# ---------------------------------------------------------------------------


class PromptVariantResponse(BaseModel):
    id: str
    stage: str
    prompt_id: str
    version: str
    variant_label: str
    status: str
    rollout_percentage: int
    created_at: datetime
    changed_at: datetime
    owner: str = ""
    notes: str = ""


class PromptVariantListResponse(BaseModel):
    total: int
    variants: List[PromptVariantResponse]


class StartRolloutRequest(BaseModel):
    stage: str = Field(
        ..., description="Agent stage: 'planner', 'synthesizer', 'judge'"
    )
    prompt_id: str = Field(..., description="Prompt registry id (e.g. 'planner')")
    version: str = Field(..., description="Semver of the CERTIFIED prompt to test")
    variant_label: str = Field(..., description="Human-readable label: 'v2-concise'")
    rollout_percentage: int = Field(..., ge=1, le=99, description="% of traffic [1–99]")
    owner: str = ""
    notes: str = ""


class AdjustRolloutRequest(BaseModel):
    rollout_percentage: int = Field(..., ge=0, le=99, description="New % [0–99]")
