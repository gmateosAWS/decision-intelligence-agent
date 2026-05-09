"""
spec/versioning.py
──────────────────
Semantic versioning logic for specs.

Version format: MAJOR.MINOR.PATCH
- MAJOR: breaking changes (variable set or causal graph changed)
- MINOR: non-breaking additions (parameter bounds adjusted, new metadata)
- PATCH: documentation, descriptions, cosmetic changes

Designed to support future spec migration (item 10.4) and validation (item 3.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Set, Tuple

import yaml

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class BumpType(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


@dataclass(frozen=True)
class SpecVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version_str: str) -> "SpecVersion":
        """Parse '1.2.3' into SpecVersion. Raises ValueError if invalid."""
        if not validate_version(version_str):
            raise ValueError(
                f"Invalid semver string: {version_str!r}. Expected X.Y.Z "
                f"with non-negative integers."
            )
        parts = version_str.split(".")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def bump(self, bump_type: BumpType) -> "SpecVersion":
        """Return a new version bumped by the given type.

        major: X+1.0.0 · minor: X.Y+1.0 · patch: X.Y.Z+1
        """
        if bump_type == BumpType.MAJOR:
            return SpecVersion(self.major + 1, 0, 0)
        if bump_type == BumpType.MINOR:
            return SpecVersion(self.major, self.minor + 1, 0)
        return SpecVersion(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def _tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __gt__(self, other: "SpecVersion") -> bool:  # type: ignore[override]
        return self._tuple() > other._tuple()

    def __ge__(self, other: "SpecVersion") -> bool:  # type: ignore[override]
        return self._tuple() >= other._tuple()

    def __lt__(self, other: "SpecVersion") -> bool:  # type: ignore[override]
        return self._tuple() < other._tuple()

    def __le__(self, other: "SpecVersion") -> bool:  # type: ignore[override]
        return self._tuple() <= other._tuple()


def validate_version(version_str: str) -> bool:
    """Check if a string is valid semver (X.Y.Z, all non-negative integers)."""
    return bool(_SEMVER_RE.match(version_str))


# ---------------------------------------------------------------------------
# Structural key extraction — private
# ---------------------------------------------------------------------------


def _extract_structural_keys(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the structural elements that drive bump-type detection."""
    variables = parsed.get("variables", {})

    decision_names: Set[str] = {
        d.get("name", "") for d in variables.get("decisions", [])
    }
    target_names: Set[str] = {t.get("name", "") for t in variables.get("targets", [])}
    intermediate_names: Set[str] = {
        i.get("name", "") for i in variables.get("intermediate", [])
    }

    causal_edges: FrozenSet[Tuple[Any, Any]] = frozenset(
        (r.get("from"), r.get("to")) for r in parsed.get("causal_relationships", [])
    )

    bounds: Dict[str, Tuple[Any, Any, Any]] = {}
    for dv in variables.get("decisions", []):
        name = dv.get("name", "")
        b = dv.get("bounds", {})
        bounds[name] = (b.get("min"), b.get("max"), b.get("steps"))

    return {
        "decision_names": decision_names,
        "target_names": target_names,
        "intermediate_names": intermediate_names,
        "causal_edges": causal_edges,
        "bounds": bounds,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_bump_type(old_yaml: str, new_yaml: str) -> BumpType:
    """Compare two spec YAMLs and determine the required bump type.

    - Variables added/removed/renamed → MAJOR
    - Causal relationships changed → MAJOR
    - Parameter bounds changed → MINOR
    - Description/metadata only → PATCH

    TODO(product): when item 3.3 lands, this integrates with spec validation.
    """
    old = yaml.safe_load(old_yaml)
    new = yaml.safe_load(new_yaml)

    old_keys = _extract_structural_keys(old)
    new_keys = _extract_structural_keys(new)

    if (
        old_keys["decision_names"] != new_keys["decision_names"]
        or old_keys["target_names"] != new_keys["target_names"]
        or old_keys["intermediate_names"] != new_keys["intermediate_names"]
        or old_keys["causal_edges"] != new_keys["causal_edges"]
    ):
        return BumpType.MAJOR

    if old_keys["bounds"] != new_keys["bounds"]:
        return BumpType.MINOR

    return BumpType.PATCH
