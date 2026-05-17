# Roadmap llull — del prototipo al producto (v4)

**Propósito.** Ordenar los 116 items del inventario en iteraciones con criterio de entrega claro, priorizando por desbloqueo técnico (qué habilita a qué), después por valor entregado (qué puede demostrarse al final), y con ataques puntuales al factor riesgo (qué conviene validar pronto).

**Cómo leerlo.** Este documento se lee junto al inventario v4, al que referencia por códigos (1.1, 6.1.e, etc.). No duplica las descripciones — las referencia. Cuando necesites el detalle de un item, abre el inventario al lado.

**Estructura.** Primero el grafo de dependencias (para entender por qué las cosas van donde van), luego las cuatro iteraciones (I1, I2A, I2B, I3) con su contenido y justificación, y al final los items que quedan fuera.

**Cambios respecto a v3.** Esta versión integra los 19 items nuevos del inventario v4, derivados del análisis de las 4 auditorías de LlullGen y de las 4 arquitecturas objetivo. Los cambios concretos al ordenamiento son tres: (1) **el ObjectBus (1.6) se adelanta a I1** porque desbloquea simultáneamente memoria analítica activa, multi-agente y lineage; (2) **el control de gasto LLM completo (8.7.b–f) se anticipa a I2A en lo crítico** y queda en I3 lo más sofisticado, porque parte del control de gasto es prerequisito de tener pilotos con datos reales sin riesgo presupuestario; (3) **el Bloque A multi-agente (5.3 descompuesto en 5.3.a/b/c) entra en I3 con su mínimo viable** — solo 5.3.a + 5.3.b + 5.12, dejando 5.3.c y los sub-agentes adicionales en "Más allá".

Las dos decisiones declaradas en ADR-002 (LangGraph como motor de orquestación) y ADR-003 (política de reutilización de componentes de LlullGen) son ortogonales al roadmap pero condicionan cómo se implementan los items que las usan.

---

## Grafo de dependencias

Antes de asignar items a iteraciones, hay que ver qué habilita a qué. Estas son las cadenas de dependencia más fuertes del inventario:

### Cadena 1 — Base de persistencia (crítica, desbloquea casi todo)

```
1.1 PostgreSQL ──→ 1.2 pgvector
               ──→ 1.5 Spec as data ──→ 3.1 DAG builder visual
                │                   ──→ 3.2 Generador conversacional
                │                   ──→ 3.3 Validación automática
                │                   ──→ 3.6 Versionado semántico del spec
                │                   ──→ 6.1.d Spec Service
                │                   ──→ 10.4 Versionado del spec como artefacto
               ──→ 7.1 Multi-tenancy (RLS)
               ──→ 8.1 Runs en Postgres
```

**Implicación:** 1.1 es el item más bloqueante del inventario entero. Hasta que Postgres esté en pie, no se puede hacer nada en multi-tenancy, observabilidad analítica, spec-as-data, ni pgvector.

### Cadena 2 — APIficación (crítica, desbloquea UI y multi-usuario)

```
6.1.e Agent Service (monolito modular) ──→ 6.1.d Spec Service (primera extracción)
                                       ──→ 6.4 Endpoints admin/health
                                       ──→ 6.5 Versionado de API
                                       ──→ 7.5 SSO (la API es lo que se protege)
                                       ──→ 3.1 DAG builder (consume API de specs)
                                       ──→ 5.3 Multi-agente (los sub-agentes son servicios)
```

**Implicación:** el Agent Service como monolito modular (que expone los endpoints del prototipo como API REST) es el segundo gran habilitador. Combinado con 1.1, forma el "paquete fundacional" de la Iteración 1.

### Cadena 3 — Datos reales (habilita el primer cliente piloto)

```
2.1 Conectores batch ──→ 2.2 Data Mapping Layer ──→ 2.6 Data bindings en spec
                     ──→ 2.5 Validación semántica (Great Expectations)
```

**Implicación:** el primer cliente no va a tener Kafka, sino Excel/CSV básico. Los conectores batch + mapping + validación son el paquete mínimo que hace que llull funcione con datos reales.

### Cadena 4 — Seguridad mínima enterprise

```
1.1 PostgreSQL ──→ 7.1 Multi-tenancy (RLS) ──→ 7.2 RBAC
6.1.e Agent Service ──→ 7.5 SSO ──→ 7.6 Cifrado
                                ──→ 7.8 Audit log
```

**Implicación:** no se puede vender al primer cliente enterprise sin multi-tenancy, SSO, cifrado y audit log. Este paquete corre en paralelo a los datos reales y ambos deben estar listos antes de que llegue el primer cliente.

### Cadena 5 — Calidad y gobernanza (cierra el loop de confianza)

```
8.1 Runs en Postgres ──→ 5.1 Judge offline
                     ──→ 10.2 Datasets de evaluación ──→ 5.2 Test suites
                                                     ──→ 10.3 Evaluación pre-promoción
```

**Implicación:** las piezas de evaluación offline dependen de tener los runs en Postgres (no en JSONL). Los datasets de evaluación son el artefacto que habilita tanto las test suites como la evaluación pre-promoción de cambios. Sin estos tres, no hay disciplina de calidad del sistema agentic.

### Cadena 6 — MLOps (gobernanza de modelos predictivos)

```
9.3 Experiment tracking (MLflow) ──→ 9.5 Model Registry
                                 ──→ 9.1 Versionado de datasets
                                 ──→ 9.2 Pipeline reproducible ──→ 9.4 Validación pre-promoción
                                                               ──→ 9.7 Monitorización drift
                                                               ──→ 9.8 Triggers reentrenamiento
```

**Implicación:** MLflow es el ancla de esta cadena. Una vez que existe, el pipeline se construye incrementalmente encima.

### Cadena 7 — CI/CD (base operativa)

```
11.1 Pipeline CI ──→ 11.3 Contenedorización ──→ 11.4 Kubernetes
                                            ──→ 11.5 Despliegue por entornos
```

**Implicación:** el pipeline CI es independiente de casi todo lo demás y debe existir desde el día 1. La contenedorización y Kubernetes son requisito de despliegue real.

### Cadena 8 — ObjectBus y memoria analítica activa (nueva en v4)

```
1.1 PostgreSQL ──→ 1.6 ObjectBus ──→ 5.10 Memoria analítica activa ──→ 5.11 MemoryService
                                  ──→ 5.3.a Multi-agente mínimo (sin recomputar)
                                  ──→ 10.10 LineageRecord (objetos consumidos/producidos)
```

**Implicación:** 1.6 (ObjectBus) es habilitador horizontal. Persistir los outputs del Decision Agent (resultados Monte Carlo, escenarios optimizados, distribuciones) habilita simultáneamente: follow-ups sin recomputar, multi-agente coherente, y trazabilidad de objetos en LineageRecord. Por eso entra en I1 a pesar de no ser estrictamente necesario para el criterio de entrega de I1: su ausencia haría que I3 sea más cara.

### Cadena 9 — Control de gasto LLM completo (nueva en v4)

```
5.6 LLMFactory ──→ 8.7.a Cuotas tenant
              ──→ 8.7.b Hard request-level ceilings ──→ 8.7.c Budget reservation
                                                    ──→ 8.7.d Fallback chain por slot
                                                    ──→ 8.7.e Budgets capability/peer
              ──→ 8.7.f Cost lineage ──→ 10.10 LineageRecord
              ──→ 5.12 Recursion guard
```

**Implicación:** las seis dimensiones del control de gasto (tenant, run, slot, peer, lineage, recursion) tienen orden de criticidad distinto. **8.7.b** (hard request-level ceilings) es el más crítico porque previene runaway runs y debe estar antes de cualquier piloto con datos reales. **8.7.c, d** entran en I2A junto con la primera versión productiva del LLMFactory. **8.7.e** entra en I3 con el multi-agente. **8.7.f** entra en I3 como parte del LineageRecord. **5.12** entra en I3 con el multi-agente.

### Cadena 10 — Multi-agente con governance (nueva en v4)

```
1.6 ObjectBus ──→ 5.3.a MVP Bloque A ──┐
5.10 ActiveAnalyticalState ───────────┤
5.11 MemoryService ───────────────────┤──→ 5.3.b Capability Graph ──→ 5.12 Recursion guard
                                       │                            ──→ 8.7.e Budgets peer
6.1.e Agent Service ───────────────────┘
```

**Implicación:** el multi-agente con governance no se puede hacer "después" — requiere que las tres piezas habilitadoras estén primero (ObjectBus, ActiveAnalyticalState, MemoryService). 5.3.a y 5.3.b van juntos siempre: capability graph es prerequisito ético del multi-agente, no opcional. 5.3.c (Alert/Report/Action) queda en "Más allá".

### Cadena 11 — Governance unificada y lineage (nueva en v4)

```
10.8 Registry pattern ──→ MetricRegistry · DimensionRegistry · EntityRegistry · PromptRegistry · ModelRegistry · ToolRegistry · SkillRegistry · PolicyRegistry · BudgetRegistry · VocabularyRegistry
              │
              └──→ 10.10 LineageRecord ──→ 7.8 Audit log enriquecido
                                       ──→ 3.7 Portabilidad (export legible)
                                       ──→ 12.8 Onboarding regulado
```

**Implicación:** el patrón registry es la base de gobernanza. Sin él, cada artefacto se gobierna a su manera. Se introduce parcialmente en I2A (PromptRegistry, primer registry concreto) y se generaliza en I3 al resto. **10.10 (LineageRecord tipado)** es lo que cierra trazabilidad regulatoria y cuelga de tener todos los registries.

---

## Tabla resumen de dependencias críticas

| Item                         | Depende de                | Desbloquea                                      |
| ---------------------------- | ------------------------- | ----------------------------------------------- |
| **1.1** PostgreSQL           | nada                      | 1.2, 1.5, 1.6, 7.1, 8.1, y transitivamente casi todo |
| **1.5** Spec as data         | 1.1                       | 3.1, 3.2, 3.3, 3.6, 5.9 (vocabularios), 6.1.d, 8.7.d (chains), 10.4 |
| **1.6** ObjectBus            | 1.1                       | 5.3.a, 5.10, 10.10 (objetos en lineage) |
| **5.6** LLMFactory completo  | 1.1, 5.6 actual           | 8.7.a–d, control de coste end-to-end |
| **5.10** ActiveAnalyticalState | 1.5, 1.6                | 5.11, 5.3.a (continuidad multi-agente) |
| **5.11** MemoryService       | 5.10                      | governance memoria, lint boundary, debugging multi-agente |
| **6.1.e** Agent Service      | nada (porta el prototipo) | 6.4, 6.5, 7.5, UI, multi-usuario                |
| **7.1** Multi-tenancy        | 1.1                       | 7.2, 7.9 (data leakage cross-tenant)            |
| **8.1** Runs en Postgres     | 1.1                       | 5.1, 10.2, 10.10 (lineage)                      |
| **8.7.b** Hard ceilings      | 5.6                       | pilotos seguros, prevención de runaway          |
| **10.8** Registry pattern    | 1.1, 1.5                  | governance unificada, 10.10                     |
| **10.10** LineageRecord      | 10.8, 1.6, 8.7.f          | 7.8 enriquecido, portabilidad, regulado         |
| **11.1** Pipeline CI         | nada                      | 11.3, 11.4, 11.5, calidad del código            |
| **2.1** Conectores batch     | nada                      | 2.2, 2.5, 2.6, 2.10 (gateway)                   |
| **9.3** MLflow               | nada                      | 9.1, 9.2, 9.4, 9.5, 9.7, 9.8                    |
| **10.2** Datasets evaluación | 8.1                       | 5.2, 10.3, 10.11 (golden eval con CI gates)     |

---

## Las cuatro iteraciones

Cada iteración tiene: un **criterio de entrega** (qué se puede demostrar al final que antes no se podía), un **listado de items** agrupados en paquetes funcionales, y una **justificación** de por qué ese item va ahí y no en otro sitio.

La Iteración 2 original se ha subdividido en **I2A** (datos reales + calidad del agente, validación interna) e **I2B** (seguridad enterprise + operación, apertura a cliente externo). La lógica: validar primero que el producto funciona con datos reales en entorno controlado, antes de invertir en la capa de seguridad que lo abre al exterior.

---

## ITERACIÓN 1 — Fundación productiva

### Criterio de entrega

Al final de esta iteración, llull es un **servicio desplegable con API REST, persistencia en PostgreSQL, búsqueda vectorial sobre pgvector + pgvectorscale (ADR-005), ObjectBus para artefactos analíticos por sesión, specs versionados en base de datos, pipeline CI funcional, los primeros tests del sistema agentic, y una interfaz web visual (Streamlit) que permite hacer demos sin necesidad de terminal**. Todavía no tiene multi-tenancy ni datos reales de cliente, pero un ingeniero o un consultor puede interactuar con él vía API o vía web, desplegar cambios con confianza, y empezar a medir la calidad del agente sistemáticamente.

Es el paso de prototipo/demo a un sistema con base técnica seria sobre la que se empieza a construir el producto.

### Paquete 1A — Base de persistencia ✅ COMPLETADO

| Item                              | Estado / Justificación                                                                                                                                                       |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1.1** PostgreSQL                | ✅ Hecho — 5 tablas, Alembic migrations, dual-backend con SQLite fallback.                                                                                                   |
| **1.2** pgvector + pgvectorscale  | ✅ Hecho — `knowledge_documents` table con embedding column; índice actual `ivfflat`; evolución a `StreamingDiskANN` (pgvectorscale) cuando triggers ADR-005 se activen. FAISS fallback solo en local dev sin Docker. |
| **1.5** Spec as data              | ✅ Hecho — `specs` + `spec_versions` tables; `spec_repository.py` CRUD; `spec_loader.py` DB-first with YAML fallback.                                                        |
| **1.6** ObjectBus de tres niveles `[v4]` | ⏳ Pendiente (I1 diferido) — deferred until LlullGen codebase available for reference (ADR-003). Next priority after current audit work. |
| **8.1** Runs en Postgres          | ✅ Hecho — `agent_runs` table; `PostgresSink` escribe en cada run; JSONL fallback vía `JsonlSink`.                                                                            |
| **1.3** Triggers de migración a Qdrant formalizados | ✅ Hecho — cinco triggers objetivos en ADR-005 (`docs/ADR-005-vector-store-strategy.md`): volumen >50M vectores, latencia p95 >50ms/30d, aislamiento contractual, multitenancy estratificado, hybrid search. Evaluación cada 6 meses. ADR-001 marcado como Superseded. |

### Paquete 1B — API y servicio ✅ COMPLETADO

| Item                                       | Estado / Justificación                                                                                                                                                                                                |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **6.1.e** Agent Service (monolito modular) | ✅ Hecho — FastAPI con routers `/v1/query`, `/v1/sessions`, `/v1/runs`, `/v1/specs`, `/healthz`, `/readyz`. Pydantic schemas. |
| **6.4** Endpoints admin/health             | ✅ Hecho — `/healthz`, `/readyz`, `/v1/debug/config`.                                                                        |
| **6.5** Versionado de API                  | ✅ Hecho — prefijo `/v1/` en todos los routers.                                                                              |

### Paquete 1C — Disciplina de ingeniería ✅ COMPLETADO

| Item                                 | Estado                                                                                                                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **11.1** Pipeline CI                 | ✅ Hecho — `.github/workflows/ci.yml`: job unit (black+ruff+pytest -m "not integration") + job integration (Postgres service, alembic, data+model bootstrap). CI badge en README. |
| **11.3** Contenedorización           | ✅ Hecho — `Dockerfile` multi-stage (builder + runtime), `docker-compose.yml` actualizado (api service + healthcheck postgres), `.dockerignore`.                                 |
| **5.2** Test suites del agente (v1)  | ✅ Hecho — `tests/evaluation/test_agent_golden.py` (15 queries canónicas: routing, param propagation, result shape) + `tests/ci/test_smoke.py` (imports + healthz/readyz). 76 unit tests total. |
| **5.7** Fallback robusto del planner | ✅ Hecho en 1D — subsumed by LLMFactory pattern (ADR-003/paquete 2A.3).                                                                                                         |

### Paquete 1D — Parches inmediatos al prototipo ✅ COMPLETADO

| Item                                                | Estado |
| --------------------------------------------------- | ------ |
| **4.1** Verificar simulación con params arbitrarios | ✅ Hecho |
| **5.5** Ampliar ventana de historial                | ✅ Hecho |
| **5.6** Extender soporte multi-proveedor LLM        | ✅ Hecho (OpenAI + Anthropic via `llm_factory.py`) |
| **5.7** Fallback robusto del planner                | ✅ Hecho (5 failure modes, `fallback_triggered` tracked) |
| **12.4** Política de fallback entre proveedores LLM | ✅ Hecho (switch automático, logging) |
| **12.5** Gestión de rate limiting del LLM           | ✅ Hecho (tenacity, backoff exponencial, degradación) |

### Paquete 1E — Interfaz visual para demos ✅ COMPLETADO

| Item                                  | Estado |
| ------------------------------------- | ------ |
| **6.6** Interfaz web con Streamlit    | ✅ Hecho (`streamlit_app.py`, chat + DAG + gráficos + gestión de sesiones) |
| UX polish para demo con dirección     | ✅ Hecho (welcome block, staged spinner, badge tool+latencia, results directo) |
| Despliegue Community Cloud            | ✅ Hecho (psycopg2-binary, `.python-version`, deps fijadas, self-bootstrap) |
| fix: lazy LLM init                    | ✅ Hecho (elimina `KeyError: 'agents.llm_factory'` en cold start) |

### Items que no entran en la Iteración 1 y por qué

- **Multi-tenancy (7.1)**: requiere 1.1, pero además requiere diseñar el schema con `tenant_id` desde cero. Si se hace a medias (schema sin RLS, "ya lo pondremos"), la deuda es enorme. Preferible cerrar Postgres con un schema limpio en I1 y añadir RLS como primer paso de I2.
- **SSO (7.5)**: requiere que haya una API que proteger. Se activa en I2 cuando el Agent Service ya esté estable.
- **Datos reales (2.1)**: se podría meter, pero la I1 ya tiene mucho peso. Meterlo aquí dispersa el foco. En I2 es el primer paquete.
- **MLflow (9.3)**: es independiente y podría ir aquí, pero aporta poco valor hasta que haya datos reales y múltiples modelos. En I2 o I3 tiene más sentido.

---

## ITERACIÓN 2A — Datos reales y calidad del agente (piloto interno)

### Criterio de entrega

Al final de esta sub-iteración, llull puede **ingerir datos reales de un cliente (Excel/CSV/SQL) protegidos por el SQL Execution Gateway, mapearlos al spec asistido por LLM, validarlos semánticamente, crear specs conversacionalmente, mantener estado analítico activo entre turnos con memoria tipada, controlar el gasto LLM en sus dimensiones críticas (cuota tenant + ceilings por run + fallback chain), y tiene un proceso de evaluación de calidad del agente reproducible y automatizado con prompt capture y golden eval inicial**. Es el sistema que el equipo interno de Inverence puede usar para validar con datos reales de un cliente candidato, antes de abrirlo al exterior. Todavía no tiene multi-tenancy ni SSO — opera en un entorno controlado interno.

Es el paso de sistema con base técnica seria a sistema que demuestra valor con datos reales **de forma controlada en gasto y trazable en memoria**.

### Paquete 2A.1 — Datos reales del cliente

| Item                                              | Justificación                                                                                                                                              |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **2.1** Conectores batch (Excel, CSV, SQL)        | El primer cliente va a tener Excel. Es lo mínimo para validar el producto con datos reales.                                                                |
| **2.2** Data Mapping Layer asistida por LLM       | Sin esto, hay que reescribir el spec a mano para cada cliente. Con esto, el onboarding es asistido.                                                        |
| **2.5** Validación semántica (Great Expectations) | Expectations declarativas sobre los datos antes de que entren al motor. Bloquea drift silencioso. No necesita Kafka — funciona sobre los conectores batch. |
| **2.10** SQL Execution Gateway con políticas R0–R3 `[v4]` | Chokepoint único por el que pasa toda ejecución SQL. R0 bloquea DDL/DML, R1–R3 declaradas en YAML asseradel en startup. Defense-in-depth contra SQL injection emergente del LLM. Va emparejado con 2.1 desde el primer momento — no se ejecuta SQL real sin el gateway. |
| **2.6** Data bindings en el spec                  | Conecta el spec con los conectores reales. Se introduce ahora porque es la pieza que cierra la cadena 2.1 → 2.2 → 2.6.                                     |
| **2.6** Data bindings en el spec                  | Cada variable del spec sabe de dónde vienen sus datos. Conecta ingesta con modelo de dominio.                                                              |

### Paquete 2A.2 — Modelo de dominio operativo

| Item                                       | Justificación                                                                                                                                                                                                                                                                                      |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **3.2** Generador conversacional de specs  | El consultor describe el dominio en lenguaje natural, el LLM genera el borrador. Reduce drásticamente el tiempo de onboarding. No necesita el DAG builder visual (viene en I3).                                                                                                                    |
| ~~**3.3** Validación automática del spec~~ ✅ | ~~Impide que un spec mal formado llegue al runtime. Condición necesaria para que 3.2 sea usable por no-técnicos.~~ Completado 2026-05-11: `assert_dag_acyclic()` en `system/system_graph.py`, hook lazy en `spec_loader._parse_raw()`, `_validate_dag_acyclic()` en `spec_repository`. 7 tests. POST /v1/specs con ciclo → 422. |
| ~~**3.5** Políticas de autonomía en el spec~~ ✅ | ~~Añadir `autonomy_policy` al spec. Es un parche pequeño con impacto alto: el primer cliente querrá saber quién controla qué.~~ Completado 2026-05-09: `spec/autonomy.py`, planner consulta la política, conditional edge en workflow, `GET/PUT /v1/specs/{id}/autonomy`. |
| **3.7** Portabilidad del modelo de dominio | Principio de diseño + endpoints de exportación: spec, modelos, mappings, runs, evaluaciones en formatos abiertos (YAML, JSON, ONNX, Parquet). Se implementa en I2A porque informa el diseño de todo lo que toca datos de cliente. Argumento comercial directo: "en llull tu conocimiento es tuyo". |
| **4.3** Skills engine + exposición MCP | Contrato técnico de skills (tools vs skills), registro dinámico en el spec, exposición como MCP servers. Incluye el flujo de productificación de modelos de Inverence. Posiciona a llull como plataforma de capacidades analíticas consumible por cualquier agente MCP-compatible. |

### Paquete 2A.3 — Memoria activa y control de gasto crítico `[v4]`

| Item                                          | Justificación                                                                                                                                                  |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **5.6** LLMFactory completo (multi-proveedor + budget guard + fallback chain) | Evolución del 5.6 actual. Necesario antes de tener pilotos con datos reales: sin context-budget pre-flight, una conversación larga del consultor con histórico de cliente puede romper por overflow. Sin fallback chain por slot, no hay forma de degradar elegantemente bajo presión de coste. |
| ~~**5.9** GroundedTokens — guardrail anti-alucinación de entidades~~ ✅ | ~~Defense-in-depth para conversaciones largas. Vocabularios alimentados desde el spec por dominio (no hardcoded).~~ Completado 2026-05-17: `system/grounded_tokens.py` (Vocabulary, UngroundedTokenError, validate_strict blocking + check_observational non-blocking); spec extended with aliases + DerivedMetric; planner inner check → clarification node; judge observational scan; AgentState + RunResult + QueryResponse clarification fields; 34 new tests (370 total). Tech debt: near-match suggestion deferred. |
| ~~**5.10** Memoria analítica activa tipada~~ ✅ | ~~Pieza central. Sustituye "el LLM se acuerda de la conversación" por "el sistema mantiene estado tipado entre turnos". Habilita follow-ups precisos como "y si subo el marketing un 10%" sin ambigüedad.~~ Completado 2026-05-13: MVP v1 — `ActiveAnalyticalState` (mutable) + `FrozenActiveAnalyticalState` + `MemoryCoordinator` (single-writer) + append-only audit log + migration 007 + `GET /v1/sessions/{id}/state` + `/state/audit`. v2 slots (dimensions, period, geography) deferred to 5.11. 24 new tests (281 total). ObjectBus dependency documented in `docs/tech_debt.md`. |
| ~~**5.11** MemoryService — interfaz única~~ ✅ | ~~Va con 5.10. Establece la disciplina arquitectónica desde día 1 (lint en CI bloquea acceso raw a `conversation_history` fuera de `memory/`). Barato hacerlo ahora, caro después.~~ Completado 2026-05-14: `core/protocols/memory.py` (`MemoryService` Protocol, `@runtime_checkable`) + `memory/service.py` (`LocalMemoryService`) + `get_memory_service()` singleton + boundary lint in CI + pre-commit hook + planner reads frozen snapshot + `governance/memory_boundary_exceptions.yaml` allowlist. 22 new tests (303 total). |
| **5.13** User-driven state corrections | Ciclo explícito `propose_state_update` → revisión del usuario → `commit_state_update`. Implementa los stubs del MemoryService Protocol (5.11). Sin esto, los errores de identificación de intent/métricas se propagan silenciosamente entre turnos. Endpoint `POST /v1/sessions/{id}/state/corrections` + UI para editar slots. Introduce reglas `volatile`/`sticky` para slot inheritance. Cierra deuda técnica "5.11 → 5.13". |
| ~~**8.7.a** Cuotas y presupuestos por tenant~~ ✅ | ~~Era el 8.7 original de v3.~~ Completado 2026-05-12: `config/model_pricing.yaml` + `evaluation/cost.py` + `evaluation/currency.py` (Frankfurter USD→EUR). Cost fields in RunResult → QueryResponse → RunRecord → agent_runs (migration 006). |
| ~~**8.7.b** Hard request-level budget ceilings~~ ✅ | ~~**El item de coste más crítico.**~~ Completado 2026-05-12: `evaluation/budget.py` (RunBudget.from_env, BudgetTracker, BudgetExceededError). Tracker wired in `invoke_with_fallback` + all 3 nodes. `/v1/budget/current` + `/v1/budget/exchange-rate` endpoints. 25 tests. |
| **8.7.c** Budget reservation antes de ejecutar | Estimación a priori del coste. Permite rechazar planes caros antes de empezar y proponer alternativas. Habilitador de 8.7.d. |
| **8.7.d** Fallback chain por slot según presupuesto | Degradación elegante: Sonnet → Haiku → reject. Declarado en spec (no hardcoded). Crítico cuando aparezca el primer cliente con cuotas estrictas. |

### Paquete 2A.4 — Evaluación y calidad

| Item                                                | Justificación                                                                                                                          |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **10.2** Datasets de evaluación del sistema agentic | Colección curada de queries para testing. Habilita 5.2 (test suites v2), 10.3 y 5.1.                                                   |
| **5.2** Test suites v2 (ampliación)                 | Ampliar las 10-15 queries de I1 a un dataset completo con casos por tool, límite y regresión. Ejecutado en CI y en evaluación offline. |
| **5.1** Judge offline sobre logs históricos         | Procesamiento periódico de runs para detectar degradaciones. Depende de 8.1 (runs en Postgres, hecho en I1).                           |
| **10.3** Evaluación offline pre-promoción           | Gate de calidad para cambios en prompts, tools o modelos LLM. Depende de 10.2.                                                         |
| **10.9** Prompt capture infraestructura `[v4]`      | Captura del prompt completo enviado a cada LLM, etiquetado por stage. Complementa el prompt registry (10.1) — el registry es la fuente de verdad, capture es el exporter por run. Habilita debugging post-hoc y enriquece evaluaciones offline (10.3). |

### Paquete 2A.5 — Parches y mejoras del agente

| Item                                                      | Justificación                                                                                    |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| ~~**3.6** Versionado semántico del spec~~ ✅ 2026-05-09   | `spec/versioning.py`: SpecVersion, BumpType, detect_bump_type. semver validation in create/update/seed. `POST /v1/specs/{id}/bump`. Migration 003 CHECK constraint. 145 tests pass. |
| **10.4** Versionado del spec como artefacto de despliegue | PR, review, validación automática, promoción entre entornos. Aplica la disciplina de I1 al spec. |
| ~~**10.1** Prompt registry~~ ✅ 2026-05-10               | `prompts/` package; `PromptRecord` + `PromptStatus`; `get_prompt_template(stage, fallback)` con fallback inline; `seed_prompts_from_code()` idempotente; migration 004 (tabla prompts), 005 (3 prompt_version cols en agent_runs); 5 endpoints REST `/v1/prompts`; versiones propagadas por AgentState → RunRecord → PostgresSink; 220 tests pasan. |
| ~~**10.2** Prompt A/B testing~~ ✅ 2026-05-17            | `prompts/routing.py` (sha256-bucket deterministic routing, `@lru_cache` per stage, `invalidate_variant_cache()`); `PromptVariant` + `PromptVariantStatus` en `prompts/models.py`; `get_prompt_template()` → 3-tuple `(content, version, variant_label)`; variant CRUD en `prompts/registry.py`; migrations 008 (`prompt_variants`) + 009 (`*_variant_label` cols on `agent_runs`); 6 endpoints REST; `ui/dashboard.py` variant table; 27 new tests (330 total). Tech debt: auto-promotion deferred to 10.3. |

### Por qué I2A va antes de I2B

La lógica es: **validar primero que el producto funciona con datos reales en un entorno controlado, antes de invertir en la capa de seguridad enterprise que lo abre al exterior**. Las piezas de seguridad (multi-tenancy, SSO, cifrado, audit) son imprescindibles para el cliente externo, pero no aportan valor hasta que el producto demuestra que funciona con datos reales. Hacer la seguridad primero es construir la cerradura antes de saber si la casa vale la pena.

Además, I2A es más barata en tiempo y complejidad que I2B, lo que significa que se puede obtener feedback real más rápido. Un consultor de Inverence probando llull con datos de un cliente candidato genera aprendizaje inmediato sobre la calidad del onboarding, del mapping, de las recomendaciones — y ese aprendizaje puede redirigir prioridades antes de invertir en la capa enterprise.

---

## ITERACIÓN 2B — Seguridad enterprise y operación (apertura a cliente externo)

### Criterio de entrega

Al final de esta sub-iteración, llull está **listo para ponerse delante de un cliente enterprise en un piloto controlado: multi-tenancy funcional, SSO, cifrado, audit log, mitigaciones AI-native, despliegue en Kubernetes con entornos separados, observabilidad clásica, backups, y políticas de retención GDPR**. Es el sistema que pasa la primera due diligence de seguridad de un BBVA o una Comunidad de Madrid.

Es el paso de sistema que funciona con datos reales "internamente" a sistema que se puede enseñar y comercializar.

### Paquete 2B.1 — Seguridad enterprise mínima

| Item                                    | Justificación                                                                                                                                                                     |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **7.1** Multi-tenancy con RLS           | Sobre el schema de Postgres definido en I1, añadir `tenant_id` y políticas RLS. Es una decisión de modelo de datos que no puede posponerse más si hay un cliente en el horizonte. |
| **7.5** SSO con OIDC (+SAML)            | El primer cliente enterprise va a exigirlo. Authlib sobre FastAPI.                                                                                                                |
| **7.6** Cifrado en tránsito y en reposo | TLS 1.3, mTLS entre servicios internos, cifrado de Postgres. No negociable para enterprise.                                                                                       |
| **7.7** Gestión de secretos con Vault   | API keys, credenciales de cliente, tokens. Fuera del código, fuera de env vars de imágenes.                                                                                       |
| **7.8** Audit log append-only           | Requisito regulatorio. Toda acción administrativa registrada.                                                                                                                     |
| **7.9** Mitigaciones AI-native          | Prompt injection, data leakage cross-tenant, control de exfiltración vía LLM. Se implementan ahora porque son riesgos reales cuando hay datos de clientes en el sistema.          |

### Paquete 2B.2 — Operación productiva

| Item                                                      | Justificación                                                                                  |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **11.4** Kubernetes con Helm                              | Necesario para desplegar en un entorno real. Depende de 11.3 (contenedorización, hecho en I1). |
| **11.5** Despliegue por entornos (dev/staging/prod)       | Separación de entornos con promoción controlada.                                               |
| **11.6** Rolling deployment con health checks             | Despliegues sin downtime.                                                                      |
| **8.2** Métricas con OpenTelemetry + Prometheus + Grafana | Observabilidad clásica. Sin esto, operar en producción es a ciegas.                            |
| **8.3** Métricas específicas del agente                   | Judge score, distribución de tools, coste por query. Exportadas a Prometheus.                  |
| **12.1** Política de retención de datos                   | GDPR. Configurable por tenant.                                                                 |
| **12.2** Backup y disaster recovery                       | Backups de Postgres, procedimiento de restauración probado.                                    |

### Items que no entran en la Iteración 2 (ni A ni B) y por qué

- **DAG builder visual (3.1)**: alto valor pero alto esfuerzo, y depende de 1.5 que se habrá hecho en I1. Es el plato fuerte de I3. El consultor puede operar con el generador conversacional (3.2) + API de specs durante el piloto.
- **CDC/Debezium (2.3)**: el primer cliente usa Excel, no streaming de datos transaccionales. Si lo pidiera, se adelanta.
- **Multi-agente (5.3.a/b)**: requiere ObjectBus + ActiveAnalyticalState + MemoryService como prerequisitos técnicos (todos en I1/I2A) y un caso de uso real de "acción post-decisión" que el piloto interno valide. Es el plato fuerte de I3 junto al DAG builder.
- **Redis para memoria (1.4)**: optimización que solo se justifica con cientos de sesiones concurrentes. El primer piloto no va a tenerlas.
- **Conectores REST, data warehouses (2.8, 2.9)**: se construyen cuando aparezca el cliente que los necesita, no antes.
- **MLflow (9.3)**: es independiente y podría ir aquí, pero aporta poco valor hasta que haya datos reales y múltiples modelos. En I3 tiene más sentido.
- **8.7.e/f, 5.12 (resto del control de gasto)**: las dimensiones críticas (tenant, run, slot) están en I2A. Las dimensiones avanzadas (peer, lineage, recursion) requieren multi-agente, que está en I3.
- **10.10 LineageRecord tipado, 10.11 Golden eval con CI gates, 10.8 Registry pattern unificado**: requieren que múltiples registries existan (PromptRegistry está en I2A, pero MetricRegistry, DimensionRegistry, EntityRegistry, ToolRegistry, ModelRegistry vienen con el escalado de I3). Sin ellos, 10.10 no tiene fuentes que referenciar.

---

## ITERACIÓN 3 — Producto diferencial

### Criterio de entrega

Al final de esta iteración, llull tiene su **capacidad diferencial más visible desplegada: el DAG builder visual, el Bloque A multi-agente con governance (Decision Agent + Dashboard Agent coordinados por Supervisor de LangGraph + capability graph tipado + recursion guard + budgets por peer), la primera extracción de servicios, scenario comparison, análisis causal, MLOps básico con MLflow, observabilidad completa, governance unificada con registries tipados, LineageRecord por respuesta y golden eval con CI gates**. Es el sistema que se presenta al mercado como producto, no como piloto.

Además, se abordan las primeras piezas de escalado (Redis para memoria, paralelización de simulaciones, WebSockets) y las primeras piezas de gobernanza formal completa (RBAC, OPA, lineage tipado, dimensiones avanzadas del control de gasto).

### Paquete 3A — DAG builder y onboarding avanzado

| Item                                                    | Justificación                                                                                                                                                                |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **3.1** DAG builder visual                              | La feature de producto más visible. Editor visual con React Flow o D3.js. Depende de 1.5 (spec as data, hecho en I1) y de 6.1.d (Spec Service).                              |
| **6.1.d** Spec Service (primera extracción de servicio) | Se extrae ahora porque el DAG builder necesita una API dedicada para specs. Es el primer servicio que sale del monolito.                                                     |
| **12.8** Proceso de onboarding documentado              | Las tres fases formalizadas: modelo causal, datos reales, modelos predictivos. Con 3.1, 3.2, 2.1, 2.2, la herramienta está completa; falta el proceso documentado alrededor. |

### Paquete 3B — Bloque A multi-agente con governance `[v4]`

| Item                                            | Justificación                                                                                                                                          |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **5.3.a** MVP Bloque A — Supervisor + Decision Agent + Dashboard Agent | Patrón Supervisor de LangGraph (declarado en ADR-002). El Decision Agent es el prototipo actual envuelto como sub-agente; el Dashboard Agent recibe su output vía ObjectBus (1.6) y genera la visualización. Primera demostración tangible del Bloque A. |
| **5.3.b** Capability Graph tipado               | Tabla declarativa de quién puede llamar a quién, con qué payloads, profundidad y budget. Prerequisito ético del multi-agente, no opcional. Sin esto, multi-agente no es vendible a cliente regulado. Va siempre con 5.3.a. |
| **5.12** Recursion guard y depth limits         | Cap de profundidad y de número total de handoffs por run. Detección de ciclos. Sin esto, un bug en routing puede consumir miles de dólares antes de detectarse. |
| **8.7.e** Budgets por capability/peer           | Cuando el Decision Agent invoca al Dashboard Agent, declara qué fracción del budget transfiere. Modelo `share | slice | separate`. Pieza necesaria de governance multi-agente. |

### Paquete 3C — Capacidades analíticas avanzadas

| Item                                     | Justificación                                                                     |
| ---------------------------------------- | --------------------------------------------------------------------------------- |
| **4.2** Optimización multi-variable      | Bayesian o genéticos. Desbloquea dominios con más de 2 variables de decisión.     |
| **4.4** Motor de simulación paralelizado | Multiprocessing/joblib. Primera línea de defensa de rendimiento.                  |
| **4.5** Scenario comparison              | Comparativa estructurada de múltiples escenarios. Valor prescriptivo alto.        |
| **4.6** Análisis causal automatizado     | "¿Por qué cambió este resultado?" recorriendo el DAG. Capacidad diferencial real. |

### Paquete 3D — MLOps

| Item                                           | Justificación                                                  |
| ---------------------------------------------- | -------------------------------------------------------------- |
| **9.3** Experiment tracking con MLflow         | Ancla de la cadena de MLOps.                                   |
| **9.5** Model Registry con MLflow              | Versionado formal de modelos con aliases y promoción.          |
| **9.1** Versionado de datasets con DVC         | Reproducibilidad de entrenamientos.                            |
| **9.2** Pipeline de entrenamiento reproducible | Contenedores con dependencias fijadas. Sobre Kubeflow/Prefect. |
| **9.4** Validación automática pre-promoción    | Gate de calidad para modelos.                                  |

### Paquete 3E — Escalado y rendimiento

| Item                                      | Justificación                                                                                                    |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **1.4** Redis para memoria caliente       | Se introduce si el piloto de I2 ha mostrado contención en Postgres con sesiones concurrentes. Si no, se pospone. |
| **6.2** WebSockets                        | Streaming de respuestas y notificaciones async. Mejora la experiencia del usuario.                               |
| **5.4** Agentes async como tool del grafo | El patrón de tool asíncrona. Prepara para event-driven sin introducirlo todavía.                                 |

### Paquete 3F — Governance unificada y lineage `[v4]`

| Item                                      | Justificación                                                                                                                                              |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **7.2** RBAC con scoping por dominio      | Sobre el multi-tenancy de I2. Roles y capabilities granulares.                                                                                             |
| **7.3** Políticas de autonomía en runtime | El planner consulta la política del spec antes de ejecutar tools sensibles.                                                                                |
| **7.4** OPA como servicio de autorización | Centralización de políticas. Depende de que haya un modelo de permisos (7.2).                                                                              |
| **10.8** Registry pattern unificado `[v4]` | Generalización del PromptRegistry de I2A al resto: MetricRegistry, DimensionRegistry, EntityRegistry, ModelRegistry, ToolRegistry, SkillRegistry, PolicyRegistry, BudgetRegistry, VocabularyRegistry. Cada artefacto con `id · version · status · owners · sunset_date · adr`. Storage GitOps + Postgres. |
| **8.7.f** Cost lineage por run `[v4]`     | Breakdown de coste por nodo del plan. Indexado por `run_id`. Pieza del LineageRecord.                                                                      |
| **10.10** LineageRecord tipado `[v4]`     | Pieza que cierra trazabilidad regulatoria completa. Cada respuesta lleva la cadena completa: routing, plan, agentes invocados con versiones, tools ejecutadas, métricas usadas con IDs y versiones, reglas aplicadas, políticas evaluadas, objetos consumidos/producidos, cost lineage, judge verdict. Reemplaza al 10.5 genérico. |
| **10.11** Golden eval harness con CI gates `[v4]` | Tres gates separados: routing-gate, plan-gate, response-shape-gate. Refina 10.2 + 10.3 con la nomenclatura precisa de las arquitecturas objetivo. |

### Paquete 3G — Observabilidad completa

| Item                                         | Justificación                                                                |
| -------------------------------------------- | ---------------------------------------------------------------------------- |
| **8.4** Logging centralizado con Loki + run_id por contextvar `[v4 — refinado]` | Logs estructurados, correlación por run_id/session_id/tenant_id. run_id propagado vía contextvars (patrón inspirado en LlullLogger de LlullGen). |
| **8.5** Alerting con políticas por severidad | Alertas sobre métricas técnicas y del agente.                                |
| **8.6** Dashboard multi-tenant               | Visibilidad para el admin del cliente sobre sus propias sesiones y métricas. |

### Paquete 3H — Mejoras del agente

| Item                                                 | Justificación                                                                |
| ---------------------------------------------------- | ---------------------------------------------------------------------------- |
| **5.8** Memoria persistente sobre el dominio         | El agente mejora con el uso.                                                 |
| **10.7** Guardrails de output del LLM                | Más allá del judge: detección de alucinaciones, respuestas fuera de dominio. Trabaja con 5.9 (GroundedTokens, en I2A). |
| **12.6** Documentación operativa                     | Runbooks, playbooks, diagramas, glosario.                                    |

---

## Items que quedan fuera de las tres iteraciones

Estos items son reales y necesarios, pero su timing depende de señales externas (un cliente que lo exija, un volumen que lo justifique, una oportunidad estratégica que lo habilite). Se revisan al inicio de cada ciclo de planificación.

| Item                                                | Por qué queda fuera                                                                                                                                                       | Señal que lo activaría                                                                                       |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **2.3** CDC con Debezium/Kafka                      | Ningún cliente del primer año va a necesitar streaming real-time.                                                                                                         | Un cliente con fuentes transaccionales que exija latencia de segundos.                                       |
| **2.4** Schema registry                             | Emparejado con 2.3. Sin Kafka no tiene sentido.                                                                                                                           | Se activa junto con 2.3.                                                                                     |
| **2.7** Ontologías corporativas                     | Técnicamente complejo, valor alto pero para un subconjunto de clientes.                                                                                                   | Un cliente enterprise con ontología formalizada (BBVA, AAPP) que quiera usarla.                              |
| **2.8** Conectores REST (ERP, CRM)                  | Se construye conector a conector cuando un cliente lo necesita.                                                                                                           | Un cliente cuya fuente principal sea Salesforce, SAP, etc.                                                   |
| **2.9** Conectores data warehouses                  | Igual que 2.8, bajo demanda.                                                                                                                                              | Un cliente con Snowflake/BigQuery/Redshift.                                                                  |
| **3.4** Generación automática de spec desde datos   | Aspiracional. Requiere madurez del spec, del mapping layer y de la capa analítica.                                                                                        | Madurez del producto + demanda clara de onboarding más rápido.                                               |
| **5.3.c** Sub-agentes adicionales (Alert / Report / Action) | Cada uno se incorpora bajo demanda real. Alert cuando un cliente pida notificaciones programadas. Report cuando pida exports estructurados. Action cuando haya demanda de "el sistema ejecuta", el caso más sensible en autonomía. Cada uno respeta el capability graph (5.3.b) — no entran por la puerta de atrás. | Demanda concreta de un cliente piloto. |
| **5.3** Orquestación multi-agente (resto)           | Los sub-agentes adicionales (Alert, Report, Action) viven aquí porque dependen de que aparezca el caso de uso real.                                                       | Ver fila anterior 5.3.c.                                                                                     |
| **6.1.a–c, f, g** Extracción de servicios restantes | Se extraen cuando hay razón concreta: escalado independiente, equipo separado, integración externa.                                                                       | Señal de escalado, equipo creciendo, o modelo externo de Inverence que necesite su propio servicio.          |
| **6.3** Event-driven con message broker             | Solo cuando una tarea real rompa el SLA síncrono.                                                                                                                         | Simulación o optimización que tarde más de lo admisible incluso paralelizada.                                |
| **7.10** Despliegues dedicados (single-tenant)      | Requiere madurez del IaC (11.7) y un cliente que lo exija contractualmente.                                                                                               | Contrato con un banco o administración pública con requisito de aislamiento total.                           |
| **9.6** Shadow/canary para modelos                  | Requiere volumen de tráfico real suficiente para que las comparativas sean significativas.                                                                                | Múltiples clientes en producción con modelos que se reentrenan regularmente.                                 |
| **9.7** Monitorización de drift                     | Requiere labels reales (feedback del cliente sobre la calidad de recomendaciones).                                                                                        | Datos de feedback reales del primer piloto.                                                                  |
| **9.8** Triggers de reentrenamiento                 | Requiere 9.7 (drift) y 9.2 (pipeline reproducible).                                                                                                                       | Pipeline completo y métricas de drift definidas.                                                             |
| **9.9** Múltiples modelos por dominio               | El prototipo tiene uno. Más modelos aparecen orgánicamente con más clientes y más dominios.                                                                               | Segundo o tercer cliente con dominios distintos.                                                             |
| **11.7** Terraform (IaC)                            | Importante pero no bloqueante hasta que haya múltiples entornos reales que gestionar.                                                                                     | Segundo entorno de producción o primer despliegue dedicado.                                                  |
| **11.8** Stack cloud-agnostic completo              | Es una propiedad emergente de usar componentes portables, no un item que se "implementa". Se valida cuando se hace el primer despliegue en un cloud distinto al original. | Primer cliente que exija un cloud diferente al que se eligió inicialmente.                                   |
| **12.3** Validación causal del DAG                  | Proceso de producto, no de código. Requiere trabajar con consultores de Inverence y con el primer cliente real.                                                           | Onboarding del primer piloto.                                                                                |
| **12.7** SDK cliente                                | Valor alto cuando hay integraciones de clientes. Antes de eso, la API documentada (OpenAPI) es suficiente.                                                                | Segundo o tercer cliente integrando contra la API.                                                           |

---

## Mapa visual de las iteraciones

```
╔══════════════════════════════════════════════════════════════════════════╗
║                          PROTOTIPO ACTUAL                                ║
║  REPL · SQLite + FAISS · LangGraph · Spec YAML estático · JSONL logs     ║
╚══════════════════════════════════════╦═══════════════════════════════════╝
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ITERACIÓN 1 — Fundación productiva                                      │
│                                                                          │
│  ┌─────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐   │
│  │ Persistencia    │ │ API & Servicio   │ │ Ingeniería               │   │
│  │                 │ │                  │ │                          │   │
│  │ PostgreSQL      │ │ Agent Service    │ │ Pipeline CI              │   │
│  │ pgvector        │ │ (monolito        │ │ Contenedorización        │   │
│  │ Spec as data    │ │  modular)        │ │ Test suites v1           │   │
│  │ ObjectBus 3-tier│ │ Endpoints admin  │ │ Fallback robusto         │   │
│  │ Runs en Postgres│ │ Versionado API   │ │                          │   │
│  │ Ruta Qdrant doc.│ │                  │ │                          │   │
│  └─────────────────┘ └──────────────────┘ └──────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ ✅ Parches (1D): multi-turno · multi-proveedor LLM · rate limit │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ 🖥️ UI: Streamlit — chat visual, DAG, gráficos de resultados     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ITERACIÓN 2A — Datos reales y calidad (piloto interno)                  │
│                                                                          │
│  ┌───────────────────┐ ┌──────────────────┐ ┌────────────────────────┐   │
│  │ Datos reales      │ │ Modelo dominio   │ │ Memoria + gasto        │   │
│  │                   │ │                  │ │                        │   │
│  │ Conectores batch  │ │ Generador conv.  │ │ LLMFactory completo    │   │
│  │ Mapping Layer LLM │ │ Validación auto. │ │ GroundedTokens guard   │   │
│  │ Great Expectations│ │ Políticas auton. │ │ ActiveAnalyticalState  │   │
│  │ SQL Gateway R0-R3 │ │ Portabilidad     │ │ MemoryService protocol │   │
│  │ Data bindings     │ │ Skills+MCP       │ │ Cuotas tenant (8.7.a)  │   │
│  │                   │ │                  │ │ Hard ceilings (8.7.b)  │   │
│  │                   │ │                  │ │ Budget reserve (8.7.c) │   │
│  │                   │ │                  │ │ Fallback chain (8.7.d) │   │
│  └───────────────────┘ └──────────────────┘ └────────────────────────┘   │
│  ┌─────────────────────────────────┐ ┌────────────────────────────────┐  │
│  │ Evaluación y calidad            │ │ Mejoras del agente             │  │
│  │                                 │ │                                │  │
│  │ Datasets evaluación             │ │ Versionado spec                │  │
│  │ Test suites v2                  │ │ Spec como artefacto            │  │
│  │ Judge offline                   │ │ Prompt registry                │  │
│  │ Eval. pre-promoción             │ │  (1er registry tipado)         │  │
│  │ Prompt capture                  │ │                                │  │
│  └─────────────────────────────────┘ └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ITERACIÓN 2B — Seguridad enterprise y operación (cliente externo)       │
│                                                                          │
│  ┌───────────────────────────┐  ┌────────────────────────────────────┐   │
│  │ Seguridad enterprise      │  │ Operación productiva               │   │
│  │                           │  │                                    │   │
│  │ Multi-tenancy (RLS)       │  │ Kubernetes + Helm                  │   │
│  │ SSO (OIDC + SAML)         │  │ Entornos dev/staging/prod          │   │
│  │ Cifrado tránsito/reposo   │  │ Rolling deployment                 │   │
│  │ Vault (secretos)          │  │ OTel + Prometheus + Grafana        │   │
│  │ Audit log                 │  │ Métricas agentic                   │   │
│  │ Mitigaciones AI-native    │  │ Retención datos · Backup/DR        │   │
│  └───────────────────────────┘  └────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ITERACIÓN 3 — Producto diferencial                                      │
│                                                                          │
│  ┌───────────────────┐ ┌──────────────────┐ ┌────────────────────────┐   │
│  │ DAG builder       │ │ Bloque A multi-A │ │ Analítica avanzada     │   │
│  │                   │ │                  │ │                        │   │
│  │ Editor visual     │ │ MVP Supervisor   │ │ Optim. multi-var       │   │
│  │ Spec Service      │ │ + Decision Agent │ │ Paralelización         │   │
│  │ Onboarding doc.   │ │ + Dashboard Agt  │ │ Scenario comparison    │   │
│  │                   │ │ Capability Graph │ │ Análisis causal        │   │
│  │                   │ │ Recursion guard  │ │                        │   │
│  │                   │ │ Budgets peer     │ │                        │   │
│  └───────────────────┘ └──────────────────┘ └────────────────────────┘   │
│  ┌───────────────────┐ ┌──────────────────┐ ┌────────────────────────┐   │
│  │ MLOps             │ │ Escalado         │ │ Governance + Lineage   │   │
│  │                   │ │                  │ │                        │   │
│  │ MLflow tracking   │ │ Redis memoria    │ │ RBAC + OPA             │   │
│  │ Model Registry    │ │ WebSockets       │ │ Registry pattern unif. │   │
│  │ DVC datasets      │ │ Async tools      │ │ Cost lineage (8.7.f)   │   │
│  │ Pipeline reprod.  │ │                  │ │ LineageRecord tipado   │   │
│  │ Validación pre-prom.│                  │ │ Golden eval CI gates   │   │
│  └───────────────────┘ └──────────────────┘ └────────────────────────┘   │
│  ┌───────────────────┐ ┌────────────────────────────────────────────┐    │
│  │ Observab. compl.  │ │ Mejoras del agente                         │    │
│  │                   │ │                                            │    │
│  │ Loki+contextvars  │ │ Memoria dominio · Guardrails output LLM    │    │
│  │ Alerting          │ │ Documentación operativa                    │    │
│  │ Dashboard m-tenant│ │                                            │    │
│  └───────────────────┘ └────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  MÁS ALLÁ — Bajo demanda / señal de mercado                              │
│                                                                          │
│  CDC + Kafka · Ontologías · Sub-agentes Alert/Report/Action              │
│  Extracción servicios · Event-driven · Despliegues dedicados             │
│  Shadow/canary · Drift/retrain · Terraform · SDK cliente                 │
│  Generación spec desde datos                                             │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Notas finales

**Sobre la subdivisión de la Iteración 2.** La I2 original concentraba demasiados ejes para un equipo pequeño: datos reales, seguridad, evaluación y operación. La subdivisión en 2A y 2B permite obtener feedback real más rápido. I2A valida con un consultor interno de Inverence que el producto funciona con datos reales. Ese feedback puede redirigir prioridades antes de invertir en la capa enterprise de I2B. Si todo va bien, el equipo trabaja I2A e I2B de forma consecutiva pero con un punto de revisión entre ambas. Si I2A revela problemas graves (el mapping no funciona, el generador conversacional produce specs inutilizables, la validación semántica bloquea datos válidos), se itera sobre I2A antes de abrir I2B.

**Sobre el tamaño de las iteraciones.** La Iteración 1 es la más acotada y la que más impacto tiene por item. La I2A es manejable (15 items, foco en producto y calidad). La I2B es más pesada en infraestructura (13 items, foco en seguridad y operación). La Iteración 3 es donde llull se diferencia — pero solo es posible si I1, I2A e I2B están sólidas.

**Sobre la flexibilidad.** Este roadmap no es un compromiso contractual. Es un mapa del terreno con una ruta recomendada. Si un cliente aparece antes de lo esperado y exige algo de I3 (digamos, el DAG builder), se adelanta. Si un riesgo se materializa (digamos, que el proveedor de LLM cambia su pricing), se reordena. Las iteraciones tienen criterio de entrega, no fecha. Eso da flexibilidad sin perder dirección.

**Sobre lo que queda fuera.** Los items del bloque "más allá" no están descartados — están diferidos hasta que haya una señal clara que los active. La señal está documentada para cada uno. Eso significa que nadie tiene que "recordar" que había que hacer CDC; cuando el primer cliente pida streaming, se mira el inventario, se lee la señal, y se planifica.

**Sobre la integración con Managed Agents.** Este roadmap es independiente de la decisión sobre Managed Agents. Si se decide incorporarlos (parcial o totalmente), los items que más se ven afectados son: 6.1.e (Agent Service), 5.4 (async tools), 6.3 (event-driven), y partes de 7.9 (seguridad AI-native) y 8 (observabilidad). El inventario y el roadmap se actualizarían para reflejar qué items asume Managed Agents y cuáles siguen siendo propios. Esa es una conversación separada que se puede tener cuando el inventario y el roadmap estén estabilizados.

**Sobre los ADRs (nuevos en v4).** Tres decisiones arquitectónicas quedan registradas como ADRs (Architecture Decision Records) en el repositorio de docs del proyecto:

- **ADR-001 — pgvector sobre Qdrant**: ⚠️ SUPERSEDED por ADR-005 (2026-05-06). Preservado por trazabilidad histórica.
- **ADR-005 — Vector store strategy for the enterprise multi-agent platform**: nuevo. Reevalúa ADR-001 bajo las premisas enterprise (millones de vectores por tenant, multi-tenancy estricto, sectores regulados). Decisión: pgvector + pgvectorscale (StreamingDiskANN) dentro del mismo Postgres, con cinco triggers formales para migración parcial a Qdrant. Condiciona los items 1.2, 1.3, 1.4, 7.1, 11.1 y el path de evolución del knowledge layer.
- **ADR-002 — LangGraph como motor de orquestación**: nuevo. Documenta por qué llull mantiene LangGraph (con patrón Supervisor para multi-agente) frente a alternativas como el A2A custom de LlullGen, AutoGen, CrewAI o el A2A protocol de Google ADK. Condiciona cómo se implementan 5.3.a, 5.3.b, 5.4, 5.12.
- **ADR-003 — Política de reutilización de componentes de LlullGen**: nuevo. Documenta cómo se reutilizan los componentes salvables de LlullGen (LLMFactory, ObjectBus, GroundedTokens, SQL Gateway, prompt capture, LlullLogger) — inspiración conceptual sí, porting de código no — y por qué. Condiciona cómo se implementan 1.6, 2.10, 5.6, 5.9, 8.4, 10.9.

Los ADRs son ortogonales al roadmap pero condicionan el cómo de cada item que los usa. Sirven además como blindaje político: dejan tu razonamiento documentado desde día 1 frente a reescrituras posteriores motivadas por preferencias del equipo existente.

**Sobre el control de gasto LLM en v4.** Las seis dimensiones del control (cuota tenant, hard ceilings por run, budget reservation, fallback chain por slot, budgets por peer, cost lineage) se distribuyen entre I2A (las cuatro primeras, críticas para piloto seguro) e I3 (las dos últimas, requieren multi-agente y registries unificados). Esta cobertura completa cierra el gap explícito que la auditoría AI Layer de LlullGen reporta y que v3 cubría parcialmente.
