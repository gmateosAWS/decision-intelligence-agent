"""
agents/i18n.py
──────────────
Centralized language support for agent responses.

Every component that generates user-facing text (synthesizer, judge revision,
future skills) must use this module to resolve language-specific templates.
This is a prerequisite for the skills engine (item 4.3) where each skill
needs language-aware output.

Skills integration pattern
--------------------------
A future skill that needs to respond in the user's language only needs::

    from agents.i18n import get_system_language_directive
    system_msg = get_system_language_directive(state["language"])

No knowledge of synthesizer or judge internals required.
"""

from __future__ import annotations

LANGUAGE_NAMES: dict[str, str] = {
    "ca": "Catalan",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese",
}

SYNTH_INSTRUCTIONS: dict[str, str] = {
    "es": (
        "Proporciona una interpretación de negocio clara y concisa "
        "(3-5 frases, específica y cuantitativa):\n"
        "- Qué significan los números\n"
        "- Qué debería hacer el decisor\n"
        "- Riesgos o matices relevantes\n\n"
        "Tu respuesta COMPLETA debe estar en español."
    ),
    "en": (
        "Provide a clear, concise business interpretation "
        "(3-5 sentences, specific and quantitative):\n"
        "- What the numbers mean\n"
        "- What the decision-maker should do\n"
        "- Key risks or caveats\n\n"
        "Your ENTIRE response must be in English."
    ),
}

REVISE_INSTRUCTIONS: dict[str, str] = {
    "es": (
        "Reescribe la respuesta de forma que esté estrictamente fundamentada "
        "en la salida de la herramienta, responda directamente la pregunta del "
        "usuario y sea concisa. No introduzcas hechos que no estén en la salida "
        "de la herramienta. Si hay números, úsalos. Si hay incertidumbre, "
        "menciónala.\n\n"
        "Tu respuesta COMPLETA debe estar en español."
    ),
    "en": (
        "Rewrite the answer so it is strictly grounded in the tool output, "
        "directly answers the user's question, and stays concise. "
        "Do not introduce facts not present in the raw tool output. "
        "If numbers exist, use them. If uncertainty exists, mention it.\n\n"
        "Your ENTIRE response must be in English."
    ),
}


def get_language_name(code: str) -> str:
    """Return the full language name for an ISO 639-1 code, defaulting to English."""
    return LANGUAGE_NAMES.get(code, "English")


def get_synth_instructions(language_code: str) -> str:
    """Return synthesizer instructions for the given language, with English fallback."""
    if language_code in SYNTH_INSTRUCTIONS:
        return SYNTH_INSTRUCTIONS[language_code]
    lang_name = get_language_name(language_code)
    return (
        "Provide a clear, concise business interpretation "
        "(3-5 sentences, specific and quantitative):\n"
        "- What the numbers mean\n"
        "- What the decision-maker should do\n"
        "- Key risks or caveats\n\n"
        f"Your ENTIRE response must be in {lang_name}."
    )


def get_revise_instructions(language_code: str) -> str:
    """Return revision instructions for the given language, with English fallback."""
    if language_code in REVISE_INSTRUCTIONS:
        return REVISE_INSTRUCTIONS[language_code]
    lang_name = get_language_name(language_code)
    return (
        "Rewrite the answer so it is strictly grounded in the tool output, "
        "directly answers the user's question, and stays concise. "
        "Do not introduce facts not present in the raw tool output. "
        "If numbers exist, use them. If uncertainty exists, mention it.\n\n"
        f"Your ENTIRE response must be in {lang_name}."
    )


def get_system_language_directive(language_code: str) -> str:
    """Return a system-prompt sentence that enforces the response language.

    Injects into any system prompt to make a skill or node respond in the
    user's language without coupling to synthesizer or judge internals.
    """
    lang_name = get_language_name(language_code)
    return f"You MUST respond ONLY in {lang_name}. Every word must be in {lang_name}."
