"""
evaluation/confidence.py
------------------------
ConfidenceScorer: derives a 0-1 confidence score from tool output.

Extracted from AgentObserver._derive_confidence so it can be used
independently by skills, tests, and future ObjectBus consumers (item 1.6).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ConfidenceScorer:
    """
    Heuristic confidence scoring for tool outputs.

    Two entry points:
    - compute_from_result(result): derives from raw tool dict
      (simulation / optimization / knowledge)
    - compute(judge_score, success, fallback_triggered): composite score
      from run outcome
    """

    def compute_from_result(self, result: Dict[str, Any]) -> Optional[float]:
        """
        Derive a [0, 1] confidence score from tool output dict.

        - Simulation: 1 - downside_risk_pct / 100
        - Optimization: 1.0 if expected_profit > 0 else 0.3
        - Knowledge (RAG): fixed 0.9
        - Unknown: None
        """
        if not isinstance(result, dict):
            return None
        if "downside_risk_pct" in result:
            risk = float(result["downside_risk_pct"])
            return round(max(0.0, 1.0 - risk / 100.0), 3)
        if "expected_profit" in result:
            profit = float(result.get("expected_profit", 0))
            return 1.0 if profit > 0 else 0.3
        if "answer" in result or "documents" in result:
            return 0.9
        return None

    def compute(
        self,
        judge_score: Optional[float] = None,
        success: bool = True,
        fallback_triggered: bool = False,
    ) -> Optional[float]:
        """
        Composite confidence from run-level signals.

        Used for post-run reporting; does not replace compute_from_result.
        Returns None when there is not enough signal.
        """
        if not success:
            return 0.0
        if judge_score is not None:
            penalty = 0.05 if fallback_triggered else 0.0
            return round(max(0.0, min(1.0, judge_score - penalty)), 3)
        return None
