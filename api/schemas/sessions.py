"""api/schemas/sessions.py — Session response models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: str
    last_active: str
    turn_count: int


class SessionListResponse(BaseModel):
    sessions: List[SessionResponse]
    total: int


# ── Analytical State (item 5.10) ─────────────────────────────────────────────


class AnalyticalStateResponse(BaseModel):
    """Serialised read-only snapshot of ActiveAnalyticalState."""

    session_id: str
    version: int
    last_turn_id: int
    intent: Optional[str] = None
    metrics: List[Dict[str, Any]] = []
    active_simulation_run: Optional[str] = None
    active_optimization_run: Optional[str] = None
    active_scenarios: List[str] = []


class StateTransitionResponse(BaseModel):
    """One audit-log entry from the state mutation log."""

    turn_id: int
    version_before: int
    version_after: int
    slot: str
    op: str
    before: Any = None
    after: Any = None
    cause: str
    evidence: str
    timestamp: str


class StateAuditResponse(BaseModel):
    session_id: str
    transitions: List[StateTransitionResponse]
    total: int
