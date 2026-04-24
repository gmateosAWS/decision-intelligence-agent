"""api/routers/specs.py — CRUD for /v1/specs."""

from __future__ import annotations

import uuid
from typing import List

import yaml
from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_db
from api.schemas.specs import (
    SpecCreate,
    SpecListResponse,
    SpecResponse,
    SpecVersionResponse,
)

router = APIRouter(tags=["specs"])


def _spec_to_response(row, *, include_yaml: bool = False) -> SpecResponse:
    return SpecResponse(
        id=row.id,
        domain_name=row.domain_name,
        version=row.version,
        status=row.status,
        created_at=str(row.created_at),
        description=row.description,
        yaml_content=row.yaml_content if include_yaml else None,
    )


@router.get("/specs", response_model=SpecListResponse, summary="List specs")
def list_specs(db=Depends(get_db)) -> SpecListResponse:
    """Return all spec rows ordered by most-recently created."""
    from db.models import Spec

    rows = db.query(Spec).order_by(Spec.created_at.desc()).all()
    return SpecListResponse(specs=[_spec_to_response(r) for r in rows], total=len(rows))


@router.get(
    "/specs/{spec_id}",
    response_model=SpecResponse,
    summary="Get spec detail (includes YAML content)",
)
def get_spec_detail(spec_id: str, db=Depends(get_db)) -> SpecResponse:
    from db.models import Spec

    try:
        uid = uuid.UUID(spec_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid spec_id")
    row = db.get(Spec, uid)
    if row is None:
        raise HTTPException(status_code=404, detail="Spec not found")
    return _spec_to_response(row, include_yaml=True)


@router.post(
    "/specs",
    response_model=SpecResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new spec from YAML",
)
def create_spec(body: SpecCreate) -> SpecResponse:
    """Parse the supplied YAML, extract the domain name, and insert a draft spec row."""
    try:
        parsed = yaml.safe_load(body.yaml_content)
        domain_name: str = parsed["domain"]["name"]
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    from spec.spec_repository import create_spec as _create

    spec = _create(
        yaml_content=body.yaml_content,
        domain_name=domain_name,
        version=body.version,
        description=body.description,
    )
    return _spec_to_response(spec)


@router.put(
    "/specs/{spec_id}/activate",
    response_model=SpecResponse,
    summary="Activate a spec (archives the currently active one)",
)
def activate_spec(spec_id: str) -> SpecResponse:
    try:
        uid = uuid.UUID(spec_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid spec_id")

    from spec.spec_repository import activate_spec as _activate

    try:
        spec = _activate(uid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _spec_to_response(spec)


@router.get(
    "/specs/{spec_id}/versions",
    response_model=List[SpecVersionResponse],
    summary="Version history for a spec",
)
def get_spec_versions(spec_id: str, db=Depends(get_db)) -> List[SpecVersionResponse]:
    from db.models import SpecVersion

    try:
        uid = uuid.UUID(spec_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid spec_id")

    rows = (
        db.query(SpecVersion)
        .filter(SpecVersion.spec_id == uid)
        .order_by(SpecVersion.created_at.desc())
        .all()
    )
    return [
        SpecVersionResponse(
            id=r.id,
            spec_id=r.spec_id,
            version=r.version,
            change_summary=r.change_summary,
            created_at=str(r.created_at),
        )
        for r in rows
    ]
