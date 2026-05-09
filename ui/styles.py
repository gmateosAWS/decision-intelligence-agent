"""
ui/styles.py
-------------
CSS constants, logo HTML, tool label/colour maps, and the sanitize_markdown
helper.  No Streamlit state access — pure constants and pure functions.
"""

from __future__ import annotations

import re
from typing import Dict

# ---------------------------------------------------------------------------
# Logo HTML
# ---------------------------------------------------------------------------

LOGO_FULL = (
    '<span style="font-family: Georgia, serif; font-size: 52px; '
    'font-weight: 400; letter-spacing: -2px; line-height: 1;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
)

LOGO_COMPACT = (
    '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">'
    '<span style="font-family: Georgia, serif; font-size: 26px; '
    'font-weight: 400; letter-spacing: -1px;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
    '<span style="font-size: 15px; color: #6b7280;">Decision Intelligence Agent</span>'
    "</div>"
)

LOGO_SIDEBAR = (
    '<span style="font-family: Georgia, serif; font-size: 28px; '
    'font-weight: 400; letter-spacing: -1px;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
)

# ---------------------------------------------------------------------------
# Tab CSS
# ---------------------------------------------------------------------------

TAB_STYLE_CSS = """
<style>
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: transparent !important;
}
.stTabs button[role="tab"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 10px 28px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #9ca3af !important;
}
.stTabs button[role="tab"]:hover {
    color: #374151 !important;
    background: rgba(108,142,245,0.06) !important;
}
.stTabs button[role="tab"][aria-selected="true"] {
    color: #111827 !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #6c8ef5 !important;
    height: 2px !important;
}
.stTabs [data-baseweb="tab-border"] {
    background-color: #e5e7eb !important;
    height: 1px !important;
}
</style>
"""

# ---------------------------------------------------------------------------
# Tool display maps
# ---------------------------------------------------------------------------

TOOL_LABELS: Dict[str, str] = {
    "optimization": "🟢 Optimización",
    "simulation": "🔵 Simulación",
    "knowledge": "🟣 Conocimiento",
}

TOOL_COLORS: Dict[str, str] = {
    "optimization": "#22c55e",
    "simulation": "#3b82f6",
    "knowledge": "#a855f7",
}

# ---------------------------------------------------------------------------
# Markdown sanitizer
# ---------------------------------------------------------------------------


def sanitize_markdown(text: str) -> str:
    """Close unclosed inline markdown delimiters to prevent style bleed."""
    if len(re.findall(r"```", text)) % 2 == 1:
        text = text.rstrip() + "\n```"
    no_fences = re.sub(r"```[\s\S]*?```", "", text)
    if no_fences.count("`") % 2 == 1:
        text += "`"
    if len(re.findall(r"\*\*", text)) % 2 == 1:
        text += "**"
    return text
