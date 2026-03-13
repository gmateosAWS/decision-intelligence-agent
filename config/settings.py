"""
config/settings.py  (MODIFIED — Mejora 1: spec-driven)
────────────────────────────────────────────────────────
This module is now a THIN ADAPTER over the organizational spec.
All numeric parameters are loaded from spec/organizational_model.yaml.

Backward compatibility is fully preserved: all existing imports continue
to work without changes (PRICE_MIN, PRICE_MAX, DEFAULT_MARKETING, etc.).

To change model parameters: edit spec/organizational_model.yaml.
Do NOT add new hardcoded constants here.
"""

from spec.spec_loader import get_spec

# ── Load spec once ────────────────────────────────────────────────────────────
_spec = get_spec()

# Resolve decision variable bounds by name
_price_var = _spec.get_decision_var("price")
_marketing_var = _spec.get_decision_var("marketing_spend")

# ── Exported constants (backward-compatible names) ────────────────────────────
UNIT_COST = _spec.business_parameters.get("unit_cost", 10.0)

# Simulation
MC_RUNS = _spec.simulation_runs

# Price optimization range
PRICE_MIN = _price_var.bounds_min
PRICE_MAX = _price_var.bounds_max
PRICE_STEPS = _price_var.steps

# Default marketing level used when optimizing over price only
DEFAULT_MARKETING = _spec.fixed_variables.get(
    "marketing_spend",
    _marketing_var.default,
)
