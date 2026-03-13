"""
system/system_model.py  (MODIFIED — Mejora 1: spec-driven)
──────────────────────────────────────────────────────────
The SystemModel now loads ALL its parameters from the organizational spec.
Nothing is hardcoded here: unit_cost and ml_model_path come from the spec.

This means changing the business domain only requires editing
spec/organizational_model.yaml — no code changes needed.
"""

import pickle

from spec.spec_loader import get_spec


class SystemModel:
    def __init__(self):
        spec = get_spec()
        # ── Load ML model path from spec (not hardcoded) ──────────────────
        self.demand_model = pickle.load(open(spec.ml_model_path, "rb"))
        # ── Load business parameters from spec ────────────────────────────
        self.unit_cost = spec.business_parameters.get("unit_cost", 10.0)
        # ── Keep a reference to the spec for inspection / observability ───
        self.spec = spec

    def evaluate(self, price: float, marketing: float) -> dict:
        """
        Evaluate the organizational model for a given (price, marketing) point.
        Returns a dict of all variable values, including the profit target.
        """
        demand = self.demand_model.predict([[price, marketing]])[0]
        revenue = price * demand
        cost = demand * self.unit_cost
        profit = revenue - cost

        return {
            "price": price,
            "marketing": marketing,
            "demand": demand,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
        }
