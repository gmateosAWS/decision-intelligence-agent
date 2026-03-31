"""
agents/state.py
---------------
Shared mutable state (``AgentState`` TypedDict) passed between LangGraph
nodes in the Decision Intelligence Agent pipeline.

Fields
------
  query        (str)                 -- user's original question
  action       (str | None)          -- tool selected by the planner
  reasoning    (str | None)          -- planner's CoT reasoning for the choice
  params       (Dict[str, float])    -- decision-variable values extracted from
                                        the query; keys match spec variable names
                                        exactly; tools fall back to spec defaults
                                        for any missing key
  raw_result   (dict | None)         -- raw output from the analytical tool
  answer       (str | None)          -- final natural-language response
  run_id       (str | None)          -- observability correlation ID
  judge_score  (float | None)        -- quality score assigned by the judge
  judge_passed (bool | None)         -- whether the draft passed without revision
  judge_feedback (str | None)        -- judge's explanation of its verdict
  judge_revised  (bool | None)       -- whether the answer was rewritten once
  history      (List[Dict[str,str]]) -- accumulated (query, answer) turn pairs;
                                        merged via operator.add so LangGraph
                                        appends rather than replacing the list
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    query: str
    action: Optional[str]
    reasoning: Optional[str]
    params: Dict[str, float]  # parámetros extraídos por el planner
    raw_result: Optional[Dict[str, Any]]
    answer: Optional[str]
    run_id: Optional[str]
    judge_score: Optional[float]
    judge_passed: Optional[bool]
    judge_feedback: Optional[str]
    judge_revised: Optional[bool]
    # Conversation history – LangGraph merges with operator.add (append)
    history: Annotated[List[Dict[str, str]], operator.add]
