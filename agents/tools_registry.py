"""
agents/tools_registry.py
────────────────────────
Tool cost classification used by the proactive confirmation gate (item 5.13).

Each tool declares its cost class at the system level — not in the spec, since
tool cost is a property of how the tool is implemented, independent of the
business domain. When item 4.3 (external skills) lands, each registered skill
declares its cost_class at registration time and the dict below is extended
dynamically.

Cost classes:
- "cheap": tools whose execution is sub-second and uses no LLM calls beyond
  the routing decision. Knowledge retrieval, lookups, simple aggregations.
  Cheap tools NEVER trigger proactive confirmation.
- "expensive": tools whose execution is expensive in wallclock, in compute,
  or in business consequence. Simulations, optimizations, anything that
  commits to an analytical conclusion. Expensive tools MAY trigger proactive
  confirmation when low-confidence signals are present.

The classification is consulted by memory/proactive_confirmation.py via
get_tool_cost_class(tool_name). Defaults to "cheap" for unknown tools so
new tools added without explicit classification don't add unnecessary friction.
"""

from __future__ import annotations

from typing import Literal

ToolCostClass = Literal["cheap", "expensive"]

_TOOL_COST_CLASS: dict[str, ToolCostClass] = {
    "optimization": "expensive",
    "simulation": "expensive",
    "knowledge": "cheap",
}


def get_tool_cost_class(tool: str) -> ToolCostClass:
    """Return cost class for a tool. Defaults to 'cheap' for unknown tools."""
    return _TOOL_COST_CLASS.get(tool, "cheap")


def register_tool_cost_class(tool: str, cost_class: ToolCostClass) -> None:
    """Register a new tool with its cost class.

    Called by skill registration (item 4.3) when an external skill declares
    itself as cheap or expensive at registration time.
    """
    _TOOL_COST_CLASS[tool] = cost_class
