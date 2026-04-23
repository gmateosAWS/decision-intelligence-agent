"""
evaluation/metrics.py
---------------------
Load and aggregate metrics from the run log.

Backend selection:
  DATABASE_URL set  → reads from agent_runs table (Postgres)
  DATABASE_URL unset → reads from JSONL file (original behaviour)

Entry points
------------
  load_runs(log_path)        → list[dict]   raw records
  compute_metrics(runs)      → dict          aggregated stats
  print_report(metrics)      → None          formatted CLI output
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def load_runs(log_path: str = "logs/agent_runs.jsonl") -> List[Dict]:
    """
    Load all run records.

    Uses the Postgres agent_runs table when DATABASE_URL is set;
    falls back to reading the JSONL file otherwise.
    """
    if os.getenv("DATABASE_URL", ""):
        try:
            return _load_runs_postgres()
        except Exception as exc:
            logger.warning("Postgres load_runs failed (%s), falling back to JSONL", exc)
    return _load_runs_jsonl(log_path)


def _load_runs_postgres() -> List[Dict]:
    from db.engine import get_session
    from db.models import AgentRun

    with get_session() as session:
        rows = session.query(AgentRun).order_by(AgentRun.timestamp).all()
        return [
            {
                "run_id": row.run_id,
                "session_id": str(row.session_id) if row.session_id else None,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "query": row.query,
                "action": row.action,
                "reasoning": row.reasoning,
                "planner_latency_ms": row.planner_latency_ms,
                "planner_model": row.planner_model,
                "tool_latency_ms": row.tool_latency_ms,
                "confidence_score": row.confidence_score,
                "synthesizer_latency_ms": row.synthesizer_latency_ms,
                "answer_length": row.answer_length,
                "synthesizer_model": row.synthesizer_model,
                "judge_latency_ms": row.judge_latency_ms,
                "judge_score": row.judge_score,
                "judge_passed": row.judge_passed,
                "judge_revised": row.judge_revised,
                "judge_feedback": row.judge_feedback,
                "judge_model": row.judge_model,
                "total_latency_ms": row.total_latency_ms,
                "success": row.success,
                "error": row.error,
            }
            for row in rows
        ]


def _load_runs_jsonl(log_path: str) -> List[Dict]:
    """Load all run records from a JSONL file, skipping blank/malformed lines."""
    path = Path(log_path)
    if not path.exists():
        return []
    runs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return runs


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def compute_metrics(runs: List[Dict]) -> Dict:
    """
    Compute a comprehensive set of metrics from a list of run records.

    Returns
    -------
    dict with keys:
      total_runs, success_rate,
      avg_total_latency_ms, p50_total_latency_ms, p95_total_latency_ms,
      avg_planner_latency_ms, avg_tool_latency_ms, avg_synthesizer_latency_ms,
      avg_judge_latency_ms, avg_confidence_score, avg_judge_score,
      judge_approval_rate, judge_revision_rate,
      tool_distribution (dict action → count),
      error_count, errors (list of error strings),
      sessions (list of unique session ids),
      recent_runs (last 10 run records)
    """
    if not runs:
        return {}

    total = len(runs)
    success = sum(1 for r in runs if r.get("success", True))

    tool_counts: Dict[str, int] = defaultdict(int)

    total_lat: List[float] = []
    planner_lat: List[float] = []
    tool_lat: List[float] = []
    synth_lat: List[float] = []
    judge_lat: List[float] = []
    confidences: List[float] = []
    judge_scores: List[float] = []
    judge_passes = 0
    judge_total = 0
    judge_revisions = 0
    errors: List[str] = []
    sessions: set = set()

    for r in runs:
        sessions.add(r.get("session_id", "?"))

        if r.get("action"):
            tool_counts[r["action"]] += 1

        _append_if(total_lat, r.get("total_latency_ms"))
        _append_if(planner_lat, r.get("planner_latency_ms"))
        _append_if(tool_lat, r.get("tool_latency_ms"))
        _append_if(synth_lat, r.get("synthesizer_latency_ms"))
        _append_if(judge_lat, r.get("judge_latency_ms"))
        _append_if(confidences, r.get("confidence_score"))
        _append_if(judge_scores, r.get("judge_score"))

        if r.get("judge_passed") is not None:
            judge_total += 1
            if r.get("judge_passed"):
                judge_passes += 1
        if r.get("judge_revised"):
            judge_revisions += 1

        if not r.get("success", True) and r.get("error"):
            errors.append(r["error"])

    return {
        "total_runs": total,
        "success_count": success,
        "error_count": total - success,
        "success_rate": round(success / total, 4) if total else 0.0,
        "avg_total_latency_ms": _mean(total_lat),
        "p50_total_latency_ms": _percentile(total_lat, 50),
        "p95_total_latency_ms": _percentile(total_lat, 95),
        "avg_planner_latency_ms": _mean(planner_lat),
        "avg_tool_latency_ms": _mean(tool_lat),
        "avg_synthesizer_latency_ms": _mean(synth_lat),
        "avg_judge_latency_ms": _mean(judge_lat),
        "avg_confidence_score": _mean(confidences),
        "avg_judge_score": _mean(judge_scores),
        "judge_approval_rate": (
            round(judge_passes / judge_total, 4) if judge_total else None
        ),
        "judge_revision_rate": (
            round(judge_revisions / judge_total, 4) if judge_total else None
        ),
        "tool_distribution": dict(tool_counts),
        "errors": errors,
        "sessions": sorted(sessions),
        "recent_runs": runs[-10:],
    }


# ---------------------------------------------------------------------------
# CLI report
# ---------------------------------------------------------------------------


def print_report(metrics: Dict) -> None:
    """
    Print a formatted summary report to stdout.
    """
    if not metrics:
        print("  No run data found. Run `python app.py` first.")
        return

    W = 60  # separator width
    # line = "─" * W

    def _fmt_ms(v: Optional[float]) -> str:
        return f"{v:,.0f} ms" if v is not None else "n/a"

    def _fmt_pct(v: float) -> str:
        return f"{v * 100:.1f}%"

    def _fmt_conf(v: Optional[float]) -> str:
        if v is None:
            return "n/a"
        bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
        return f"{v:.2f}  {bar}"

    print()
    print("┌" + "─" * (W - 2) + "┐")
    print(f"│{'  Decision Intelligence Agent – Run Report':^{W-2}}│")
    print("├" + "─" * (W - 2) + "┤")

    print(f"│  {'Total runs':<30} {metrics['total_runs']:>10}           │")
    print(f"│  {'Successful':<30} {metrics['success_count']:>10}           │")
    print(f"│  {'Errors':<30} {metrics['error_count']:>10}           │")
    print(f"│  {'Success rate':<30} {_fmt_pct(metrics['success_rate']):>15}      │")
    print(f"│  {'Sessions':<30} {len(metrics['sessions']):>10}           │")

    print("├" + "─" * (W - 2) + "┤")
    print(f"│{'  Latency':^{W-2}}│")
    print("├" + "─" * (W - 2) + "┤")

    print(f"│  {'Avg total':<30} {_fmt_ms(metrics['avg_total_latency_ms']):>15}      │")
    print(f"│  {'p50 total':<30} {_fmt_ms(metrics['p50_total_latency_ms']):>15}      │")
    print(f"│  {'p95 total':<30} {_fmt_ms(metrics['p95_total_latency_ms']):>15}      │")
    v = _fmt_ms(metrics["avg_planner_latency_ms"])
    print(f"│  {'Avg planner':<30} {v:>15}      │")
    print(f"│  {'Avg tool':<30} {_fmt_ms(metrics['avg_tool_latency_ms']):>15}      │")
    v = _fmt_ms(metrics["avg_synthesizer_latency_ms"])
    print(f"│  {'Avg synthesizer':<30} {v:>15}      │")
    v = _fmt_ms(metrics["avg_judge_latency_ms"])
    print(f"│  {'Avg judge':<30} {v:>15}      │")

    print("├" + "─" * (W - 2) + "┤")
    print(f"│{'  Quality':^{W-2}}│")
    print("├" + "─" * (W - 2) + "┤")

    v = _fmt_conf(metrics["avg_confidence_score"])
    print(f"│  {'Avg confidence score':<30} {v:>24} │")
    judge_score = metrics.get("avg_judge_score")
    judge_score_s = _fmt_conf(judge_score)
    print(f"│  {'Avg judge score':<30} {judge_score_s:>24} │")
    approval = metrics.get("judge_approval_rate")
    revision = metrics.get("judge_revision_rate")
    approval_s = _fmt_pct(approval) if approval is not None else "n/a"
    revision_s = _fmt_pct(revision) if revision is not None else "n/a"
    print(f"│  {'Judge approval rate':<30} {approval_s:>15}      │")
    print(f"│  {'Judge revision rate':<30} {revision_s:>15}      │")

    dist = metrics.get("tool_distribution", {})
    if dist:
        print("├" + "─" * (W - 2) + "┤")
        print(f"│{'  Tool usage':^{W-2}}│")
        print("├" + "─" * (W - 2) + "┤")
        total = sum(dist.values())
        for tool, cnt in sorted(dist.items(), key=lambda x: -x[1]):
            bar = "█" * int((cnt / total) * 20)
            print(f"│  {tool:<16} {cnt:>4} ({cnt/total*100:4.0f}%)  {bar:<20}  │")

    errors = metrics.get("errors", [])
    if errors:
        print("├" + "─" * (W - 2) + "┤")
        print(f"│{'  Errors':^{W-2}}│")
        print("├" + "─" * (W - 2) + "┤")
        for e in errors[-5:]:
            print(f"│  ⚠  {str(e)[:W-8]:<{W-8}} │")

    recent = metrics.get("recent_runs", [])
    if recent:
        print("├" + "─" * (W - 2) + "┤")
        print(f"│{'  Last runs':^{W-2}}│")
        print("├" + "─" * (W - 2) + "┤")
        for r in recent[-5:]:
            ts = r.get("timestamp", "?")[:19].replace("T", " ")
            action = (r.get("action") or "?")[:12]
            lat = r.get("total_latency_ms")
            ok = "✓" if r.get("success", True) else "✗"
            lat_s = f"{lat:,.0f}ms" if lat else "   n/a"
            q = r.get("query", "?")[:28]
            print(f"│  {ok} {ts}  {action:<12}  {lat_s:>8}  {q:<28} │")

    print("└" + "─" * (W - 2) + "┘")
    print()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _append_if(lst: list, value) -> None:
    if value is not None:
        try:
            lst.append(float(value))
        except (TypeError, ValueError):
            pass


def _mean(lst: List[float]) -> Optional[float]:
    return round(statistics.mean(lst), 2) if lst else None


def _percentile(lst: List[float], pct: int) -> Optional[float]:
    if not lst:
        return None
    s = sorted(lst)
    idx = int(len(s) * pct / 100)
    return round(s[min(idx, len(s) - 1)], 2)
