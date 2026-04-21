# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. This is a working prototype, not production code yet.

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
- OpenAI models via env vars: `PLANNER_MODEL`, `SYNTHESIZER_MODEL`, `JUDGE_MODEL` (default: gpt-4o-mini)
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

## Conventions

- Formatter: `black` (line-length 88)
- Linter: `ruff`
- Type hints on all function signatures
- Docstrings on all modules and public functions (numpy-style)
- No bare `except:` — always catch specific exceptions
- All config via `.env` or spec YAML — never hardcode values

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

## Current roadmap context

The project has a 96-item backlog organized in 4 iterations (I1 → I2A → I2B → I3). We are starting I1. The first items to implement are the parches (patches) from Paquete 1D — small, self-contained improvements to the existing prototype:

- **5.5** Make history window configurable (currently hardcoded to 3 turns)
- **5.6** Add support for at least one non-OpenAI LLM provider (Anthropic)
- **5.7** Formalize fallback policy when planner fails
- **4.1** Verify simulation works with arbitrary params from query
- **12.5** Add rate limiting / graceful degradation for LLM calls
- **12.4** Define fallback policy between LLM providers

After patches, the big items of I1 are:
- **1.1** Migrate from SQLite to PostgreSQL
- **1.2** Replace FAISS with pgvector
- **1.5** Spec as data (spec stored in DB, versioned)
- **6.1.e** Wrap the prototype as a FastAPI service (Agent Service)
- **11.1** CI pipeline (GitHub Actions)
- **11.3** Dockerize

Full roadmap: see `llull_roadmap_v3.md` in project knowledge.
Full backlog: see `llull_inventario_v3.md` in project knowledge.
