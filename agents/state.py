"""
agents/state.py
---------------
AgentState TypedDict – the shared mutable state passed between LangGraph nodes.

Fields
------
  query      (str)            – user's original question
  action     (str | None)     – tool selected by the planner
  reasoning  (str | None)     – planner's explanation of its choice
  raw_result (dict | None)    – raw output from the analytical tool
  answer     (str | None)     – synthesized natural-language response
  run_id     (str | None)     – observability correlation ID (set by app.py)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    query: str
    action: Optional[str]
    reasoning: Optional[str]
    raw_result: Optional[Dict[str, Any]]
    answer: Optional[str]
    run_id: Optional[str]  # correlation ID for the observer
