"""
config/settings.py
------------------
Thin adapter over the organizational spec.
All numeric parameters are loaded from spec/organizational_model.yaml.

Backward compatibility: call-site imports are unchanged — every previous
constant (UNIT_COST, MC_RUNS, …) is replaced by a same-named accessor
function.  Callers that did ``from config.settings import UNIT_COST`` now
do ``from config.settings import get_unit_cost`` and call it as a function.

Lazy loading: no IO or DB access happens at import time.  The spec is
fetched on the first accessor call and cached for the process lifetime.

To change model parameters: edit spec/organizational_model.yaml.
Do NOT add new hardcoded constants here.
"""

from __future__ import annotations

from typing import Optional

from spec.spec_loader import get_spec

_settings_cache: Optional[dict] = None


def _load_settings() -> dict:
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    spec = get_spec()
    price_var = spec.get_decision_var("price")
    marketing_var = spec.get_decision_var("marketing_spend")
    _settings_cache = {
        "unit_cost": float(spec.business_parameters.get("unit_cost", 10.0)),
        "mc_runs": int(spec.simulation_runs),
        "price_min": float(price_var.bounds_min),
        "price_max": float(price_var.bounds_max),
        "price_steps": int(price_var.steps),
        "default_marketing": float(
            spec.fixed_variables.get("marketing_spend", marketing_var.default)
        ),
    }
    return _settings_cache


def get_unit_cost() -> float:
    return float(_load_settings()["unit_cost"])


def get_mc_runs() -> int:
    return int(_load_settings()["mc_runs"])


def get_price_min() -> float:
    return float(_load_settings()["price_min"])


def get_price_max() -> float:
    return float(_load_settings()["price_max"])


def get_price_steps() -> int:
    return int(_load_settings()["price_steps"])


def get_default_marketing() -> float:
    return float(_load_settings()["default_marketing"])
