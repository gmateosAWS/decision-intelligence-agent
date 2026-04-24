"""api/routers/health.py — Liveness, readiness and debug-config endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    postgres: bool
    spec_loaded: bool


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
def healthz() -> HealthResponse:
    """Always returns 200 — confirms the process is alive."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse, summary="Readiness probe")
def readyz() -> ReadyResponse:
    """Returns 200 when Postgres and the active spec are reachable."""
    postgres_ok = False
    try:
        from db.engine import check_connection

        postgres_ok = check_connection()
    except Exception:
        pass

    spec_ok = False
    try:
        from spec.spec_loader import get_spec

        get_spec()
        spec_ok = True
    except Exception:
        pass

    return ReadyResponse(
        status="ready" if (postgres_ok and spec_ok) else "degraded",
        postgres=postgres_ok,
        spec_loaded=spec_ok,
    )


@router.get("/v1/debug/config", summary="Non-sensitive runtime configuration")
def debug_config() -> dict:
    """Returns the active LLM provider/model configuration (no secrets)."""
    return {
        "planner_provider": os.getenv("PLANNER_PROVIDER", "openai"),
        "planner_model": os.getenv("PLANNER_MODEL", "gpt-4o-mini"),
        "synthesizer_provider": os.getenv("SYNTHESIZER_PROVIDER", "openai"),
        "synthesizer_model": os.getenv("SYNTHESIZER_MODEL", "gpt-4o-mini"),
        "judge_provider": os.getenv("JUDGE_PROVIDER", "openai"),
        "judge_model": os.getenv("JUDGE_MODEL", "gpt-4o-mini"),
        "fallback_provider": os.getenv("FALLBACK_PROVIDER", ""),
        "history_window": os.getenv("HISTORY_WINDOW", "3"),
    }
