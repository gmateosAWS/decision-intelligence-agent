"""
api/main.py
-----------
FastAPI application for the Decision Intelligence Agent.

Exposes the agent as a modular HTTP monolith. All business logic lives in the
existing Python modules (agents/, spec/, memory/, evaluation/); the API layer
only routes, validates, and translates.

Run:
    uvicorn api.main:app --reload --port 8000

Docs:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed spec on startup (idempotent)
    try:
        from db.engine import check_connection

        if check_connection():
            from spec.spec_loader import SPEC_PATH
            from spec.spec_repository import seed_from_yaml

            seed_from_yaml(SPEC_PATH)
            logger.info("Spec seeded / verified on startup.")
    except Exception as exc:
        logger.warning("Spec seed skipped (DB unavailable): %s", exc)

    yield
    # Nothing to tear down — DB engine and graph are process singletons


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="llull — Decision Intelligence Agent API",
    description=(
        "Spec-driven decision intelligence agent exposed as an HTTP API. "
        "The LLM orchestrates; Python computes. "
        "See [GitHub](https://github.com/gmateosAWS/decision-intelligence-agent) "
        "for full documentation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — configurable via CORS_ORIGINS env var (comma-separated)
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8501,http://localhost:3000,http://localhost:8000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from agents.llm_factory import LLMUnavailableError

    if isinstance(exc, LLMUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"error": "LLM service unavailable", "detail": str(exc)},
        )
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from api.routers import health, query, runs, sessions, specs  # noqa: E402

app.include_router(health.router)  # /healthz, /readyz, /v1/debug/config at root
app.include_router(query.router, prefix="/v1")
app.include_router(sessions.router, prefix="/v1")
app.include_router(runs.router, prefix="/v1")
app.include_router(specs.router, prefix="/v1")
