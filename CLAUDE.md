# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. This is a working prototype evolving toward production.

## Core architecture

```
spec/organizational_model.yaml  ← single source of truth for the domain
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     FAISS RAG (lazy-loaded)
        │
        └── agents/
             ├── state.py              AgentState TypedDict
             ├── planner.py            LLM → structured ToolSelection (Pydantic)
             ├── tools.py              tool wrappers consuming spec defaults
             ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
             └── judge.py             online quality gate + single-pass revision

memory/checkpointer.py   SqliteSaver + agent_sessions table
evaluation/observer.py    JSONL run logging
config/settings.py        thin adapter over spec (backward-compatible)
app.py                    REPL entry point
```

## Design principles (non-negotiable)

1. **Spec-driven**: all domain knowledge lives in `spec/organizational_model.yaml`. To change the domain, edit the YAML — no code changes.
2. **LLM orchestrates, never computes**: the LLM selects tools via structured output. All calculations are deterministic Python.
3. **Each tool is a pure function of (spec, params) → result**: tools read from the spec, receive params, return dicts. No side effects.
4. **The graph is the architecture**: LangGraph defines the flow. Adding a node = adding a capability. The judge is inside the graph, not outside.
5. **Provider-agnostic**: the system must work with multiple LLM providers. No hardcoded dependency on a single provider.

## Key files to understand first

- `spec/organizational_model.yaml` — read this first, everything derives from it
- `spec/spec_loader.py` — typed dataclasses that parse the YAML into `OrganizationalModelSpec`
- `agents/workflow.py` — the LangGraph graph definition
- `agents/planner.py` — how the LLM decides which tool to use (structured output with `ToolSelection`)
- `system/system_model.py` — `_NODE_FORMULAS` dict and topological evaluation
- `app.py` — the REPL loop and session management

## Current tech stack

- Python 3.10+
- LangGraph >= 1.0 with `langgraph-checkpoint-sqlite`
- LangChain (openai, community, core) >= 0.3
- LLM models via env vars: `PLANNER_MODEL`, `SYNTHESIZER_MODEL`, `JUDGE_MODEL` (default: gpt-4o-mini)
- `HISTORY_WINDOW` env var controls conversation history depth (default: 3)
- FAISS for vector search (faiss-cpu)
- scikit-learn for the demand model (RandomForest)
- networkx for the causal DAG
- SQLite for checkpointing and session persistence

## Build steps (run once after setup)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python data/generate_data.py           # synthetic dataset
python models/train_demand_model.py    # train RF model → models/demand_model.pkl
python knowledge/build_index.py        # FAISS index → knowledge_index/
python app.py                          # run the agent REPL
```

## Testing policy

Every PR must include tests for the code it changes. Use `pytest`.

- **Unit tests**: test individual functions in isolation. Mock LLM calls, don't hit real APIs in unit tests.
- **Integration tests**: test the interaction between components (e.g., planner + tools). These may use real LLM calls if needed, marked with `@pytest.mark.integration` so they can be skipped in CI.
- **Test location**: `tests/` directory, mirroring the source structure (e.g., `tests/agents/test_planner.py`).
- **Naming**: `test_<function_name>_<scenario>` (e.g., `test_planner_fallback_on_invalid_output`).
- **No tests that depend on specific LLM output text** — test structure, types, and behavior, not exact wording.

Run tests:
```bash
pytest                              # all unit tests
pytest -m integration               # integration tests only
pytest --tb=short -q                # quick summary
```

## Conventions

- Formatter: `black` (line-length 88)
- Linter: `ruff`
- Type hints on all function signatures
- Docstrings on all modules and public functions (numpy-style)
- No bare `except:` — always catch specific exceptions
- All config via `.env` or spec YAML — never hardcode values
- Every new feature must include unit tests

## What NOT to change without discussion

- The spec-driven principle: do not embed domain logic in code
- The graph structure (planner → tool → synthesizer → judge): changes here affect everything
- The `ToolSelection` Pydantic schema in `agents/planner.py`: all tools depend on it
- The `_NODE_FORMULAS` registry pattern in `system/system_model.py`: this is how the DAG evaluates

## Git workflow

- Main branch: `main`
- Feature branches: `feature/<item-id>-<short-description>` (e.g. `feature/5.5-history-window`)
- Commit messages: `[<item-id>] <description>` (e.g. `[5.5] Make history window configurable`)
- PRs into main with description of what changed and why

## Completed items

- [x] **5.5** History window configurable via `HISTORY_WINDOW` env var (default 3)

## Current work: Bloque A — Multi-provider LLM (items 5.6 + 12.4 + 12.5)

**Branch**: `feature/5.6-multi-provider-llm`

Three related items implemented together:

**5.6 — Multi-provider LLM support**
Add Anthropic (via `langchain-anthropic`) as a second LLM provider alongside OpenAI. Each node (planner, synthesizer, judge) can independently use any provider. Configuration via env vars:
```
PLANNER_PROVIDER=openai          # or "anthropic"
PLANNER_MODEL=gpt-4o-mini        # or "claude-sonnet-4-20250514"
SYNTHESIZER_PROVIDER=openai
SYNTHESIZER_MODEL=gpt-4o-mini
JUDGE_PROVIDER=openai
JUDGE_MODEL=gpt-4o-mini
```

Implementation approach:
- Create a factory function `get_chat_model(provider, model_name) -> BaseChatModel` in a new file `agents/llm_factory.py`
- The factory returns `ChatOpenAI(model=...)` or `ChatAnthropic(model=...)` based on provider
- Replace all direct `ChatOpenAI(...)` instantiations in `workflow.py` (and anywhere else) with calls to the factory
- Update `.env.example` with the new variables
- Add `langchain-anthropic` to `requirements.txt`

**12.4 — Fallback policy between providers**
If the primary provider fails (API error, timeout, rate limit), automatically retry with a fallback provider. Configuration:
```
FALLBACK_PROVIDER=anthropic
FALLBACK_MODEL=claude-sonnet-4-20250514
LLM_MAX_RETRIES=2
LLM_TIMEOUT=30
```

Implementation approach:
- Add retry logic with fallback in `llm_factory.py`: try primary → on failure → try fallback → on failure → raise with clear error
- Log provider switches via standard logging
- The fallback is per-call, not per-session — each call tries primary first

**12.5 — Rate limiting and graceful degradation**
Handle provider rate limits without crashing:
- Exponential backoff on 429 responses (use `tenacity` library)
- If retries exhausted, try fallback provider
- If all providers exhausted, return a structured error message to the user ("service temporarily unavailable"), not a stack trace

Implementation approach:
- Add `tenacity` to `requirements.txt`
- Wrap the LLM call in the factory with retry decorator
- Return structured error dict on total failure so the graph can handle it gracefully

### Tests required for this block

In `tests/agents/test_llm_factory.py`:
- `test_get_chat_model_openai` — returns ChatOpenAI instance
- `test_get_chat_model_anthropic` — returns ChatAnthropic instance
- `test_get_chat_model_unknown_provider` — raises ValueError
- `test_fallback_on_primary_failure` — mock primary to fail, verify fallback is called
- `test_retry_on_rate_limit` — mock 429, verify retry with backoff
- `test_graceful_error_on_total_failure` — mock all providers failing, verify structured error (no crash)

### After this block

Next: Bloque B — Planner robustness (items 5.7 + 4.1), branch `feature/5.7-planner-robustness`

Then: Paquete 1A (PostgreSQL + pgvector + spec as data) — the big structural change of I1.

Full roadmap: see `llull_roadmap_v3.md` in project knowledge.
Full backlog: see `llull_inventario_v3.md` in project knowledge.
