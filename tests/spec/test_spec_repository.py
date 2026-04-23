"""
tests/spec/test_spec_repository.py
-----------------------------------
Integration tests for spec/spec_repository.py.

Requires a running PostgreSQL instance (docker compose up -d) and the
spec tables migrated (alembic upgrade head).

Mark: @pytest.mark.integration
"""

from __future__ import annotations

import uuid

import pytest

from spec.spec_loader import SPEC_PATH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_YAML = """\
domain:
  name: test_domain_{uid}
  description: Integration test domain
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


def _make_yaml(uid: str) -> str:
    return _SAMPLE_YAML.format(uid=uid)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_create_spec_from_yaml():
    """create_spec() inserts a draft row and a matching SpecVersion."""
    from db.engine import get_session
    from db.models import Spec, SpecVersion
    from spec.spec_repository import create_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_domain_{uid}"
    yaml_text = _make_yaml(uid)

    spec = create_spec(yaml_text, domain_name=domain, version="1.0.0")

    assert spec.domain_name == domain
    assert spec.version == "1.0.0"
    assert spec.status == "draft"

    with get_session() as session:
        row = session.get(Spec, spec.id)
        assert row is not None
        versions = session.query(SpecVersion).filter_by(spec_id=spec.id).all()
        assert len(versions) == 1
        assert versions[0].version == "1.0.0"
        session.delete(row)  # cleanup


@pytest.mark.integration
def test_get_active_spec():
    """activate_spec() makes a spec active; get_active_spec() retrieves it."""
    from spec.spec_repository import activate_spec, create_spec, get_active_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_domain_{uid}"
    spec = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(spec.id)

    active = get_active_spec(domain)
    assert active is not None
    assert active.domain_name == domain
    assert active.status == "active"

    # cleanup
    from db.engine import get_session
    from db.models import Spec

    with get_session() as session:
        row = session.get(Spec, spec.id)
        if row:
            session.delete(row)


@pytest.mark.integration
def test_update_creates_new_version():
    """update_spec() creates a new draft row; original row is unchanged."""
    from spec.spec_repository import activate_spec, create_spec, update_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_domain_{uid}"

    original = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(original.id)

    # Produce a trivially different YAML
    new_yaml = _make_yaml(uid).replace("version: '1.0.0'", "version: '1.1.0'")
    new_spec = update_spec(
        original.id,
        new_yaml,
        new_version="1.1.0",
        change_summary="bump version",
    )

    assert new_spec.version == "1.1.0"
    assert new_spec.status == "draft"

    # cleanup
    from db.engine import get_session
    from db.models import Spec

    with get_session() as session:
        for sid in (original.id, new_spec.id):
            row = session.get(Spec, sid)
            if row:
                session.delete(row)


@pytest.mark.integration
def test_only_one_active_per_domain():
    """Activating a new spec archives the previously active one."""
    from spec.spec_repository import activate_spec, create_spec, get_active_spec

    uid = uuid.uuid4().hex[:8]
    domain = f"test_domain_{uid}"

    spec_v1 = create_spec(_make_yaml(uid), domain_name=domain, version="1.0.0")
    activate_spec(spec_v1.id)

    new_yaml = _make_yaml(uid).replace("version: '1.0.0'", "version: '2.0.0'")
    spec_v2 = create_spec(new_yaml, domain_name=domain, version="2.0.0")
    activate_spec(spec_v2.id)

    # Only v2 should be active
    active = get_active_spec(domain)
    assert active is not None
    assert active.version == "2.0.0"

    # v1 should be archived
    from db.engine import get_session
    from db.models import Spec

    with get_session() as session:
        v1 = session.get(Spec, spec_v1.id)
        assert v1 is not None
        assert v1.status == "archived"
        session.delete(v1)
        v2 = session.get(Spec, spec_v2.id)
        if v2:
            session.delete(v2)


@pytest.mark.integration
def test_seed_from_yaml_file():
    """seed_from_yaml() creates an active spec; calling it twice is a no-op."""
    from spec.spec_repository import seed_from_yaml

    # Use the real YAML but with a temp override of domain name is not needed;
    # just test idempotency against the real YAML (retail_pricing domain)
    spec1 = seed_from_yaml(SPEC_PATH)
    assert spec1.status == "active"
    assert spec1.domain_name == "retail_pricing"

    # Second call must be a no-op (same object returned)
    spec2 = seed_from_yaml(SPEC_PATH)
    assert spec2.id == spec1.id


@pytest.mark.integration
def test_run_records_spec_version():
    """AgentRun rows written via observer carry spec_id and spec_version."""

    from db.engine import get_session
    from db.models import AgentRun
    from evaluation.observer import AgentObserver
    from spec.spec_repository import get_active_spec, seed_from_yaml

    seed_from_yaml(SPEC_PATH)
    active = get_active_spec("retail_pricing")
    assert active is not None

    obs = AgentObserver()
    obs.start_run("test query for spec traceability")
    obs.set_spec(str(active.id), active.version)
    obs.end_run(success=True)

    with get_session() as session:
        run = (
            session.query(AgentRun)
            .filter_by(spec_version=active.version)
            .order_by(AgentRun.timestamp.desc())
            .first()
        )
        assert run is not None
        assert run.spec_id == active.id
        assert run.spec_version == active.version
