# ADR-003 — Política de reutilización de componentes de LlullGen en la plataforma llull

| Campo | Valor |
|---|---|
| **Estado** | Aceptada |
| **Fecha** | 2026-05-05 |
| **Autor** | Gustavo Mateos (Architect) |
| **Decisores** | Architect (autor), CEO Inverence (revisión) |
| **Supersede** | — |
| **Superseded by** | — |
| **Relacionada con** | ADR-001 (pgvector vs Qdrant), ADR-002 (LangGraph como motor de orquestación) |

---

## Contexto

LlullGen es el MVP "text-to-query conversacional" desarrollado por el equipo técnico actual de Inverence. La plataforma llull (visión global de decision intelligence, encarnada en la arquitectura "llull Decision Intelligence Architecture") **no se construye sobre LlullGen** — se construye sobre el prototipo Decision Intelligence Agent que ya tiene su núcleo arquitectónico correcto (spec-driven, DAG causal, herramientas deterministas, LLM como orquestador no como calculadora).

Sin embargo, LlullGen contiene **componentes técnicos individuales bien diseñados** que resuelven problemas reales que llull va a tener que resolver de todas formas. La auditoría del codebase de LlullGen (puntuación global 2.05/5) reconoce explícitamente buena ingeniería en piezas concretas a pesar de la fragilidad estructural del conjunto.

El problema a resolver es: **cómo aprovechar el trabajo bien hecho sin importar las limitaciones estructurales del entorno donde vive ese trabajo**, y hacerlo de forma que (a) sea técnicamente robusto, (b) respete la arquitectura objetivo de llull, (c) sea defendible políticamente frente al equipo que escribió ese código.

## Opciones consideradas

### Opción A — Porting directo del código de LlullGen

Copiar los módulos rescatables de LlullGen al repo de llull con cambios mínimos (renombrados, adaptación de imports). Reutilización máxima de líneas de código.

### Opción B — Inspiración conceptual sin reutilización de código (clean reimplementation) [DECISIÓN]

Tomar el patrón arquitectónico, el contrato y las lecciones aprendidas de cada componente identificado como rescatable, y **reimplementarlo limpio** sobre la arquitectura llull respetando el spec-driven, los registries tipados, la disciplina de governance y la nomenclatura llull.

### Opción C — Ignorar LlullGen completamente y diseñar de cero

Tratar a LlullGen como inexistente. Diseñar cada pieza desde primeros principios sin examinar lo que ya existe en LlullGen.

## Análisis

### Opción A — Porting directo

**Ventajas:**
- Reutilización máxima de líneas. Velocidad inicial alta.

**Desventajas (decisivas):**

- **Hereda la deuda estructural.** La auditoría documenta dual architecture coexistiendo (LangGraph-style PlanExecutor y A2A custom dispatch), 4.5%–17% dark code (planner architecture nunca alcanzable, ~7kLOC zombie), 443 cláusulas `except Exception:` indiscriminadas, type: ignore aisladores en piezas críticas, in-function imports masivos, requirements.txt con duplicados.
- **Hereda los bugs estructurales.** Validator-Reconciler implementado pero **deshabilitado en producción** (`parallel_executor.py:48-55`). Routing LLM con free-form JSON parsing en lugar de structured output. Helpers reconstruidos perdiendo `conversation_history`. ChartAgent leyendo `conversation_history[-4:]` directamente bypassing toda abstracción.
- **Hereda el sesgo de dominio.** Vocabularios geo/métricas hardcodeados en español dentro de Python. SQL policies con valores específicos de un dominio inferidos a hardcoded. Esto contradice el principio spec-driven de llull.
- **Hereda el bug crítico de seguridad.** `pickle.loads(request.data)` en endpoint POST público sin auth (la auditoría de seguridad lo puntúa con 0/5). Aunque el endpoint específico no se porte, el riesgo de arrastrar patrones similares es real.
- **Genera fricción política mayor.** Portar el código y luego refactorizarlo significa tocar lo que el equipo escribió. Reescribir desde cero es menos invasivo conceptualmente: "construyo mi solución, no toco la tuya".
- **El esfuerzo "ahorrado" se paga después.** Cada PR que toque ese código tendrá que entender por qué se hizo así, qué partes son intencionales y qué partes son accidente, qué tests son reales y qué tests son cosméticos (la auditoría reporta tests mocking en typo'd import paths que validan bugs).

### Opción B — Inspiración conceptual + clean reimplementation

**Ventajas:**

- **Captura el valor sin la deuda.** Aprendizajes incorporados, código limpio.
- **Respeta la arquitectura llull desde día 1.** Cada pieza nace alineada con spec-driven, registries tipados, MemoryService boundary, capability graph.
- **Velocidad real comparable a porting.** El componente conceptual ya está diseñado y validado; reescribirlo sobre la base limpia es más rápido que adaptar código frágil. Estimación: 60–80% del tiempo de un diseño from-scratch para los componentes más simples; 100–120% para los más complejos (que requieren adaptaciones significativas como GroundedTokens spec-driven).
- **Defendible políticamente.** "He estudiado tu trabajo, he extraído las ideas valiosas, las he integrado en la arquitectura de llull con las adaptaciones que requiere el contexto." Es respeto explícito sin compromiso técnico.
- **Coherente con la decisión documentada en ADR-002** (LangGraph como motor): si rechazamos el A2A custom de LlullGen como motor por sus limitaciones estructurales, no tiene sentido portar el código de los demás módulos sin examinar si arrastran patrones similares.

**Desventajas:**

- **Esfuerzo de implementación no nulo.** No es código gratis. Hay que reescribir.
- **Requiere disciplina** para no caer tentado a "copiar y pegar" cuando hay presión de tiempo.

### Opción C — Ignorar LlullGen completamente

**Ventajas:**
- Cero contaminación conceptual.

**Desventajas (decisivas):**

- **Pierde aprendizajes valiosos.** Componentes como GroundedTokens (que la auditoría llama "the single architecturally serious memory-governance primitive in the codebase") resuelven problemas reales que llull va a enfrentar.
- **Reinventa la rueda.** El equipo de LlullGen ya hizo el trabajo de descubrir qué patrones funcionan (LLMFactory con budget guard, ObjectBus tres niveles, SQL Gateway con políticas tipadas, query_id por contextvar). Repetir el descubrimiento es desperdicio.
- **Comunica desprecio injustificado.** Ignorar el trabajo del equipo cuando hay piezas valiosas envía la señal equivocada. Políticamente peor que la opción B.

## Decisión

**Adoptamos la Opción B: inspiración conceptual sin reutilización de código.**

### Catálogo de componentes con política de reutilización declarada

Para cada componente rescatable identificado en LlullGen, este ADR declara: el patrón conceptual a adoptar, las adaptaciones requeridas, el item del inventario llull en el que se materializa, y el principio de "código limpio nuevo" sin porting directo.

#### 1. LLMFactory con multi-proveedor + budget guard + context-budget pre-flight

| | |
|---|---|
| **Patrón conceptual** | Registry tipado de modelos × slots × versiones, con context-budget pre-flight que reduce mensajes deterministamente antes de overflow, y fallback chain por slot |
| **Inventario llull** | Item 5.6 (ampliado) |
| **Adaptaciones** | (a) Cost ledger por llamada como input para 8.7.f; (b) slots como Pydantic enum, no strings; (c) registrar proveedores adicionales relevantes para llull (Bedrock, Vertex AI, Ollama); (d) fallback chain extendida para activarse por **presupuesto** además de por error (8.7.d); (e) `LLMFactory` como Pydantic model en `ModelRegistry` (10.8), no como singleton |
| **No portar** | Código directo de `logic/llm/llm_factory.py` y `logic/llm/budget_guard.py` |

#### 2. ObjectBus de tres niveles (hot/warm/cold) con checksums y session scoping

| | |
|---|---|
| **Patrón conceptual** | Almacén de objetos por sesión con tres niveles (hot in-memory, warm Postgres-Parquet, cold SQL-recompute), checksum SHA-256, scoping `session_id` + `role`, event log de puts/gets |
| **Inventario llull** | Item 1.6 (nuevo) |
| **Adaptaciones** | (a) **Ampliar el contrato** para guardar outputs tipados de `SystemModel.evaluate()`, runs de Monte Carlo con distribuciones, escenarios optimizados, rastros de análisis causal — no solo DataFrames de SQL; (b) `grain contract` tipado como Pydantic model (lo recomienda explícitamente la Memory Architecture target); (c) integración con LineageRecord (10.10) — los `objects_consumed` y `objects_produced` viven en el bus |
| **No portar** | Código directo de `logic/bus/object_bus.py` |

#### 3. GroundedTokens (guardrail anti-alucinación de entidades)

| | |
|---|---|
| **Patrón conceptual** | Set de tokens permitidos extraído pre-LLM solo de turnos del usuario + vocabulario del dominio; validación post-LLM contra el set; fallback a raw query si over-stripping |
| **Inventario llull** | Item 5.9 (nuevo) |
| **Adaptaciones críticas** | (a) Vocabularios geo/métricas/dimensiones/locales **alimentados desde el spec por dominio**, no hardcodeados como literales en español dentro de Python (corrección directa del bug estructural que la auditoría señala); (b) `VocabularyRegistry` (10.8) como fuente de verdad; (c) por-locale, no español-only |
| **No portar** | Código directo de `logic/selectors/followup_resolver.py` ni los literales `_GEO_TERMS`, `_METRIC_TOKENS`, `_MONTHS` |

#### 4. SQL Execution Gateway con políticas R0–R3 tipadas

| | |
|---|---|
| **Patrón conceptual** | Chokepoint único de ejecución SQL con cuatro tiers de política (R0 absoluto, R1 core, R2 dominio, R3 observe-only) declarados en YAML versionado |
| **Inventario llull** | Item 2.10 (nuevo) |
| **Adaptaciones críticas** | (a) **Aserción del YAML en startup** — si está mal formado o no existe, el sistema no arranca (corrección directa del bug que la auditoría reporta: en LlullGen el código dice cargar `config/sql_policy.yaml` pero el archivo no existe y cae a hardcoded defaults silenciosamente); (b) políticas en `PolicyRegistry` (10.8) con versionado y owners; (c) integración con `LineageRecord` — toda query queda en `policies_evaluated` |
| **No portar** | Código directo de `tools/sql/sql_gateway.py` ni `config/sql_policy.yaml` |

#### 5. Sandbox executor de pandas (regex + AST whitelist + timeout + I/O caps)

| | |
|---|---|
| **Patrón conceptual** | Validación regex+AST de código pandas generado por LLM, ejecución con timeout y caps de filas |
| **Inventario llull** | **No incorporado en v4.** Queda como **opcional bajo demanda** en "Más allá" |
| **Justificación de no incorporación** | La arquitectura llull está deliberadamente diseñada para evitar que el LLM genere código de cálculo (las herramientas son deterministas: Monte Carlo, grid search, RAG, modelos predictivos como skills 4.3). El sandbox solo aplicaría si en algún momento un cliente demandara "análisis exploratorio ad-hoc sobre resultados de simulación", lo cual es señal explícita para activarlo |
| **Activación** | Cliente real que pida análisis ad-hoc post-decisional |

#### 6. Prompt capture infraestructura

| | |
|---|---|
| **Patrón conceptual** | Captura activable del prompt completo enviado a cada LLM con etiquetado por stage, formato legible para debugging |
| **Inventario llull** | Item 10.9 (nuevo) |
| **Adaptaciones** | (a) Captura como **exporter** del PromptRegistry (10.1), no como sistema independiente; el Registry es la fuente de verdad de los prompts, capture es cómo se materializaron en cada run con sus variables instanciadas; (b) integración con LineageRecord — cada prompt capturado se referencia por `prompt_version` y `run_id`; (c) export a Loki estructurado, no archivo plano |
| **No portar** | Código directo de `logic/llm/prompt_capture.py` |

#### 7. LlullLogger con `query_id` por contextvar

| | |
|---|---|
| **Patrón conceptual** | Logger con `query_id` propagado vía Python `contextvars`, captura de logs por query, exporter a backend centralizado |
| **Inventario llull** | Item 8.4 (ampliado) |
| **Adaptaciones** | (a) Sustituir OpenSearch por Loki (cloud-agnostic, alineado con item 11.8); (b) añadir `run_id`, `session_id`, `tenant_id` además de `query_id` para alinear con la nomenclatura RunEnvelope; (c) integración con OpenTelemetry (8.2) para que `run_id` sea también `trace_id` del span raíz |
| **No portar** | Código directo de `logger/llull_logger.py` ni `logger/opensearch_handler.py` |

#### 8. Taxonomía conceptual de las 4 arquitecturas objetivo (registries, lineage, evals)

| | |
|---|---|
| **Patrón conceptual** | Registries tipados con contrato común (`id · version · status · owners · changed_at · sunset_date · adr`); LineageRecord tipado por respuesta; Capability Graph tipado para multi-agente; golden eval con tres CI gates (routing/plan/response-shape) |
| **Inventario llull** | Items 10.8 (Registry pattern unificado), 10.10 (LineageRecord), 5.3.b (Capability Graph), 10.11 (Golden eval CI gates) |
| **Adaptaciones** | (a) Esto es taxonomía conceptual, no código existente. Se incorpora de las 4 arquitecturas **objetivo** de Alfred (que son specs, no implementaciones); (b) implementación propia tipada Pydantic + storage GitOps en `/governance/<registry>/<artifact>.yaml` |
| **No portar** | No aplica (no hay código LlullGen para estos conceptos — están solo en las arquitecturas objetivo) |

### Principios operativos de la política

Esta política se aplica con tres principios operativos no negociables:

**Principio 1 — Lectura del código de LlullGen como referencia, sí; copia, no.**

El architect y cualquier persona del equipo puede (y debe) leer el código de LlullGen para entender cómo el equipo resolvió cada problema, qué decisiones tomó, qué bugs encontró, qué edge cases descubrió. Esa lectura es valiosa. Lo que no se hace es copy-paste de bloques de código.

**Principio 2 — Cada componente se escribe con tests y documentación nuevos.**

No se hereda ni un test ni una línea de documentación de LlullGen. Cada componente nuevo en llull lleva su propia suite de tests escrita desde cero (con la golden eval harness 10.11 como gate de calidad) y su propia documentación interna. Esto previene heredar tests cosméticos o documentación obsoleta.

**Principio 3 — Adaptaciones críticas se ejecutan desde día 1.**

Las adaptaciones marcadas como "críticas" en el catálogo (vocabularios desde spec en GroundedTokens, aserción del YAML en startup en SQL Gateway, MemoryService boundary lint) **se implementan desde la primera versión** del componente en llull. No son refactor futuro — son condición de aceptación.

## Consecuencias

### Positivas

- **Velocidad de implementación razonable** sobre arquitectura limpia. Los componentes salen con calidad production-ready desde día 1 en llull.
- **Aprendizaje del equipo de LlullGen aprovechado** sin importar la deuda estructural de su entorno.
- **Defensa política sólida.** Cada conversación con el equipo de LlullGen sobre "por qué no usas mi código" tiene respuesta documentada en este ADR con razones técnicas concretas y reconocimiento explícito del valor conceptual.
- **Coherencia con ADR-002.** Si rechazamos el A2A custom de LlullGen como motor por sus limitaciones, esta ADR explica que el rechazo no es por desprecio del trabajo del equipo sino por análisis técnico componente por componente.
- **Tracking explícito de qué componente se reutilizó conceptualmente y cómo se adaptó.** Esto facilita el dialog con el equipo de LlullGen y deja trazabilidad para auditorías futuras.

### Negativas asumidas

- **Esfuerzo de reimplementación no trivial.** Especialmente para LLMFactory y ObjectBus, que son los componentes más complejos. Mitigación: el roadmap v4 los planifica con holgura realista.
- **Posible fricción inicial con el equipo de LlullGen** que vea la política como "no quieres usar mi código". Mitigación: este ADR documenta exhaustivamente el rationale técnico por componente. Cualquier discusión parte de este documento, no de cero.
- **Riesgo de "redescubrir" bugs** que el equipo de LlullGen ya resolvió. Mitigación: principio 1 — leer el código de LlullGen como referencia es parte del proceso, no opcional.

### Neutras / a monitorizar

- **Casos en que la adaptación crítica revele que el patrón conceptual no es trasladable** y haya que diseñar from-scratch. Si esto ocurre con frecuencia, revisar este ADR. Hipótesis: ocurrirá con 0–1 de los 7 componentes catalogados.
- **Aparición de nuevos componentes rescatables en LlullGen** a medida que ese MVP evolucione. Cada nuevo candidato se evalúa por la misma matriz (patrón conceptual / item llull / adaptaciones / no portar) y se añade al catálogo de este ADR como amendment.

## Items del inventario afectados

Esta política condiciona la implementación de los siguientes items, que tienen "inspiración LlullGen + adaptaciones críticas" como contrato implícito:

- **1.6** ObjectBus de tres niveles
- **2.10** SQL Execution Gateway con políticas tipadas
- **5.6** LLMFactory con multi-proveedor + budget guard + context-budget pre-flight
- **5.9** GroundedTokens — guardrail anti-alucinación de entidades
- **8.4** Logging centralizado con propagación de run_id por contextvar
- **10.9** Prompt capture infraestructura

Y condiciona también, indirectamente, los items que dependen de los anteriores: 5.10 (memoria activa, depende del ObjectBus), 5.11 (MemoryService, hereda lecciones del fallo de boundary en LlullGen), 8.7.b–d (control de gasto, sobre LLMFactory), 10.10 (LineageRecord, sobre prompt capture y registries).

## Referencias

- **Auditorías del CEO sobre LlullGen** (las 4 PDF):
  - `Codebase_Review__Architecture_Audit.pdf` — puntuación 2.05/5, 28 dimensiones, 16 capacidades faltantes.
  - `AI___Agent_Layer_Audit.pdf` — puntuación 2.65/5, gaps documentados en A2A custom y control de gasto.
  - `Conversational_and_Analytical_Memory_System_Audit.pdf` — puntuación 1.5/5, fragmentación de memoria, GroundedTokens identificado como pieza arquitectónicamente correcta.
  - `Ontology__Semantic_Knowledge_Layer_Audit.pdf` — puntuación 1.8/5, scaffold parcial, bug del YAML que no existe en disco.
- **Arquitecturas objetivo de Alfred** (las 4 HTML):
  - `LlullGen___Target_AI___Agent_Layer_Architecture.html` — Capability Graph, RunEnvelope, BudgetGuard.
  - `LlullGen___Target_Codebase_Governance_Architecture.html` — registries tipados, lineage, governance unificada.
  - `LlullGen___Target_Conversational___Analytical_Memory_Architecture.html` — ActiveAnalyticalState, MemoryService como única seam.
  - `LlullGen___Target_Ontology___Semantic_Knowledge_Architecture.html` — Metric/Dimension/Entity/Vocabulary registries.
- ADR-002 — LangGraph como motor de orquestación (para el rechazo del A2A custom como motor).
- Inventario llull v4 — todos los items listados en sección "Items afectados".
- Roadmap llull v4 — Cadenas 8 (ObjectBus), 9 (Control de gasto), 10 (Multi-agente con governance), 11 (Governance unificada y lineage).

## Revisión

Esta política se revisa cuando:

- Aparezca un nuevo componente rescatable en LlullGen (se añade al catálogo como amendment).
- La implementación real de uno de los componentes catalogados revele que el patrón conceptual no es trasladable y requiera diseño from-scratch.
- El equipo técnico actual de LlullGen proponga formalmente reutilización directa de código y aporte argumentos técnicos no contemplados en este ADR.
- Auditorías futuras de LlullGen modifiquen sustancialmente el diagnóstico sobre alguno de los componentes catalogados.

Fuera de estos disparadores, la política se considera estable.
