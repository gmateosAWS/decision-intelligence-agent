"""
evaluation/dashboard.py
-----------------------
Generate a self-contained HTML dashboard from run logs,
and print a CLI summary report.

Usage
-----
    python evaluation/dashboard.py                    # uses default log path
    python evaluation/dashboard.py --log logs/agent_runs.jsonl
    python evaluation/dashboard.py --out my_report.html
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .metrics import compute_metrics, load_runs, print_report

# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Decision Intelligence Agent – Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<style>
  :root {{
    --bg:      #0f1117;
    --card:    #1a1d2e;
    --border:  #2e3250;
    --accent:  #6c8ef5;
    --green:   #4caf50;
    --red:     #f44336;
    --yellow:  #ffc107;
    --text:    #e2e8f0;
    --muted:   #8892a4;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 14px;
    padding: 24px;
  }}
  h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 4px; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .08em;
        color: var(--muted); margin-bottom: 16px; }}
  h3 {{ font-size: 13px; font-weight: 600; margin-bottom: 12px; color: var(--muted); }}
  .header {{ margin-bottom: 32px; }}
  .generated {{ font-size: 12px; color: var(--muted); }}

  /* KPI cards */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .kpi {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 24px;
  }}
  .kpi-label {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  .kpi-value {{ font-size: 28px; font-weight: 700; }}
  .kpi-sub   {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .green {{ color: var(--green); }}
  .red   {{ color: var(--red);   }}
  .blue  {{ color: var(--accent);}}

  /* Latency section */
  .row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 32px;
  }}
  @media (max-width: 700px) {{ .row {{ grid-template-columns: 1fr; }} }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
  }}
  .chart-wrap {{ position: relative; height: 220px; }}

  /* Latency table */
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th {{
    text-align: left;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    color: var(--muted);
    font-weight: 500;
  }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid #1e2138;
  }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
  }}
  .badge-ok  {{ background: #1b3a1e; color: var(--green); }}
  .badge-err {{ background: #3a1b1b; color: var(--red);   }}

  /* Confidence bar */
  .conf-track {{
    background: #2e3250;
    border-radius: 4px;
    height: 8px;
    width: 120px;
    display: inline-block;
    vertical-align: middle;
  }}
  .conf-fill {{
    height: 8px;
    border-radius: 4px;
    background: var(--accent);
  }}

  /* Errors */
  .error-list {{ list-style: none; }}
  .error-list li {{
    padding: 8px 12px;
    border-left: 3px solid var(--red);
    background: #1e1515;
    border-radius: 0 6px 6px 0;
    margin-bottom: 6px;
    font-size: 12px;
    color: #f99;
  }}

  footer {{
    margin-top: 40px;
    color: var(--muted);
    font-size: 11px;
    text-align: center;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>🧠 Decision Intelligence Agent</h1>
  <h2>Observability Dashboard</h2>
  <span class="generated">Generated {generated_at}</span>
</div>

<!-- KPI cards -->
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-label">Total Runs</div>
    <div class="kpi-value blue">{total_runs}</div>
    <div class="kpi-sub">{sessions} session(s)</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Success Rate</div>
    <div class="kpi-value {sr_class}">{success_rate}%</div>
    <div class="kpi-sub">{success_count} ok · {error_count} err</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Avg Total Latency</div>
    <div class="kpi-value">{avg_total_ms}</div>
    <div class="kpi-sub">p95 = {p95_total_ms}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Avg Confidence</div>
    <div class="kpi-value {conf_class}">{avg_confidence}</div>
    <div class="kpi-sub">derived from tool output</div>
  </div>
</div>

<!-- Charts row -->
<div class="row">
  <div class="card">
    <h3>Tool Distribution</h3>
    <div class="chart-wrap">
      <canvas id="toolChart"></canvas>
    </div>
  </div>
  <div class="card">
    <h3>Latency Breakdown (avg)</h3>
    <div class="chart-wrap">
      <canvas id="latChart"></canvas>
    </div>
  </div>
</div>

<!-- Latency detail table -->
<div class="card" style="margin-bottom:32px">
  <h3>Latency Detail</h3>
  <table>
    <tr>
      <th>Stage</th><th>Avg (ms)</th><th>Share</th>
    </tr>
    {latency_rows}
  </table>
</div>

<!-- Recent runs -->
<div class="card" style="margin-bottom:32px">
  <h3>Recent Runs (last 10)</h3>
  <table>
    <tr>
      <th>Timestamp</th><th>Run ID</th><th>Tool</th>
      <th>Total (ms)</th><th>Confidence</th><th>Status</th><th>Query</th>
    </tr>
    {run_rows}
  </table>
</div>

{errors_section}

<footer>Decision Intelligence Agent · Observability Layer · Mejora 2</footer>

<script>
// Tool distribution doughnut
new Chart(document.getElementById('toolChart'), {{
  type: 'doughnut',
  data: {{
    labels: {tool_labels},
    datasets: [{{
      data: {tool_values},
      backgroundColor: ['#6c8ef5','#4caf50','#ffc107','#f44336'],
      borderWidth: 0,
    }}]
  }},
  options: {{
    plugins: {{
      legend: {{ labels: {{ color: '#e2e8f0' }} }}
    }}
  }}
}});

// Latency stacked bar
new Chart(document.getElementById('latChart'), {{
  type: 'bar',
  data: {{
    labels: ['Planner', 'Tool', 'Synthesizer'],
    datasets: [{{
      label: 'avg ms',
      data: {lat_values},
      backgroundColor: ['#6c8ef5','#4caf50','#ffc107'],
      borderRadius: 6,
      borderWidth: 0,
    }}]
  }},
  options: {{
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ ticks: {{ color: '#8892a4' }}, grid: {{ color: '#2e3250' }} }},
      y: {{ ticks: {{ color: '#8892a4' }}, grid: {{ color: '#2e3250' }},
            title: {{ display: true, text: 'ms', color: '#8892a4' }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""


def _ms(v) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.0f}"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}"


def generate_html_dashboard(
    log_path: str = "logs/agent_runs.jsonl",
    output_path: str = "logs/dashboard.html",
) -> str:
    """
    Generate a self-contained HTML dashboard from JSONL logs.
    Returns the absolute path of the generated file.
    """
    runs = load_runs(log_path)
    metrics = compute_metrics(runs)

    if not metrics:
        # Empty state
        metrics = {
            "total_runs": 0,
            "success_count": 0,
            "error_count": 0,
            "success_rate": 0.0,
            "sessions": [],
            "avg_total_latency_ms": None,
            "p95_total_latency_ms": None,
            "avg_planner_latency_ms": None,
            "avg_tool_latency_ms": None,
            "avg_synthesizer_latency_ms": None,
            "avg_confidence_score": None,
            "tool_distribution": {},
            "errors": [],
            "recent_runs": [],
        }

    # KPI values
    sr = metrics["success_rate"]
    sr_class = "green" if sr >= 0.9 else ("yellow" if sr >= 0.7 else "red")
    avg_conf = metrics["avg_confidence_score"]
    conf_val = f"{avg_conf:.2f}" if avg_conf is not None else "n/a"
    conf_cls = "green" if (avg_conf or 0) >= 0.8 else "blue"

    # Tool distribution for Chart.js
    dist = metrics.get("tool_distribution", {})
    tool_labels = json.dumps(list(dist.keys()))
    tool_values = json.dumps(list(dist.values()))

    # Latency values for Chart.js
    p_ms = metrics.get("avg_planner_latency_ms") or 0
    t_ms = metrics.get("avg_tool_latency_ms") or 0
    s_ms = metrics.get("avg_synthesizer_latency_ms") or 0
    lat_values = json.dumps([round(p_ms), round(t_ms), round(s_ms)])

    # Latency rows for table
    total_ms = (p_ms + t_ms + s_ms) or 1

    def share(v):
        return f"{v/total_ms*100:.0f}%" if total_ms else "—"

    latency_rows = "".join(
        [
            f"<tr><td>Planner</td><td>{_ms(p_ms)}</td><td>{share(p_ms)}</td></tr>",
            f"<tr><td>Tool</td><td>{_ms(t_ms)}</td><td>{share(t_ms)}</td></tr>",
            f"<tr><td>Synthesizer</td><td>{_ms(s_ms)}</td><td>{share(s_ms)}</td></tr>",
        ]
    )

    # Recent run rows
    def conf_cell(v):
        if v is None:
            return "n/a"
        pct = int(float(v) * 100)
        return (
            f'<div class="conf-track">'
            f'<div class="conf-fill" style="width:{pct}%">'
            f"</div></div>"
            f" {float(v):.2f}"
        )

    run_rows = ""
    for r in reversed(metrics.get("recent_runs", [])):
        ok = r.get("success", True)
        if ok:
            badge = '<span class="badge badge-ok">OK</span>'
        else:
            badge = '<span class="badge badge-err">ERR</span>'
        ts = (r.get("timestamp") or "")[:19].replace("T", " ")
        rid = r.get("run_id", "?")[:10]
        act = r.get("action") or "?"
        lat = _ms(r.get("total_latency_ms"))
        conf = conf_cell(r.get("confidence_score"))
        q = (r.get("query") or "?")[:55]
        run_rows += (
            f"<tr><td>{ts}</td><td><code>{rid}</code></td><td>{act}</td>"
            f"<td>{lat}</td><td>{conf}</td><td>{badge}</td>"
            f"<td title='{q}'>{q}{'…' if len(r.get('query',''))>55 else ''}</td></tr>"
        )
    if not run_rows:
        run_rows = (
            "<tr><td colspan='7' "
            "style='color:var(--muted);text-align:center'>"
            "No runs yet</td></tr>"
        )

    # Errors section
    errors = metrics.get("errors", [])
    if errors:
        items = "\n".join(f"<li>{e}</li>" for e in errors[-10:])
        errors_section = (
            '<div class="card" style="margin-bottom:32px">'
            "<h3>⚠ Errors</h3>"
            f'<ul class="error-list">{items}</ul>'
            "</div>"
        )
    else:
        errors_section = ""

    html = _HTML_TEMPLATE.format(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        total_runs=metrics["total_runs"],
        sessions=len(metrics.get("sessions", [])),
        success_count=metrics["success_count"],
        error_count=metrics["error_count"],
        success_rate=_pct(sr),
        sr_class=sr_class,
        avg_total_ms=_ms(metrics.get("avg_total_latency_ms")) + " ms",
        p95_total_ms=_ms(metrics.get("p95_total_latency_ms")) + " ms",
        avg_confidence=conf_val,
        conf_class=conf_cls,
        tool_labels=tool_labels,
        tool_values=tool_values,
        lat_values=lat_values,
        latency_rows=latency_rows,
        run_rows=run_rows,
        errors_section=errors_section,
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out.resolve())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decision Intelligence Agent – Observability Dashboard"
    )
    parser.add_argument(
        "--log",
        default="logs/agent_runs.jsonl",
        help="Path to JSONL run log  (default: logs/agent_runs.jsonl)",
    )
    parser.add_argument(
        "--out",
        default="logs/dashboard.html",
        help="Output HTML file path  (default: logs/dashboard.html)",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Print CLI report only, skip HTML generation",
    )
    args = parser.parse_args()

    runs = load_runs(args.log)
    metrics = compute_metrics(runs)

    print_report(metrics)

    if not args.no_html:
        path = generate_html_dashboard(args.log, args.out)
        print(f"  HTML dashboard → {path}\n")


if __name__ == "__main__":
    main()
