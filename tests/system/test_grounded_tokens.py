"""
tests/system/test_grounded_tokens.py
--------------------------------------
Unit tests for system/grounded_tokens.py (item 5.9).

All tests load the healthcare_demo_spec.yaml fixture — a domain deliberately
different from retail_pricing to prove no vocabulary names are hardcoded.
Tests run without a database (spec loaded from YAML via load_spec()).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spec.spec_loader import load_spec
from system.grounded_tokens import (
    UngroundedTokenError,
    build_vocabulary,
    check_observational,
    get_vocabulary,
    invalidate_vocabulary_cache,
    validate_strict,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "healthcare_demo_spec.yaml"


@pytest.fixture(autouse=True)
def clear_vocab_cache():
    """Ensure each test starts with a clean vocabulary cache."""
    invalidate_vocabulary_cache()
    yield
    invalidate_vocabulary_cache()


@pytest.fixture()
def spec():
    return load_spec(FIXTURE_PATH)


# ---------------------------------------------------------------------------
# build_vocabulary — structure and contents
# ---------------------------------------------------------------------------


def test_vocabulary_contains_decision_variable_names(spec):
    vocab = build_vocabulary(spec)
    assert "bed_capacity" in vocab.tokens
    assert "staffing_ratio" in vocab.tokens


def test_vocabulary_contains_target_variable_names(spec):
    vocab = build_vocabulary(spec)
    assert "patient_throughput" in vocab.tokens


def test_vocabulary_contains_aliases(spec):
    vocab = build_vocabulary(spec)
    # bed_capacity aliases: beds, capacity
    assert "beds" in vocab.tokens
    assert "capacity" in vocab.tokens
    # staffing_ratio alias: nurse_ratio
    assert "nurse_ratio" in vocab.tokens
    # patient_throughput aliases: throughput, patients_treated
    assert "throughput" in vocab.tokens
    assert "patients_treated" in vocab.tokens


def test_vocabulary_contains_derived_metric_ids(spec):
    vocab = build_vocabulary(spec)
    assert "cost_per_patient" in vocab.tokens


def test_vocabulary_contains_derived_metric_aliases(spec):
    vocab = build_vocabulary(spec)
    assert "cpp" in vocab.tokens
    assert "unit_cost" in vocab.tokens


def test_vocabulary_is_lowercased(spec):
    vocab = build_vocabulary(spec)
    # All tokens must be lowercase
    for token in vocab.tokens:
        assert token == token.lower(), f"Token not lowercased: {token}"


def test_vocabulary_does_not_contain_hardcoded_retail_names(spec):
    """Critical: no retail prototype names must appear in a healthcare vocab."""
    vocab = build_vocabulary(spec)
    assert "price" not in vocab.tokens
    assert "marketing_spend" not in vocab.tokens
    assert "expected_profit" not in vocab.tokens
    assert "demand" not in vocab.tokens


def test_vocabulary_spec_version(spec):
    vocab = build_vocabulary(spec)
    assert vocab.spec_version == "0.1.0"


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


def test_build_vocabulary_is_cached(spec):
    v1 = build_vocabulary(spec)
    v2 = build_vocabulary(spec)
    assert v1 is v2  # same object from cache


def test_get_vocabulary_returns_same_as_build(spec):
    v1 = build_vocabulary(spec)
    v2 = get_vocabulary(spec)
    assert v1 is v2


def test_invalidate_clears_cache(spec):
    v1 = build_vocabulary(spec)
    invalidate_vocabulary_cache()
    v2 = build_vocabulary(spec)
    assert v1 is not v2  # new object after invalidation


# ---------------------------------------------------------------------------
# validate_strict
# ---------------------------------------------------------------------------


def test_validate_strict_passes_for_known_token(spec):
    vocab = build_vocabulary(spec)
    validate_strict("bed_capacity", vocab)  # no exception raised


def test_validate_strict_passes_for_alias(spec):
    vocab = build_vocabulary(spec)
    validate_strict("beds", vocab)  # alias


def test_validate_strict_is_case_insensitive(spec):
    vocab = build_vocabulary(spec)
    validate_strict("BED_CAPACITY", vocab)  # uppercase — must pass


def test_validate_strict_raises_for_unknown_token(spec):
    vocab = build_vocabulary(spec)
    with pytest.raises(UngroundedTokenError) as exc_info:
        validate_strict("price", vocab)
    assert exc_info.value.token == "price"
    assert exc_info.value.vocab is vocab


def test_ungrounded_token_error_message_mentions_token(spec):
    vocab = build_vocabulary(spec)
    with pytest.raises(UngroundedTokenError) as exc_info:
        validate_strict("marketing_spend", vocab)
    assert "marketing_spend" in str(exc_info.value)


# ---------------------------------------------------------------------------
# check_observational
# ---------------------------------------------------------------------------


def test_check_observational_returns_empty_for_known_tokens(spec):
    vocab = build_vocabulary(spec)
    mentions = check_observational(["bed_capacity", "patient_throughput"], vocab)
    assert mentions == []


def test_check_observational_returns_mentions_for_unknown_tokens(spec):
    vocab = build_vocabulary(spec)
    mentions = check_observational(["price", "bed_capacity", "demand"], vocab)
    unknown = {m.token for m in mentions}
    assert "price" in unknown
    assert "demand" in unknown
    assert "bed_capacity" not in unknown


def test_check_observational_is_case_insensitive(spec):
    vocab = build_vocabulary(spec)
    mentions = check_observational(["BED_CAPACITY"], vocab)
    assert mentions == []


def test_check_observational_includes_context(spec):
    vocab = build_vocabulary(spec)
    mentions = check_observational(["unknown_var"], vocab, context="raw_result")
    assert len(mentions) == 1
    assert mentions[0].context == "raw_result"


def test_check_observational_does_not_raise_on_ungrounded_tokens(spec):
    """Non-blocking: must not raise even when all tokens are ungrounded."""
    vocab = build_vocabulary(spec)
    result = check_observational(["price", "marketing_spend", "profit"], vocab)
    assert len(result) == 3  # three mentions, no exception
