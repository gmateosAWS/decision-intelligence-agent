# Decision Intelligence Agent

A **Decision Intelligence prototype** that models how an organization works causally, evaluates decisions under uncertainty, and supports prescriptive reasoning — orchestrated by an LLM agent.

The system combines deterministic analytical components (causal model, ML, Monte Carlo simulation, optimization) with LLM-based orchestration using LangGraph. The LLM **does not compute decisions**: it orchestrates specialized tools that do.

---

## Concept

Traditional analytics pipelines stop at descriptive insight:

```
data → dashboards → human decision
```

Decision Intelligence systems reason about decisions directly:

```
data → causal system model → simulation → optimization → recommendation
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

### 1 — Spec-driven architecture

The entire organizational model is declared in `spec/organizational_model.yaml`. This single file is the **source of truth** for all system components: the causal graph, the simulation engine, the optimizer, and the agent all read from it.

To adapt the system to a new domain or change a business parameter: **edit the spec**. No code changes required.

```yaml
# spec/organizational_model.yaml (excerpt)
variables:
  decisions:
    - name: price
      bounds: { min: 10.0, max: 50.0 }
  targets:
    - name: profit
      optimize: maximize

causal_relationships:
  - from: [price, marketing_spend]
    to: demand
    type: ml_estimated
```

### 2 — LLM orchestrates, tools compute

The LLM never computes a business decision. It selects the appropriate analytical tool (via structured output), passes the query to it, and synthesizes the tool's result into a natural language response.

```
User query → Planner (LLM, tool selection) → Tool (deterministic computation) → Synthesizer (LLM, natural language) → Answer
```

This separation makes the system **auditable, testable, and governable**: every computation is deterministic and inspectable, independent of the LLM.

### 3 — Graph-driven propagation

The causal DAG is not decorative. The `SystemModel.evaluate()` method propagates values through the graph in **topological order**: each node is computed only after all its causal predecessors have been resolved. Adding a new causal variable requires only registering its formula and adding an edge to the graph — no changes to the evaluation logic.

---

## Architecture

```mermaid
flowchart TD
    User[User]
    Agent[LangGraph Agent\nplanner · tool · synthesizer]
    Spec[Organizational Spec\nspec/organizational_model.yaml]
    SimTool[Simulation Tool]
    OptTool[Optimization Tool]
    KnowTool[RAG Knowledge Tool]
    SimEngine[Monte Carlo Engine]
    VectorDB[Vector Database\n20 documents · 6 categories]
    SystemModel[System Model\ncausal DAG traversal]
    MLModel[RandomForest\ndemand estimator]
    Data[Historical Sales Data]

    User --> Agent
    Spec --> SystemModel
    Spec --> SimEngine
    Spec --> OptTool

    Agent --> SimTool
    Agent --> OptTool
    Agent --> KnowTool

    SimTool --> SimEngine
    OptTool --> SimEngine
    KnowTool --> VectorDB

    SimEngine --> SystemModel
    SystemModel --> MLModel
    MLModel --> Data
```

---

## Agent Execution Flow

```mermaid
flowchart LR
    User[User Query]
    Planner["Planner\n(LLM · structured output)"]
    Opt[Optimization Tool]
    Sim[Simulation Tool]
    Know[Knowledge RAG]
    Synth["Synthesizer\n(LLM · natural language)"]
    Answer[Answer]

    User --> Planner
    Planner -->|optimization| Opt
    Planner -->|simulation| Sim
    Planner -->|knowledge| Know
    Opt --> Synth
    Sim --> Synth
    Know --> Synth
    Synth --> Answer
```

The planner uses **structured output** (Pydantic schema) to guarantee the tool selection is always a valid, typed value — no fragile string parsing.

The synthesizer receives the raw tool result and produces a business-oriented response: it explains what the numbers mean, not just what they are.

---

## Core Components

### Organizational Spec (`spec/`)

`organizational_model.yaml` declares:

- **Decision variables**: controllable inputs (price, marketing spend), with bounds and defaults
- **Intermediate variables**: derived or ML-estimated (demand, revenue, cost)
- **Target variables**: business outcomes to optimize (profit)
- **Causal relationships**: the edges of the DAG, with type (ml_estimated / formula)
- **Business parameters**: unit cost and other domain constants
- **Simulation configuration**: Monte Carlo runs, noise model
- **Optimization configuration**: target, method, fixed variables

`spec_loader.py` parses the YAML into typed Python dataclasses and exposes a singleton `get_spec()` used across all components.

---

### Data Layer (`data/`)

Synthetic sales data is generated to simulate historical observations.

Variables: `price`, `marketing`, `demand`

Demand follows the relationship:

```
demand = 120 − 1.6 × price + 0.9 × marketing + noise(σ=5)
```

The data generation parameters reflect realistic price elasticity (negative) and marketing effect (positive). 2,000 samples are generated with `numpy` random seed 42 for reproducibility.

---

### Predictive Model (`models/`)

A **RandomForest regressor** estimates the demand function from historical data:

```
(price, marketing) → demand
```

Training includes an 80/20 train/test split and reports MAE, RMSE and R² on the held-out set, along with feature importances. The trained model is persisted to `models/demand_model.pkl`.

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

The graph structure is loaded from the spec — adding a new causal variable requires only a new formula entry and a new edge in `system/system_graph.py`.

---

### Simulation Engine (`simulation/`)

`monte_carlo()` evaluates a `(price, marketing)` decision under uncertainty by running **N independent simulations** (default: 500, configurable in the spec), each with a Gaussian perturbation on the demand estimate.

Output statistics:

| Field               | Description                             |
| ------------------- | --------------------------------------- |
| `expected_profit`   | Mean profit across all runs             |
| `profit_std`        | Standard deviation — spread of outcomes |
| `profit_p10`        | 10th percentile — pessimistic scenario  |
| `profit_p90`        | 10th percentile — optimistic scenario   |
| `expected_demand`   | Mean demand across all runs             |
| `demand_std`        | Demand variability                      |
| `downside_risk_pct` | % of runs where profit < 0              |
| `n_runs`            | Number of simulations executed          |

---

### Optimization (`optimization/`)

`optimize_price()` performs a **grid search** over the price range (bounds from spec), evaluating each candidate price via Monte Carlo simulation and selecting the one that maximises `expected_profit`.

Marketing spend is held fixed at the value declared in `spec.optimization.fixed_variables`.

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

The vectorstore is loaded **lazily** (on first query, not at import time). If the index does not exist, an explicit error is raised with instructions.

---

### Agent Layer (`agents/`)

The agent is implemented as a **3-node LangGraph graph**:

**`planner_node`** — Selects the appropriate tool using `gpt-4o-mini` with structured output. The LLM receives a full system prompt describing the domain and each tool's purpose. Output is a typed `ToolSelection(tool, reasoning)` object — no string parsing.

**`tool_node`** — Executes the selected tool. Wrapped in `try/except`: errors are captured and propagated to the state rather than crashing the graph.

**`synthesizer_node`** — Receives the raw tool output and the original query, and produces a business-oriented natural language answer: what do the numbers mean, what should the decision-maker do.

**`AgentState`** TypedDict fields:

| Field        | Set by      | Description                         |
| ------------ | ----------- | ----------------------------------- |
| `query`      | Input       | User's original question            |
| `action`     | Planner     | Selected tool name                  |
| `reasoning`  | Planner     | LLM's reasoning for tool selection  |
| `raw_result` | Tool        | Raw output from the analytical tool |
| `answer`     | Synthesizer | Final natural language response     |

---

## Repository Structure

```
decision-intelligence-agent/
├── spec/
│   ├── organizational_model.yaml   # ← Single source of truth for the domain model
│   ├── spec_loader.py              # Typed YAML parser, singleton get_spec()
│   └── __init__.py
├── data/
│   └── generate_data.py            # Synthetic sales dataset (2,000 samples)
├── models/
│   └── train_demand_model.py       # RF training, evaluation metrics, model export
├── system/
│   ├── system_graph.py             # Causal DAG — edges loaded from spec
│   └── system_model.py             # Graph-traversal evaluation engine
├── simulation/
│   ├── montecarlo.py               # Monte Carlo engine (N runs, noise model)
│   └── scenario_runner.py          # Scenario wrapper
├── optimization/
│   └── optimizer.py                # Grid search over price range
├── knowledge/
│   ├── build_index.py              # FAISS index builder (20 docs, 6 categories)
│   └── retriever.py                # Lazy-loaded similarity search
├── agents/
│   ├── state.py                    # AgentState TypedDict
│   ├── tools.py                    # Tool wrappers (spec-driven defaults)
│   ├── planner.py                  # LLM planner with structured output
│   └── workflow.py                 # LangGraph: planner → tool → synthesizer
├── evaluation/
│   ├── __init__.py
│   ├── observer.py                 # AgentObserver: run lifecycle, JSONL logging, confidence scoring
│   ├── metrics.py                  # load_runs / compute_metrics / print_report
│   └── dashboard.py                # HTML dashboard generator + CLI entry point
├── config/
│   └── settings.py                 # Thin adapter over spec (backward-compatible)
├── logs/                           # Created at runtime
│   ├── agent_runs.jsonl            # Append-only run log (one JSON per line)
│   ├── agent.log                   # Verbose debug log
│   └── dashboard.html              # Generated by evaluation/dashboard.py
├── app.py                          # REPL entry point with observability (Mejora 2)
├── .env.example                    # Environment variable template
├── requirements.txt
└── README.md
```

---

## Setup

**1. Create and activate a virtual environment**

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure API key**

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key
```

Get your key from: https://platform.openai.com/api-keys

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

Output: `models/demand_model.pkl` — also prints MAE, RMSE and R² on the test set.

**Build the knowledge index**

```bash
python knowledge/build_index.py
```

Output: `knowledge_index/` directory — FAISS index of 20 domain documents.

> The organizational spec (`spec/organizational_model.yaml`) is loaded automatically at runtime. No additional build step required.

---

## Run the Agent

```bash
python app.py
```

**Example session:**

```
╔══════════════════════════════════════════════════════════╗
║        Decision Intelligence Agent                      ║
╠══════════════════════════════════════════════════════════╣
║  Ask business questions about pricing and marketing.    ║
║  Examples:                                              ║
║    • What price should maximise profit?                 ║
║    • What happens if I set price to 30?                 ║
║    • How does the demand model work?                    ║
║  Type 'exit' to quit.                                   ║
╚══════════════════════════════════════════════════════════╝

Ask a business question: What price should maximise profit?

Based on the optimization analysis, the price that maximises expected
profit is approximately 23.7 EUR, yielding an expected profit of 412 EUR
per period. At this price, demand is estimated at 43 units with a
downside risk of less than 2% (probability of loss). Setting price
above 30 EUR reduces demand sharply due to price elasticity, lowering
total profit despite the higher margin per unit.

Ask a business question: exit
Goodbye.
```

---

---

## Observability & Evaluation Layer (`evaluation/`)

> Added in **Mejora 2**. Every agent run is captured, measured and visualisable.

### Architecture

```
app.py
  └─ AgentObserver.start_run(query)          ← opens a RunRecord
       ├─ planner_node  → obs.record_planner()
       ├─ tool_node     → obs.record_tool()
       └─ synthesizer_node → obs.record_synthesizer()
  └─ AgentObserver.end_run()                 ← writes to JSONL

logs/
  ├─ agent_runs.jsonl   ← one JSON record per run (append-only)
  ├─ agent.log          ← verbose debug log
  └─ dashboard.html     ← generated on demand
```

### Components

| Module                    | Responsibility                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| `evaluation/observer.py`  | `AgentObserver` – wraps each run, records timing, derives confidence score, writes JSONL    |
| `evaluation/metrics.py`   | `load_runs` / `compute_metrics` – aggregates stats from JSONL; `print_report` – CLI summary |
| `evaluation/dashboard.py` | `generate_html_dashboard` – self-contained HTML with Chart.js; CLI entry point              |

### RunRecord fields

| Field                    | Source           | Description                                                                                     |
| ------------------------ | ---------------- | ----------------------------------------------------------------------------------------------- |
| `run_id`                 | observer         | Unique ID per query (12-char hex)                                                               |
| `session_id`             | observer         | Groups runs within one `python app.py` session                                                  |
| `timestamp`              | observer         | ISO-8601 UTC                                                                                    |
| `query`                  | input            | Raw user question                                                                               |
| `action`                 | planner          | `optimization` / `simulation` / `knowledge`                                                     |
| `reasoning`              | planner          | LLM's explanation of tool choice                                                                |
| `planner_latency_ms`     | planner node     | Time from entry to structured output                                                            |
| `tool_latency_ms`        | tool node        | Time to execute the analytical tool                                                             |
| `synthesizer_latency_ms` | synthesizer node | Time for natural-language response                                                              |
| `total_latency_ms`       | observer         | End-to-end wall time                                                                            |
| `confidence_score`       | observer         | Derived: `1 – downside_risk_pct/100` for Monte Carlo, `1.0/0.3` for optimization, `0.9` for RAG |
| `raw_result_keys`        | tool node        | Dict keys returned by the tool                                                                  |
| `success`                | observer         | `false` if any node raised an exception                                                         |
| `error`                  | observer         | Exception message if `success=false`                                                            |
| `answer_length`          | synthesizer      | Character count of the final answer                                                             |

### LangSmith integration

Set these variables in `.env` to enable automatic tracing of every LangGraph invocation:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls__your_key
LANGCHAIN_PROJECT=decision-intelligence-agent
```

`AgentObserver.langsmith_config()` injects `run_name`, `tags` and `metadata` so
each run appears named and tagged in the LangSmith UI. No code changes required —
tracing activates automatically when the env var is present.

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
- Tool distribution doughnut chart
- Latency breakdown bar chart (planner / tool / synthesizer)
- Recent runs table with per-run confidence bars
- Error log (if any failures occurred)

---

## Adapting to a New Domain

The spec-driven architecture makes domain adaptation straightforward. To model a different business scenario:

1. Edit `spec/organizational_model.yaml` — define your variables, causal relationships, bounds and parameters
2. Register formula functions for new derived nodes in `system/system_model.py` (`_NODE_FORMULAS`)
3. Retrain the ML model if the input/output variables change (`models/train_demand_model.py`)
4. Rebuild the knowledge index with domain-specific documents (`knowledge/build_index.py`)

No changes to the agent, planner, workflow, or simulation engine are required.

---

## Key Design Decisions

| Decision                                           | Rationale                                                                                                           |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Spec-driven YAML over hardcoded parameters         | Domain model is explicit, auditable, and changeable without touching code                                           |
| LLM selects tools via structured output (Pydantic) | Eliminates fragile string parsing; tool selection is always a valid typed value                                     |
| LLM orchestrates, does not compute                 | Computations are deterministic and testable; LLM adds language understanding and synthesis                          |
| DAG-driven topological evaluation                  | Adding new causal variables requires only formula registration, not refactoring `evaluate()`                        |
| Lazy FAISS loading                                 | Import never fails due to missing index; failure is explicit and informative                                        |
| Synthesizer node separate from tool node           | Raw analytical output and natural language presentation are decoupled concerns                                      |
| Monte Carlo over point estimates                   | Decisions are evaluated under uncertainty; risk (downside_risk_pct) is a first-class output                         |
| JSONL observability log                            | Every run is persisted as a structured record; metrics and dashboards are derived offline without affecting runtime |
| Confidence score derived from tool output          | A single 0-1 score makes run quality comparable across tool types without requiring LLM self-evaluation             |
| Observer injected via LangGraph configurable       | Observability is decoupled from business logic; nodes remain testable in isolation without an observer              |

---

## Mejora 3 – Memoria Conversacional Multi-turno

### Objetivo

Dotar al agente de **memoria persistente entre turnos** y de un sistema de
**gestión de sesiones** que permite:

- Mantener el contexto de la conversación durante varios turnos dentro de la
  misma sesión.
- Reanudar sesiones anteriores después de reiniciar el proceso.
- Listar, explorar y borrar sesiones desde la CLI.

---

### Arquitectura: Memory Layer

```
app.py (REPL)
│
├── memory/
│   ├── __init__.py          ← exports públicos
│   ├── checkpointer.py      ← SqliteSaver singleton + agent_sessions table
│   └── session_manager.py   ← CRUD y listado de sesiones (CLI helpers)
│
├── agents/
│   ├── state.py             ← añade campo `history` (Annotated + operator.add)
│   ├── planner.py           ← inyecta últimos 3 turnos en el prompt LLM
│   └── workflow.py          ← build_graph(checkpointer=...) con persistencia
│
└── data/
    └── checkpoints.db       ← SQLite: tablas LangGraph + agent_sessions
```

---

### Componentes nuevos / modificados

#### `memory/checkpointer.py`

| Responsabilidad            | Detalle                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| `get_checkpointer()`       | Singleton `SqliteSaver` apuntando a `data/checkpoints.db`          |
| `register_turn()`          | Upsert en `agent_sessions`: actualiza `last_active` y `turn_count` |
| `_ensure_sessions_table()` | Crea la tabla `agent_sessions` si no existe                        |

Esquema de `agent_sessions`:

```
session_id  TEXT PRIMARY KEY
title       TEXT   -- primeros 60 chars de la primera query
created_at  TEXT   -- ISO 8601 UTC
last_active TEXT   -- ISO 8601 UTC, actualizado en cada turno
turn_count  INTEGER
```

#### `memory/session_manager.py`

```python
SessionManager.list_sessions()        # → List[dict]
SessionManager.get_session(sid)       # → dict | None
SessionManager.delete_session(sid)    # → bool
SessionManager.print_sessions()       # tabla numerada en stdout
SessionManager.session_info(sid)      # detalle de una sesión
```

#### `agents/state.py` (modificado)

```python
history: Annotated[List[Dict[str, str]], operator.add]
```

`operator.add` indica a LangGraph que los retornos de `history` de cada nodo
se **concatenan** en lugar de reemplazarse, acumulando todos los turnos.

#### `agents/planner.py` (modificado)

```python
_HISTORY_WINDOW = 3   # turnos anteriores inyectados en el prompt

messages = [system_prompt]
for turn in history[-_HISTORY_WINDOW:]:
    messages += [{"role": "user",      "content": turn["query"]},
                 {"role": "assistant", "content": turn["answer"]}]
messages.append({"role": "user", "content": current_query})
```

Esto permite referencias naturales entre turnos:

> _Usuario:_ "¿Cuál es el precio óptimo?"
> _Usuario:_ "¿Y si el precio fuese 28?" ← el planner entiende el contexto

#### `agents/workflow.py` (modificado)

- `build_graph(checkpointer=None)` acepta un `SqliteSaver` opcional.
- `synthesizer_node` devuelve `{"answer": ..., "history": [new_turn]}`.
  LangGraph aplica `operator.add` y el nuevo turno queda en el estado
  persistido bajo el `thread_id` de la sesión.

#### `app.py` (modificado)

Se añade gestión completa de sesiones en el REPL:

```
session new              # nueva sesión (nuevo thread_id)
session list             # lista de sesiones guardadas
session resume <id>      # reanudar por session_id completo
session resume <#>       # reanudar por índice de 'session list'
session info             # detalle de la sesión activa
session delete <id>      # elimina sesión del registro
dashboard                # métricas CLI + dashboard.html (Mejora 2)
exit                     # salir
```

El `thread_id` se pasa en el config de LangGraph:

```python
cfg["configurable"]["thread_id"] = session_id
result = graph.invoke({"query": raw, "run_id": run_id}, config=cfg)
```

---

### Flujo de un turno

```
Usuario escribe query
     │
     ▼
app.py: start_run() + build config {thread_id, observer}
     │
     ▼
graph.invoke()
  ├─ planner_node  → inyecta history[-3:] en prompt LLM
  ├─ tool_node     → ejecuta optimization / simulation / knowledge
  └─ synthesizer_node → genera answer + retorna {history: [new_turn]}
     │
     ▼
SqliteSaver persiste estado completo (historia acumulada)
     │
     ▼
register_turn() → upsert en agent_sessions
     │
     ▼
observer.end_run() → escribe logs/agent_runs.jsonl
```

---

python --version### Ejemplo de sesión multi-turno

```
$ python app.py

  ● New session: 3f8a2c1d-…

Ask a business question: What price maximises profit?
  The optimization tool suggests a price of €24.50 …

Ask a business question: What if price is 20?
  At €20.00 the simulation shows expected profit of €8,400 …

Ask a business question: session list
  #   Session ID                           Turns  Last active           Title
  ─────────────────────────────────────────────────────────────────────────────
  1   3f8a2c1d-…                           2      2025-07-15 10:22:01   What price maximises pro

Ask a business question: session info
  Session ID   : 3f8a2c1d-…
  Title        : What price maximises profit?
  Created      : 2025-07-15T10:21:44+00:00
  Last active  : 2025-07-15T10:22:01+00:00
  Turn count   : 2

# --- Después de reiniciar ---

Ask a business question: session resume 1
  ● Resumed session: 3f8a2c1d-…

Ask a business question: And what about price 28?
  Building on previous context: at €28.00 profit is …
```
