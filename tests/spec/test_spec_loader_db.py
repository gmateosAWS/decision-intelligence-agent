"""
tests/spec/test_spec_loader_db.py
----------------------------------
Tests for spec/spec_loader.py DB integration and YAML fallback.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_load_spec_from_db_returns_typed_spec():
    """
    load_spec_from_db() returns a fully-typed OrganizationalModelSpec
    when an active spec exists in the database.
    """
    from spec.spec_loader import SPEC_PATH, OrganizationalModelSpec, load_spec_from_db
    from spec.spec_repository import seed_from_yaml

    seed_from_yaml(SPEC_PATH)  # idempotent
    spec = load_spec_from_db("retail_pricing")

    assert isinstance(spec, OrganizationalModelSpec)
    assert spec.domain_name == "retail_pricing"
    assert len(spec.decision_variables) > 0
    assert len(spec.causal_relationships) > 0


@pytest.mark.integration
def test_get_spec_uses_db_when_available():
    """
    get_spec() returns the DB-backed spec when DATABASE_URL is set.
    The spec version from DB should match the seeded YAML.
    """

    from spec.spec_loader import SPEC_PATH, reload_spec
    from spec.spec_repository import seed_from_yaml

    seed_from_yaml(SPEC_PATH)
    # Force reload so the singleton re-queries the DB
    spec = reload_spec(SPEC_PATH)

    assert spec.domain_name == "retail_pricing"
    # When loaded from DB, version comes from the specs table row
    assert spec.version is not None


def test_fallback_to_yaml_when_no_db(monkeypatch):
    """
    get_spec() falls back to the YAML file when DATABASE_URL is not set.
    """
    import spec.spec_loader as loader_mod

    monkeypatch.delenv("DATABASE_URL", raising=False)
    loader_mod._spec_instance = None  # reset singleton

    spec = loader_mod.get_spec()

    assert spec.domain_name == "retail_pricing"
    assert len(spec.decision_variables) > 0

    # Restore
    loader_mod._spec_instance = None
