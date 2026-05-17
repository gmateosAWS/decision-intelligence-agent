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
  language     (str)                 -- ISO 639-1 code detected by planner
                                        (e.g. "es", "en", "fr"); default "en"
  raw_result   (dict | None)         -- raw output from the analytical tool
  answer       (str | None)          -- final natural-language response
  run_id       (str | None)          -- observability correlation ID
  judge_score  (float | None)        -- quality score assigned by the judge
  judge_passed (bool | None)         -- whether the draft passed without revision
  judge_feedback (str | None)        -- judge's explanation of its verdict
  judge_revised  (bool | None)       -- whether the answer was rewritten once
  requires_confirmation (bool)       -- autonomy policy: show plan, wait for OK
  requires_approval     (bool)       -- autonomy policy: propose only, no execution
  confirmation_message  (str | None) -- message displayed to the user for review
  planner_prompt_version    (str | None) -- registry version of planner template
  synthesizer_prompt_version (str | None) -- registry version of synthesizer template
  judge_prompt_version      (str | None) -- registry version of judge template
  planner_variant_label     (str | None) -- A/B variant label for planner (item 10.2)
  synthesizer_variant_label (str | None) -- A/B variant label for synthesizer
                                             (item 10.2)
  judge_variant_label       (str | None) -- A/B variant label for judge (item 10.2)
  clarification_needed (bool)          -- True when planner caught an ungrounded
                                          token (item 5.9); routes to clarification
                                          node instead of tool
  ungrounded_token     (str | None)    -- the raw token that failed vocabulary
                                          validation (stored as str, not exception,
                                          because the checkpointer cannot serialise
                                          exception objects)
  clarification_message (str | None)  -- message shown to the user when
                                          clarification is needed
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
    language: str  # ISO 639-1 code detected by planner; default "en"
    raw_result: Optional[Dict[str, Any]]
    answer: Optional[str]
    run_id: Optional[str]
    judge_score: Optional[float]
    judge_passed: Optional[bool]
    judge_feedback: Optional[str]
    judge_revised: Optional[bool]
    # Autonomy policy flags — set by planner_node when policy != auto
    requires_confirmation: bool  # show plan to user and wait for OK
    requires_approval: bool  # propose only, do not execute without approval
    confirmation_message: Optional[str]  # message shown to the user
    # Prompt Registry traceability (item 10.1) — None when registry unavailable
    planner_prompt_version: Optional[str]
    synthesizer_prompt_version: Optional[str]
    judge_prompt_version: Optional[str]
    # A/B variant labels (item 10.2) — None when no variants are active
    planner_variant_label: Optional[str]
    synthesizer_variant_label: Optional[str]
    judge_variant_label: Optional[str]
    # GroundedTokens clarification (item 5.9) — set when planner catches
    # an ungrounded token; routes to clarification node instead of tool.
    # Exceptions cannot be stored in AgentState (not serialisable by the
    # checkpointer), so we store the raw token string instead.
    clarification_needed: bool
    ungrounded_token: Optional[str]  # the token that failed validation
    clarification_message: Optional[str]  # message displayed to the user
    # Conversation history – LangGraph merges with operator.add (append)
    history: Annotated[List[Dict[str, str]], operator.add]
