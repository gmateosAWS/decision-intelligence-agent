"""
tests/prompts/test_ab_registry.py
-----------------------------------
Unit tests for variant CRUD and get_prompt_template 3-tuple (item 10.2).
Uses mocks — no DB required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# get_prompt_template — 3-tuple signature (no DB)
# ---------------------------------------------------------------------------


def test_get_prompt_template_fallback_returns_3_tuple():
    """When no DB and no variants, fallback returns (content, None, None)."""
    from prompts.registry import get_prompt_template

    with patch("prompts.routing.select_variant", return_value=None):
        with patch("prompts.registry.get_certified_prompt", return_value=None):
            result = get_prompt_template("planner", "FALLBACK_CONTENT")

    assert isinstance(result, tuple)
    assert len(result) == 3
    template, version, variant_label = result
    assert template == "FALLBACK_CONTENT"
    assert version is None
    assert variant_label is None


def test_get_prompt_template_certified_returns_3_tuple():
    """When certified prompt found but no variant, returns (content, version, None)."""
    from datetime import datetime, timezone

    from prompts.models import PromptRecord, PromptStatus
    from prompts.registry import get_prompt_template

    mock_record = PromptRecord(
        id="planner",
        version="1.0.0",
        status=PromptStatus.CERTIFIED,
        stage="planner",
        content="CERTIFIED CONTENT",
        created_at=datetime.now(timezone.utc),
        changed_at=datetime.now(timezone.utc),
    )
    with patch("prompts.routing.select_variant", return_value=None):
        with patch("prompts.registry.get_certified_prompt", return_value=mock_record):
            result = get_prompt_template("planner", "FALLBACK")

    template, version, variant_label = result
    assert template == "CERTIFIED CONTENT"
    assert version == "1.0.0"
    assert variant_label is None


def test_get_prompt_template_variant_returns_3_tuple():
    """When variant is selected, returns (variant_content, version, label)."""
    from datetime import datetime, timezone

    from prompts.models import PromptVariant, PromptVariantStatus
    from prompts.registry import get_prompt_template

    mock_variant = PromptVariant(
        id="v-001",
        stage="planner",
        prompt_id="planner",
        version="2.0.0",
        variant_label="v2-concise",
        status=PromptVariantStatus.CANDIDATE,
        rollout_percentage=20,
        created_at=datetime.now(timezone.utc),
        changed_at=datetime.now(timezone.utc),
    )

    with patch("prompts.routing.select_variant", return_value=mock_variant):
        with patch(
            "prompts.registry._get_cached_prompt_content",
            return_value="VARIANT CONTENT",
        ):
            result = get_prompt_template("planner", "FALLBACK", session_id="sess-abc")

    template, version, variant_label = result
    assert template == "VARIANT CONTENT"
    assert version == "2.0.0"
    assert variant_label == "v2-concise"


def test_get_prompt_template_variant_content_miss_falls_back():
    """If variant content fetch fails (returns None), fall back to certified prompt."""
    from datetime import datetime, timezone

    from prompts.models import (
        PromptRecord,
        PromptStatus,
        PromptVariant,
        PromptVariantStatus,
    )
    from prompts.registry import get_prompt_template

    mock_variant = PromptVariant(
        id="v-002",
        stage="planner",
        prompt_id="planner",
        version="2.0.0",
        variant_label="v2-bad",
        status=PromptVariantStatus.CANDIDATE,
        rollout_percentage=10,
        created_at=datetime.now(timezone.utc),
        changed_at=datetime.now(timezone.utc),
    )
    mock_certified = PromptRecord(
        id="planner",
        version="1.0.0",
        status=PromptStatus.CERTIFIED,
        stage="planner",
        content="CERTIFIED FALLBACK",
        created_at=datetime.now(timezone.utc),
        changed_at=datetime.now(timezone.utc),
    )

    with patch("prompts.routing.select_variant", return_value=mock_variant):
        with patch("prompts.registry._get_cached_prompt_content", return_value=None):
            with patch(
                "prompts.registry.get_certified_prompt", return_value=mock_certified
            ):
                template, version, variant_label = get_prompt_template(
                    "planner", "RAW FALLBACK", session_id="sess-x"
                )

    assert template == "CERTIFIED FALLBACK"
    assert version == "1.0.0"
    assert variant_label is None  # no variant served


# ---------------------------------------------------------------------------
# Validate rollout_percentage constraints in PromptVariant model
# ---------------------------------------------------------------------------


def test_prompt_variant_rollout_pct_valid():
    from datetime import datetime, timezone

    from prompts.models import PromptVariant, PromptVariantStatus

    v = PromptVariant(
        id="x",
        stage="planner",
        prompt_id="planner",
        version="1.0.0",
        variant_label="v2",
        status=PromptVariantStatus.CANDIDATE,
        rollout_percentage=50,
        created_at=datetime.now(timezone.utc),
        changed_at=datetime.now(timezone.utc),
    )
    assert v.rollout_percentage == 50


def test_prompt_variant_rollout_pct_invalid():
    from datetime import datetime, timezone

    import pydantic

    from prompts.models import PromptVariant, PromptVariantStatus

    with pytest.raises(pydantic.ValidationError):
        PromptVariant(
            id="x",
            stage="planner",
            prompt_id="planner",
            version="1.0.0",
            variant_label="v2",
            status=PromptVariantStatus.CANDIDATE,
            rollout_percentage=101,  # invalid
            created_at=datetime.now(timezone.utc),
            changed_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# AgentState includes variant_label fields
# ---------------------------------------------------------------------------


def test_agent_state_has_variant_label_fields():
    from agents.state import AgentState

    state: AgentState = {
        "query": "test",
        "planner_variant_label": "v2",
        "synthesizer_variant_label": None,
        "judge_variant_label": "judge-v1",
    }
    assert state["planner_variant_label"] == "v2"
    assert state["synthesizer_variant_label"] is None
    assert state["judge_variant_label"] == "judge-v1"
