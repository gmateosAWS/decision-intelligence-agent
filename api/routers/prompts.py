"""
api/routers/prompts.py
----------------------
CRUD + lifecycle endpoints for the Prompt Registry (item 10.1).

Endpoints
---------
GET    /v1/prompts                          List prompts (filterable by stage, status)
GET    /v1/prompts/{id}/{version}           Prompt detail
POST   /v1/prompts                          Create a draft prompt
PUT    /v1/prompts/{id}/{version}/certify   Promote to certified
PUT    /v1/prompts/{id}/{version}/deprecate Deprecate a prompt
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from api.schemas.prompts import (
    PromptCreateRequest,
    PromptDeprecateRequest,
    PromptListResponse,
    PromptResponse,
)

router = APIRouter(tags=["prompts"])


def _to_response(record) -> PromptResponse:
    return PromptResponse(
        id=record.id,
        version=record.version,
        status=(
            record.status.value if hasattr(record.status, "value") else record.status
        ),
        stage=record.stage,
        content=record.content,
        variables=record.variables,
        owner=record.owner,
        description=record.description,
        created_at=record.created_at,
        changed_at=record.changed_at,
        sunset_date=record.sunset_date,
        replacement_id=record.replacement_id,
        adr=record.adr,
    )


@router.get("/prompts", response_model=PromptListResponse, summary="List prompts")
def list_prompts(
    stage: Optional[str] = None,
    status: Optional[str] = None,
):
    from prompts.models import PromptStatus
    from prompts.registry import list_prompts as _list

    status_filter = None
    if status is not None:
        try:
            status_filter = PromptStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid status '{status}'."
                    " Valid values: draft, certified, deprecated."
                ),
            )

    records = _list(stage=stage, status=status_filter)
    return PromptListResponse(
        total=len(records), prompts=[_to_response(r) for r in records]
    )


@router.get(
    "/prompts/{prompt_id}/{version}",
    response_model=PromptResponse,
    summary="Get a specific prompt version",
)
def get_prompt(prompt_id: str, version: str):
    from prompts.registry import get_prompt as _get

    record = _get(prompt_id, version)
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"Prompt '{prompt_id}@{version}' not found."
        )
    return _to_response(record)


@router.post(
    "/prompts",
    response_model=PromptResponse,
    status_code=201,
    summary="Create a draft prompt",
)
def create_prompt(body: PromptCreateRequest):
    from prompts.registry import create_prompt as _create

    try:
        record = _create(
            prompt_id=body.id,
            stage=body.stage,
            content=body.content,
            version=body.version,
            variables=body.variables,
            owner=body.owner,
            description=body.description,
            adr=body.adr,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _to_response(record)


@router.put(
    "/prompts/{prompt_id}/{version}/certify",
    response_model=PromptResponse,
    summary="Promote a draft prompt to certified",
)
def certify_prompt(prompt_id: str, version: str):
    from prompts.registry import certify_prompt as _certify

    try:
        record = _certify(prompt_id, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _to_response(record)


@router.put(
    "/prompts/{prompt_id}/{version}/deprecate",
    response_model=PromptResponse,
    summary="Deprecate a prompt",
)
def deprecate_prompt(
    prompt_id: str, version: str, body: Optional[PromptDeprecateRequest] = None
):
    from prompts.registry import deprecate_prompt as _deprecate

    replacement = body.replacement_id if body else None
    try:
        record = _deprecate(prompt_id, version, replacement_id=replacement)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _to_response(record)
