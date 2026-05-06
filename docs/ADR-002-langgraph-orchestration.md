# ADR-002 — LangGraph como motor de orquestación de la plataforma llull

| Campo | Valor |
|---|---|
| **Estado** | Aceptada |
| **Fecha** | 2026-05-05 |
| **Autor** | Gustavo Mateos (Architect) |
| **Decisores** | Architect (autor), CEO Inverence (revisión) |
| **Supersede** | — |
| **Superseded by** | — |
| **Relacionada con** | ADR-001 (pgvector vs Qdrant), ADR-003 (reutilización LlullGen) |

---

## Contexto

La plataforma llull es un sistema agentic de decision intelligence cuyo prototipo actual (Decision Intelligence Agent) está construido sobre LangGraph con un grafo de tres nodos (planner → tool → synthesizer) y checkpointing en SQLite. El roadmap v4 proyecta evolución hacia un Bloque A multi-agente (Orchestrator coordinando Decision Agent + Dashboard Agent + sub-agentes adicionales bajo demanda — Alert, Report, Action) — items 5.3.a, 5.3.b, 5.3.c del inventario.

Necesitamos declarar formalmente qué motor de orquestación usa llull en su evolución multi-agente, por tres razones:

1. **Técnica.** La elección condiciona items concretos del roadmap: 5.3.a (MVP Bloque A), 5.3.b (capability graph), 5.4 (agentes async como tool), 5.12 (recursion guard), 8.7.e (budgets por peer), y la forma de implementar los registries del 10.8.

2. **Diferencial vs LlullGen.** El equipo técnico actual de Inverence ha desarrollado en LlullGen un message bus custom etiquetado internamente como "A2A" (~900 LOC entre `bus.py`, `channel.py`, `dispatcher.py`, `mailbox.py`, `null_channel.py`). La auditoría que el propio CEO ha hecho sobre el AI Layer de LlullGen reporta limitaciones estructurales serias en este bus, y existe la posibilidad de que se proponga generalizarlo como motor de la plataforma llull. Conviene que la decisión quede registrada con su rationale antes de que llegue esa propuesta, no después.

3. **Política.** Esta decisión documentada blinda al architect frente a reescrituras posteriores motivadas por preferencias del equipo existente, y proporciona un argumento técnico consistente para las conversaciones que vendrán.

## Opciones consideradas

Cinco opciones, evaluadas explícitamente:

### Opción A — LangGraph (con `langgraph-supervisor` para multi-agente) [DECISIÓN]

Framework de orquestación basado en grafos dirigidos tipados, parte del ecosistema LangChain. Soporte nativo para checkpointing (`AsyncPostgresSaver`, `AsyncSqliteSaver`), structured outputs Pydantic, y tres patrones multi-agente con primitivas oficiales: Supervisor (`langgraph-supervisor`), Swarm (`langgraph-swarm`) y Network (con `Command` directamente).

**Versión actual del prototipo**: LangGraph ya en uso para el grafo del Decision Intelligence Agent. La evolución a multi-agente es aditiva, no sustitutiva.

### Opción B — Sustituir LangGraph por A2A custom de LlullGen

Adoptar el message bus interno de LlullGen como motor de orquestación de llull. La decisión implicaría reescribir el grafo del prototipo como serie de agentes con mailbox + dispatcher.

### Opción C — AutoGen / AG2

Framework multi-agente de Microsoft Research. Versión v0.4+ rearquitectada con event-driven core, async-first, GroupChat como patrón primario de coordinación.

### Opción D — CrewAI

Framework role-based donde agentes se organizan como "crew" con tareas. Strong en el patrón Supervisor-Worker via metáfora crew/task.

### Opción E — OpenAI Agents SDK (con A2A protocol de Google ADK como capa de federación)

SDK nativo de OpenAI con primitivas Handoff, locked al ecosistema OpenAI. El A2A protocol de Google ADK (no confundir con el A2A custom de LlullGen) es un estándar abierto reciente para que agentes de frameworks distintos se comuniquen.

## Criterios de evaluación

| Criterio | Peso | Razón |
|---|---|---|
| Continuidad con prototipo | Alto | El prototipo ya usa LangGraph; cambiar significa reescribir el núcleo funcional ya validado |
| Patrones multi-agente nativos | Alto | El Bloque A necesita Supervisor desde día 1 y debe poder graduar a Swarm si la latencia lo justifica |
| Trazabilidad y auditoría | Crítico | llull va a sectores regulados (banca, salud, AAPP); cada handoff debe ser un span trazable |
| Checkpointing en Postgres | Crítico | Inventario item 1.1; condición necesaria para multi-tenancy |
| Recursion guards y depth limits | Alto | Inventario item 5.12; previene runaway runs en multi-agente |
| Madurez y comunidad | Medio | Determina velocidad de resolución de bugs, calidad de docs, disponibilidad de patrones |
| Federación con agentes externos | Bajo (hoy), creciente | A medio plazo llull puede necesitar hablar con agentes externos via estándar |
| Lock-in al proveedor | Medio | Coherente con principio 3.7 portabilidad; evitar lock-in a un cloud o un proveedor de modelos |

## Análisis de las opciones

### Opción A — LangGraph + Supervisor pattern

**Ventajas:**

- **Continuidad total con el prototipo.** El Decision Agent del Bloque A es literalmente el grafo actual envuelto como sub-agente. Cero reescritura del núcleo funcional ya validado.
- **Tres patrones multi-agente nativos** (Supervisor, Swarm, Network) con primitivas oficiales. Permite empezar con Supervisor — el más simple, con routing accuracy más alto y debugging más fácil — y graduar a Swarm si datos de producción demuestran que la latencia es el cuello de botella. Es exactamente la recomendación consensuada del sector ("start with supervisor; graduate to swarm when measurement justifies").
- **`Command` objects tipados** para handoffs: `Command(goto=..., graph=Command.PARENT, update={...})`. El estado compartido es un Pydantic model con scope por agente. Esto permite implementar limpiamente el capability graph (5.3.b) como una tabla de declaraciones tipadas que el Supervisor consulta antes de cada handoff.
- **Checkpointing nativo** con `AsyncPostgresSaver` (alineado con item 1.1 del inventario). El estado se serializa a Postgres por turno, permitiendo recuperación tras fallo, replay de runs y trazabilidad por sesión.
- **LangSmith integrado.** Cada nodo del grafo y cada handoff entre agentes es un span. Esto convierte el debugging de un incidente multi-agente en algo que se ve, no algo que se imagina. Crítico para sectores regulados donde "explica por qué este cliente recibió esta recomendación" es una pregunta legal.
- **`recursion_limit` nativo** del runtime. Implementa el item 5.12 (recursion guard) con una sola línea de configuración. La auditoría AI Layer de LlullGen señala explícitamente la ausencia de recursion guards como gap.
- **Tooling maduro:** `create_react_agent`, `create_supervisor`, `create_swarm` están listos para usar. La curva de adopción es prácticamente cero para un equipo que ya conoce el framework.

**Desventajas:**

- **Acoplamiento al ecosistema LangChain.** Si LangChain tomara una dirección que no nos sirva, migrar tendría coste. Mitigación: el contrato externo de llull (API REST, capability graph, registries) es independiente del framework; LangGraph es un detalle de implementación encapsulado en el Agent Service (6.1.e).
- **El stack LangChain ha tenido reputación de inestabilidad de APIs en el pasado.** En 2026 el ecosistema está más estable, especialmente la rama `langgraph-*` que tiene política de versionado más conservadora que `langchain` core. Mitigación: pinear versiones en `requirements.txt`, evals automatizados en CI (10.11) detectan regresiones antes de merge.

### Opción B — A2A custom de LlullGen

**Análisis basado en la propia auditoría del CEO sobre el AI Layer de LlullGen:**

- **Capping en profundidad 1.** El dispatcher levanta `DispatchDepthExceeded` cuando un helper trata de pedir ayuda a un tercero. "Multi-agent" en LlullGen significa "primary + un helper", nada más. El Bloque A de llull requiere mínimo profundidad 2 (Orchestrator → Decision Agent → tools, y eventualmente Decision Agent → Dashboard Agent en cadena).
- **Helpers reconstruidos pierden contexto.** Cuando el dispatcher reconstruye un helper agent, pierde `conversation_history` y `previous_sql`. Resultado documentado en la auditoría: una pregunta follow-up "haz un chart de eso" puede generar SQL fresco diferente al de la query anterior. Es un bug estructural derivado del diseño, no un bug puntual reparable. Para llull esto es inaceptable: la coherencia entre Decision Agent y Dashboard Agent es el caso de uso central del Bloque A.
- **`AgentCapability.can_request_help_from`** está declarado en código pero no se lee en runtime. La governance del multi-agente es declarativa pero no aplicada — exactamente el problema que el capability graph (5.3.b) quiere resolver.
- **Sin recursion guard real.** La auditoría reporta como gap explícito.
- **Sin checkpointing nativo a Postgres.** Habría que construirlo.
- **Sin tooling de tracing.** Habría que construirlo.
- **No es estándar.** Es código interno de un MVP que internaliza decisiones específicas de su caso de uso (text-to-SQL/BI). Adoptar este código como motor de la plataforma llull significaría heredar sus limitaciones estructurales y la deuda técnica documentada.

**Conclusión:** la auditoría del propio CEO documenta que este componente necesitaría rediseño de cero para soportar multi-agente real. Adoptarlo no es reutilización — es asumir un proyecto de reescritura mayor con menor calidad esperada que LangGraph.

**Aclaración terminológica importante:** el "A2A" de LlullGen comparte sigla por casualidad con el A2A protocol de Google ADK, que sí es un estándar abierto. Son cosas distintas. El A2A protocol de Google se considera en la opción E como capa de federación, no como motor de orquestación.

### Opción C — AutoGen / AG2

**Ventajas:** strong en patrones de debate y group chat, async-first, pluggable orchestration strategies.

**Desventajas:**

- **Reescritura completa del prototipo.** El grafo actual no se traduce a la metáfora de conversación de AutoGen sin reescribir el núcleo.
- **Patrón GroupChat es Swarm, no Supervisor.** Para llull queremos empezar con Supervisor (routing accuracy alto, trazabilidad determinista), no con conversación abierta entre agentes.
- **Menor madurez de checkpointing a Postgres** comparado con LangGraph.
- **Curva de adopción no nula** para un equipo que ya domina LangGraph.

### Opción D — CrewAI

**Ventajas:** abstracción role-based atractiva conceptualmente, popular para prototipos rápidos.

**Desventajas (consenso del sector):**

- **Sin checkpointing nativo para workflows largos.** Bloqueante para la persistencia de sesiones multi-tenant que llull necesita.
- **Control limitado sobre comunicación agente-a-agente** (mediada por task outputs, no direct messaging).
- **Error handling coarse-grained.**
- Equipos que empiezan con CrewAI suelen migrar a LangGraph cuando necesitan production-grade state management. Adoptarla sería plantar deuda de migración futura.

### Opción E — OpenAI Agents SDK + A2A protocol de Google ADK

**Ventajas:** primitivas multi-agente nativas en SDK de OpenAI, A2A protocol como estándar abierto de federación cross-framework.

**Desventajas:**

- **Lock-in a OpenAI** para el SDK (sin TypeScript oficial, locked a modelos OpenAI). Contradice directamente el principio 3.7 (portabilidad) y el item 5.6 (LLMFactory multi-proveedor).
- **El handoff pattern se vuelve unwieldy con más de 8-10 tipos de agente** según la propia documentación. llull a medio plazo va precisamente en esa dirección.
- El **A2A protocol de Google ADK** es interesante pero sirve para **federación con agentes externos** — no como motor interno. Es complementario, no alternativa.

## Decisión

**Adoptamos LangGraph como motor de orquestación de la plataforma llull, con patrón Supervisor de `langgraph-supervisor` para el Bloque A multi-agente.**

Detalles operativos:

- **Patrón inicial: Supervisor.** Un nodo orquestador central enruta a sub-agentes especializados con structured output Pydantic. Routing accuracy alto, debugging fácil, alineado con la disciplina de gobernanza (capability graph + budgets).
- **Graduación a Swarm o Network solo bajo evidencia empírica** de que (a) la latencia del Supervisor es el cuello de botella documentado, (b) los agentes raramente fallan en routing, y (c) el caso de uso requiere flujos no predecibles. La transición se evalúa con datos reales de producción, no por preferencia estética.
- **Estado compartido mediante `AgentState` Pydantic** propagado por el grafo. Cada agente declara qué slots del estado puede leer/escribir; el `MemoryService` (item 5.11) es la única seam que muta el `ActiveAnalyticalState` (item 5.10).
- **Checkpointing con `AsyncPostgresSaver`** sobre la base de datos del item 1.1.
- **LangSmith para tracing** en desarrollo y staging. En producción, exportar spans a OpenTelemetry → Loki/Prometheus (items 8.2, 8.4) para no depender exclusivamente de LangSmith en cliente regulado.
- **A2A protocol de Google ADK queda en evaluación** como capa de federación con agentes externos en futuro. No es motor interno. Cuando aparezca un caso de uso real (un cliente que quiera invocar agentes de llull desde su propio agente Vertex AI, por ejemplo), se evalúa adopción incremental compatible con LangGraph internamente.

## Consecuencias

### Positivas

- **Continuidad total con el prototipo.** Cero reescritura del núcleo funcional ya validado en demos.
- **Decisión 5.3 del inventario queda implementable directamente.** El item 5.3.a (MVP Bloque A) se construye con `create_supervisor` + dos agentes envueltos. Plazo realista: 2-3 semanas de trabajo concentrado.
- **Item 5.12 (recursion guard) se reduce a configurar `recursion_limit`** del runtime, más una capa propia que registre el incidente y devuelva respuesta degradada.
- **Capability graph (5.3.b) se implementa como Pydantic model** consultado por el Supervisor antes de cada handoff. Lookup table en Postgres, hot-reloadable.
- **Trazabilidad regulatoria** habilitada nativamente vía LangSmith spans + OpenTelemetry export. Habilita item 10.10 (LineageRecord).
- **Skills horizontales del equipo crecen sobre tecnología reconocible.** Cualquier desarrollador con experiencia LangGraph entra al proyecto sin curva inicial.

### Negativas asumidas

- **Acoplamiento al ecosistema LangChain.** Si LangChain tomara una dirección que no nos sirva, hay coste de migración. Mitigación documentada en sección "Análisis".
- **La opción de adoptar el A2A custom de LlullGen** queda explícitamente descartada. Esto puede generar fricción con el equipo técnico actual, que invirtió esfuerzo significativo en construirlo. Mitigación: este ADR documenta el rationale técnico de forma exhaustiva y referenciable; cualquier discusión futura puede partir de aquí en lugar de empezar de cero.
- **Si en el futuro emerge un estándar dominante de orquestación multi-agente** distinto a LangGraph, habrá que evaluar migración. Mitigación: el contrato externo de llull (API, capability graph, registries) es framework-agnostic; el motor de orquestación es un detalle interno encapsulado en el Agent Service (6.1.e), reemplazable sin afectar al resto del sistema.

### Neutras / a monitorizar

- **Performance de LangGraph con `AsyncPostgresSaver` bajo concurrencia alta** debe medirse en I2A piloto. Si aparece contención, item 1.4 (Redis para memoria caliente) entra en juego antes de lo previsto.
- **Política de versionado de `langgraph-*`.** Pinear versiones en `requirements.txt` y revisar minor updates como parte del ciclo de actualización de dependencias.

## Items del inventario afectados

Esta decisión condiciona la implementación de los siguientes items:

- **5.3.a, 5.3.b, 5.3.c** — Bloque A multi-agente, todas las sub-features
- **5.4** — Agentes async como tool del grafo (patrón nativo de LangGraph: tool que devuelve `Command` con `goto` a un nodo async)
- **5.10, 5.11** — Memoria activa tipada y MemoryService (se integran como nodes/protocols del grafo)
- **5.12** — Recursion guard y depth limits
- **6.1.e** — Agent Service (encapsula LangGraph internamente)
- **8.7.e** — Budgets por capability/peer (consultados por el Supervisor antes de cada handoff)

## Referencias

- Auditoría AI/Agent Layer de LlullGen — `AI _ Agent Layer Audit.pdf` (gaps documentados sobre A2A custom).
- AI/Agent Architecture target — `LlullGen___Target_AI___Agent_Layer_Architecture.html` (conceptos de Capability Graph, RunEnvelope, BudgetGuard adaptados a llull).
- LangGraph multi-agent patterns: documentación oficial de `langgraph-supervisor` y `langgraph-swarm`.
- "Agent Architecture Patterns: 2026 Taxonomy" — referencia del consenso del sector sobre Supervisor-first.
- Inventario llull v4 — items 5.3.a/b/c, 5.4, 5.10, 5.11, 5.12, 6.1.e, 8.7.e.
- Roadmap llull v4 — Cadenas de dependencia 8 (ObjectBus → memoria → multi-agente) y 10 (Multi-agente con governance).

## Revisión

Esta decisión se revisa cuando:

- El equipo arquitectónico considere que datos de producción justifican graduación de Supervisor a Swarm o Network.
- Aparezca un estándar dominante de orquestación multi-agente con suficiente madurez para justificar evaluación de migración.
- El A2A protocol de Google ADK madure al punto de ser candidato de capa de federación con agentes externos.
- LangChain/LangGraph cambie significativamente su política de versionado, pricing, o licencia.

Fuera de estos disparadores, la decisión se considera estable.
