"""api/schemas/query.py — Request/Response models for POST /v1/query."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

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
    # Autonomy policy fields: non-zero when the agent's policy requires review
    requires_confirmation: bool = False
    requires_approval: bool = False
    confirmation_message: Optional[str] = None
    # Cost tracking (item 8.7.a+b)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_calls_count: int = 0
    budget_exceeded: bool = False
    budget_exceeded_reason: Optional[str] = None
    # GroundedTokens clarification (item 5.9)
    clarification_needed: bool = False
    clarification_message: Optional[str] = None
    # Proactive confirmation gate (item 5.13)
    awaiting_user_confirmation: bool = False
    proposal: Optional[Dict[str, Any]] = None
