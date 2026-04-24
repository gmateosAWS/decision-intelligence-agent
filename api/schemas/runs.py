"""api/schemas/runs.py — Run response models."""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from pydantic import BaseModel


class RunResponse(BaseModel):
    id: uuid.UUID
    run_id: str
    session_id: Optional[uuid.UUID] = None
    timestamp: str
    query: str
    action: Optional[str] = None
    success: bool = True
    total_latency_ms: Optional[float] = None
    judge_score: Optional[float] = None
    confidence_score: Optional[float] = None
    spec_version: Optional[str] = None
    # Detail-only fields (populated by GET /runs/{run_id})
    answer_length: Optional[int] = None
    reasoning: Optional[str] = None
    raw_result: Optional[Any] = None
    error: Optional[str] = None


class RunListResponse(BaseModel):
    runs: List[RunResponse]
    total: int
