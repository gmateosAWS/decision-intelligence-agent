# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. Evolving from prototype to product.

## Core architecture

```
spec/organizational_model.yaml  ← seed + SQLite fallback (runtime: specs table in DB)
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

api/
├── main.py              FastAPI app, lifespan, CORS, global error handler
├── dependencies.py      get_db, get_graph (lru_cache singletons)
├── routers/
│    ├── query.py         POST /v1/query
│    ├── sessions.py      CRUD /v1/sessions
│    ├── runs.py          GET /v1/runs
│    ├── specs.py         CRUD /v1/specs
│    └── health.py        /healthz, /readyz, /v1/debug/config
└── schemas/             Pydantic request/response models

app.py                    REPL (legacy)
streamlit_app.py          Web UI
docker-compose.yml        PostgreSQL 16 + pgvector
alembic.ini               migration config
tests/                    unit + integration tests
docs/                     inventario, roadmap, ADRs
```

## Design principles (non-negotiable)

1. **Spec-driven**: domain knowledge in spec DB (versioned); YAML is seed + fallback
2. **LLM orchestrates, never computes**: structured output selects tools
3. **Tools are pure functions**: (spec, params) → result
4. **The graph is the architecture**: LangGraph defines the flow
5. **Provider-agnostic**: multi-provider via `llm_factory.py`
6. **Product-grade**: proper migrations, error handling, tests, Docker
7. **Dual-backend**: Postgres primary, SQLite/FAISS fallback when `DATABASE_URL` not set

## MANDATORY: Documentation updates on every PR

**Every PR must update ALL relevant documentation. This is not optional.**

Before committing, check and update each of these files if the changes affect them:

1. **`CLAUDE.md`** — update architecture diagram, completed items, current work section
2. **`README.md`** — update file tree, setup steps, env vars, feature descriptions
3. **`docs/llull_roadmap_v3.md`** — mark items as completed, update paquete status
4. **`docs/llull_inventario_v3.md`** — mark items as completed if applicable
5. **`docs/adr-*.md`** — write new ADR if an architectural decision was made
6. **`.env.example`** — add any new environment variables

If unsure whether a file needs updating, update it. Documentation debt compounds faster than technical debt.

## Database

PostgreSQL 16 with pgvector, managed via Docker Compose and Alembic.

```env
DATABASE_URL=postgresql://llull:llull@localhost:5432/llull
```

Five tables: `agent_sessions`, `agent_runs`, `knowledge_documents`, `specs`, `spec_versions`.

```bash
docker compose up -d
alembic upgrade head
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
docker compose up -d
alembic upgrade head
python data/generate_data.py
python models/train_demand_model.py
python knowledge/build_index.py
streamlit run streamlit_app.py
```

## Testing

```bash
pytest                                  # unit tests
pytest -m integration                   # DB tests (needs Docker)
```

## Conventions

`black` (88), `ruff`, type hints, numpy docstrings, no bare except, config via .env/YAML. Every feature includes tests. Every PR updates docs.

## What NOT to change without discussion

Spec-driven principle, graph structure, `ToolSelection` schema, `_NODE_FORMULAS` registry.

## Git workflow

`feature/<item-id>-<desc>`, commits `[<item-id>] <desc>`, PRs into main.

## Completed items

### Paquete 1D ✅
- [x] 5.5, 5.6, 12.4, 12.5, 5.7, 4.1

### Paquete 1E ✅
- [x] 6.6 Streamlit UI

### Paquete 1A ✅
- [x] 1.1 PostgreSQL, 1.2 pgvector, 8.1 runs in Postgres, 1.5 spec as data, 1.3 ADR

### Paquete 1B ✅
- [x] 6.1.e Agent Service (FastAPI monolith modular, all routers, Pydantic schemas)
- [x] 6.4 Endpoints admin/health (/healthz, /readyz, /v1/debug/config)
- [x] 6.5 API versioning (/v1/ prefix)

## Current work

**Paquete 1C — CI pipeline** (GitHub Actions, Dockerfile, test suites v1)

Branch: `feature/11.1-ci-pipeline`

Items: 11.1 Pipeline CI, 11.3 Contenedorización (Dockerfile multi-stage), 5.2 Test suites v1

## Build and run (API)

```bash
uvicorn api.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Next after Paquete 1B

- **Paquete 1C**: CI pipeline (GitHub Actions), Dockerfile multi-stage, test suites v1
- Then I1 is complete → move to I2A

Full roadmap: `docs/llull_roadmap_v3.md`
Full backlog: `docs/llull_inventario_v3.md`
