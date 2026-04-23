"""
spec/spec_loader.py
───────────────────
Loads and parses the organizational model specification.

Backend selection (same dual-backend pattern as the rest of the system):
  DATABASE_URL set  → reads from the 'specs' table (Postgres)
  DATABASE_URL unset → reads from the YAML file (original behaviour)

Design principle (spec-driven):
  The spec is the contract. Code components receive structured objects,
  never raw YAML dicts. This makes the boundary explicit and testable.

Public API (unchanged):
  get_spec()           -> OrganizationalModelSpec   (singleton, tries DB first)
  reload_spec()        -> OrganizationalModelSpec   (force reload)
  load_spec(path)      -> OrganizationalModelSpec   (always reads YAML file)
  load_spec_from_db(domain_name) -> OrganizationalModelSpec
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

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
class DemandModelSpec:
    """Coefficients of the synthetic linear demand function.

    Formula:
        demand = base_demand
                 + price_elasticity * price
                 + marketing_effect * marketing_spend
                 + noise(sigma=noise_sigma)

    These values are the single source of truth for both data generation
    (generate_data.py) and any analytical validation of model predictions.
    """

    base_demand: float  # Intercept: baseline units at price=0, marketing=0
    price_elasticity: float  # Units lost per EUR increase in price (negative)
    marketing_effect: float  # Units gained per EUR of marketing spend
    noise_sigma: float  # Std dev of Gaussian demand noise (units)


@dataclass
class DataGenerationSpec:
    """Parameters controlling the synthetic training dataset.

    All bounds here should mirror the decision variable bounds so that the
    trained ML model interpolates (not extrapolates) at inference time.
    """

    n_samples: int
    random_seed: int
    price_min: float
    price_max: float
    marketing_min: float
    marketing_max: float


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

    # Demand model coefficients (spec-driven, used by generate_data.py)
    demand_model: DemandModelSpec

    # Data generation configuration (spec-driven, used by generate_data.py)
    data_generation: DataGenerationSpec

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


def _parse_raw(raw: Dict) -> OrganizationalModelSpec:
    """Parse a raw YAML dict (already loaded) into a typed OrganizationalModelSpec."""

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

    # Causal relationships -> expand multi-target entries
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

    # Demand model coefficients
    dm_raw = raw.get("demand_model", {})
    demand_model = DemandModelSpec(
        base_demand=float(dm_raw.get("base_demand", 120.0)),
        price_elasticity=float(dm_raw.get("price_elasticity", -1.6)),
        marketing_effect=float(dm_raw.get("marketing_effect", 0.0009)),
        noise_sigma=float(dm_raw.get("noise_sigma", 5.0)),
    )

    # Data generation config
    dg_raw = raw.get("data_generation", {})
    data_generation = DataGenerationSpec(
        n_samples=int(dg_raw.get("n_samples", 2000)),
        random_seed=int(dg_raw.get("random_seed", 42)),
        price_min=float(dg_raw.get("price_min", 10.0)),
        price_max=float(dg_raw.get("price_max", 50.0)),
        marketing_min=float(dg_raw.get("marketing_min", 1000.0)),
        marketing_max=float(dg_raw.get("marketing_max", 20000.0)),
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
        demand_model=demand_model,
        data_generation=data_generation,
        optimization_target=opt.get("target", "profit"),
        optimization_method=opt.get("method", "grid_search"),
        optimization_decision_vars=opt.get("decision_variables", []),
        fixed_variables={
            k: float(v) for k, v in opt.get("fixed_variables", {}).items()
        },
    )


def load_spec(path: Path = SPEC_PATH) -> OrganizationalModelSpec:
    """Load and parse the YAML spec file into a typed OrganizationalModelSpec."""
    with open(path, "r", encoding="utf-8") as f:
        raw: Dict = yaml.safe_load(f)
    return _parse_raw(raw)


def load_spec_from_db(domain_name: str) -> OrganizationalModelSpec:
    """
    Load the active spec for *domain_name* from Postgres.

    Raises RuntimeError if no active spec is found.
    """
    from spec.spec_repository import get_active_spec

    spec_row = get_active_spec(domain_name)
    if spec_row is None:
        raise RuntimeError(
            f"No active spec found for domain '{domain_name}' in the database. "
            "Run seed_from_yaml() first or set DATABASE_URL='' to use the YAML file."
        )
    raw = spec_row.parsed_content
    logger.debug(
        "Loaded spec for domain '%s' v%s from DB", domain_name, spec_row.version
    )
    return _parse_raw(raw)


# ── SINGLETON ─────────────────────────────────────────────────────────────────
# The spec is loaded once at startup and shared across all components.

_spec_instance: Optional[OrganizationalModelSpec] = None


def get_spec(path: Path = SPEC_PATH) -> OrganizationalModelSpec:
    """
    Return the singleton spec instance, loading it on first call.

    Resolution order:
      1. DATABASE_URL set → load from Postgres (active spec for the YAML domain)
      2. Postgres unavailable or no active spec → fall back to YAML file
    """
    global _spec_instance  # noqa: PLW0603
    if _spec_instance is None:
        _spec_instance = _load_spec_with_fallback(path)
    return _spec_instance


def _load_spec_with_fallback(path: Path) -> OrganizationalModelSpec:
    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        try:
            # Peek at the domain name from the YAML to know which domain to query
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            domain_name = raw["domain"]["name"]
            spec = load_spec_from_db(domain_name)
            logger.info("Spec loaded from DB: domain=%s v%s", domain_name, spec.version)
            return spec
        except Exception as exc:
            logger.warning(
                "Could not load spec from DB (%s) — falling back to YAML file", exc
            )
    spec = load_spec(path)
    logger.info("Spec loaded from YAML file: %s", path)
    return spec


def reload_spec(path: Path = SPEC_PATH) -> OrganizationalModelSpec:
    """Force reload of the spec (useful in tests or hot-reload scenarios)."""
    global _spec_instance  # noqa: PLW0603
    _spec_instance = _load_spec_with_fallback(path)
    return _spec_instance
