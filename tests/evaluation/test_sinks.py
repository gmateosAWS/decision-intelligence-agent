"""
tests/evaluation/test_sinks.py
-------------------------------
Unit tests for RunSink implementations and ConfidenceScorer.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from evaluation.confidence import ConfidenceScorer
from evaluation.sinks.base import RunSink
from evaluation.sinks.jsonl_sink import JsonlSink
from evaluation.sinks.langsmith_sink import LangSmithBridge
from evaluation.sinks.postgres_sink import PostgresSink

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RECORD: Dict[str, Any] = {
    "run_id": "abc123",
    "session_id": "s1",
    "timestamp": "2026-05-08T00:00:00+00:00",
    "query": "test query",
    "action": "simulation",
    "success": True,
    "total_latency_ms": 150.0,
}


# ---------------------------------------------------------------------------
# RunSink Protocol
# ---------------------------------------------------------------------------


class TestRunSinkProtocol:
    def test_jsonl_sink_satisfies_protocol(self, tmp_path):
        sink = JsonlSink(tmp_path)
        assert isinstance(sink, RunSink)

    def test_postgres_sink_satisfies_protocol(self):
        assert isinstance(PostgresSink(), RunSink)

    def test_langsmith_bridge_satisfies_protocol(self):
        assert isinstance(LangSmithBridge(), RunSink)

    def test_custom_sink_satisfies_protocol(self):
        class MySink:
            def finalize_run(self, record: Dict[str, Any]) -> None:
                pass

        assert isinstance(MySink(), RunSink)


# ---------------------------------------------------------------------------
# JsonlSink
# ---------------------------------------------------------------------------


class TestJsonlSink:
    def test_writes_jsonl_line(self, tmp_path):
        sink = JsonlSink(tmp_path)
        sink.finalize_run(SAMPLE_RECORD)
        path = tmp_path / "agent_runs.jsonl"
        assert path.exists()
        line = json.loads(path.read_text(encoding="utf-8").strip())
        assert line["run_id"] == "abc123"

    def test_appends_multiple_records(self, tmp_path):
        sink = JsonlSink(tmp_path)
        sink.finalize_run({**SAMPLE_RECORD, "run_id": "r1"})
        sink.finalize_run({**SAMPLE_RECORD, "run_id": "r2"})
        lines = (
            (tmp_path / "agent_runs.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        assert len(lines) == 2
        assert json.loads(lines[0])["run_id"] == "r1"
        assert json.loads(lines[1])["run_id"] == "r2"

    def test_creates_log_dir_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "logs"
        JsonlSink(nested)
        assert nested.exists()

    def test_does_not_raise_on_write_error(self, tmp_path):
        sink = JsonlSink(tmp_path)
        # Make the directory read-only to trigger OSError
        (tmp_path / "agent_runs.jsonl").write_text("", encoding="utf-8")
        os.chmod(tmp_path / "agent_runs.jsonl", 0o444)
        try:
            sink.finalize_run(SAMPLE_RECORD)  # must not raise
        finally:
            os.chmod(tmp_path / "agent_runs.jsonl", 0o644)


# ---------------------------------------------------------------------------
# PostgresSink
# ---------------------------------------------------------------------------


class TestPostgresSink:
    def test_skips_when_no_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        sink = PostgresSink()
        sink.finalize_run(SAMPLE_RECORD)  # must not raise

    def test_calls_get_session_when_database_url_set(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://dummy/test")
        mock_session = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_session)
        mock_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch("evaluation.sinks.postgres_sink.get_session", return_value=mock_cm),
            patch("evaluation.sinks.postgres_sink.AgentRun") as mock_run_cls,
        ):
            sink = PostgresSink()
            sink.finalize_run(SAMPLE_RECORD)
            mock_session.add.assert_called_once()
            mock_run_cls.assert_called_once()

    def test_does_not_raise_on_db_error(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://dummy/test")
        with patch(
            "evaluation.sinks.postgres_sink.get_session",
            side_effect=Exception("connection refused"),
        ):
            PostgresSink().finalize_run(SAMPLE_RECORD)  # must not raise


# ---------------------------------------------------------------------------
# ConfidenceScorer
# ---------------------------------------------------------------------------


class TestConfidenceScorer:
    def test_simulation_confidence(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"downside_risk_pct": 20.0}) == pytest.approx(
            0.8
        )

    def test_simulation_zero_risk(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"downside_risk_pct": 0.0}) == 1.0

    def test_simulation_100_risk(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"downside_risk_pct": 100.0}) == 0.0

    def test_optimization_positive_profit(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"expected_profit": 500.0}) == 1.0

    def test_optimization_negative_profit(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"expected_profit": -10.0}) == 0.3

    def test_knowledge_answer_key(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"answer": "some text"}) == 0.9

    def test_knowledge_documents_key(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"documents": []}) == 0.9

    def test_unknown_returns_none(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result({"something_else": 42}) is None

    def test_non_dict_returns_none(self):
        scorer = ConfidenceScorer()
        assert scorer.compute_from_result("not a dict") is None  # type: ignore[arg-type]

    def test_compute_failed_run(self):
        scorer = ConfidenceScorer()
        assert scorer.compute(success=False) == 0.0

    def test_compute_with_judge_score(self):
        scorer = ConfidenceScorer()
        assert scorer.compute(judge_score=0.85, success=True) == pytest.approx(0.85)

    def test_compute_with_fallback_penalty(self):
        scorer = ConfidenceScorer()
        result = scorer.compute(judge_score=0.85, success=True, fallback_triggered=True)
        assert result == pytest.approx(0.8)

    def test_compute_no_signal_returns_none(self):
        scorer = ConfidenceScorer()
        assert scorer.compute() is None


# ---------------------------------------------------------------------------
# AgentObserver integration (sink dispatch)
# ---------------------------------------------------------------------------


class TestAgentObserverSinkDispatch:
    def test_end_run_dispatches_to_all_sinks(self, tmp_path):
        from evaluation.observer import AgentObserver

        collected: list = []

        class CollectorSink:
            def finalize_run(self, record: Dict[str, Any]) -> None:
                collected.append(record)

        observer = AgentObserver(sinks=[CollectorSink()], log_dir=str(tmp_path))
        observer.start_run("how much profit?")
        observer.end_run()
        assert len(collected) == 1
        assert collected[0]["query"] == "how much profit?"

    def test_default_sinks_include_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from evaluation.observer import AgentObserver

        observer = AgentObserver(log_dir=str(tmp_path))
        observer.start_run("test")
        observer.end_run()
        assert (tmp_path / "agent_runs.jsonl").exists()

    def test_cancel_run_does_not_dispatch(self, tmp_path):
        from evaluation.observer import AgentObserver

        collected: list = []

        class CollectorSink:
            def finalize_run(self, record: Dict[str, Any]) -> None:
                collected.append(record)

        observer = AgentObserver(sinks=[CollectorSink()], log_dir=str(tmp_path))
        observer.start_run("test cancel")
        observer.cancel_run("test reason")
        assert len(collected) == 0

    def test_public_api_unchanged(self, tmp_path, monkeypatch):
        """Callers that pass only log_dir must continue to work."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from evaluation.observer import AgentObserver

        obs = AgentObserver(log_dir=str(tmp_path))
        run_id = obs.start_run("test compat")
        assert isinstance(run_id, str) and len(run_id) == 12
        obs.record_planner("simulation", "price query", 10.0)
        obs.record_tool("simulation", {"downside_risk_pct": 15.0}, 80.0)
        obs.record_synthesizer("The profit is X", 30.0)
        obs.record_judge(0.9, True, "OK", 20.0, False)
        record = obs.end_run()
        assert record is not None
        assert record["success"] is True
        assert record["confidence_score"] == pytest.approx(0.85)
