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
             ├── planner.py            LLM → structured ToolSelection (Pydantic) + fallback policy
             ├── llm_factory.py        get_chat_model() + invoke_with_fallback() + LLMUnavailableError
             ├── tools.py              tool wrappers consuming spec defaults
             ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
             └── judge.py             online quality gate + single-pass revision

memory/checkpointer.py   SqliteSaver + agent_sessions table
evaluation/observer.py    JSONL run logging (includes fallback events)
config/settings.py        thin adapter over spec (backward-compatible)
app.py                    REPL entry point (legacy, kept for dev use)
streamlit_app.py          Web UI (chat + DAG + result charts)
tests/agents/             unit tests
docs/                     project documentation (inventario, roadmap)
```

## Design principles (non-negotiable)

1. **Spec-driven**: all domain knowledge lives in `spec/organizational_model.yaml`. To change the domain, edit the YAML — no code changes.
2. **LLM orchestrates, never computes**: the LLM selects tools via structured output. All calculations are deterministic Python.
3. **Each tool is a pure function of (spec, params) → result**: tools read from the spec, receive params, return dicts. No side effects.
4. **The graph is the architecture**: LangGraph defines the flow. Adding a node = adding a capability. The judge is inside the graph, not outside.
5. **Provider-agnostic**: the system works with multiple LLM providers via `agents/llm_factory.py`. No hardcoded dependency on a single provider.

## Key files to understand first

- `spec/organizational_model.yaml` — read this first, everything derives from it
- `spec/spec_loader.py` — typed dataclasses that parse the YAML into `OrganizationalModelSpec`
- `agents/llm_factory.py` — LLM provider factory with fallback and retry logic
- `agents/workflow.py` — the LangGraph graph definition
- `agents/planner.py` — tool selection with structured output + formalized fallback policy
- `system/system_model.py` — `_NODE_FORMULAS` dict and topological evaluation
- `streamlit_app.py` — web UI entry point
- `docs/llull_roadmap_v3.md` — current roadmap with iteration status

## Current tech stack

- Python 3.10+
- LangGraph >= 1.0 with `langgraph-checkpoint-sqlite`
- LangChain (openai, anthropic, community, core) >= 0.3
- LLM providers: OpenAI and Anthropic, configurable per node
- Fallback: automatic provider switch, exponential backoff (tenacity)
- Streamlit >= 1.35 for web UI
- Plotly >= 5.20 for charts and DAG visualization
- FAISS for vector search (faiss-cpu)
- scikit-learn for the demand model (RandomForest)
- networkx for the causal DAG
- SQLite for checkpointing and session persistence

## LLM configuration

```env
PLANNER_PROVIDER=openai
PLANNER_MODEL=gpt-4o-mini
SYNTHESIZER_PROVIDER=openai
SYNTHESIZER_MODEL=gpt-4o-mini
JUDGE_PROVIDER=openai
JUDGE_MODEL=gpt-4o-mini
FALLBACK_PROVIDER=anthropic
FALLBACK_MODEL=claude-sonnet-4-20250514
LLM_MAX_RETRIES=2
LLM_TIMEOUT=30
HISTORY_WINDOW=3
```

## Build and run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python data/generate_data.py
python models/train_demand_model.py
python knowledge/build_index.py

# Web UI
streamlit run streamlit_app.py

# Legacy REPL (dev only)
python app.py
```

## Testing policy

Every PR must include tests. Use `pytest`.

- Unit tests: mock LLM calls, no real API hits
- Integration tests: marked `@pytest.mark.integration`
- Location: `tests/` mirroring source structure
- Naming: `test_<function_name>_<scenario>`

```bash
pytest
pytest -m integration
```

## Conventions

- `black` (line-length 88), `ruff`
- Type hints on all signatures, numpy-style docstrings
- No bare `except:`, all config via `.env` or spec YAML
- Every feature includes unit tests

## What NOT to change without discussion

- The spec-driven principle
- The graph structure (planner → tool → synthesizer → judge)
- The `ToolSelection` Pydantic schema
- The `_NODE_FORMULAS` registry

## Git workflow

- Feature branches: `feature/<item-id>-<short-description>`
- Commit messages: `[<item-id>] <description>`
- PRs into main

## Project documentation

Living docs in `docs/` directory, versioned with git:
- `docs/llull_inventario_v3.md` — full backlog (97 items)
- `docs/llull_roadmap_v3.md` — iteration plan with progress tracking

## Completed items

### Paquete 1D — Parches ✅
- [x] **5.5** History window configurable via `HISTORY_WINDOW` env var
- [x] **5.6** Multi-provider LLM (OpenAI + Anthropic) via `llm_factory.py`
- [x] **12.4** Fallback between providers (automatic switch)
- [x] **12.5** Rate limiting with backoff (tenacity) + graceful degradation
- [x] **5.7** Planner fallback policy (5 failure modes, `fallback_triggered` tracked)
- [x] **4.1** Simulation with arbitrary params verified

### Paquete 1E — UI ✅
- [x] **6.6** Streamlit web UI (`streamlit_app.py`, chat + DAG + charts)

## Current task: Move docs to repo + README update

Create `docs/` directory in the repo root and move planning docs there:
```
docs/
├── llull_inventario_v3.md
└── llull_roadmap_v3.md
```

Also update README.md:
1. Add `docs/` to the file tree
2. Add `streamlit_app.py` to the file tree with description
3. Add "Run the Web UI" section: `streamlit run streamlit_app.py`
4. Update the LLM configuration section with all new env vars
5. Add the multi-provider and fallback info to Key Design Decisions table
6. Add `tests/` to the file tree

Use branch `feature/docs-and-readme` or commit directly to main (it's documentation only).

## Next in roadmap (paused)

**Paquete 1A — Base de persistencia**: PostgreSQL, pgvector, spec as data, runs in Postgres. This is the big structural change of I1.

Remaining I1 items (1A + 1B + 1C) are paused until the demo with the CEO and president next week.

Full roadmap: `docs/llull_roadmap_v3.md`
Full backlog: `docs/llull_inventario_v3.md`
