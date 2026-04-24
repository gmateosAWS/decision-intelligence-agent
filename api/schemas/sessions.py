"""api/schemas/sessions.py — Session response models."""

from __future__ import annotations

from typing import List

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
