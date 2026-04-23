# CLAUDE.md

## What is this project

Decision Intelligence Agent ("llull") — a spec-driven agent that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning. The LLM orchestrates; Python computes. Evolving from prototype to product.

## Core architecture

```
spec/organizational_model.yaml  ← single source of truth for the domain
        │
        ├── system/system_graph.py     DAG built from spec's causal_relationships
        ├── system/system_model.py     topological evaluation engine (formula registry)
        ├── simulation/montecarlo.py   Monte Carlo with noise from spec
        ├── optimization/optimizer.py  grid search over decision variable bounds
        ├── knowledge/retriever.py     FAISS RAG → migrating to pgvector
        │
        └── agents/
             ├── state.py              AgentState TypedDict
             ├── planner.py            LLM → structured ToolSelection + fallback policy
             ├── llm_factory.py        get_chat_model() + invoke_with_fallback()
             ├── tools.py              tool wrappers consuming spec defaults
             ├── workflow.py           LangGraph: planner → tool → synthesizer → judge → END
             └── judge.py             online quality gate + single-pass revision

memory/checkpointer.py   SqliteSaver → migrating to PostgresSaver
evaluation/observer.py    JSONL logging → adding Postgres writes
config/settings.py        thin adapter over spec
app.py                    REPL entry point (legacy)
streamlit_app.py          Web UI (chat + DAG + charts)
tests/                    unit tests
docs/                     inventario + roadmap (versioned)
```

## Design principles (non-negotiable)

1. **Spec-driven**: domain knowledge in `spec/organizational_model.yaml` only
2. **LLM orchestrates, never computes**: structured output selects tools
3. **Tools are pure functions**: (spec, params) → result, no side effects
4. **The graph is the architecture**: LangGraph defines the flow
5. **Provider-agnostic**: multi-provider via `llm_factory.py`
6. **Product-grade from now on**: proper migrations, error handling, tests, Docker. No prototype patches.

## Testing policy

Every PR must include tests. `pytest`. Mock LLM calls in unit tests. `@pytest.mark.integration` for DB/API tests.

## Conventions

`black` (88), `ruff`, type hints, numpy docstrings, no bare except, config via .env/YAML only.

## What NOT to change without discussion

Spec-driven principle, graph structure, `ToolSelection` schema, `_NODE_FORMULAS` registry.

## Git workflow

Feature branches: `feature/<item-id>-<desc>`. Commits: `[<item-id>] <desc>`. PRs into main.

## Completed items

- [x] **Paquete 1D** ✅ — 5.5, 5.6, 12.4, 12.5, 5.7, 4.1
- [x] **Paquete 1E** ✅ — 6.6 Streamlit UI

## Current work: Feature A — PostgreSQL migration (items 1.1 + 1.2 + 8.1)

**Branch**: `feature/1.1-postgresql-migration`

Migrate ALL persistence from SQLite + FAISS to PostgreSQL + pgvector. Product-grade: Alembic migrations, Docker Compose, connection pooling, environment-based config.

### New infrastructure

**docker-compose.yml** in project root:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: llull
      POSTGRES_USER: llull
      POSTGRES_PASSWORD: llull
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

**New env var**: `DATABASE_URL=postgresql://llull:llull@localhost:5432/llull`

**New dependencies** for requirements.txt:
```
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
psycopg[binary]>=3.1
alembic>=1.13
langgraph-checkpoint-postgres>=1.0
pgvector>=0.3
```

### New directory: `db/`

```
db/
├── engine.py          SQLAlchemy engine singleton, URL from DATABASE_URL env var
├── models.py          SQLAlchemy models for all tables
└── migrations/        Alembic migrations
    ├── env.py
    └── versions/
        └── 001_initial_schema.py
```

### Database schema (3 tables)

**agent_sessions** (replaces SQLite table in memory/checkpointer.py):
```sql
CREATE TABLE agent_sessions (
    session_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title        TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active  TIMESTAMPTZ NOT NULL DEFAULT now(),
    turn_count   INTEGER NOT NULL DEFAULT 0
);
```

**agent_runs** (item 8.1 — replaces JSONL in evaluation/observer.py):
```sql
CREATE TABLE agent_runs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id             UUID REFERENCES agent_sessions(session_id),
    run_id                 TEXT NOT NULL,
    timestamp              TIMESTAMPTZ NOT NULL DEFAULT now(),
    query                  TEXT NOT NULL,
    action                 TEXT,
    reasoning              TEXT,
    planner_latency_ms     FLOAT,
    tool_latency_ms        FLOAT,
    synthesizer_latency_ms FLOAT,
    judge_latency_ms       FLOAT,
    total_latency_ms       FLOAT,
    judge_score            FLOAT,
    judge_passed           BOOLEAN,
    judge_revised          BOOLEAN,
    judge_feedback         TEXT,
    confidence_score       FLOAT,
    success                BOOLEAN NOT NULL DEFAULT true,
    error                  TEXT,
    answer_length          INTEGER,
    planner_model          TEXT,
    synthesizer_model      TEXT,
    judge_model            TEXT,
    fallback_triggered     BOOLEAN DEFAULT false,
    raw_result             JSONB
);
CREATE INDEX idx_runs_session ON agent_runs(session_id);
CREATE INDEX idx_runs_timestamp ON agent_runs(timestamp);
```

**knowledge_documents** (item 1.2 — replaces FAISS index):
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE knowledge_documents (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content    TEXT NOT NULL,
    category   TEXT,
    embedding  vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_knowledge_embedding ON knowledge_documents
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 5);
```

### Files to modify

**memory/checkpointer.py**:
- Replace `SqliteSaver` with `PostgresSaver` from `langgraph-checkpoint-postgres`
- Read `DATABASE_URL` from env
- Keep `get_checkpointer()` interface so callers don't change
- Keep SQLite as fallback: if `DATABASE_URL` not set, fall back to SQLite with a warning log. This lets devs run without Docker during development.

**memory/session_manager.py**:
- Replace `sqlite3` queries with SQLAlchemy queries against `agent_sessions` model
- Same public API: `list_sessions()`, `get_session()`, `delete_session()`, `register_turn()`

**knowledge/build_index.py**:
- Replace FAISS creation with: generate embeddings via OpenAI, INSERT into `knowledge_documents` table
- Keep the same `DOCUMENTS` list — just change the storage backend
- If `DATABASE_URL` not set, fall back to FAISS with warning

**knowledge/retriever.py**:
- Replace FAISS load/search with pgvector cosine similarity query
- Same public API: `retrieve_knowledge(query, k=3) -> str`
- If `DATABASE_URL` not set, fall back to FAISS

**evaluation/observer.py**:
- Add parallel write to `agent_runs` table alongside existing JSONL
- JSONL stays as backup for now (dual-write)

**evaluation/metrics.py**:
- Add option to read from Postgres instead of JSONL
- Default to Postgres if `DATABASE_URL` is set, JSONL otherwise

**streamlit_app.py**:
- Update if it directly accesses SQLite or FAISS paths

**.env.example**:
- Add `DATABASE_URL`

### Implementation order

1. `docker-compose.yml` — verify Postgres + pgvector starts
2. `db/engine.py` — connection management
3. `db/models.py` — SQLAlchemy models
4. Alembic setup + initial migration
5. `memory/checkpointer.py` → PostgresSaver
6. `memory/session_manager.py` → SQLAlchemy
7. `knowledge/build_index.py` → pgvector inserts
8. `knowledge/retriever.py` → pgvector queries
9. `evaluation/observer.py` → dual-write (JSONL + Postgres)
10. `evaluation/metrics.py` → read from Postgres
11. Update `streamlit_app.py` if needed
12. Update `.env.example` and README
13. Tests

### Tests required

All DB tests marked `@pytest.mark.integration` (need Docker running):

- `tests/db/test_engine.py`: `test_engine_connects`
- `tests/db/test_models.py`: `test_session_crud`, `test_run_crud`, `test_knowledge_insert_and_search`
- `tests/memory/test_checkpointer_postgres.py`: `test_saves_and_loads_state`
- `tests/knowledge/test_retriever_pgvector.py`: `test_retrieve_relevant_docs`
- `tests/memory/test_fallback_to_sqlite.py`: `test_sqlite_fallback_when_no_database_url`

### What NOT to do

- Don't remove SQLite/FAISS code — keep behind fallback (`DATABASE_URL` present = Postgres, absent = SQLite/FAISS)
- Don't change the graph structure or tool interfaces
- Don't change how the spec is loaded (that's 1.5, next feature)

### Post-completion

After merge, update these files:
- `CLAUDE.md` — mark 1.1, 1.2, 8.1 as completed, update architecture diagram
- `docs/llull_roadmap_v3.md` — mark items as done in Paquete 1A
- `docs/llull_inventario_v3.md` — no structural changes needed
- Write `docs/adr-001-pgvector-over-qdrant.md` (item 1.3)

## Next after Feature A

- **Feature B (1.5)**: Spec as data in Postgres
- **Paquete 1B**: FastAPI Agent Service
- **Paquete 1C**: CI pipeline, Docker, test suites

Full roadmap: `docs/llull_roadmap_v3.md`
Full backlog: `docs/llull_inventario_v3.md`
