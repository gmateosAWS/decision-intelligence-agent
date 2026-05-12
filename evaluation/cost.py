"""LLM cost calculation from token usage and model pricing table (item 8.7.a)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yaml

_PRICING_PATH = Path(__file__).parent.parent / "config" / "model_pricing.yaml"


@dataclass(frozen=True)
class ModelPricing:
    input_per_1k_tokens: float  # USD; -1 = unknown
    output_per_1k_tokens: float  # USD; -1 = unknown


def _load_pricing() -> Dict[str, ModelPricing]:
    with open(_PRICING_PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return {name: ModelPricing(**vals) for name, vals in raw["models"].items()}


@lru_cache(maxsize=1)
def _pricing_table() -> Dict[str, ModelPricing]:
    return _load_pricing()


def reload_pricing() -> None:
    """Clear the pricing cache so the next call re-reads the YAML."""
    _pricing_table.cache_clear()


def get_pricing(model: str) -> Optional[ModelPricing]:
    table = _pricing_table()
    return table.get(model) or table.get("unknown")


def calculate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return cost in USD; 0.0 when pricing is unknown (-1) or model not found."""
    pricing = get_pricing(model)
    if pricing is None:
        return 0.0
    if pricing.input_per_1k_tokens < 0 or pricing.output_per_1k_tokens < 0:
        return 0.0
    return (
        input_tokens * pricing.input_per_1k_tokens / 1000
        + output_tokens * pricing.output_per_1k_tokens / 1000
    )
