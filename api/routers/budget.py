"""api/routers/budget.py — Budget endpoints (item 8.7.b).

GET /v1/budget/current   — active per-run budget ceilings (from env vars).
GET /v1/budget/exchange-rate — current USD→EUR rate from Frankfurter cache.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/budget", tags=["budget"])


class BudgetResponse(BaseModel):
    max_llm_calls: int
    max_wallclock_s: float
    max_cost_usd: float
    max_tokens: int
    limits_active: bool


class ExchangeRateResponse(BaseModel):
    usd_to_eur: float
    source: str


@router.get(
    "/current",
    response_model=BudgetResponse,
    summary="Active per-run budget ceilings",
)
def get_current_budget() -> BudgetResponse:
    """Return the per-run budget limits read from environment variables."""
    from evaluation.budget import RunBudget

    budget = RunBudget.from_env()
    limits_active = any(
        [
            budget.max_llm_calls > 0,
            budget.max_wallclock_s > 0,
            budget.max_cost_usd > 0,
            budget.max_tokens > 0,
        ]
    )
    return BudgetResponse(
        max_llm_calls=budget.max_llm_calls,
        max_wallclock_s=budget.max_wallclock_s,
        max_cost_usd=budget.max_cost_usd,
        max_tokens=budget.max_tokens,
        limits_active=limits_active,
    )


@router.get(
    "/exchange-rate",
    response_model=ExchangeRateResponse,
    summary="Current USD→EUR exchange rate",
)
def get_exchange_rate() -> ExchangeRateResponse:
    """Return the cached USD→EUR rate (Frankfurter API, 1-hour TTL)."""
    import os

    from evaluation.currency import get_eur_per_usd

    rate = get_eur_per_usd()
    env_override = os.environ.get("EUR_USD_RATE")
    source = "env_override" if env_override else "frankfurter_api_or_default"
    return ExchangeRateResponse(usd_to_eur=rate, source=source)
