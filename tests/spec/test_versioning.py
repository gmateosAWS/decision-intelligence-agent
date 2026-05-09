"""
tests/spec/test_versioning.py
------------------------------
Unit tests for spec/versioning.py.  No database required.
"""

from __future__ import annotations

import pytest

from spec.versioning import BumpType, SpecVersion, detect_bump_type, validate_version

# ---------------------------------------------------------------------------
# Minimal YAML fixtures
# ---------------------------------------------------------------------------

_BASE_YAML = """\
domain:
  name: test_domain
variables:
  decisions:
    - name: price
      bounds: {min: 10.0, max: 50.0, steps: 10}
      default: 25.0
  targets:
    - name: profit
  intermediate: []
causal_relationships:
  - from: price
    to: profit
"""


def _yaml_with_extra_decision() -> str:
    """Adds a second decision variable → structural MAJOR change."""
    return _BASE_YAML.replace(
        "  targets:\n",
        "    - name: marketing\n"
        "      bounds: {min: 0, max: 10000, steps: 10}\n"
        "      default: 1000.0\n"
        "  targets:\n",
    )


def _yaml_wider_bounds() -> str:
    """Widens price.bounds.max → non-breaking MINOR change."""
    return _BASE_YAML.replace("max: 50.0", "max: 80.0")


def _yaml_new_description() -> str:
    """Adds a domain description field → cosmetic PATCH change."""
    return _BASE_YAML.replace(
        "  name: test_domain\n", "  name: test_domain\n  description: Updated\n"
    )


# ---------------------------------------------------------------------------
# validate_version
# ---------------------------------------------------------------------------


def test_validate_version_valid() -> None:
    assert validate_version("1.2.3") is True
    assert validate_version("0.0.0") is True
    assert validate_version("100.200.300") is True


def test_validate_version_invalid() -> None:
    for bad in ["abc", "1.2", "", "1.2.3.4", "v1.0.0", "-1.0.0", "1.0"]:
        assert validate_version(bad) is False, f"Expected False for {bad!r}"


# ---------------------------------------------------------------------------
# SpecVersion.parse
# ---------------------------------------------------------------------------


def test_parse_valid_version() -> None:
    sv = SpecVersion.parse("1.2.3")
    assert sv == SpecVersion(1, 2, 3)
    assert str(sv) == "1.2.3"


def test_parse_zero_version() -> None:
    sv = SpecVersion.parse("0.0.0")
    assert sv == SpecVersion(0, 0, 0)


@pytest.mark.parametrize("bad", ["abc", "1.2", "", "1.2.3.4", "v1.0.0", "-1.0.0"])
def test_parse_invalid_version(bad: str) -> None:
    with pytest.raises(ValueError):
        SpecVersion.parse(bad)


# ---------------------------------------------------------------------------
# SpecVersion.bump
# ---------------------------------------------------------------------------


def test_bump_major() -> None:
    assert SpecVersion.parse("1.2.3").bump(BumpType.MAJOR) == SpecVersion(2, 0, 0)


def test_bump_major_resets_minor_patch() -> None:
    assert SpecVersion.parse("0.9.9").bump(BumpType.MAJOR) == SpecVersion(1, 0, 0)


def test_bump_minor() -> None:
    assert SpecVersion.parse("1.2.3").bump(BumpType.MINOR) == SpecVersion(1, 3, 0)


def test_bump_minor_resets_patch() -> None:
    assert SpecVersion.parse("1.2.9").bump(BumpType.MINOR) == SpecVersion(1, 3, 0)


def test_bump_patch() -> None:
    assert SpecVersion.parse("1.2.3").bump(BumpType.PATCH) == SpecVersion(1, 2, 4)


def test_bump_from_zero() -> None:
    assert SpecVersion(0, 0, 0).bump(BumpType.PATCH) == SpecVersion(0, 0, 1)


# ---------------------------------------------------------------------------
# SpecVersion comparisons
# ---------------------------------------------------------------------------


def test_version_comparison_gt() -> None:
    assert SpecVersion.parse("1.2.3") > SpecVersion.parse("1.2.2")
    assert SpecVersion.parse("2.0.0") > SpecVersion.parse("1.9.9")
    assert SpecVersion.parse("1.3.0") > SpecVersion.parse("1.2.99")


def test_version_comparison_lt() -> None:
    assert SpecVersion.parse("1.2.2") < SpecVersion.parse("1.2.3")
    assert SpecVersion.parse("1.9.9") < SpecVersion.parse("2.0.0")


def test_version_comparison_eq() -> None:
    assert SpecVersion.parse("1.2.3") == SpecVersion.parse("1.2.3")
    assert SpecVersion.parse("1.2.3") >= SpecVersion.parse("1.2.3")
    assert SpecVersion.parse("1.2.3") <= SpecVersion.parse("1.2.3")


def test_version_max() -> None:
    versions = [
        SpecVersion.parse("1.0.0"),
        SpecVersion.parse("1.9.9"),
        SpecVersion.parse("2.0.0"),
        SpecVersion.parse("1.2.3"),
    ]
    assert max(versions) == SpecVersion.parse("2.0.0")


# ---------------------------------------------------------------------------
# detect_bump_type
# ---------------------------------------------------------------------------


def test_detect_bump_variable_added() -> None:
    assert detect_bump_type(_BASE_YAML, _yaml_with_extra_decision()) == BumpType.MAJOR


def test_detect_bump_variable_removed() -> None:
    # Remove the only decision variable → MAJOR
    new = _BASE_YAML.replace(
        "  decisions:\n"
        "    - name: price\n"
        "      bounds: {min: 10.0, max: 50.0, steps: 10}\n"
        "      default: 25.0\n",
        "  decisions: []\n",
    )
    assert detect_bump_type(_BASE_YAML, new) == BumpType.MAJOR


def test_detect_bump_causal_edge_changed() -> None:
    new = _BASE_YAML.replace(
        "  - from: price\n    to: profit", "  - from: price\n    to: demand"
    )
    assert detect_bump_type(_BASE_YAML, new) == BumpType.MAJOR


def test_detect_bump_param_changed() -> None:
    assert detect_bump_type(_BASE_YAML, _yaml_wider_bounds()) == BumpType.MINOR


def test_detect_bump_description_only() -> None:
    assert detect_bump_type(_BASE_YAML, _yaml_new_description()) == BumpType.PATCH


def test_detect_bump_identical_yaml() -> None:
    assert detect_bump_type(_BASE_YAML, _BASE_YAML) == BumpType.PATCH
