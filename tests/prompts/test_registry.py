"""
tests/prompts/test_registry.py
-------------------------------
Unit tests for the Prompt Registry (item 10.1).

All tests run without a database — the registry functions either:
  - return None / [] when DATABASE_URL is not set (read ops)
  - raise RuntimeError when DATABASE_URL is not set (write ops)

The lifecycle tests mock the DB layer so they exercise the business logic
without requiring Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from prompts.models import PromptRecord, PromptStatus
from prompts.registry import (
    JUDGE_REVISION_TEMPLATE,
    JUDGE_SYSTEM_TEMPLATE,
    PLANNER_SYSTEM_TEMPLATE,
    SYNTHESIZER_SYSTEM_TEMPLATE,
    get_prompt_template,
    seed_prompts_from_code,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    prompt_id: str = "planner",
    version: str = "1.0.0",
    status: PromptStatus = PromptStatus.CERTIFIED,
    stage: str = "planner",
    content: str = "Hello {domain_name}",
    variables: list | None = None,
) -> PromptRecord:
    now = datetime.now(timezone.utc)
    return PromptRecord(
        id=prompt_id,
        version=version,
        status=status,
        stage=stage,
        content=content,
        variables=variables or ["domain_name"],
        created_at=now,
        changed_at=now,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_prompt_status_values():
    assert PromptStatus.DRAFT.value == "draft"
    assert PromptStatus.CERTIFIED.value == "certified"
    assert PromptStatus.DEPRECATED.value == "deprecated"


def test_prompt_record_defaults():
    now = datetime.now(timezone.utc)
    rec = PromptRecord(
        id="planner",
        version="1.0.0",
        stage="planner",
        content="Hello",
        created_at=now,
        changed_at=now,
    )
    assert rec.status == PromptStatus.DRAFT
    assert rec.variables == []
    assert rec.owner == ""
    assert rec.sunset_date is None


# ---------------------------------------------------------------------------
# get_prompt_template — fallback when no DB
# ---------------------------------------------------------------------------


def test_get_prompt_template_returns_fallback_when_no_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    content, version, variant_label = get_prompt_template("planner", "FALLBACK")
    assert content == "FALLBACK"
    assert version is None
    assert variant_label is None


def test_get_prompt_template_returns_registry_content(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    record = _make_record(content="REGISTRY CONTENT", version="2.0.0")
    with patch("prompts.registry.get_certified_prompt", return_value=record):
        content, version, variant_label = get_prompt_template("planner", "FALLBACK")
    assert content == "REGISTRY CONTENT"
    assert version == "2.0.0"
    assert variant_label is None


def test_get_prompt_template_returns_fallback_on_registry_none(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    with patch("prompts.registry.get_certified_prompt", return_value=None):
        content, version, variant_label = get_prompt_template("planner", "FALLBACK")
    assert content == "FALLBACK"
    assert version is None
    assert variant_label is None


# ---------------------------------------------------------------------------
# seed_prompts_from_code
# ---------------------------------------------------------------------------


def test_seed_from_code_creates_four_prompts(monkeypatch):
    """seed_prompts_from_code() seeds planner, synthesizer, judge, judge.revision."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    certified_records = []

    def mock_get_certified(stage):
        return None  # nothing in registry yet

    def mock_create(prompt_id, stage, content, version, **kwargs):
        return _make_record(prompt_id, version, PromptStatus.DRAFT, stage, content)

    def mock_certify(prompt_id, version):
        rec = _make_record(prompt_id, version, PromptStatus.CERTIFIED, stage=prompt_id)
        certified_records.append(rec)
        return rec

    with (
        patch("prompts.registry.get_certified_prompt", side_effect=mock_get_certified),
        patch("prompts.registry.create_prompt", side_effect=mock_create),
        patch("prompts.registry.certify_prompt", side_effect=mock_certify),
    ):
        result = seed_prompts_from_code()

    assert len(result) == 4
    stages = {r.stage for r in result}
    assert stages == {"planner", "synthesizer", "judge", "judge.revision"}


def test_seed_idempotent(monkeypatch):
    """If certified prompts already exist, seed_from_code returns them unchanged."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    existing = _make_record("planner", "1.0.0", PromptStatus.CERTIFIED, "planner")

    with (
        patch("prompts.registry.get_certified_prompt", return_value=existing),
        patch("prompts.registry.create_prompt") as mock_create,
    ):
        result = seed_prompts_from_code()

    mock_create.assert_not_called()
    assert all(r.status == PromptStatus.CERTIFIED for r in result)


def test_seed_skips_when_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = seed_prompts_from_code()
    assert result == []


# ---------------------------------------------------------------------------
# Template constants are non-empty and contain expected placeholders
# ---------------------------------------------------------------------------


def test_planner_template_has_required_placeholders():
    assert "{domain_name}" in PLANNER_SYSTEM_TEMPLATE
    assert "{examples}" in PLANNER_SYSTEM_TEMPLATE
    assert "{vars_description}" in PLANNER_SYSTEM_TEMPLATE


def test_synthesizer_template_has_required_placeholder():
    assert "{language_directive}" in SYNTHESIZER_SYSTEM_TEMPLATE


def test_judge_template_has_required_placeholder():
    assert "{threshold}" in JUDGE_SYSTEM_TEMPLATE


def test_judge_revision_template_has_required_placeholder():
    assert "{language_directive}" in JUDGE_REVISION_TEMPLATE
