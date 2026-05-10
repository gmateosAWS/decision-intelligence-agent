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
