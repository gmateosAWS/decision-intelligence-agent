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


# ── State proposals & commits (item 5.13) ────────────────────────────────────


class SlotProposalSchema(BaseModel):
    """One proposed mutation on a single state slot."""

    slot: str
    current_value: Any = None
    proposed_value: Any = None
    reason: str = ""


class ProposalCreateRequest(BaseModel):
    """Request body for POST /sessions/{id}/state/proposals."""

    source: str  # "proactive_planner" | "reactive_user"
    pending_mutations: Optional[List[SlotProposalSchema]] = None


class ProposalResponse(BaseModel):
    """Response body containing the generated StateProposal."""

    session_id: str
    turn_id: int
    source: str
    mutations: List[SlotProposalSchema]
    triggered_signals: List[str] = []
    candidate_runs: Dict[str, List[Dict[str, Any]]] = {}
    created_at: str


class CommitDecisionRequest(BaseModel):
    """Request body for POST /sessions/{id}/state/commits."""

    proposal_turn_id: int
    approved_mutations: List[SlotProposalSchema] = []
    rejected_slots: List[str] = []
    freeze_slots: List[str] = []
    unfreeze_slots: List[str] = []
    resume_query: bool = True  # if True, re-invoke agent with bypass_gate after commit


class CommitResultResponse(BaseModel):
    """Response body for a committed state decision."""

    session_id: str
    version_before: int
    version_after: int
    applied_mutations: List[SlotProposalSchema]
    skipped_slots: List[str]
    committed_at: str
    resumed_run: Optional[Dict[str, Any]] = None  # populated when resume_query=True
