"""
spec/spec_repository.py
-----------------------
CRUD operations for the specs and spec_versions tables.

All functions require DATABASE_URL to be set. Callers that want YAML fallback
should check db.engine.check_connection() before calling these.

Public API
----------
  create_spec(yaml_content, domain_name, version, *, created_by, description) -> Spec
  get_active_spec(domain_name) -> Spec | None
  get_spec_by_version(domain_name, version) -> Spec | None
  list_specs(domain_name?) -> List[Spec]
  update_spec(spec_id, yaml_content, new_version, change_summary, *, created_by) -> Spec
  activate_spec(spec_id) -> Spec
  seed_from_yaml(yaml_path) -> Spec   # idempotent — no-op if already seeded
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import List, Optional

import yaml

from db.engine import get_session
from db.models import Spec, SpecVersion

logger = logging.getLogger(__name__)

_INITIAL_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_spec(
    yaml_content: str,
    domain_name: str,
    version: str,
    *,
    created_by: Optional[str] = None,
    description: Optional[str] = None,
) -> Spec:
    """Insert a new spec row (status=draft) and record the first SpecVersion."""
    parsed = yaml.safe_load(yaml_content)
    with get_session() as session:
        spec = Spec(
            domain_name=domain_name,
            version=version,
            status="draft",
            yaml_content=yaml_content,
            parsed_content=parsed,
            created_by=created_by,
            description=description,
        )
        session.add(spec)
        session.flush()  # populate spec.id before creating version

        session.add(
            SpecVersion(
                spec_id=spec.id,
                version=version,
                yaml_content=yaml_content,
                parsed_content=parsed,
                change_summary="Initial version",
                created_by=created_by,
            )
        )
        session.expunge(spec)
        return spec


def get_active_spec(domain_name: str) -> Optional[Spec]:
    """Return the single active spec for *domain_name*, or None."""
    with get_session() as session:
        row = (
            session.query(Spec)
            .filter_by(domain_name=domain_name, status="active")
            .first()
        )
        if row is not None:
            session.expunge(row)
        return row


def get_spec_by_version(domain_name: str, version: str) -> Optional[Spec]:
    """Return a spec by (domain_name, version), or None."""
    with get_session() as session:
        row = (
            session.query(Spec)
            .filter_by(domain_name=domain_name, version=version)
            .first()
        )
        if row is not None:
            session.expunge(row)
        return row


def list_specs(domain_name: Optional[str] = None) -> List[Spec]:
    """List all specs, optionally filtered by domain_name, newest first."""
    with get_session() as session:
        q = session.query(Spec)
        if domain_name:
            q = q.filter_by(domain_name=domain_name)
        rows = q.order_by(Spec.created_at.desc()).all()
        for r in rows:
            session.expunge(r)
        return rows


def update_spec(
    spec_id: uuid.UUID,
    yaml_content: str,
    new_version: str,
    change_summary: Optional[str] = None,
    *,
    created_by: Optional[str] = None,
) -> Spec:
    """
    Create a new spec row derived from *spec_id* with the updated YAML.

    The new row has status='draft'. The caller must call activate_spec()
    to promote it. A SpecVersion audit record is created for the new spec.
    """
    parsed = yaml.safe_load(yaml_content)
    with get_session() as session:
        parent = session.get(Spec, spec_id)
        if parent is None:
            raise ValueError(f"Spec {spec_id} not found")

        new_spec = Spec(
            domain_name=parent.domain_name,
            version=new_version,
            status="draft",
            yaml_content=yaml_content,
            parsed_content=parsed,
            created_by=created_by,
            description=parent.description,
        )
        session.add(new_spec)
        session.flush()

        session.add(
            SpecVersion(
                spec_id=new_spec.id,
                version=new_version,
                yaml_content=yaml_content,
                parsed_content=parsed,
                change_summary=change_summary or f"Updated from {parent.version}",
                created_by=created_by,
            )
        )
        session.expunge(new_spec)
        return new_spec


def activate_spec(spec_id: uuid.UUID) -> Spec:
    """
    Set *spec_id* to status='active' and archive any other active spec
    for the same domain. Only one spec per domain can be active at a time.
    """
    with get_session() as session:
        target = session.get(Spec, spec_id)
        if target is None:
            raise ValueError(f"Spec {spec_id} not found")

        # Archive current active specs for this domain
        session.query(Spec).filter(
            Spec.domain_name == target.domain_name,
            Spec.status == "active",
            Spec.id != spec_id,
        ).update({"status": "archived"})

        target.status = "active"
        session.flush()
        session.expunge(target)
        return target


def seed_from_yaml(yaml_path: Path) -> Spec:
    """
    Import *yaml_path* into the specs table as version 1.0.0 with status='active'.

    Idempotent: if a spec for the same domain_name already exists in the DB,
    returns the existing active spec without modifying anything.
    """
    yaml_text = yaml_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(yaml_text)
    domain_name = parsed["domain"]["name"]

    # Check if any spec already exists for this domain
    existing = get_active_spec(domain_name)
    if existing is not None:
        logger.info(
            "seed_from_yaml: spec already exists for '%s' (v%s) — skipping",
            domain_name,
            existing.version,
        )
        return existing

    logger.info(
        "seed_from_yaml: seeding spec for domain '%s' from %s", domain_name, yaml_path
    )
    spec = create_spec(
        yaml_content=yaml_text,
        domain_name=domain_name,
        version=_INITIAL_VERSION,
        description=f"Initial seed from {yaml_path.name}",
    )
    return activate_spec(spec.id)
