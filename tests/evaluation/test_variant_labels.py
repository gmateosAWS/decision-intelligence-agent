"""
tests/evaluation/test_variant_labels.py
----------------------------------------
Verify that A/B variant labels propagate from record_* methods
through RunRecord to the dict emitted by end_run() (item 10.2).
"""

from __future__ import annotations

from evaluation.observer import AgentObserver, RunRecord


class _NullSink:
    """Sink that captures the final record dict."""

    def __init__(self):
        self.records = []

    def finalize_run(self, record):
        self.records.append(record)


def _make_observer() -> tuple[AgentObserver, _NullSink]:
    sink = _NullSink()
    obs = AgentObserver(sinks=[sink])
    return obs, sink


# ---------------------------------------------------------------------------
# RunRecord default values
# ---------------------------------------------------------------------------


def test_run_record_variant_labels_default_none():
    from datetime import datetime, timezone

    r = RunRecord(
        run_id="x",
        session_id="s",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query="q",
    )
    assert r.planner_variant_label is None
    assert r.synthesizer_variant_label is None
    assert r.judge_variant_label is None


# ---------------------------------------------------------------------------
# record_planner
# ---------------------------------------------------------------------------


def test_record_planner_stores_variant_label():
    obs, sink = _make_observer()
    obs.start_run("test query")
    obs.record_planner(
        action="optimization",
        reasoning="test",
        latency_ms=10.0,
        model="gpt-4o-mini",
        prompt_version="1.0.0",
        variant_label="v2-concise",
    )
    record = obs.end_run()
    assert record is not None
    assert record["planner_variant_label"] == "v2-concise"


def test_record_planner_variant_label_default_none():
    obs, sink = _make_observer()
    obs.start_run("test query")
    obs.record_planner(action="knowledge", reasoning="test", latency_ms=5.0)
    record = obs.end_run()
    assert record is not None
    assert record["planner_variant_label"] is None


# ---------------------------------------------------------------------------
# record_synthesizer
# ---------------------------------------------------------------------------


def test_record_synthesizer_stores_variant_label():
    obs, sink = _make_observer()
    obs.start_run("q")
    obs.record_synthesizer(
        answer="answer text",
        latency_ms=20.0,
        model="gpt-4o-mini",
        prompt_version="1.0.0",
        variant_label="v3-detailed",
    )
    record = obs.end_run()
    assert record is not None
    assert record["synthesizer_variant_label"] == "v3-detailed"


def test_record_synthesizer_variant_label_default_none():
    obs, sink = _make_observer()
    obs.start_run("q")
    obs.record_synthesizer(answer="ans", latency_ms=10.0)
    record = obs.end_run()
    assert record is not None
    assert record["synthesizer_variant_label"] is None


# ---------------------------------------------------------------------------
# record_judge
# ---------------------------------------------------------------------------


def test_record_judge_stores_variant_label():
    obs, sink = _make_observer()
    obs.start_run("q")
    obs.record_judge(
        score=0.9,
        approved=True,
        feedback="great",
        latency_ms=15.0,
        revised=False,
        model="gpt-4o-mini",
        prompt_version="1.0.0",
        variant_label="judge-v2",
    )
    record = obs.end_run()
    assert record is not None
    assert record["judge_variant_label"] == "judge-v2"


def test_record_judge_variant_label_default_none():
    obs, sink = _make_observer()
    obs.start_run("q")
    obs.record_judge(
        score=0.8,
        approved=True,
        feedback="ok",
        latency_ms=12.0,
        revised=False,
    )
    record = obs.end_run()
    assert record is not None
    assert record["judge_variant_label"] is None


# ---------------------------------------------------------------------------
# All three labels present end-to-end
# ---------------------------------------------------------------------------


def test_all_variant_labels_propagate():
    obs, sink = _make_observer()
    obs.start_run("multi-label test")
    obs.record_planner(
        action="simulation",
        reasoning="r",
        latency_ms=8.0,
        variant_label="planner-v2",
    )
    obs.record_synthesizer(answer="ans", latency_ms=12.0, variant_label="synth-v3")
    obs.record_judge(
        score=0.85,
        approved=True,
        feedback="ok",
        latency_ms=9.0,
        revised=False,
        variant_label="judge-v1-ctrl",
    )
    record = obs.end_run()
    assert record is not None
    assert record["planner_variant_label"] == "planner-v2"
    assert record["synthesizer_variant_label"] == "synth-v3"
    assert record["judge_variant_label"] == "judge-v1-ctrl"

    # Sink received the same record
    assert len(sink.records) == 1
    assert sink.records[0]["judge_variant_label"] == "judge-v1-ctrl"
