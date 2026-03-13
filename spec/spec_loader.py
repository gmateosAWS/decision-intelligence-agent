"""
spec/spec_loader.py
───────────────────
Loads and parses the organizational model specification (YAML).
Provides a typed, validated interface to the rest of the system.

Design principle (spec-driven):
  The spec is the contract. Code components receive structured objects,
  never raw YAML dicts. This makes the boundary explicit and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Default path: spec/ directory next to this file
SPEC_PATH = Path(__file__).parent / "organizational_model.yaml"


# ── TYPED DATA CLASSES ────────────────────────────────────────────────────────


@dataclass
class DecisionVariable:
    """A controllable input to the organizational model."""

    name: str
    description: str
    unit: str
    bounds_min: float
    bounds_max: float
    steps: int
    default: float


@dataclass
class IntermediateVariable:
    """A derived or ML-estimated variable."""

    name: str
    description: str
    unit: str
    estimated_by: Optional[str]  # "ml_model" | "formula" | None
    ml_model_path: Optional[str]
    formula: Optional[str]


@dataclass
class TargetVariable:
    """A business outcome variable to track or optimize."""

    name: str
    description: str
    unit: str
    formula: str
    optimize: str  # "maximize" | "minimize" | "none"


@dataclass
class CausalRelationship:
    """One directed edge (or fan-in) in the causal DAG."""

    from_vars: List[str]
    to_var: str
    rel_type: str
    description: str


@dataclass
class ConstraintSpec:
    expression: str
    description: str


@dataclass
class OrganizationalModelSpec:
    """Complete, validated representation of the organizational model spec."""

    # Domain metadata
    domain_name: str
    domain_description: str
    version: str

    # Variables
    decision_variables: List[DecisionVariable]
    intermediate_variables: List[IntermediateVariable]
    target_variables: List[TargetVariable]

    # Structure
    causal_relationships: List[CausalRelationship]
    constraints: List[ConstraintSpec]

    # Parameters
    business_parameters: Dict[str, Any]
    simulation_runs: int
    noise_std: float

    # Optimization
    optimization_target: str
    optimization_method: str
    optimization_decision_vars: List[str]
    fixed_variables: Dict[str, float]

    # ── Convenience helpers ───────────────────────────────────────────────────

    def get_decision_var(self, name: str) -> DecisionVariable:
        for v in self.decision_variables:
            if v.name == name:
                return v
        raise KeyError(f"Decision variable '{name}' not found in spec.")

    @property
    def ml_model_path(self) -> str:
        """Path of the primary ML model (first intermediate with ml_model)."""
        for v in self.intermediate_variables:
            if v.estimated_by == "ml_model" and v.ml_model_path:
                return v.ml_model_path
        return "models/demand_model.pkl"


# ── PARSER ────────────────────────────────────────────────────────────────────


def load_spec(path: Path = SPEC_PATH) -> OrganizationalModelSpec:
    """Load and parse the YAML spec file into a typed OrganizationalModelSpec."""
    with open(path, "r", encoding="utf-8") as f:
        raw: Dict = yaml.safe_load(f)

    # Decision variables
    decision_vars: List[DecisionVariable] = []
    for v in raw["variables"]["decisions"]:
        b = v["bounds"]
        decision_vars.append(
            DecisionVariable(
                name=v["name"],
                description=v["description"],
                unit=v.get("unit", ""),
                bounds_min=float(b["min"]),
                bounds_max=float(b["max"]),
                steps=int(b.get("steps", 50)),
                default=float(v.get("default", b["min"])),
            )
        )

    # Intermediate variables
    intermediate_vars: List[IntermediateVariable] = []
    for v in raw["variables"].get("intermediate", []):
        intermediate_vars.append(
            IntermediateVariable(
                name=v["name"],
                description=v["description"],
                unit=v.get("unit", ""),
                estimated_by=v.get("estimated_by"),
                ml_model_path=v.get("ml_model_path"),
                formula=v.get("formula"),
            )
        )

    # Target variables
    target_vars: List[TargetVariable] = []
    for v in raw["variables"].get("targets", []):
        target_vars.append(
            TargetVariable(
                name=v["name"],
                description=v["description"],
                unit=v.get("unit", ""),
                formula=v.get("formula", ""),
                optimize=v.get("optimize", "none"),
            )
        )

    # Causal relationships → expand multi-target entries
    relationships: List[CausalRelationship] = []
    for rel in raw.get("causal_relationships", []):
        froms = rel["from"] if isinstance(rel["from"], list) else [rel["from"]]
        targets = rel["to"] if isinstance(rel["to"], list) else [rel["to"]]
        for t in targets:
            relationships.append(
                CausalRelationship(
                    from_vars=froms,
                    to_var=t,
                    rel_type=rel.get("type", "unknown"),
                    description=rel.get("description", ""),
                )
            )

    # Constraints
    constraints: List[ConstraintSpec] = []
    for c in raw.get("constraints", []):
        constraints.append(
            ConstraintSpec(
                expression=c["expression"],
                description=c.get("description", ""),
            )
        )

    sim = raw.get("simulation", {})
    opt = raw.get("optimization", {})

    return OrganizationalModelSpec(
        domain_name=raw["domain"]["name"],
        domain_description=raw["domain"]["description"],
        version=raw["domain"]["version"],
        decision_variables=decision_vars,
        intermediate_variables=intermediate_vars,
        target_variables=target_vars,
        causal_relationships=relationships,
        constraints=constraints,
        business_parameters=raw.get("business_parameters", {}),
        simulation_runs=int(sim.get("monte_carlo_runs", 500)),
        noise_std=float(sim.get("noise_std", 0.1)),
        optimization_target=opt.get("target", "profit"),
        optimization_method=opt.get("method", "grid_search"),
        optimization_decision_vars=opt.get("decision_variables", []),
        fixed_variables={
            k: float(v) for k, v in opt.get("fixed_variables", {}).items()
        },
    )


# ── SINGLETON ─────────────────────────────────────────────────────────────────
# The spec is loaded once at startup and shared across all components.
# This avoids repeated I/O and ensures consistency within a process.

_spec_instance: Optional[OrganizationalModelSpec] = None


def get_spec(path: Path = SPEC_PATH) -> OrganizationalModelSpec:
    """Return the singleton spec instance, loading it on first call."""
    global _spec_instance
    if _spec_instance is None:
        _spec_instance = load_spec(path)
    return _spec_instance


def reload_spec(path: Path = SPEC_PATH) -> OrganizationalModelSpec:
    """Force reload of the spec (useful in tests or hot-reload scenarios)."""
    global _spec_instance
    _spec_instance = load_spec(path)
    return _spec_instance
