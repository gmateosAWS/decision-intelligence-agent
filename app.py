"""
app.py  – Mejora 3
-------------------
Interactive REPL with:
  • Multi-turn conversational memory via LangGraph SqliteSaver.
  • Session management: new / list / resume / info / delete.
  • Observability layer from Mejora 2 (AgentObserver, JSONL logs).
  • LangSmith tracing (optional, via env vars).

Session commands (type at the prompt)
--------------------------------------
  session new            – start a fresh conversation thread
  session list           – list all saved sessions
  session resume <id>    – resume by full session_id
  session resume <#>     – resume by index from 'session list'
  session info           – show info about the current session
  session delete <id>    – remove a session from the registry
  dashboard              – show CLI metrics + generate HTML report
  exit                   – quit
"""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv

from agents.workflow import build_graph
from evaluation.observer import AgentObserver
from memory import SessionManager, get_checkpointer, register_turn

load_dotenv()


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║      Decision Intelligence Agent  ·  v3 (memory)             ║
╠══════════════════════════════════════════════════════════════╣
║  Ask business questions about pricing and marketing.         ║
║  Commands:                                                   ║
║    session new | list | resume <id|#> | info | delete <id>   ║
║    dashboard  ·  exit                                        ║
╚══════════════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_session_id() -> str:
    return str(uuid.uuid4())


def _resolve_session(token: str) -> str | None:
    """Resolve a '#N' index or bare session_id to a session_id."""
    if token.startswith("#"):
        try:
            idx = int(token[1:]) - 1
        except ValueError:
            return None
        sessions = SessionManager.list_sessions()
        if 0 <= idx < len(sessions):
            return sessions[idx]["session_id"]
        return None
    s = SessionManager.get_session(token)
    return s["session_id"] if s else None


def _show_dashboard(observer: AgentObserver) -> None:
    from evaluation.dashboard import generate_html_dashboard
    from evaluation.metrics import compute_metrics, load_runs, print_report

    log_path = str(observer.log_dir / observer.JSONL_FILENAME)
    runs = load_runs(log_path)
    metrics = compute_metrics(runs)
    print_report(metrics)
    html_path = str(observer.log_dir / "dashboard.html")
    path = generate_html_dashboard(log_path, html_path)
    print(f"  HTML dashboard → {path}\n")


# ---------------------------------------------------------------------------
# Main REPL
# ---------------------------------------------------------------------------


def main() -> None:  # noqa: C901
    print(_BANNER)

    # -- Observability (Mejora 2) ----------------------------------------
    observer = AgentObserver(log_dir="logs")

    ls_val = os.getenv("LANGCHAIN_TRACING_V2", "false").lower()
    langsmith_enabled = ls_val == "true"
    if langsmith_enabled:
        proj = os.getenv("LANGCHAIN_PROJECT", "default")
        print(f"  ✓ LangSmith tracing enabled (project: {proj})\n")

    # -- Memory / checkpointing (Mejora 3) --------------------------------
    checkpointer = get_checkpointer()
    graph = build_graph(checkpointer=checkpointer)

    # Start a fresh session
    session_id = _new_session_id()
    is_new_session = True
    print(f"  ● New session: {session_id}\n")

    # -- REPL ------------------------------------------------------------
    while True:
        try:
            raw = input("Ask a business question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not raw:
            continue

        # ---- Built-in commands ----------------------------------------
        lower = raw.lower()

        if lower == "exit":
            print("Goodbye.")
            break

        if lower == "dashboard":
            _show_dashboard(observer)
            continue

        if lower == "session new":
            session_id = _new_session_id()
            is_new_session = True
            print(f"  ● New session: {session_id}\n")
            continue

        if lower == "session list":
            SessionManager.print_sessions()
            continue

        if lower == "session info":
            SessionManager.session_info(session_id)
            continue

        if lower.startswith("session resume "):
            token = raw[len("session resume ") :].strip()
            resolved = _resolve_session(token)
            if resolved:
                session_id = resolved
                is_new_session = False
                print(f"  ● Resumed session: {session_id}\n")
            else:
                print(f"  Session '{token}' not found.\n")
            continue

        if lower.startswith("session delete "):
            sid = raw[len("session delete ") :].strip()
            if SessionManager.delete_session(sid):
                print(f"  ✓ Deleted session '{sid}'.\n")
            else:
                print(f"  Session '{sid}' not found.\n")
            continue

        # ---- Regular query --------------------------------------------
        run_id = observer.start_run(raw)

        try:
            cfg = observer.langsmith_config()
            cfg["configurable"]["observer"] = observer
            cfg["configurable"]["thread_id"] = session_id

            result = graph.invoke(
                {"query": raw, "run_id": run_id},
                config=cfg,
            )
            answer = result.get("answer") or "(no answer generated)"
            print(f"\n{answer}\n")

            # Persist turn metadata in agent_sessions
            register_turn(
                session_id,
                raw,
                is_new=is_new_session,
            )
            is_new_session = False

            observer.end_run(success=True)

        except KeyboardInterrupt:
            print("\n[Interrupted]\n")
            observer.end_run(success=False, error="KeyboardInterrupt")

        except Exception as exc:  # noqa: BLE001
            print(f"\n[Error] {exc}\n")
            observer.end_run(success=False, error=str(exc))


if __name__ == "__main__":
    main()
