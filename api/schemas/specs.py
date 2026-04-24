"""api/schemas/specs.py — Spec request/response models."""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class SpecCreate(BaseModel):
    yaml_content: str = Field(..., description="Full YAML spec content")
    version: str = Field(..., description="Semver string, e.g. '1.1.0'")
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
