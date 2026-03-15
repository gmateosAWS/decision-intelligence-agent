"""
app.py
------
Interactive REPL entry point for the Decision Intelligence Agent.

What's new in Mejora 2
-----------------------
- AgentObserver initialized once per session.
- Each query wrapped in start_run / end_run for full observability.
- LangSmith config injected via observer.langsmith_config().
- Observer passed through LangGraph configurable dict.
- run_id stored in state for cross-component correlation.
"""

import os

from dotenv import load_dotenv
from evaluation.observer import AgentObserver

from agents.workflow import build_graph

load_dotenv()


_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         Decision Intelligence Agent  ·  v2 (observability) ║
╠══════════════════════════════════════════════════════════════╣
║  Ask business questions about pricing and marketing.        ║
║  Examples:                                                  ║
║    • What price should maximise profit?                     ║
║    • What happens if I set price to 30?                     ║
║    • How does the demand model work?                        ║
║  Type 'exit' to quit  ·  'dashboard' to view metrics       ║
╚══════════════════════════════════════════════════════════════╝
"""


def main() -> None:
    print(_BANNER)

    # -- Build graph once per session -----------------------------------
    graph = build_graph()
    observer = AgentObserver(log_dir="logs")

    # Tip: set LANGCHAIN_TRACING_V2=true in .env to enable LangSmith
    langsmith_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    if langsmith_enabled:
        project = os.getenv("LANGCHAIN_PROJECT", "default")
        print(f"  ✓ LangSmith tracing enabled  (project: {project})\n")

    # -- REPL -----------------------------------------------------------
    while True:
        try:
            query = input("Ask a business question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not query:
            continue

        if query.lower() == "exit":
            print("Goodbye.")
            break

        if query.lower() == "dashboard":
            _show_dashboard(observer)
            continue

        # -- Run ---------------------------------------------------------
        run_id = observer.start_run(query)

        try:
            # Build config: LangSmith metadata + observer reference
            config = observer.langsmith_config()
            config["configurable"]["observer"] = observer

            result = graph.invoke(
                {"query": query, "run_id": run_id},
                config=config,
            )
            answer = result.get("answer") or "(no answer generated)"
            print(f"\n{answer}\n")
            observer.end_run(success=True)

        except KeyboardInterrupt:
            print("\n[Interrupted]\n")
            observer.end_run(success=False, error="KeyboardInterrupt")

        except Exception as exc:  # noqa: BLE001
            print(f"\n[Error] {exc}\n")
            observer.end_run(success=False, error=str(exc))


def _show_dashboard(observer: AgentObserver) -> None:
    """Print CLI metrics report + generate HTML dashboard."""
    from evaluation.dashboard import generate_html_dashboard
    from evaluation.metrics import compute_metrics, load_runs, print_report

    log_path = str(observer.log_dir / observer.JSONL_FILENAME)
    runs = load_runs(log_path)
    metrics = compute_metrics(runs)
    print_report(metrics)

    html_path = str(observer.log_dir / "dashboard.html")
    path = generate_html_dashboard(log_path, html_path)
    print(f"  HTML dashboard → {path}\n")


if __name__ == "__main__":
    main()
