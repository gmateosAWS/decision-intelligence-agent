"""
tests/spec/test_spec_repository_semver.py
------------------------------------------
Integration tests for semver enforcement in spec/spec_repository.py.

Requires a running PostgreSQL instance (docker compose up -d) and the
spec tables migrated (alembic upgrade head).

Mark: @pytest.mark.integration
"""

from __future__ import annotations

import uuid

import pytest

# ---------------------------------------------------------------------------
# Shared YAML fixture (unique domain per test via uid suffix)
# ---------------------------------------------------------------------------

_SAMPLE_YAML = """\
domain:
  name: test_semver_{uid}
  description: Semver integration test domain
  version: '1.0.0'
variables:
  decisions:
    - name: price
      description: Unit sale price
      unit: EUR
      bounds: {{min: 10, max: 50, steps: 10}}
      default: 20
  intermediate: []
  targets:
    - name: profit
      description: Net profit
      unit: EUR
      formula: revenue - cost
      optimize: maximize
causal_relationships:
  - from: price
    to: profit
    type: direct
    description: price affects profit
constraints: []
business_parameters: {{}}
simulation:
  monte_carlo_runs: 100
  noise_std: 0.1
demand_model:
  base_demand: 100.0
  price_elasticity: -1.0
  marketing_effect: 0.001
  noise_sigma: 5.0
data_generation:
  n_samples: 100
  random_seed: 42
  price_min: 10.0
  price_max: 50.0
  marketing_min: 1000.0
  marketing_max: 20000.0
optimization:
  target: profit
  method: grid_search
  decision_variables: [price]
  fixed_variables: {{}}
"""


def _make_yaml(uid: str, version: str = "1.0.0") -> str:
    return _SAMPLE_YAML.format(uid=uid).replace(
        "version: '1.0.0'", f"version: '{version}'"
    )


def _cleanup(*spec_ids) -> None:
    from db.engine import get_session
    from db.models import Spec

    with get_session() as session:
        for sid in spec_ids:
            if sid is None:
                continue
            row = session.get(Spec, sid)
            if row:
                session.delete(row)


# ---------------------------------------------------------------------------
# create_spec semver validation
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_spec_validates_semver() -> None:
    """create_spec() raises ValueError for invalid semver strings."""
    from spec.spec_repository import create_spec

    uid = uuid.uuid4().hex[:8]
    with pytest.raises(ValueError, match="semver"):
        create_spec(
            _make_yaml(uid), domain_name=f"test_semver_{uid}", version="not-semver"
        )


@pytest.mark.integration
def test_create_spec_rejects_partial_version() -> None:
    from spec.spec_repository import create_spec

    uid = uuid.uuid4().hex[:8]
    with pytest.raises(ValueError):
        create_spec(_make_yaml(uid), domain_name=f"test_semver_{uid}", version="1.2")


@pytest.mark.integration
def test_create_spec_defaults_to_1_0_0() -> None:
    """create_spec() with no version argument defaults to '1.0.0'."""
    from spec.spec_repository import create_spec

    uid = uuid.uuid4().hex[:8]
    spec = create_spec(_make_yaml(uid), domain_name=f"test_semver_{uid}")
    assert spec.version == "1.0.0"
    _cleanup(spec.id)


# ---------------------------------------------------------------------------
# update_spec semver + auto-bump
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_update_spec_auto_bumps_patch() -> None:
    """update_spec() without new_version auto-detects PATCH (description change)."""
    from spec.spec_repository import activate_spec, create_spec, update_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_semver_{uid}"
    original = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(original.id)

    new_yaml = _make_yaml(uid).replace(
        "Semver integration test domain", "Updated description only"
    )
    new_spec = update_spec(original.id, new_yaml)

    assert new_spec.version == "1.0.1", f"Expected 1.0.1, got {new_spec.version}"
    assert new_spec.status == "draft"
    _cleanup(original.id, new_spec.id)


@pytest.mark.integration
def test_update_spec_auto_bumps_major() -> None:
    """update_spec() without new_version detects MAJOR when a variable is added."""
    from spec.spec_repository import activate_spec, create_spec, update_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_semver_{uid}"
    original = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(original.id)

    # Add a second decision variable → MAJOR bump
    new_yaml = _make_yaml(uid)
    new_yaml = new_yaml.replace(
        "      default: 20\n  intermediate:",
        "      default: 20\n    - name: marketing\n"
        "      bounds: {min: 0, max: 10000, steps: 5}\n"
        "      default: 1000\n  intermediate:",
    )
    new_spec = update_spec(original.id, new_yaml)

    assert new_spec.version == "2.0.0", f"Expected 2.0.0, got {new_spec.version}"
    _cleanup(original.id, new_spec.id)


@pytest.mark.integration
def test_update_spec_rejects_lower_version() -> None:
    """update_spec() with new_version below current max raises ValueError."""
    from spec.spec_repository import activate_spec, create_spec, update_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_semver_{uid}"
    original = create_spec(
        _make_yaml(uid, "2.0.0"), domain_name=domain, version="2.0.0"
    )
    activate_spec(original.id)

    with pytest.raises(ValueError, match="greater than"):
        update_spec(original.id, _make_yaml(uid, "1.0.0"), new_version="1.0.0")

    _cleanup(original.id)


@pytest.mark.integration
def test_update_spec_rejects_invalid_semver() -> None:
    """update_spec() rejects explicitly provided non-semver new_version."""
    from spec.spec_repository import activate_spec, create_spec, update_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_semver_{uid}"
    original = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(original.id)

    with pytest.raises(ValueError, match="semver"):
        update_spec(original.id, _make_yaml(uid), new_version="bad-version")

    _cleanup(original.id)


@pytest.mark.integration
def test_update_spec_auto_includes_bump_type_in_summary() -> None:
    """Auto-bumped specs include the bump type in the change_summary."""
    from db.engine import get_session
    from db.models import SpecVersion
    from spec.spec_repository import activate_spec, create_spec, update_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_semver_{uid}"
    original = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(original.id)

    new_yaml = _make_yaml(uid).replace("Semver integration test domain", "Minor tweak")
    new_spec = update_spec(original.id, new_yaml)

    with get_session() as session:
        sv = session.query(SpecVersion).filter_by(spec_id=new_spec.id).first()
        assert sv is not None
        assert "patch" in (sv.change_summary or "").lower()

    _cleanup(original.id, new_spec.id)
