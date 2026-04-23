# Decision Intelligence Agent

A **Decision Intelligence prototype** that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning -- orchestrated by an LLM agent.

The system combines spec-driven development and deterministic analytical components (causal model, ML, Monte Carlo simulation, optimization) with LLM-based orchestration using LangGraph and basic RAG for system knowledge. The LLM **does not compute decisions**: it orchestrates specialized tools that do.

---

## Concept

Traditional analytics pipelines stop at descriptive insight:

```
data -> dashboards -> human decision
```

Decision Intelligence systems reason about decisions directly:

```
data -> causal system model -> simulation -> optimization -> recommendation
```

In this prototype:

- the **organizational spec** declares the domain model as explicit, editable configuration
- the **causal graph (DAG)** represents how business variables relate and propagate
- **ML models** estimate unknown relationships from historical data
- **Monte Carlo simulation** evaluates decisions under uncertainty
- **optimization** searches for the best decision across the decision space
- an **LLM agent** orchestrates the process and synthesizes results in natural language

---

## Design Principles

### 1 - Spec-driven architecture

The organizational model is stored as a **versioned database object** in the `specs` table (PostgreSQL). `spec/organizational_model.yaml` is the initial seed and the fallback when no database is available. The causal graph, simulation engine, optimizer, and agent all read from the active spec at runtime via `get_spec()`, which queries the database first and falls back to the YAML file when `DATABASE_URL` is not set.

To adapt the system to a new domain or change a business parameter: **edit the spec**. No code changes required.

```yaml
# spec/organizational_model.yaml (excerpt)
variables:
  decisions:
    - name: price
      description: 'Unit sale price of the product'
      unit: 'EUR'
      bounds:
        min: 10.0
        max: 50.0
        steps: 60 # grid resolution for optimization
      default: 25.0

    - name: marketing_spend
      description: 'Monthly marketing investment'
      unit: 'EUR'
      bounds:
        min: 1000.0
        max: 50000.0
        steps: 20
      default: 10000.0

causal_relationships:
  - from: [price, marketing_spend]
    to: demand
    type: ml_estimated
    description: 'Demand is a function of price and marketing, learned by ML'

  - from: [price, demand]
    to: revenue
    type: formula
    description: 'Revenue = price x demand'

  - from: [demand]
    to: cost
    type: formula
    description: 'Cost = demand x unit_cost'

  - from: [revenue, cost]
    to: profit
    type: formula
    description: 'Profit = revenue - cost'
```

### 2 - LLM orchestrates, tools compute

The LLM never computes a business decision. It selects the appropriate analytical tool (via structured output), passes the query to it, and synthesizes the tool result into a natural language response.

```
User query -> Planner (LLM, tool selection) -> Tool (deterministic computation) -> Synthesizer (LLM, natural language) -> Answer
```

This separation makes the system **auditable, testable, and governable**: every computation is deterministic and inspectable, independent of the LLM.

### 3 - Graph-driven propagation

The causal DAG is not decorative. The `SystemModel.evaluate()` method propagates values through the graph in **topological order**: each node is computed only after all its causal predecessors have been resolved. Adding a new causal variable requires only registering its formula and adding an edge to the graph -- no changes to the evaluation logic.

---

## Architecture

```mermaid
flowchart TD
    User[User]
    Agent["LangGraph Agent
planner - tool - synthesizer - judge"]
    Spec["Organizational Spec
specs table (DB) · YAML fallback"]
    SimTool[Simulation Tool]
    OptTool[Optimization Tool]
    KnowTool[RAG Knowledge Tool]
    SimEngine[Monte Carlo Engine]
    VectorDB["Vector Database
20 documents - 6 categories"]
    SystemModel["System Model
causal DAG traversal"]
    MLModel["RandomForest
demand estimator"]
    Judge["Online Judge
LLM quality gate"]
    Data[Historical Sales Data]

    User --> Agent
    Spec --> SystemModel
    Spec --> SimEngine
    Spec --> OptTool

    Agent --> SimTool
    Agent --> OptTool
    Agent --> KnowTool
    Agent --> Judge

    SimTool --> SimEngine
    OptTool --> SimEngine
    KnowTool --> VectorDB

    SimEngine --> SystemModel
    SystemModel --> MLModel
    MLModel --> Data
```

---

## Capabilities

The prototype combines several architectural capabilities that make it suitable for
decision support, system explainability, and controlled LLM interaction:

- **Spec-driven domain modeling** -- business variables, causal relationships,
  simulation settings, optimization targets, and synthetic demand-model coefficients
  are stored as a versioned object in PostgreSQL (`specs` table); `spec/organizational_model.yaml`
  is the initial seed and fallback when no database is configured.
- **Deterministic analytical execution** -- optimization, Monte Carlo simulation,
  and graph propagation are performed by Python components, not by the LLM.
- **Online answer validation** -- the synthesizer output passes through an
  LLM-based judge that checks grounding, responsiveness and quantitative consistency
  before the final answer is returned.
- **Structured observability** -- every run captures tool choice, latencies,
  confidence signals, judge verdicts and final outcome in PostgreSQL (`agent_runs`) and JSONL logs.
- **Spec traceability** -- each run records the `spec_id` and `spec_version` it executed under,
  so every recommendation is tied to the exact domain model that produced it.
- **Persistent conversational memory** -- session context is stored in PostgreSQL
  (SQLite fallback) so the planner can resolve follow-up questions across multiple turns.
- **Domain-agnostic parameter extraction** -- the planner extracts decision
  parameters generically from natural language using the decision-variable names
  defined in the spec.

---

## Agent Execution Flow

```mermaid
flowchart LR
    User[User Query]
    Planner["Planner
(LLM - structured output)"]
    Opt[Optimization Tool]
    Sim[Simulation Tool]
    Know[Knowledge RAG]
    Synth["Synthesizer
(LLM - natural language)"]
    Judge["Judge
(LLM - quality gate)"]
    Answer[Final Answer]

    User --> Planner
    Planner -->|optimization| Opt
    Planner -->|simulation| Sim
    Planner -->|knowledge| Know
    Opt --> Synth
    Sim --> Synth
    Know --> Synth
    Synth --> Judge
    Judge --> Answer
```

The planner uses **structured output** (Pydantic schema) to guarantee the tool selection is always a valid, typed value -- no fragile string parsing.

The synthesizer receives the raw tool result and produces a business-oriented draft response: it explains what the numbers mean, not just what they are.

The online judge evaluates that draft against the original query and the raw tool output. If the answer is insufficiently grounded, incomplete or quantitatively inconsistent, the judge requests a revision before returning the final answer to the user.

---

## Core Components

### Organizational Spec (`spec/`)

`organizational_model.yaml` declares (and seeds the database with):

- **Decision variables**: controllable inputs (price, marketing spend), with bounds and defaults
- **Intermediate variables**: derived or ML-estimated (demand, revenue, cost)
- **Target variables**: business outcomes to optimize (profit)
- **Causal relationships**: the edges of the DAG, with type (ml_estimated / formula)
- **Business parameters**: unit cost and other domain constants
- **Simulation configuration**: Monte Carlo runs, noise model
- **Optimization configuration**: target, method, fixed variables

`spec_repository.py` provides CRUD operations (`create_spec`, `activate_spec`, `update_spec`, `seed_from_yaml`, etc.) for the `specs` and `spec_versions` tables. On first startup with Postgres, `seed_from_yaml()` imports the YAML as version `1.0.0` with status `active`; subsequent startups are no-ops.

`spec_loader.py` exposes a singleton `get_spec()` that reads the active spec from the database when `DATABASE_URL` is set, and falls back to parsing `organizational_model.yaml` otherwise. The typed `OrganizationalModelSpec` dataclass is the same in both paths.

---

### Data Layer (`data/`)

Synthetic sales data is generated to simulate historical observations. All parameters
are read from `spec/organizational_model.yaml` -- no numeric literals in code.

Variables: `price`, `marketing`, `demand`

Demand follows the relationship declared in the spec under `demand_model`:

```
demand = base_demand
         + price_elasticity * price
         + marketing_effect * marketing_spend
         + noise(sigma=noise_sigma)
```

Current spec values (`spec/organizational_model.yaml` v1.2.0):

| Parameter          | Value  | Description                                       |
| ------------------ | ------ | ------------------------------------------------- |
| `base_demand`      | 120.0  | Intercept: baseline units at price=0, marketing=0 |
| `price_elasticity` | -1.6   | Units lost per EUR increase in price              |
| `marketing_effect` | 0.0009 | Units gained per EUR of marketing spend           |
| `noise_sigma`      | 5.0    | Std dev of Gaussian demand noise (units)          |

Data generation ranges (declared under `data_generation` in the spec):

- `price`: sampled from `uniform(price_min=10, price_max=50)` -- matches decision variable bounds
- `marketing`: sampled from `uniform(marketing_min=1000, marketing_max=20000)` -- real EUR scale
- `n_samples`: 2,000 -- `random_seed`: 42 (reproducibility)

To recalibrate the demand model: edit `demand_model` and/or `data_generation` in the spec,
then re-run `python data/generate_data.py` and `python models/train_demand_model.py`.

---

### Predictive Model (`models/`)

A **RandomForest regressor** estimates the demand function from historical data:

```
(price, marketing_spend) -> demand
```

Training includes an 80/20 train/test split stratified by price quantiles. Verified performance on held-out test set:

| Metric | Value                                          |
| ------ | ---------------------------------------------- |
| R2     | 0.9257 -- explains 92.6% of demand variability |
| MAE    | 4.58 units                                     |
| RMSE   | 5.66 units                                     |

Feature importances confirm the expected causal structure:

| Feature         | Importance |
| --------------- | ---------- |
| price           | 90.87%     |
| marketing_spend | 9.13%      |

The trained model is persisted to `models/demand_model.pkl`.

---

### System Model (`system/`)

The business is represented as a **causal Directed Acyclic Graph (DAG)**:

```mermaid
flowchart LR
    price([price])
    marketing([marketing_spend])
    demand([demand])
    revenue([revenue])
    cost([cost])
    profit([profit])

    price --> demand
    marketing --> demand
    price --> revenue
    demand --> revenue
    demand --> cost
    revenue --> profit
    cost --> profit

    classDef decision fill:#4A90D9,stroke:#2C5F8A,color:#fff
    classDef variable fill:#6EAF7C,stroke:#3D7A4A,color:#fff
    classDef target   fill:#E8A838,stroke:#B07820,color:#fff

    class price,marketing decision
    class demand,revenue,cost variable
    class profit target
```

`SystemModel.evaluate()` performs a **topological traversal** of the DAG:

1. Initialises decision nodes with input values
2. For each node in topological order: computes via ML model (demand) or registered formula (revenue, cost, profit)
3. Returns a complete dict of all variable values

The graph structure is loaded from the spec -- adding a new causal variable requires only a new formula entry and a new edge in `system/system_graph.py`.

---

### Simulation Engine (`simulation/`)

`monte_carlo()` evaluates a `(price, marketing)` decision under uncertainty by running **N independent simulations** (default: 500, configurable in the spec), each with a Gaussian perturbation on the demand estimate.

Output statistics:

| Field               | Description                              |
| ------------------- | ---------------------------------------- |
| `expected_profit`   | Mean profit across all runs              |
| `profit_std`        | Standard deviation -- spread of outcomes |
| `profit_p10`        | 10th percentile -- pessimistic scenario  |
| `profit_p90`        | 90th percentile -- optimistic scenario   |
| `expected_demand`   | Mean demand across all runs              |
| `demand_std`        | Demand variability                       |
| `downside_risk_pct` | % of runs where profit < 0               |
| `n_runs`            | Number of simulations executed           |

---

### Optimization (`optimization/`)

`optimize_price()` performs a **grid search** over the price range (bounds from spec), evaluating each candidate price via Monte Carlo simulation and selecting the one that maximises `expected_profit`.

Marketing spend is held fixed at the value declared in `spec.optimization.fixed_variables`.

Validated scenario results:

| Scenario  | Price      | Demand    | Expected Profit | Downside Risk |
| --------- | ---------- | --------- | --------------- | ------------- |
| Default   | EUR 25     | ~88 units | ~EUR 1,328      | 0%            |
| Optimized | ~EUR 48.64 | ~55 units | ~EUR 2,139      | 0%            |

The optimum reflects the trade-off between lower volume and higher margin per unit: even though demand drops from 88 to 55 units (-38%), the margin increase from EUR 15 to EUR 48.64 per unit (+158%) more than compensates.

---

### Knowledge Layer (`knowledge/`)

A FAISS vector database indexes **20 domain documents** across 6 categories:

| Category         | Content                                                      |
| ---------------- | ------------------------------------------------------------ |
| `business_model` | Business overview, decision variables, constraints           |
| `causal_model`   | Demand function, revenue, cost, profit relationships         |
| `ml_model`       | RandomForest description, uncertainty interpretation         |
| `simulation`     | Monte Carlo methodology, output interpretation, risk metrics |
| `optimization`   | Grid search approach, optimal price interpretation           |
| `interpretation` | Price elasticity, marketing ROI, decision guidance           |

The vector store is loaded **lazily** (on first query, not at import time). If the index does not exist, an explicit error is raised with instructions.

---

### Agent Layer (`agents/`)

The agent is implemented as a **4-node LangGraph graph**:

**`planner_node`** -- Selects the appropriate tool using structured output (provider and model configurable via `PLANNER_PROVIDER` / `PLANNER_MODEL` env vars; defaults to OpenAI `gpt-4o-mini`). The system prompt is built dynamically from the spec, listing all decision variable names and ranges, and includes **few-shot examples generated from the spec** that demonstrate correct tool routing for optimization, simulation, and knowledge queries. The prompt also enforces a **Chain-of-Thought sequence** in the `reasoning` field: the LLM must articulate (1) what the user is asking, (2) whether concrete variable values are mentioned, (3) whether the intent is exploratory/optimization or conceptual, and (4) which tool fits best and why -- before committing to a tool choice. Output is a typed `ToolSelection(tool, reasoning, params)` object -- no string parsing. If the LLM call fails after retries, the planner falls back to the `knowledge` tool with a structured error message rather than crashing the graph.

**`tool_node`** -- Executes the selected tool. Wrapped in `try/except`: errors are captured and propagated to the state rather than crashing the graph.

**`synthesizer_node`** -- Receives the raw tool output and the original query, and produces a business-oriented draft answer (model configurable via `SYNTHESIZER_MODEL` env var, defaults to `gpt-4o-mini`): what do the numbers mean, what should the decision-maker do, and what risks or caveats matter.

**`judge_node`** -- Evaluates the synthesized answer online before it is returned to the user. The judge checks whether the answer is grounded in the raw tool output, whether it actually answers the user's question, and whether it is quantitatively consistent. If the answer does not meet the configured quality threshold, the judge revises it once and returns the corrected version.

**`AgentState`** TypedDict fields:

| Field            | Set by        | Description                                                         |
| ---------------- | ------------- | ------------------------------------------------------------------- |
| `query`          | Input         | User's original question                                            |
| `action`         | Planner       | Selected tool name                                                  |
| `reasoning`      | Planner       | LLM's reasoning for tool selection                                  |
| `params`         | Planner       | Generic dict of extracted variable values -- e.g. `{"price": 30.0}` |
| `raw_result`     | Tool          | Raw output from the analytical tool                                 |
| `answer`         | Judge         | Final natural language response returned to the user                |
| `run_id`         | Input         | Observability correlation ID                                        |
| `judge_score`    | Judge         | Overall quality score assigned by the online judge                  |
| `judge_passed`   | Judge         | Whether the initial synthesized answer passed without revision      |
| `judge_feedback` | Judge         | Judge explanation of why the answer was approved or revised         |
| `judge_revised`  | Judge         | Whether the answer had to be rewritten once before delivery         |
| `history`        | Judge         | Accumulated (query, answer) turn pairs -- merged via `operator.add` |

---

## Repository Structure

```
decision-intelligence-agent/
+-- spec/
|   +-- organizational_model.yaml   # Seed YAML + SQLite fallback (runtime source: specs table)
|   +-- spec_loader.py              # get_spec(): DB-first, YAML fallback; typed dataclasses
|   +-- spec_repository.py          # CRUD: create/activate/update/seed specs in DB
|   +-- __init__.py
+-- db/
|   +-- engine.py                   # SQLAlchemy engine, get_session() context manager
|   +-- models.py                   # ORM: AgentSession, AgentRun, KnowledgeDocument, Spec, SpecVersion
|   +-- migrations/
|       +-- env.py                  # Alembic env (psycopg3 URL normalisation)
|       +-- versions/
|           +-- 001_initial_schema.py   # agent_sessions, agent_runs, knowledge_documents
|           +-- 002_spec_tables.py      # specs, spec_versions, spec FK on agent_runs
+-- data/
|   +-- generate_data.py            # Synthetic dataset -- all params read from spec
+-- models/
|   +-- train_demand_model.py       # RF training, evaluation metrics, model export
+-- system/
|   +-- system_graph.py             # Causal DAG -- edges loaded from spec
|   +-- system_model.py             # Graph-traversal evaluation engine
+-- simulation/
|   +-- montecarlo.py               # Monte Carlo engine (N runs, noise model)
|   +-- scenario_runner.py          # Scenario wrapper
+-- optimization/
|   +-- optimizer.py                # Grid search over price range
+-- knowledge/
|   +-- build_index.py              # pgvector index builder (20 docs, 6 categories; FAISS fallback)
|   +-- retriever.py                # Similarity search: pgvector primary, FAISS fallback
+-- agents/
|   +-- state.py                    # AgentState TypedDict
|   +-- tools.py                    # Tool wrappers (spec-driven defaults + generic params)
|   +-- llm_factory.py              # get_chat_model() + invoke_with_fallback() + LLMUnavailableError
|   +-- planner.py                  # LLM planner: dynamic prompt + structured output + fallback policy
|   +-- judge.py                    # Online answer-quality judge and single-pass reviser
|   +-- workflow.py                 # LangGraph: planner -> tool -> synthesizer -> judge
+-- memory/
|   +-- __init__.py                 # Public exports
|   +-- checkpointer.py             # PostgresSaver (SqliteSaver fallback) + session helpers
|   +-- session_manager.py          # CRUD: Postgres primary, SQLite fallback
+-- evaluation/
|   +-- __init__.py
|   +-- observer.py                 # AgentObserver: run lifecycle, dual-write JSONL + Postgres
|   +-- metrics.py                  # load_runs / compute_metrics (Postgres primary, JSONL fallback)
|   +-- dashboard.py                # HTML dashboard generator + CLI entry point
+-- config/
|   +-- settings.py                 # Thin adapter over spec (backward-compatible)
+-- logs/                           # Created at runtime
|   +-- agent_runs.jsonl            # Append-only run log (JSONL fallback / duplicate)
|   +-- agent.log                   # Verbose debug log
|   +-- dashboard.html              # Generated by evaluation/dashboard.py
+-- tests/
|   +-- agents/
|   |   +-- test_llm_factory.py     # Unit tests: provider factory, fallback, retry, graceful error
|   +-- spec/
|       +-- test_spec_repository.py # Integration tests: spec CRUD + traceability (needs Postgres)
|       +-- test_spec_loader_db.py  # Integration + unit: DB-first load + YAML fallback
+-- docs/
|   +-- llull_roadmap_v3.md         # Iteration plan with progress tracking (I1 → I2A → I2B → I3)
|   +-- llull_inventario_v3.md      # Full backlog (97 items)
|   +-- adr-001-pgvector-over-qdrant.md  # Architecture decision record: vector store choice
+-- app.py                          # REPL entry point (legacy, dev use)
+-- streamlit_app.py                # Web UI: chat + causal DAG + result charts + spec version
+-- docker-compose.yml              # PostgreSQL 16 + pgvector
+-- alembic.ini                     # Alembic migration config
+-- .env.example                    # Environment variable template
+-- requirements.txt
+-- README.md
```

---

## Setup

**1. Create and activate a virtual environment**

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
# Git Bash on Windows:
source venv/Scripts/activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Start PostgreSQL and run migrations (optional but recommended)**

```bash
docker compose up -d        # starts PostgreSQL 16 + pgvector on port 5432
alembic upgrade head        # creates all tables (agent_sessions, agent_runs, knowledge_documents, specs, spec_versions)
```

Without this step the system runs in SQLite/FAISS fallback mode automatically.

**4. Configure API keys and model settings**

Create a `.env` file in the project root (copy from `.env.example`):

```env
# --- Database (optional — SQLite fallback if unset) ---
DATABASE_URL=postgresql://llull:llull@localhost:5432/llull

# --- API Keys ---
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key   # required if any node uses provider=anthropic

# --- Per-node provider and model ---
PLANNER_PROVIDER=openai          # "openai" or "anthropic"
PLANNER_MODEL=gpt-4o-mini        # e.g. "claude-sonnet-4-6" for Anthropic
SYNTHESIZER_PROVIDER=openai
SYNTHESIZER_MODEL=gpt-4o-mini
JUDGE_PROVIDER=openai
JUDGE_MODEL=gpt-4o-mini
JUDGE_THRESHOLD=0.75

# --- Fallback provider (used automatically on primary failure) ---
FALLBACK_PROVIDER=anthropic
FALLBACK_MODEL=claude-haiku-4-5-20251001

# --- Resilience ---
LLM_MAX_RETRIES=2     # retries on 429 before switching to fallback
LLM_TIMEOUT=30        # per-call timeout in seconds

# --- History ---
HISTORY_WINDOW=3      # previous turns injected into the planner prompt
```

* Each node (`PLANNER`, `SYNTHESIZER`, `JUDGE`) can use a different provider and model independently — set `*_PROVIDER` to `"openai"` or `"anthropic"` and `*_MODEL` to the corresponding model identifier.
* `FALLBACK_PROVIDER` / `FALLBACK_MODEL` configure an automatic secondary provider used by all nodes when the primary fails (API error, rate limit exhausted, timeout).
* `LLM_MAX_RETRIES` controls how many times a rate-limited call (HTTP 429) is retried with exponential backoff before falling back to the secondary provider.
* `JUDGE_THRESHOLD` defines the minimum score required for a synthesized draft to pass without revision.

OpenAI keys: https://platform.openai.com/api-keys — Anthropic keys: https://console.anthropic.com/

---

## Build Artefacts

These steps generate the files the agent needs at runtime. Run them once after setup (and again if you modify the spec or data):

**Generate synthetic dataset**

```bash
python data/generate_data.py
```

**Train the demand model**

```bash
python models/train_demand_model.py
```

Output: `models/demand_model.pkl` -- also prints MAE, RMSE and R2 on the test set.

**Build the knowledge index**

```bash
python knowledge/build_index.py
```

With `DATABASE_URL` set: inserts 20 document embeddings into the `knowledge_documents` table (pgvector).  
Without it: writes `knowledge_index/` directory (FAISS fallback).

> **Organizational spec**: loaded automatically at runtime. If `DATABASE_URL` is set and the `specs` table is empty, the system seeds `spec/organizational_model.yaml` as version `1.0.0` on first startup — no manual step required.

---

## Run the Web UI

```bash
streamlit run streamlit_app.py
```

The web interface provides:

- **Chat** — conversational interface with the same multi-turn memory as the REPL
- **Sidebar** — session management (new / resume with history restored), active LLM configuration, domain info, active spec version (with source: DB or YAML), and a causal DAG visualization
- **Results details** — inline charts per response: profit distribution (simulation), optimal values (optimization)
- **Run details** — tool badge, per-node latency, judge score, planner reasoning (collapsed by default)

---

## Run the Agent (legacy REPL)

```bash
python app.py
```

**Example session:**

```
+--------------------------------------------------------------+
|  Decision Intelligence Agent  *  v3 (memory)                 |
+--------------------------------------------------------------+
|  Ask business questions about pricing and marketing.         |
|  Commands:                                                   |
|    session new | list | resume <id|#> | info | delete <id>   |
|    dashboard * exit                                          |
+--------------------------------------------------------------+

* New session: 3f8a2c1d-...

Ask a business question: What price maximises profit?

  The optimization analysis recommends a price of approximately EUR 48.64,
  yielding an expected profit of ~EUR 2,139 with 55 units of demand.
  Downside risk is 0%. While demand drops from ~88 units at the default
  EUR 25 price, the higher margin per unit (EUR 38.64 vs EUR 15.00) more
  than compensates. Profit at the 10th percentile is still ~EUR 1,865,
  confirming a stable outcome.

Ask a business question: What about simulating at price 30?

  At EUR 30.00 the simulation shows expected profit of ~EUR 1,559 (demand
  ~78 units, std ~8 units). Compared to the optimum of EUR 48.64, this
  represents a EUR 580 reduction in expected profit but higher volume.
  Downside risk remains 0%.

Ask a business question: exit
Goodbye.
```

---

## Observability and Evaluation Layer (`evaluation/`)

Every agent run is captured, measured and visualisable.

### Architecture

```
app.py
  +-- AgentObserver.start_run(query)          opens a RunRecord
       +-- planner_node      -> obs.record_planner()
       +-- tool_node         -> obs.record_tool()
       +-- synthesizer_node  -> obs.record_synthesizer()
       +-- judge_node        -> obs.record_judge()
  +-- AgentObserver.set_spec(spec_id, version) attaches spec traceability
  +-- AgentObserver.end_run()                 dual-writes: Postgres agent_runs + JSONL

db/
  +-- agent_runs   Postgres table (primary sink)
logs/
  +-- agent_runs.jsonl   append-only fallback / duplicate
  +-- agent.log          verbose debug log
  +-- dashboard.html     generated on demand
```

### Components

| Module                    | Responsibility                                                                                           |
| ------------------------- | -------------------------------------------------------------------------------------------------------- |
| `evaluation/observer.py`  | `AgentObserver` -- wraps each run, records timing, confidence signals, spec traceability, judge verdicts; dual-writes to Postgres + JSONL |
| `evaluation/metrics.py`   | `load_runs` / `compute_metrics` -- reads from Postgres (`agent_runs`) with JSONL fallback; aggregates latency, confidence and judge-quality metrics |
| `evaluation/dashboard.py` | `generate_html_dashboard` -- self-contained HTML with Chart.js; CLI entry point                          |

### RunRecord fields

| Field                    | Source           | Description                                                                                   |
| ------------------------ | ---------------- | --------------------------------------------------------------------------------------------- |
| `run_id`                 | observer         | Unique ID per query (12-char hex)                                                             |
| `session_id`             | observer         | Groups runs within one session                                                                |
| `timestamp`              | observer         | ISO-8601 UTC                                                                                  |
| `query`                  | input            | Raw user question                                                                             |
| `action`                 | planner          | `optimization` / `simulation` / `knowledge`                                                   |
| `reasoning`              | planner          | LLM's explanation of tool choice                                                              |
| `planner_latency_ms`     | planner node     | Time from entry to structured output                                                          |
| `tool_latency_ms`        | tool node        | Time to execute the analytical tool                                                           |
| `synthesizer_latency_ms` | synthesizer node | Time for first natural-language draft                                                         |
| `judge_latency_ms`       | judge node       | Time for online answer validation and optional revision                                       |
| `judge_score`            | judge node       | Final quality score assigned by the online judge                                              |
| `judge_passed`           | judge node       | Whether the synthesizer draft passed without revision                                         |
| `judge_revised`          | judge node       | Whether the judge rewrote the answer once before delivery                                     |
| `judge_feedback`         | judge node       | Short explanation of the judge verdict                                                        |
| `total_latency_ms`       | observer         | End-to-end wall time                                                                          |
| `confidence_score`       | observer         | Derived: `1 - downside_risk_pct/100` for Monte Carlo, `1.0` for optimization, `0.9` for RAG |
| `raw_result_keys`        | tool node        | Dict keys returned by the tool                                                                |
| `success`                | observer         | `false` if any node raised an exception                                                       |
| `error`                  | observer         | Exception message if `success=false`                                                          |
| `answer_length`          | judge            | Character count of the final answer delivered to the user                                     |
| `planner_model`          | planner node     | LLM model used for tool selection                                                             |
| `synthesizer_model`      | synthesizer node | LLM model used for natural language synthesis                                                 |
| `judge_model`            | judge node       | LLM model used for online answer validation                                                   |
| `spec_id`                | observer         | UUID of the `specs` row active when this run executed                                         |
| `spec_version`           | observer         | Semver string of the active spec (e.g. `1.0.0`); enables per-version performance analysis     |

### JSONL sample (new fields)

```json
{
  "planner_model": "claude-sonnet-4-6",
  "synthesizer_model": "gpt-4o-mini",
  "judge_model": "gpt-4o-mini"
}
```

These fields are logged per run, enabling analysis of model performance across different configurations. When a provider fallback is triggered (primary failure or rate-limit exhaustion), the event is recorded in `agent.log` at `WARNING` level with the exception type and the model that handled the call — so fallback frequency is fully observable without changing the JSONL schema.

### LangSmith integration

Set these variables in `.env` to enable automatic tracing of every LangGraph invocation:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls__your_key
LANGCHAIN_PROJECT=decision-intelligence-agent
```

`AgentObserver.langsmith_config()` injects `run_name`, `tags` and `metadata` so each run appears named and tagged in the LangSmith UI. No code changes required -- tracing activates automatically when the env var is present.

### View metrics

**CLI report** (prints to terminal):

```bash
python -m evaluation.dashboard
```

**HTML dashboard** (opens in browser):

```bash
python -m evaluation.dashboard --out logs/dashboard.html
# then open logs/dashboard.html in your browser
```

**Inline (from the REPL)**:

```
Ask a business question: dashboard
```

The dashboard includes:

- KPI cards: total runs, success rate, avg latency, avg confidence
- Judge metrics: average judge score, approval rate and revision rate
- Tool distribution doughnut chart
- Latency breakdown bar chart (planner / tool / synthesizer / judge)
- Recent runs table with per-run confidence bars
- Error log (if any failures occurred)

---

## Conversational Memory

### Goal

Give the agent **persistent multi-turn memory** and a **session management** system that allows:

- Maintaining conversation context across multiple turns within the same session
- Resuming previous sessions after restarting the process
- Listing, inspecting and deleting sessions from the CLI

### Architecture

```
app.py (REPL)
|
+-- memory/
|   +-- __init__.py          Public exports
|   +-- checkpointer.py      PostgresSaver (SqliteSaver fallback) + session helpers
|   +-- session_manager.py   CRUD: Postgres primary, SQLite fallback
|
+-- agents/
|   +-- state.py             adds `history` field (Annotated + operator.add)
|   +-- planner.py           injects last 3 turns into LLM prompt
|   +-- workflow.py          build_graph(checkpointer=...) with persistence
|
+-- db/
    +-- models.py            AgentSession ORM model (Postgres)
    +-- engine.py            get_session() context manager
```

### `memory/checkpointer.py`

| Responsibility             | Detail                                                                            |
| -------------------------- | --------------------------------------------------------------------------------- |
| `get_checkpointer()`       | Returns `PostgresSaver` if `DATABASE_URL` is set, `SqliteSaver` otherwise         |
| `register_turn()`          | Upsert in `agent_sessions` (Postgres or SQLite): updates `last_active` and `turn_count` |

The `agent_sessions` table is managed via SQLAlchemy ORM (`db/models.AgentSession`) in Postgres mode and via a raw SQLite schema in fallback mode. Both expose the same columns:

```sql
session_id  UUID / TEXT PRIMARY KEY
title       TEXT    -- first 60 chars of the first query
created_at  TIMESTAMPTZ / TEXT
last_active TIMESTAMPTZ / TEXT, updated on each turn
turn_count  INTEGER
```

### `memory/session_manager.py`

```python
SessionManager.list_sessions()        # -> List[dict]
SessionManager.get_session(sid)       # -> dict | None
SessionManager.delete_session(sid)    # -> bool
SessionManager.print_sessions()       # numbered table in stdout
SessionManager.session_info(sid)      # details of a session
```

### `agents/state.py`

```python
history: Annotated[List[Dict[str, str]], operator.add]
```

`operator.add` tells LangGraph that `history` returns from each node are **concatenated** rather than replaced, accumulating all turns.

### `agents/planner.py`

```python
_HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "3"))  # configurable via env var

messages = [system_prompt]
for turn in history[-_HISTORY_WINDOW:]:
    messages += [{"role": "user",      "content": turn["query"]},
                 {"role": "assistant", "content": turn["answer"]}]
messages.append({"role": "user", "content": current_query})
```

This enables natural cross-turn references:

```
User: "What is the optimal price?"
User: "And if price is 28?"  <- planner understands the context
```

### `agents/workflow.py`

`build_graph(checkpointer=...)` compiles the LangGraph workflow with persistent state. The graph now includes an online quality gate after synthesis:

```
planner -> tool -> synthesizer -> judge -> END
```

This keeps the answer-validation logic inside the graph itself, so the final response is governed before it reaches the user.

### Turn flow

```
User writes query
     |
     v
app.py: start_run() + build config {thread_id, observer}
     |
     v
graph.invoke()
  +-- planner_node    -> injects history[-3:] into LLM prompt
  +-- tool_node       -> executes optimization / simulation / knowledge
  +-- synthesizer_node -> generates answer + returns {history: [new_turn]}
     |
     v
SqliteSaver persists complete state (accumulated history)
     |
     v
register_turn() -> upsert in agent_sessions
     |
     v
observer.end_run() -> writes logs/agent_runs.jsonl
```

### Session management commands

```
session new              new session (new thread_id)
session list             list saved sessions
session resume <id>      resume by full session_id
session resume <#>       resume by index from 'session list'
session info             details of active session
session delete <id>      remove session from registry
dashboard                CLI metrics + dashboard.html
exit                     quit
```

The `thread_id` is passed in the LangGraph config:

```python
cfg["configurable"]["thread_id"] = session_id
result = graph.invoke({"query": raw, "run_id": run_id}, config=cfg)
```

### Example multi-turn session

```
$ python app.py

  * New session: 3f8a2c1d-...

Ask a business question: What price maximises profit?
  The optimization analysis suggests ~EUR 48.64, expected profit ~EUR 2,139 ...

Ask a business question: What if price is 20?
  At EUR 20.00 the simulation shows expected profit of ~EUR 951, demand ~95 units ...

Ask a business question: session list
  #   Session ID          Turns  Last active           Title
  1   3f8a2c1d-...        2      2025-07-16 10:22:01   What price maximises pro

Ask a business question: session info
  Session ID   : 3f8a2c1d-...
  Title        : What price maximises profit?
  Created      : 2025-07-16T10:21:44+00:00
  Last active  : 2025-07-16T10:22:01+00:00
  Turn count   : 2

# --- After restart ---

Ask a business question: session resume 1
  Session resumed: 3f8a2c1d-... (2 turns)

Ask a business question: And what about price 28?
  Building on previous context: at EUR 28.00 expected profit is ~EUR 1,232 ...
```

---

## Dynamic Parameter Extraction

### Goal

Make parameter extraction from user queries fully **domain-agnostic**. Before this, the `ToolSelection` Pydantic schema had fixed fields `price: float | None` and `marketing: float | None`, coupling the planner to the retail domain. A generic `params` dict removes that coupling.

### The problem with hardcoded fields

```python
# BEFORE (coupled to retail domain)
class ToolSelection(BaseModel):
    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    price: float | None = None        # hardcoded field
    marketing: float | None = None    # hardcoded field
```

Changing the domain to energy (`generation_capacity`, `bid_price`) or healthcare (`staff_level`, `bed_count`) would require modifying the Pydantic schema and tool code -- exactly what the spec-driven architecture was meant to avoid.

### The generic solution

```python
# AFTER (domain-agnostic)
class DecisionParam(BaseModel):
    variable: str    # variable name from spec
    value: float     # value extracted from the user query

class ToolSelection(BaseModel):
    tool: Literal["optimization", "simulation", "knowledge"]
    reasoning: str
    params: List[DecisionParam] = []   # e.g. [{"variable": "price", "value": 30.0}]
```

### Dynamic system prompt from spec

The system prompt is built at runtime by reading the spec's decision variable names:

```python
def _build_system_prompt() -> str:
    spec = get_spec()
    vars_desc = "\n".join(
        f"  - {v.name}: range [{v.min}-{v.max}] {v.unit}, default {v.default}"
        for v in spec.decision_variables
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(
        domain=spec.domain,
        vars_description=vars_desc,
    )
```

The template instructs the LLM to extract values into `params` using the exact variable names from the spec:

```
If the user mentions a specific value for any decision variable
(e.g. "at 30", "if price is 28", "simulate with budget 5000"),
extract those values into the `params` list using the exact variable
names from the spec. Leave `params` empty to use spec defaults.
```

### `simulation_tool` with generic params

```python
def simulation_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    spec = get_spec()
    extracted = {p["variable"]: p["value"] for p in (state.get("params") or [])}

    # For each decision variable: extracted value > spec default
    kwargs = {
        v.name: extracted.get(v.name, v.default)
        for v in spec.decision_variables
    }

    var_names = [v.name for v in spec.decision_variables]
    result = run_scenario(
        system_model,
        kwargs[var_names[0]],   # first variable -> price
        kwargs[var_names[1]],   # second variable -> marketing_spend
    )
    return result
```

### Domain change without code changes

| Task                         | Before                                                | After          |
| ---------------------------- | ----------------------------------------------------- | -------------- |
| Change decision variables    | Edit YAML + edit ToolSelection + edit simulation_tool | Edit YAML only |
| Add a new decision variable  | Edit YAML + add field to schema                       | Edit YAML only |
| Change from retail to energy | Requires changes in planner, state, tools             | Edit YAML only |

### Validated tests

| Query                                                   | Params extracted             | Result                                                 |
| ------------------------------------------------------- | ---------------------------- | ------------------------------------------------------ |
| `Simulate profit at price 30`                           | `{"price": 30.0}`            | demand ~78 u, profit ~EUR 1,559                        |
| `What would happen if we set price at 20?`              | `{"price": 20.0}`            | demand ~95 u, profit ~EUR 951                          |
| `Run the simulation with default parameters`            | `{}`                         | default EUR 25 -> demand ~88 u, profit ~EUR 1,328      |
| `And what if marketing increases by 5000?` (multi-turn) | `{"marketing_spend": 15000}` | demand ~92 u, profit ~EUR 1,358; ROI +EUR 38/EUR 5,000 |

The last test demonstrates the interaction between multi-turn memory (context resolution: "increases by 5000" resolved as 10,000 + 5,000 = 15,000) and generic parameter extraction (mapped correctly to the spec variable name `marketing_spend`).

---

## Adapting to a New Domain

The spec-driven architecture makes domain adaptation straightforward. To model a different business scenario:

1. Edit `spec/organizational_model.yaml` -- define your variables, causal relationships, bounds and parameters
2. Update `demand_model` and `data_generation` in the spec to reflect the new domain's demand function
3. Register formula functions for new derived nodes in `system/system_model.py` (`_NODE_FORMULAS`)
4. Re-run `python data/generate_data.py` and `python models/train_demand_model.py` to retrain
5. Rebuild the knowledge index with domain-specific documents (`knowledge/build_index.py`)

No changes to the agent, planner, workflow, or simulation engine are required.

---

## Key Design Decisions

| Decision                                              | Rationale                                                                                                                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spec-driven YAML over hardcoded parameters            | Domain model is explicit, auditable, and changeable without touching code                                                                                                       |
| LLM selects tools via structured output (Pydantic)    | Eliminates fragile string parsing; tool selection is always a valid typed value                                                                                                 |
| Generic `params: Dict[str, float]` in `ToolSelection` | Variable extraction from queries is fully domain-agnostic; switching domains requires only editing the spec YAML                                                                |
| LLM orchestrates, does not compute                    | Computations are deterministic and testable; LLM adds language understanding and synthesis                                                                                      |
| Dynamic system prompt generated from spec             | Planner describes the correct variable names to the LLM without manual updates when the domain changes                                                                          |
| DAG-driven topological evaluation                     | Adding new causal variables requires only formula registration, not refactoring `evaluate()`                                                                                    |
| Lazy FAISS loading                                    | Import never fails due to missing index; failure is explicit and informative                                                                                                    |
| Synthesizer node separate from tool node              | Raw analytical output and natural language presentation are decoupled concerns                                                                                                  |
| Monte Carlo over point estimates                      | Decisions are evaluated under uncertainty; risk (`downside_risk_pct`) is a first-class output                                                                                   |
| JSONL observability log                               | Every run is persisted as a structured record; metrics and dashboards are derived offline without affecting runtime                                                             |
| Confidence score derived from tool output             | A single 0-1 score makes run quality comparable across tool types without requiring LLM self-evaluation                                                                         |
| Observer injected via LangGraph configurable          | Observability is decoupled from business logic; nodes remain testable in isolation without an observer                                                                          |
| SQLite for session persistence                        | Zero-infrastructure persistence; portable, inspectable, and sufficient for prototype scale                                                                                      |
| Demand model coefficients in spec YAML                | `base_demand`, `price_elasticity`, `marketing_effect`, `noise_sigma` are first-class spec parameters; recalibrating the model requires only editing the YAML, not touching code |
| Per-node configurable LLM models via environment variables | Planner, synthesizer and judge can each use a different model; enables cost/quality trade-offs (e.g. capable model for routing, fast model for synthesis) without code changes |
| Few-shot examples generated dynamically from the spec | Planner prompt includes routing examples built from actual decision variable names; improves tool selection accuracy while remaining fully domain-agnostic |
| Chain-of-Thought enforced in planner `reasoning` field | The prompt requires the LLM to reason through four explicit steps before selecting a tool; reduces misrouting without changing the output schema |
| `agents/llm_factory.py` — provider-agnostic LLM factory | `get_chat_model(provider, model)` returns a `BaseChatModel` for OpenAI or Anthropic; adding a new provider requires only a new branch in the factory, not changes across all nodes |
| Automatic provider fallback (`FALLBACK_PROVIDER`) | If the primary LLM fails (any error), `invoke_with_fallback()` transparently retries with a secondary provider; the graph never sees the exception, enabling zero-downtime provider switching |
| Exponential backoff on rate limits (HTTP 429) | `invoke_with_fallback()` retries up to `LLM_MAX_RETRIES` times with 2^n-second delays before escalating to the fallback provider; prevents cascading failures under API throttling |
| Streamlit as a pure presentation layer | `streamlit_app.py` wraps the existing graph without touching agent code; all session persistence, observability, and LLM orchestration flows through the same stack as `app.py` |
| PostgreSQL as primary persistence with dual-backend fallback | Every stateful component (checkpointer, sessions, runs, knowledge, specs) targets Postgres when `DATABASE_URL` is set and falls back to SQLite/FAISS/YAML automatically; no code branches in business logic |
| pgvector over dedicated vector DB | Knowledge embeddings stored in the existing Postgres instance (`knowledge_documents` table, `vector(1536)` column); avoids a second stateful service at current document volumes (see `docs/adr-001-pgvector-over-qdrant.md`) |
| Spec stored and versioned in DB | The domain model is a first-class database object with history (`specs` + `spec_versions` tables); each agent run records `spec_id` and `spec_version` so recommendations are fully traceable to the exact domain model that produced them |
