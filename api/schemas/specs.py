"""api/schemas/specs.py — Spec request/response models."""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class SpecCreate(BaseModel):
    yaml_content: str = Field(..., description="Full YAML spec content")
    version: str = Field("1.0.0", description="Semver string, e.g. '1.1.0'")
    description: Optional[str] = None


class SpecResponse(BaseModel):
    id: uuid.UUID
    domain_name: str
    version: str
    status: str
    created_at: str
    description: Optional[str] = None
    yaml_content: Optional[str] = None  # included only in detail view


class SpecVersionResponse(BaseModel):
    id: uuid.UUID
    spec_id: uuid.UUID
    version: str
    change_summary: Optional[str] = None
    created_at: str


class SpecListResponse(BaseModel):
    specs: List[SpecResponse]
    total: int


class SpecBumpRequest(BaseModel):
    yaml_content: str = Field(..., description="Full updated YAML spec content")
    bump_type: Optional[str] = Field(
        None,
        description=(
            "Explicit bump type: 'major', 'minor', or 'patch'. "
            "Auto-detected from YAML diff if omitted."
        ),
    )
    change_summary: Optional[str] = Field(
        None, description="Human-readable description of the change"
    )


class SpecBumpResponse(BaseModel):
    spec_id: uuid.UUID
    version: str
    bump_type: str
    auto_detected: bool
