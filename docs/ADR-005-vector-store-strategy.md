# ADR-004 — Vector store strategy for the enterprise multi-agent platform

| Campo | Valor |
|---|---|
| **Estado** | Aceptada |
| **Fecha** | 2026-05-06 |
| **Autor** | Gustavo Mateos (Architect) |
| **Decisores** | Architect (autor), CEO Inverence (revisión) |
| **Supersede** | **ADR-001 (pgvector over Qdrant for vector search)** |
| **Superseded by** | — |
| **Relacionada con** | ADR-002 (LangGraph orquestación), ADR-003 (reutilización LlullGen) |

---

## Context

ADR-001 (2026-04-23) decidió **pgvector sobre Qdrant** para la búsqueda vectorial, con FAISS como fallback offline. La decisión estaba bien razonada para las premisas declaradas en abril 2026: "few hundred to few thousand documents", "moderate accuracy requirements", "no filtering beyond category", "batch-built index", "single agent". Todas esas premisas describen un **prototipo**.

Cuatro circunstancias modifican fundamentalmente el contexto:

1. **El objetivo del proyecto ha cambiado.** El producto no es ya un prototipo single-agent text-to-query. Es la **plataforma llull**: arquitectura multi-agente IA-nativa para asistencia a la toma de decisiones de negocio, dirigida a sectores regulados (banca, salud, AAPP, retail enterprise). El roadmap v4 lo refleja en cuatro iteraciones: I1 fundación productiva, I2A datos reales + memoria activa + control de gasto, I2B apertura enterprise (multi-tenancy, SSO, audit log, cifrado), I3 producto diferencial (Bloque A multi-agente con governance, registries unificados, LineageRecord tipado).

2. **La carga vectorial esperada es de otro orden de magnitud.** Clientes objetivo como Quirón Hospitales (millones de documentos clínicos, protocolos, historiales), BBVA (documentación regulatoria, contratos, normativa), AAPP (expedientes, normativa, jurisprudencia) sitúan a cada cliente individual en el rango de millones a decenas de millones de vectores. El umbral original del ADR-001 ("not near millions of vectors threshold") ha dejado de ser una premisa estable; es ahora el caso base, no el caso extremo.

3. **Multi-tenancy con aislamiento estricto es requisito contractual**, no opcional. Inventario item 7.1 (Multi-tenancy con RLS), 7.5 (SSO), 7.6 (cifrado en tránsito y en reposo), 7.7 (Vault), 7.8 (audit log append-only) — todos en I2B — convierten en condición de aceptación lo que en abril 2026 era "no en alcance".

4. **El estado del arte de bases vectoriales ha cambiado.** Tres novedades técnicas que el ADR-001 no podía considerar:
   - **`pgvectorscale`** (Timescale, OSS PostgreSQL License, Rust core): extensión que complementa pgvector con un índice `StreamingDiskANN` con streaming filtering nativo. Benchmark Timescale a 50M vectores Cohere 768d: 28× mejor p95 latency y 16× más throughput que Pinecone s1 a 99% recall, dentro de Postgres.
   - **Qdrant 1.16 Tiered Multitenancy** (nov 2025): combina payload-based + shard-based en una colección, con promoción de tenant sin downtime. Flag `is_tenant=true` crea per-tenant HNSW segments. SSO + RBAC + API keys nativos. Considerado por el sector como el "graduated from pgvector" default para 2026 en agent-native retrieval.
   - **pgvector 0.7+**: HNSW estable (ya no beta como en abril 2026). Gap de rendimiento con motores dedicados drásticamente reducido.

Este ADR re-examina la decisión bajo las premisas correctas y produce una decisión nueva, no una continuación.

## Options considered

### Option A — pgvector + pgvectorscale (evolution of ADR-001) [DECISIÓN]

Mantener Postgres como única DB de persistencia. **Añadir la extensión `pgvectorscale`** sobre el pgvector existente. Mantener FAISS como fallback solo en desarrollo local sin Docker. Multi-tenancy vía RLS (item 7.1) sobre la tabla `knowledge_documents`.

### Option B — Qdrant como primary, pgvector como fallback offline

Reemplazar pgvector por Qdrant en producción. Mantener pgvector para desarrollo local. Sincronizar embeddings entre transactional DB (Postgres) y vector DB (Qdrant) vía eventos.

### Option C — Híbrido: pgvector+pgvectorscale para transaccional-vectorial + Qdrant para knowledge base masivo

Cada herramienta donde brilla. pgvector+pgvectorscale para datos vectoriales que viven al lado de datos transaccionales (memoria conversacional, ObjectBus, ActiveAnalyticalState, lineage). Qdrant para el knowledge base de gran volumen multi-tenant (documentos de cliente, normativa, protocolos clínicos).

### Option D — Pinecone (managed cloud, descartada de plano)

Considerada y descartada por el architect previamente. Vendor lock-in en infraestructura crítica de IA durante el ciclo de vida esperado del producto (10-20 años en sectores regulados) es un riesgo estratégico que no compensa con la ventaja operacional. Esta decisión no se re-abre en este ADR.

### Option E — Weaviate (managed open-source con GraphQL)

Considerada. Tiene hybrid search nativo, multi-tenancy y schemas tipados. **Descartada por** (i) overhead GraphQL sobre REST que el resto del stack llull asume, (ii) latencia 50-70ms vs 30-40ms de Qdrant a la misma carga, (iii) mayor complejidad operacional (Go runtime, módulos de vectorización opcionales que añaden superficie). No descalifica Weaviate como buen producto; sí no es la mejor opción para llull dada la arquitectura adoptada en ADR-002.

## Evaluation criteria

| Criterio | Peso | Razón |
|---|---|---|
| Operational simplicity | Alto | El equipo de Inverence es pequeño; cada componente operacional adicional es coste fijo permanente. |
| Performance at scale | Crítico | Multi-agente concurrent reads exige latencia p95 < 50ms hasta 50M vectores. |
| Multi-tenant isolation | Crítico | Sectores regulados: HIPAA, GDPR, banca, AAPP. Aislamiento contractualmente verificable. |
| Streaming filter performance | Alto | Cada query lleva 3-5 filtros estrictos (tenant + dominio + categoría + tipo + fecha). |
| Hybrid search (dense + sparse) | Medio | Útil pero no crítico para llull v1 (la búsqueda principal es semántica sobre conocimiento curado). Sí crítico para v2 cuando entren documentos crudos. |
| Open source / anti-lock-in | Alto | Coherente con principio 3.7 (portabilidad) del inventario y con el rechazo previo de Pinecone. |
| Transactional consistency | Alto | Memoria activa, lineage, cost ledger, audit log — todos en Postgres. Embeddings junto con metadata en la misma transacción simplifica enormemente la consistencia. |
| Update frequency tolerance | Alto | ObjectBus, ActiveAnalyticalState, memoria conversacional implican upserts continuos. |
| Backup / recovery uniform | Medio | Una DB → un proceso de backup. Dos DBs → coordinación de RPO/RTO entre dos sistemas. |
| Team learning curve | Medio | El equipo conoce Postgres. Aprender Qdrant es real (no infinito, pero real). |

## Analysis

### Option A — pgvector + pgvectorscale (DECISIÓN)

**Ventajas:**

- **Postgres como única DB stateful.** Continuidad total con I1 (item 1.1 PostgreSQL ya implementado). Cero servicio adicional que provisionar, monitorizar, hacer backup, integrar con SSO, parchar.
- **`pgvectorscale` aporta el rendimiento que faltaba.** El argumento R3 del ADR-001 ("sufficient performance at the document volumes in scope") tenía un techo de ~1M vectores con `ivfflat`. Con pgvectorscale el techo sube a 50M+ con `StreamingDiskANN` (benchmark Timescale 28× lower p95, 16× higher QPS vs Pinecone s1 a 99% recall en 50M vectores 768d). Esto cubre **todo el horizonte planificado** de I1 a I3.
- **Streaming filtering nativo.** `StreamingDiskANN` está diseñado para mantener accurate retrieval cuando se aplican filtros secundarios durante similarity search — exactamente el patrón de llull multi-tenant (filtros por tenant + dominio + categoría + fecha en cada query).
- **Multi-tenancy vía RLS** alineado con item 7.1. Postgres RLS es un mecanismo maduro, deny-by-default cuando se habilita, enforced a nivel de la query optimizer. Para enterprise customers que requieran physical isolation (schema-per-tenant o database-per-tenant), Postgres soporta ambos patrones nativamente — la decisión de tier se mueve a item 7.1 sin afectar a este ADR.
- **Transacciones unificadas.** Insertar un documento de cliente y su embedding en la misma transacción ACID, junto con su row de lineage (item 10.10) y su entry en cost ledger (item 8.7.f), es trivial. Con Qdrant esto requiere eventual consistency entre dos sistemas.
- **Tooling reuse total.** SQLAlchemy + Alembic + `get_session()` ya existentes funcionan tal cual. La instalación de pgvectorscale es `CREATE EXTENSION vectorscale CASCADE`. La query es `ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :k` con `WHERE tenant_id = current_setting('app.tenant_id')` (RLS). Cero código nuevo de cliente.
- **OSS PostgreSQL License**, sin vendor lock-in. Mismo principio que justificó el rechazo de Pinecone.
- **Backup unificado**: el dump de Postgres incluye los embeddings. Los embeddings nunca están "fuera" de la DB transaccional.
- **Coherencia con audit baseline 2026-05-06**: la dimensión #4 (Modularidad) y #15 (Security posture) del audit puntúan mejor con una sola DB stateful que con dos.

**Desventajas asumidas:**

- **Techo a 50M vectores por tenant individual** (con pgvectorscale tuneado). Por encima de esto, considerar Option C (híbrido) o migrar ese tenant específico a Qdrant. El umbral nuevo es 50× el del ADR-001 original.
- **No hybrid search nativo dense+sparse** como Qdrant 1.16. Postgres soporta `tsvector` para sparse, combinable con pgvector en una query, pero no es el patrón "primary" de la BD. **Mitigación**: para v1 de llull la búsqueda principal es semántica sobre conocimiento curado; cuando entren documentos crudos en gran volumen, re-evaluar.
- **Multi-tenancy con noisy neighbor** si un tenant gigante consume recursos del shared pool. **Mitigación**: el patrón híbrido que el sector recomienda (RLS para SMB, schema-per-tenant para enterprise, database-per-tenant para regulated strict) está soportado nativamente por Postgres y planificado en item 7.1.
- **Sin per-tenant HNSW segments** como Qdrant 1.16 `is_tenant=true`. **Mitigación**: el índice DiskANN de pgvectorscale es eficiente con filtros gracias al streaming filtering; no es "per-tenant graph" pero el efecto en latencia es comparable hasta el umbral de 50M.

### Option B — Qdrant como primary (rechazada)

**Ventajas:** Tiered Multitenancy nativa con per-tenant HNSW segments, hybrid search dense+sparse nativo, Rust core con latencias 10-25% mejores en open source, SSO + RBAC + API keys + Terraform Cloud API nativos. Es genuinamente excelente para los casos que va a cubrir.

**Por qué se rechaza ahora:**

- **Dobla la superficie operacional permanentemente** sin necesidad inmediata. El argumento R1 del ADR-001 sigue aplicando, y aún con más fuerza: cuando el equipo es pequeño y el roadmap está mid-execution, sumar un servicio stateful nuevo es coste fijo que no se recupera fácilmente.
- **Eventual consistency entre dos DBs.** Cada operación que toca datos transaccionales y vectoriales (insertar documento + embedding, registrar lineage con su embedding referenciado, escribir cost ledger asociado a una similarity search) deja de ser una transacción ACID. Para sectores regulados con auditoría unificada, esto es un coste real.
- **Beneficios marginales hasta los 50M vectores.** Los benchmarks que justifican Qdrant sobre pgvector son a 100M+ o cuando hay un patrón claro de "muchos tenants pequeños + un par de tenants gigantes" que llull no tendrá hasta I3+.
- **No resuelve un problema que tengamos hoy.** El problema real del audit baseline en el layer Memory (1.27/5) no es la BD vectorial — es la ausencia de `ActiveAnalyticalState` (item 5.10), `MemoryService` (5.11), `GroundedTokens` (5.9). Ningún componente vectorial cambia esos scores.

### Option C — Híbrido pgvector+pgvectorscale + Qdrant (parking)

**Ventajas:** cada motor donde brilla. pgvectorscale para transaccional-vectorial; Qdrant para knowledge base masivo multi-tenant.

**Por qué se parking, no se descarta:**

- **Complejidad operacional × 2.** Dos sistemas stateful, dos backup strategies, dos patrones de RBAC, dos modelos de multi-tenancy a alinear, dos SDKs.
- **Sincronización embedding-source es no trivial.** Cuando cambia el modelo de embedding, hay que re-indexar en dos sitios.
- **Sin caso de uso real todavía.** Llegar a Option C tiene sentido cuando se cumplan los **criterios disparadores** (sección "Migration triggers" abajo). Antes de eso, es complejidad sin payoff.

**Cuando se reconsidera:** la sección "Migration triggers" lo formaliza.

## Decision

**Adoptamos Option A: pgvector + pgvectorscale como vector store unificado de la plataforma llull, sobre la misma instancia PostgreSQL ya operada para todos los datos transaccionales y de estado.**

Detalles operativos:

- **Instalación**: `CREATE EXTENSION vector CASCADE; CREATE EXTENSION vectorscale CASCADE;` en la migración de Alembic correspondiente. Reemplaza el actual `pgvector` solo.
- **Índice**: `CREATE INDEX <name> ON <table> USING diskann (embedding vector_cosine_ops);` reemplaza el `ivfflat` actual.
- **Dimensión**: mantener `vector(1536)` para compatibilidad con OpenAI ada-002 (knowledge base actual). Soportar también `vector(3072)` para OpenAI text-embedding-3-large cuando se promueva. La elección del modelo vive en `ModelRegistry` (item 10.8), no aquí.
- **Multi-tenancy** vía RLS sobre `knowledge_documents` y futuras tablas vectoriales. Coordinado con item 7.1. Para clientes que requieran physical isolation, schema-per-tenant es la siguiente capa, dentro de Postgres.
- **FAISS** se mantiene únicamente como fallback offline en desarrollo local sin Docker (cuando `DATABASE_URL` no está set). La nota de seguridad de `allow_dangerous_deserialization=True` (audit baseline finding 6.6) se documenta inline en el código y aplica solo a este modo dev.
- **Embeddings concurrentes**: los upserts continuos de `ActiveAnalyticalState` y `ObjectBus` se benefician del modelo MVCC de Postgres sin configuración adicional. pgvectorscale soporta upserts vivos sin reindex completo.
- **Cost lineage**: cada similarity search se registra en el cost ledger (item 8.7.f) con `embedding_model_version`, `tenant_id`, `latency_ms`, `result_count`. Esto vive en la misma transacción que la search, dentro de Postgres.

## Migration triggers (cuándo este ADR se re-abre)

Esta decisión es estable hasta que ocurra cualquiera de estos disparadores objetivos. La aparición de cualquiera de ellos NO implica migración inmediata — implica abrir formalmente la evaluación de Option C (híbrido) o, en casos extremos, Option B (Qdrant primary).

1. **Volumen.** Un tenant individual supera **50 millones de vectores** en su memoria semántica + knowledge base + ObjectBus combinados. Medido por `SELECT count(*) FROM knowledge_documents WHERE tenant_id = ?` y agregados equivalentes.
2. **Latencia.** Latencia p95 de similarity search con pgvectorscale tuneado (DiskANN parámetros optimizados, statement_timeout adecuado, work_mem ajustado) supera **50ms consistentemente** durante 30 días en producción para cualquier tenant productivo.
3. **Isolation contractual.** Un cliente regulado en negociación requiere **shard-based physical isolation que RLS no satisfaga contractualmente** (HIPAA strict + business associate agreement, FedRAMP High, sectores con auditoría externa que mandate physical separation). En este caso, la primera opción a explorar es schema-per-tenant o database-per-tenant **dentro de Postgres**; Qdrant solo si esos patrones no cumplen el requisito.
4. **Tiered multitenancy operacional.** El patrón "thousands de tenants SMB + dozens de tenants enterprise gigantes" en el mismo cluster es operacionalmente justificable y RLS shared no escala. Qdrant Tiered Multitenancy diseñada exactamente para esto.
5. **Hybrid search dense+sparse a escala.** v2+ de llull con ingesta de documentos crudos del cliente requiere hybrid search nativo en gran volumen donde pgvector + tsvector combinados muestran latencia o complejidad inaceptable.

Cualquier disparador requiere un ADR nuevo con la evaluación específica de su caso. Este ADR no autoriza migración automática.

## Consequences

### Positivas

- **Continuidad total con el roadmap.** Item 1.2 (Capa vectorial sobre pgvector) en I1 se reformula como "Capa vectorial sobre pgvector + pgvectorscale" sin cambiar su iteración. Items 1.4, 1.6, 5.10, 5.11, 7.1, 8.7.f, 10.10 — todos consumidores potenciales de la capa vectorial — quedan sin cambios.
- **Audit score impact**: el findings 6.6 (FAISS `allow_dangerous_deserialization`) queda automáticamente mitigado al confinar FAISS a desarrollo local. Dimensión #4 (Modularity), #15 (Security posture) y #22 (Performance awareness) del audit baseline mejoran sin trabajo adicional. La dimensión #28 (Production-readiness) sube cuando pgvectorscale + RLS + el resto de items I2B aterricen.
- **Sin nuevo skill que aprender.** El equipo conoce Postgres. La curva pgvectorscale es de horas, no semanas.
- **Backup, monitoring, SSO, auditoría se hacen sobre un solo sistema.** Coherente con el principio de "un único stateful service" del ADR-001 que sigue siendo correcto.
- **Decisión defendible en review enterprise.** Cuando un cliente regulado pregunte "qué BD vectorial usáis", la respuesta "PostgreSQL con extensiones OSS" es trivial de auditar.

### Negativas asumidas

- **Cuando los disparadores se cumplan, la migración a Option C (híbrido) será trabajo real**, no trivial. Cada migration trigger fijado en este ADR pretende dar suficiente runway para que la migración se planifique con holgura, no que se haga.
- **Sin hybrid search dense+sparse nativo** hasta que se justifique. La combinación pgvector + tsvector con `ts_rank * (1 - cosine_distance)` funciona pero no es elegante.
- **El equipo no tendrá experiencia en Qdrant** si los disparadores tardan en cumplirse. Se mitiga con prueba de concepto periódica (cada 6 meses) de Qdrant en una rama, manteniendo el conocimiento operacional vivo.

### Neutras / a monitorizar

- **Roadmap de pgvectorscale**: extension joven (v0.x todavía en 2026). Monitorizar releases. Si Timescale cambia política de licenciamiento o deja de mantenerlo, se re-evalúa.
- **Embedding model dimension changes**: cuando se actualice de `vector(1536)` a `vector(3072)` el reindex es no trivial. Coordinar con `ModelRegistry` (10.8).
- **Performance real en producción**: el benchmark Timescale es laboratorio. La latencia real con multi-tenancy + RLS + cargas concurrentes de Bloque A multi-agente solo se conoce en producción. Monitorizar p95 desde el primer piloto.

## Items del inventario afectados

Esta decisión condiciona la implementación de los siguientes items:

- **1.2** Capa vectorial sobre pgvector → ahora "pgvector + pgvectorscale". Iteración sin cambio (I1).
- **1.3** Ruta a Qdrant documentada → este ADR es la documentación. Se mantiene como item del inventario apuntando a este ADR.
- **1.4** Redis para memoria caliente → no afectado, ortogonal.
- **1.6** ObjectBus de tres niveles → no afectado, ortogonal (ObjectBus no es vectorial).
- **5.9** GroundedTokens → no afectado, los vocabularios viven en `VocabularyRegistry` (estructurado), no como embeddings.
- **5.10** ActiveAnalyticalState → no afectado en este ADR; cuando se persista activelyparts de él para search semántico de turnos pasados, usará pgvector+pgvectorscale.
- **7.1** Multi-tenancy con RLS → confirma RLS sobre Postgres como mecanismo primary. Compatible directo con pgvectorscale.
- **7.6** Cifrado en tránsito y en reposo → aplica a Postgres como un todo, incluye los embeddings.
- **7.8** Audit log append-only → cada similarity search queda en la misma transacción que su audit entry.
- **8.7.f** Cost lineage por run → cada similarity search registra coste en mismo journal transaccional.
- **10.10** LineageRecord tipado → puede referenciar `embedding_version`, `index_name`, `result_ids` de la search sin cross-DB references.
- **11.1** Pipeline CI → debe tener un service container con Postgres + extensiones `vector` + `vectorscale` para los tests de integración.

## Audit baseline impact (commit `5d2adf5`, 2026-05-06)

Esta decisión modifica indirectamente las puntuaciones futuras de las siguientes dimensiones del audit baseline:

- Codebase #4 Modularity: la decisión refuerza la "single stateful service" pattern — futuro score esperado ≥ 4.
- Codebase #15 Security posture: con FAISS confinado a dev y RLS sobre pgvector+pgvectorscale, esta dimensión sube cuando items 7.x aterricen.
- Codebase #22 Performance awareness: pgvectorscale optimiza el item #22 sin trabajo adicional del equipo.
- Memory #13 Contextual retrieval: streaming filtering nativo facilita el item #13 cuando ActiveAnalyticalState (5.10) lo consuma.

El finding 6.6 del audit (FAISS `allow_dangerous_deserialization=True` sin comentario) queda **mitigado** por esta decisión: el flag aplica solo a desarrollo local, se documenta como tal en el código y nunca se ejecuta en producción.

## Referencias

- ADR-001 — pgvector over Qdrant for vector search (2026-04-23). Superseded por este ADR.
- Timescale, "PostgreSQL and Pgvector: Now Faster Than Pinecone, 75% Cheaper, and 100% Open Source" (feb 2025), métricas del benchmark 50M Cohere 768d.
- Qdrant blog, "Qdrant 1.16 — Tiered Multitenancy & Disk-Efficient Vector Search" (nov 2025).
- pgvectorscale GitHub: https://github.com/timescale/pgvectorscale
- Qdrant Multi-Tenancy documentation: https://qdrant.tech/articles/multitenancy/
- Inventario llull v4 — items 1.2, 1.3, 1.4, 1.6, 5.10, 7.1, 7.6, 7.8, 8.7.f, 10.10, 11.1.
- Audit baseline 2026-05-06 (commit `5d2adf5`) — finding 6.6.

## Revisión

Esta decisión se revisa cuando se cumpla cualquiera de los disparadores documentados en la sección "Migration triggers". Adicionalmente:

- Cada 6 meses, prueba de concepto interna de Qdrant en una rama de evaluación para mantener viva la experiencia operacional del equipo.
- Si pgvectorscale cambia de licencia o deja de ser mantenido activamente por Timescale, evaluación inmediata.
- Si el embedding model standard cambia y obliga a reindex masivo, reconsiderar si es la oportunidad de evaluar Option C.

Fuera de estos disparadores, la decisión se considera estable.
