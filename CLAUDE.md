# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. Evolving from prototype to product.

## Core architecture

```
spec/organizational_model.yaml  ← seed + SQLite fallback (runtime source: specs table in DB)
        │
        ├── spec/
        │    ├── spec_repository.py   CRUD: create/activate/update/seed specs in DB
        │    └── spec_loader.py       get_spec() — DB-first, YAML fallback
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     pgvector search (FAISS fallback)
        │
        ├── agents/
        │    ├── state.py              AgentState TypedDict
        │    ├── planner.py            LLM → structured ToolSelection + fallback policy
        │    ├── llm_factory.py        get_chat_model() + invoke_with_fallback()
        │    ├── tools.py              tool wrappers consuming spec defaults
        │    ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
        │    └── judge.py             online quality gate + single-pass revision
        │
        ├── db/
        │    ├── engine.py             SQLAlchemy engine, get_session()
        │    ├── models.py             AgentSession, AgentRun, KnowledgeDocument, Spec, SpecVersion
        │    └── migrations/           Alembic (001_initial_schema, 002_spec_tables)
        │
        ├── memory/
        │    ├── checkpointer.py       PostgresSaver (SQLite fallback)
        │    └── session_manager.py    SQLAlchemy queries (SQLite fallback)
        │
        ├── evaluation/
        │    ├── observer.py           dual-write: JSONL + Postgres
        │    ├── metrics.py            reads from Postgres (JSONL fallback)
        │    └── dashboard.py          HTML dashboard
        │
        └── config/settings.py        thin adapter over spec

app.py                    REPL (legacy)
streamlit_app.py          Web UI
docker-compose.yml        PostgreSQL 16 + pgvector
alembic.ini               migration config
tests/                    unit + integration tests
docs/                     inventario + roadmap
```

## Design principles (non-negotiable)

1. **Spec-driven**: domain knowledge in spec DB (versioned); YAML is seed + fallback
2. **LLM orchestrates, never computes**: structured output selects tools
3. **Tools are pure functions**: (spec, params) → result
4. **The graph is the architecture**: LangGraph defines the flow
5. **Provider-agnostic**: multi-provider via `llm_factory.py`
6. **Product-grade**: proper migrations, error handling, tests, Docker
7. **Dual-backend**: Postgres primary, SQLite/FAISS fallback when `DATABASE_URL` not set

## Database

PostgreSQL 16 with pgvector, managed via Docker Compose and Alembic.

```env
DATABASE_URL=postgresql://llull:llull@localhost:5432/llull
```

Five tables: `agent_sessions`, `agent_runs`, `knowledge_documents` (with vector(1536)), `specs`, `spec_versions`.

```bash
docker compose up -d                    # start Postgres
alembic upgrade head                    # run migrations
```

Without `DATABASE_URL`, the system falls back to SQLite + FAISS automatically.

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
docker compose up -d                    # Postgres
alembic upgrade head                    # migrations
python data/generate_data.py
python models/train_demand_model.py
python knowledge/build_index.py         # inserts into pgvector (or FAISS)
streamlit run streamlit_app.py          # web UI
```

## Testing

```bash
pytest                                  # unit tests
pytest -m integration                   # DB tests (needs Docker)
```

## Conventions

`black` (88), `ruff`, type hints, numpy docstrings, no bare except, config via .env/YAML.

## What NOT to change without discussion

Spec-driven principle, graph structure, `ToolSelection` schema, `_NODE_FORMULAS` registry.

## Git workflow

`feature/<item-id>-<desc>`, commits `[<item-id>] <desc>`, PRs into main.

## Completed items

### Paquete 1D ✅
- [x] 5.5 History window configurable
- [x] 5.6 Multi-provider LLM (OpenAI + Anthropic)
- [x] 12.4 Fallback between providers
- [x] 12.5 Rate limiting + graceful degradation
- [x] 5.7 Planner fallback policy
- [x] 4.1 Simulation params verified

### Paquete 1E ✅
- [x] 6.6 Streamlit UI

### Paquete 1A ✅
- [x] 1.1 PostgreSQL migration (PostgresSaver, SQLAlchemy, Alembic, dual-backend)
- [x] 1.2 pgvector (knowledge_documents, cosine search, FAISS fallback)
- [x] 8.1 Runs in Postgres (agent_runs table, dual-write, metrics from Postgres)
- [x] 1.5 Spec as data (specs + spec_versions tables, spec_repository CRUD, DB-first loader, spec traceability on runs)
- [x] 1.3 pgvector vs Qdrant ADR written (docs/adr-001-pgvector-over-qdrant.md)

## Next: Paquete 1B — FastAPI Agent Service

Expose the agent as a proper HTTP API (FastAPI monolith modular). Items: 6.1.e, 6.4, 6.5.

Or **Paquete 1C** — CI pipeline (GitHub Actions, pytest, linting, Docker build).

Full roadmap: `docs/llull_roadmap_v3.md`
Full backlog: `docs/llull_inventario_v3.md`
