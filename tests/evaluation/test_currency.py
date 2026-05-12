"""Tests for evaluation/currency.py — USD→EUR conversion (item 8.7.a)."""

from __future__ import annotations

import pytest

from evaluation import currency as cur


def setup_function():
    cur.clear_cache()


def test_get_eur_per_usd_returns_positive_float() -> None:
    rate = cur.get_eur_per_usd()
    assert isinstance(rate, float)
    assert rate > 0


def test_env_fallback_used_when_api_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("EUR_USD_RATE", "0.85")
    cur.clear_cache()
    # Patch requests so network call fails
    monkeypatch.setattr("builtins.__import__", _fail_requests_import)
    rate = cur.get_eur_per_usd()
    assert rate == pytest.approx(0.85)


def test_hardcoded_fallback_when_no_env_and_no_network(monkeypatch) -> None:
    monkeypatch.delenv("EUR_USD_RATE", raising=False)
    cur.clear_cache()
    monkeypatch.setattr("builtins.__import__", _fail_requests_import)
    rate = cur.get_eur_per_usd()
    assert rate == pytest.approx(0.92)


def test_usd_to_eur_converts_correctly(monkeypatch) -> None:
    monkeypatch.setenv("EUR_USD_RATE", "0.90")
    cur.clear_cache()
    eur = cur.usd_to_eur(10.0)
    assert eur == pytest.approx(9.0)


def test_cache_is_reused_on_second_call() -> None:
    r1 = cur.get_eur_per_usd()
    r2 = cur.get_eur_per_usd()
    assert r1 == r2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else None  # type: ignore[union-attr]


def _fail_requests_import(name, *args, **kwargs):
    if name == "requests":
        raise ImportError("mocked network unavailable")
    import builtins

    return builtins.__import__(name, *args, **kwargs)
