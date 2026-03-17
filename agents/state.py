"""
agents/state.py  – Mejora 3
---------------------------
AgentState TypedDict – shared mutable state for the LangGraph nodes.

Fields
------
  query      (str)                – user's original question
  action     (str | None)         – tool selected by the planner
  reasoning  (str | None)         – planner's explanation of its choice
  price      (float | None)       – price extracted from the query (if any)
  marketing  (float | None)       – marketing spend extracted from the query (if any
  raw_result (dict | None)        – raw output from the analytical tool
  answer     (str | None)         – synthesized natural-language response
  run_id     (str | None)         – observability correlation ID
  history    (List[Dict[str,str]])– accumulated (query, answer) turn pairs
                                    (uses operator.add so LangGraph appends
                                    rather than replacing the list)
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    query: str
    action: Optional[str]
    reasoning: Optional[str]
    price: Optional[float]  # parámetro extraído por el planner
    marketing: Optional[float]  # parámetro extraído por el planner
    raw_result: Optional[Dict[str, Any]]
    answer: Optional[str]
    run_id: Optional[str]
    # Conversation history – LangGraph merges with operator.add (append)
    history: Annotated[List[Dict[str, str]], operator.add]
