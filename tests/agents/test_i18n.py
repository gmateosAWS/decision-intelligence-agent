"""tests/agents/test_i18n.py — Unit tests for agents/i18n.py."""

from __future__ import annotations

from agents.i18n import (
    get_language_name,
    get_revise_instructions,
    get_synth_instructions,
    get_system_language_directive,
)


def test_known_language_returns_name() -> None:
    assert get_language_name("es") == "Spanish"
    assert get_language_name("de") == "German"
    assert get_language_name("fr") == "French"
    assert get_language_name("en") == "English"


def test_unknown_language_falls_back_to_english() -> None:
    assert get_language_name("xx") == "English"
    assert get_language_name("") == "English"
    assert get_language_name("zz") == "English"


def test_synth_instructions_spanish_contains_spanish_text() -> None:
    result = get_synth_instructions("es")
    assert "español" in result.lower()
    assert "beneficio" in result.lower() or "decisor" in result.lower()


def test_synth_instructions_english_contains_english_text() -> None:
    result = get_synth_instructions("en")
    assert "English" in result


def test_synth_instructions_unknown_language_falls_back_with_name() -> None:
    result = get_synth_instructions("de")
    assert "German" in result


def test_revise_instructions_spanish_contains_spanish_text() -> None:
    result = get_revise_instructions("es")
    assert "español" in result.lower()


def test_revise_instructions_unknown_language_falls_back_with_name() -> None:
    result = get_revise_instructions("fr")
    assert "French" in result


def test_system_directive_contains_language_name() -> None:
    directive = get_system_language_directive("es")
    assert "Spanish" in directive


def test_system_directive_format() -> None:
    directive = get_system_language_directive("fr")
    assert "French" in directive
    assert "MUST" in directive
    assert "respond" in directive.lower() or "ONLY" in directive
