"""
evaluation/sinks/postgres_sink.py
-----------------------------------
PostgresSink: writes completed run records to the agent_runs table.

Fail-open: warns on error, never raises, so a DB outage does not crash
the agent. Skips silently when DATABASE_URL is not set.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from db.engine import get_session
    from db.models import AgentRun
except Exception:  # noqa: BLE001  # db package optional
    get_session = None  # type: ignore[assignment]
    AgentRun = None  # type: ignore[assignment,misc]


class PostgresSink:
    """Persists run records to the ``agent_runs`` Postgres table."""

    def finalize_run(self, record: Dict[str, Any]) -> None:
        if not os.getenv("DATABASE_URL", ""):
            return
        if get_session is None or AgentRun is None:
            logger.warning("PostgresSink: db package not available — skipping")
            return
        try:
            spec_id_raw = record.get("spec_id")
            try:
                spec_uuid = uuid.UUID(spec_id_raw) if spec_id_raw else None
            except (ValueError, AttributeError):
                spec_uuid = None

            session_id_raw = record.get("session_id")
            try:
                session_uuid = uuid.UUID(session_id_raw) if session_id_raw else None
            except (ValueError, AttributeError):
                session_uuid = None

            with get_session() as session:
                session.add(
                    AgentRun(
                        session_id=session_uuid,
                        run_id=record.get("run_id", ""),
                        query=record.get("query", ""),
                        action=record.get("action"),
                        reasoning=record.get("reasoning"),
                        planner_latency_ms=record.get("planner_latency_ms"),
                        planner_model=record.get("planner_model"),
                        tool_latency_ms=record.get("tool_latency_ms"),
                        confidence_score=record.get("confidence_score"),
                        synthesizer_latency_ms=record.get("synthesizer_latency_ms"),
                        answer_length=record.get("answer_length"),
                        synthesizer_model=record.get("synthesizer_model"),
                        judge_latency_ms=record.get("judge_latency_ms"),
                        judge_score=record.get("judge_score"),
                        judge_passed=record.get("judge_passed"),
                        judge_revised=record.get("judge_revised"),
                        judge_feedback=record.get("judge_feedback"),
                        judge_model=record.get("judge_model"),
                        raw_result=record.get("raw_result"),
                        total_latency_ms=record.get("total_latency_ms"),
                        success=record.get("success", True),
                        error=record.get("error"),
                        spec_id=spec_uuid,
                        spec_version=record.get("spec_version"),
                        planner_prompt_version=record.get("planner_prompt_version"),
                        synthesizer_prompt_version=record.get(
                            "synthesizer_prompt_version"
                        ),
                        judge_prompt_version=record.get("judge_prompt_version"),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("PostgresSink: failed to write run to Postgres: %s", exc)
