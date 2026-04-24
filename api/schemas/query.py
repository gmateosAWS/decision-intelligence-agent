"""api/schemas/query.py — Request/Response models for POST /v1/query."""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Business question for the agent")
    session_id: Optional[uuid.UUID] = Field(
        None, description="Resume an existing session; omit to start a new one"
    )


class QueryResponse(BaseModel):
    answer: str
    session_id: uuid.UUID
    run_id: str
    tool_used: Optional[str] = None
    confidence: Optional[float] = None
    latency_ms: Optional[float] = None
    fallback_triggered: bool = False
    spec_version: Optional[str] = None
