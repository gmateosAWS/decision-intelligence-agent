# Inventario de mejoras y evolutivos de la plataforma llull (v4)

**Propósito del documento.** Consolidar en un único sitio todas las mejoras, evolutivos, features y decisiones técnicas que han ido apareciendo dispersas en los documentos de trabajo. No es un roadmap todavía — es el backlog de tareas o inventario completo sobre el que después se decidirá orden y prioridad.

**Cambios respecto a v3.** Esta versión incorpora el aprendizaje derivado del análisis de las 4 auditorías que el CEO de Inverence ha hecho sobre LlullGen (el MVP "text-to-query conversacional" del equipo actual) y de las 4 arquitecturas objetivo que él propone. El inventario integra ahora: (1) componentes técnicos reutilizables del codebase de LlullGen, identificados como "rescatables" y reimplantados aquí limpios; (2) la taxonomía conceptual que recorre las 4 arquitecturas objetivo (registries tipados, lineage, capability graph, evals con CI gates); (3) un control de gasto LLM mucho más completo y multi-dimensional, sustituyendo el control parcial de v3. Los items nuevos se marcan con la etiqueta `[v4]` al final del título para facilitar la lectura comparada con v3.

**Nomenclatura platforma llull vs LlullGen.** A partir de esta versión, "llull" o "plataforma llull" se refiere a nuestra plataforma global de decisión inteligente (la que encarna la visión "Decision Intelligence Architecture"), construida sobre el prototipo Decision Intelligence Agent. "LlullGen" se refiere al MVP "text-to-query conversacional" actualmente en desarrollo por el equipo técnico de Inverence, del que se reutilizan componentes específicos pero sobre el que la plataforma llull no se construye.

**Cómo leerlo.** Los items están agrupados por bloques temáticos emergentes, no por orden de ejecución. Cada item lleva una etiqueta de granularidad:

- `[parche]` — trabajo de horas o un día. Cambios locales, sin impacto arquitectónico.
- `[feature]` — trabajo de una a tres semanas. Piezas funcionales nuevas, bien acotadas.
- `[bloque]` — trabajo de más de un mes. Cambios estructurales que habilitan muchas cosas.

---

## 1. Persistencia y estado

Todo lo relacionado con dónde y cómo se guarda la información que el sistema necesita para funcionar: sesiones, runs, specs, conocimiento, memoria conversacional.

### 1.1 Migración de SQLite a PostgreSQL como núcleo de persistencia `[feature]` ✅ COMPLETADO

Reemplazar `SqliteSaver` por `AsyncPostgresSaver` para el checkpointing del grafo LangGraph, y mover la tabla `agent_sessions` y los logs JSONL de runs a tablas Postgres. La arquitectura del prototipo está diseñada para que este cambio sea prácticamente una línea en `checkpointer.py`, pero en la práctica implica también definir el esquema relacional completo (sesiones, runs, usuarios, dominios) y una primera iteración de migraciones.

_Resuelve:_ el prototipo no aguanta concurrencia real, no permite queries analíticas sobre runs históricos, y no sirve como base para multi-tenancy. Postgres es el punto de partida para todo lo demás en esta sección.

### 1.2 Capa vectorial sobre pgvector `[feature]` ✅ COMPLETADO

Reemplazar el índice FAISS local por la extensión `pgvector` de PostgreSQL. El knowledge layer pasa a ser una tabla más de Postgres, con filtros por metadata (tenant, dominio, categoría) como cláusulas WHERE. Elimina la necesidad de mantener un store separado y sincronizarlo con el resto del estado.

_Resuelve:_ FAISS local no soporta multi-tenancy, no tiene filtros nativos, no tiene replicación y no escala a miles de documentos por cliente. Para el volumen previsible del primer año de llull (decenas de miles de docs por cliente), pgvector es suficiente.

### 1.3 Ruta de migración a Qdrant identificada pero no ejecutada `[parche]` ✅ COMPLETADO

Documentar explícitamente en qué condiciones (volumen, latencia, features avanzadas como hybrid search) migraríamos el vector store a Qdrant. Tener el plan escrito no implica hacerlo — implica que cuando el síntoma aparezca, no hay que rediseñar desde cero.

_Resuelve:_ evita parálisis por análisis al elegir vector DB, y deja claro que pgvector es un punto de partida consciente, no una decisión permanente.

### 1.4 Redis como capa caliente para memoria de agentes `[feature]`

Separar la memoria del agente en dos capas: Redis para estado activo de sesiones vivas (checkpointing del grafo, últimos turnos, contexto en curso), y PostgreSQL para persistencia duradera y queries analíticas. Patrón cache-aside con flush asíncrono cuando la sesión expira o se cierra.

_Resuelve:_ cuando escale a cientos de sesiones concurrentes con turnos frecuentes, Postgres sufre por el patrón escritura-continua-de-blobs-pequeños + lecturas-muy-frecuentes. Es una optimización que se introduce cuando el síntoma aparece, no de entrada, pero la arquitectura lógica lo contempla desde el día 1.

### 1.5 Spec as data — el spec vive en base de datos `[feature]` ✅ COMPLETADO

El spec YAML deja de ser un fichero estático y pasa a ser un objeto de base de datos con historial de versiones, validación en tiempo real y edición programática desde la UI. Soporta versiones candidate/staging/production igual que un modelo, tiene diffs legibles entre versiones, y cada run del agente queda asociado a la versión exacta del spec con la que se ejecutó.

_Resuelve:_ sin esto no hay DAG builder visual (B.1), no hay onboarding de clientes nuevos sin reiniciar el servicio, y no hay trazabilidad real ("¿con qué versión del modelo de negocio recibió BBVA esta recomendación?"). Es habilitador de varios bloques estratégicos.

### 1.6 ObjectBus de tres niveles para artefactos de decisión `[feature] [v4]`

Almacén de objetos por sesión con tres niveles de persistencia: hot in-memory para resultados de turno activo, warm en Postgres (Parquet bytes) para artefactos recientes, cold con SQL-recompute o regeneración determinista cuando se evict desde warm. Cada objeto lleva checksum SHA-256, metadatos de grano y columnas (`grain contract`), scoping por `session_id` y `role`, y un event log que registra puts y gets. El ObjectBus es el sustrato sobre el que el Decision Agent guarda sus outputs (resultados de Monte Carlo, escenarios optimizados, distribuciones de beneficio, recomendaciones prescriptivas) para que turnos posteriores u otros agentes los consuman sin recomputar.

Inspirado en el patrón homónimo de LlullGen (que la auditoría destaca como "well-thought-out" y le da 3/5), pero ampliado: en LlullGen guarda DataFrames de SQL; en llull guarda además los outputs tipados de `SystemModel.evaluate()`, los resultados Monte Carlo con sus distribuciones, los escenarios comparados de 4.5, y los rastros de análisis causal de 4.6. Implementación limpia, no porting directo del código de LlullGen.

_Resuelve:_ tres problemas a la vez. (1) Latencia de follow-ups: cuando el usuario dice "y si subo el marketing un 10%", no hay que rerunnear toda la simulación anterior, solo deltas. (2) Bloque A multi-agente: cuando el Dashboard Agent consume el resultado del Decision Agent, lo lee del bus, no recomputa. (3) Lineage e2e (10.5): el bus es donde vive la cadena de evidencia que cada respuesta arrastra. Es un habilitador horizontal de tres bloques distintos.

**Dependencia:** 1.1 (PostgreSQL). **Habilita:** 5.3 (multi-agente sin recomputación), 5.5 (ventana de historial extendida vía referencias a objetos), 10.5 (lineage), 8.7 (cost lineage).

---

## 2. Ingesta y conexión con datos reales

Todo lo que tiene que ver con pasar de datos sintéticos a datos de cliente, con las garantías necesarias para que no se degrade silenciosamente.

### 2.1 Conectores batch básicos (Excel, CSV, SQL) `[feature]`

Primera capa de conectores simples: leer Excel y CSV subidos por el usuario, y queries SQL sobre bases de datos relacionales del cliente. Incluye inferencia de schema, detección de tipos y volumen mínimo antes de aceptar los datos.

_Resuelve:_ el primer cliente piloto no va a tener Debezium ni Kafka — va a tener Excel. Sin esto no hay validación real del producto.

### 2.2 Data Mapping Layer asistida por LLM `[feature]`

Capa que traduce nombres de columnas y conceptos del cliente ("ventas_netas_q3", "coste_por_lead") a las variables del spec ("revenue", "marketing_spend"). El mapping se sugiere automáticamente por un LLM basándose en nombres y tipos, y el consultor lo valida y corrige manualmente la primera vez. Una vez definido, se persiste y se reutiliza en cada ingesta posterior.

_Resuelve:_ sin esta capa, cada cliente nuevo requiere reescribir el spec a mano para que coincida con sus datos. La mapping layer es lo que hace que el mismo motor funcione para retail, energía, salud, sin tocar código.

### 2.3 Ingesta CDC con Debezium sobre Kafka `[bloque]`

Para fuentes transaccionales (Postgres, MySQL, SQL Server del cliente), Change Data Capture con Debezium leyendo del log de replicación y emitiendo eventos a Kafka. Latencia de segundos, cero impacto en el sistema origen, garantías at-least-once.

_Resuelve:_ cuando el cliente exige que llull reaccione a cambios en tiempo real (pricing de un banco que se recalcula varias veces al día), el pulling batch no llega. Es la opción arquitectónicamente correcta para fuentes críticas, pero solo se introduce cuando un cliente real lo justifica.

### 2.4 Contratos de datos con schema registry `[feature]`

Schema Registry (Confluent o equivalente) sobre los topics de Kafka. Cada topic tiene un schema Avro/Protobuf asociado, y los productores que intentan publicar con schemas incompatibles son rechazados en publicación. Bloquea schema drift de tipo "añadieron una columna nueva que rompe deserialización".

_Resuelve:_ es la primera capa contra el drift silencioso. Emparejado con 2.3.

### 2.5 Validación semántica con Great Expectations `[feature]`

Suite de expectations declarativas que se ejecuta sobre los datos antes de que entren al feature store o al motor del spec. Valida rangos, distribuciones, no-nulidad, unicidad, coherencia temporal. Si los datos fallan, el pipeline para y se genera un incidente — no se degrada el modelo en silencio.

_Resuelve:_ bloquea el drift semántico (el campo sigue siendo un float pero ahora viene en céntimos en vez de euros). Las expectations son parte del contrato con el cliente — no las escribe el ingeniero una vez, son un artefacto versionado del dominio.

### 2.6 Data bindings en el spec `[feature]`

Extender el spec de dominio para que cada variable declarada tenga asociado un `data_binding`: de qué fuente viene, con qué transformación, qué expectations debe cumplir. El spec deja de ser solo "definición causal del negocio" y pasa a ser también el contrato de cómo los datos reales alimentan ese modelo.

_Resuelve:_ conecta los dos mundos (spec de dominio e ingesta) sin acoplar el código. El spec sigue siendo la única fuente de verdad.

### 2.7 Integración de ontologías corporativas `[bloque]`

Leer ontologías del cliente (OWL/RDF) e incorporarlas automáticamente al spec: el vocabulario de variables, las relaciones ya formalizadas, las restricciones. BBVA, Comunidad de Madrid y otros clientes enterprise tienen ontologías corporativas propias.

_Resuelve:_ el onboarding de un cliente nuevo se reduce drásticamente si ya tiene su dominio formalizado. Es una ventaja competitiva real, pero técnicamente compleja. Se mete en roadmap largo, no corto.

### 2.8 Conectores REST (ERP, CRM) `[feature]`

Adaptadores genéricos para APIs REST de sistemas enterprise (Salesforce, SAP, HubSpot). Incluye autenticación (OAuth 2.0), gestión de rate limits, reintentos con backoff, y normalización del output al formato interno.

_Resuelve:_ muchos clientes no van a dar acceso directo a sus bases de datos por política interna, pero sí exponen APIs. Sin conectores REST, llull no puede trabajar con ellos.

### 2.9 Conectores a data warehouses (Snowflake, BigQuery, Redshift) `[feature]`

Conectores específicos para los tres data warehouses más comunes en empresas medianas-grandes. Incluye query builder asistido (para que el consultor no tenga que escribir SQL a mano) y un modelo semántico intermedio para aislar al agente del schema concreto del cliente.

_Resuelve:_ en empresas que ya tienen un data warehouse centralizado, llull debe consumir desde ahí en lugar de ir a las fuentes transaccionales.

### 2.10 SQL Execution Gateway con políticas tipadas `[feature] [v4]`

Chokepoint único por el que pasa **toda** ejecución SQL contra fuentes de cliente. Implementa cuatro tiers de políticas:

- **R0 — bloqueo absoluto:** DDL siempre bloqueado (CREATE, DROP, ALTER, TRUNCATE), DML bloqueado por defecto (INSERT, UPDATE, DELETE), con whitelist explícita por dominio cuando un caso de uso legítimo lo requiera. R0 nunca se bypassa.
- **R1 — políticas core:** identifier-safe SQL (psycopg2.sql.Identifier para nombres de tabla/columna, nunca f-string interpolation), límite de complejidad (CTEs anidados, joins), límite de duración (statement timeout), límite de tamaño de resultado.
- **R2 — políticas por dominio:** declaradas en el spec del dominio. Reglas como "métricas marcadas como `additivity: false` no pueden agregarse con SUM sobre dimensiones temporales", "ciertas tablas requieren filtros obligatorios", "joins entre datasets cross-tenant prohibidos".
- **R3 — políticas observe-only:** detectores con severidad warning que registran patrones potencialmente problemáticos sin bloquear, alimentando alertas y revisión periódica.

Las políticas viven en YAML versionado y son **asseradas en startup** — si el YAML está mal formado o no existe, el sistema no arranca. Esto es una corrección directa del bug que la auditoría de Ontology Layer reporta en LlullGen: el código dice cargar `config/sql_policy.yaml` pero el archivo no existe en disco y cae a hardcoded defaults silenciosamente. En llull esto no puede pasar.

Inspirado en el `SQL Execution Gateway` de LlullGen (~645 LOC entre policy y gateway, "uncommon discipline" según la auditoría). Reescritura limpia.

_Resuelve:_ defense-in-depth contra (a) SQL injection emergente del LLM, (b) errores semánticos sutiles que producen resultados plausibles pero incorrectos, (c) consultas accidentales que cargan el sistema del cliente. Es el complemento natural de 2.5 (Great Expectations valida los datos; el gateway valida las queries).

**Dependencia:** 2.1, 1.5. **Habilita:** 7.8 (audit log unificado), 7.9 (mitigaciones AI-native), 10.7.

---

## 3. Modelo de dominio y spec

Todo lo que tiene que ver con cómo se captura y se evoluciona el modelo causal de la organización del cliente.

### 3.1 DAG builder visual `[bloque]`

Editor visual del grafo causal: nodos como variables, aristas como relaciones causales. React Flow o D3.js. Permite crear, editar y borrar variables, definir tipos y rangos, marcar variables de decisión/intermedias/objetivo, previsualizar el impacto de cambios. La edición visual actualiza el spec en la base de datos en tiempo real.

_Resuelve:_ nadie en BBVA o Securitas va a editar YAML. Sin esta capa, el spec-driven es una decisión técnica potente pero no llega al usuario de negocio. Depende de 1.5 (spec as data).

### 3.2 Generador conversacional de specs `[feature]`

El consultor describe el modelo en lenguaje natural ("quiero optimizar el coste de adquisición de clientes, que depende del canal de marketing y el segmento"), y un LLM genera el borrador del spec YAML. El `spec_builder_tool` se añade como nueva tool del planner en el grafo LangGraph.

_Resuelve:_ acelera radicalmente el primer paso del onboarding. Sin esto, cada dominio nuevo empieza desde cero editando a mano. Funciona en combinación con 3.1 (el borrador conversacional se refina visualmente).

### 3.3 Validación automática del spec `[feature]`

Cuando se crea o modifica un spec, validación automática: detectar ciclos en el DAG (tiene que ser acíclico), variables sin fórmula, fórmulas inconsistentes, objetivos inalcanzables, referencias a variables no definidas, rangos contradictorios. Los errores se presentan con mensajes accionables, no stack traces.

_Resuelve:_ impide que un spec mal formado llegue al runtime. Es condición necesaria para que tanto 3.1 como 3.2 sean usables por no-técnicos.

### 3.4 Generación automática de spec a partir de datos `[bloque]`

Dado un dataset del cliente, el sistema analiza estructura, correlaciones y semántica de nombres, y propone un DAG inicial ("he analizado tus datos de ventas y propongo este modelo, ¿lo ajustamos?"). El consultor refina sobre la propuesta en lugar de empezar desde cero.

_Resuelve:_ capacidad de onboarding radicalmente diferente a cualquier competidor. Es aspiracional, pero el prototipo está diseñado para que esta pieza sea aditiva.

### 3.5 Extensión del spec para declarar políticas de autonomía `[parche]` ✅ COMPLETADO 2026-05-09

Añadir al spec un campo `autonomy_policy` por tipo de decisión: consultas de conocimiento pueden ser automáticas, recomendaciones de alto impacto requieren human-in-the-loop obligatorio. El planner consulta la política antes de ejecutar una tool sensible.

_Resuelve:_ el nivel de autonomía del agente es un parámetro de negocio del cliente, no una decisión técnica. Debe vivir en el spec, no hardcodeado.

_Implementado:_ `spec/autonomy.py` (AutonomyLevel, ToolAutonomyPolicy, AutonomyPolicy), sección `autonomy_policy` en YAML + parser en spec_loader, planner consulta política tras selección de tool, `_route_after_planner` conditional edge en workflow, `GET/PUT /v1/specs/{id}/autonomy`, 26 tests. Base para items 7.3 + 5.3.b.

### 3.6 Versionado semántico del spec con migraciones `[feature]` ✅ COMPLETADO 2026-05-09

Cada spec tiene una versión semántica (major.minor.patch), y los cambios entre versiones pueden requerir migración de runs históricos o de modelos predictivos asociados. Por ejemplo, renombrar una variable requiere actualizar referencias en todas las partes del sistema que la usen.

_Resuelve:_ sin versionado semántico, cualquier cambio al spec rompe la trazabilidad histórica y puede invalidar modelos ya desplegados.

### 3.7 Portabilidad del modelo de dominio como principio de diseño `[feature]`

Todo lo que llull aprende sobre el negocio del cliente debe ser propiedad del cliente, exportable en formatos abiertos y legible sin llull. Concretamente: el spec completo (YAML o JSON), los modelos predictivos entrenados (serialización estándar + metadatos de entrenamiento), los data mappings, los runs históricos con sus resultados, las evaluaciones del judge, y los datasets de evaluación. Cada uno con un endpoint de exportación y un formato documentado.

Este no es solo un requisito técnico — es un **principio arquitectónico declarado y un argumento comercial**. La pregunta "¿qué se lleva el cliente si deja llull?" debe tener una respuesta clara: "se lleva todo su conocimiento, versionado, en formatos abiertos". Esto posiciona a llull como la alternativa "own your intelligence" frente a plataformas que bloquean el contexto acumulado por el agente (el riesgo de "behavioral lock-in" que describe la literatura reciente sobre estrategias de plataforma de los proveedores de LLM).

Implica diseñar cada pieza del sistema con la exportabilidad en mente desde el principio — no como un afterthought. Los formatos deben ser estándares (JSON, YAML, ONNX para modelos, Parquet para datos, OpenTelemetry para trazas), y la documentación de cada formato debe ser pública.

_Resuelve:_ diferencial comercial directo con clientes enterprise que evalúan riesgo de plataforma. Argumento de venta concreto frente a la competencia que ejecuta "lock-in by design". Y una garantía para el cliente que reduce la barrera de adopción: "prueba llull sabiendo que si no funciona, te llevas todo lo que pusiste más todo lo que el sistema generó".

---

## 4. Capa analítica y predictiva

El motor determinista que calcula: modelos ML, simulación Monte Carlo, optimización, y la integración con los modelos analíticos propietarios de Inverence.

### 4.1 Simulación con parámetros arbitrarios desde la query `[parche]` ✅ COMPLETADO

Actualmente el `simulation_tool` siempre simula con el precio por defecto del spec porque no extrae el valor de la query. El problema ya está resuelto por la extracción dinámica de parámetros en el planner (ver README): el `simulation_tool` ya recibe los params extraídos y los aplica. Pero conviene validar esto con un caso real y documentarlo como cerrado.

_Resuelve:_ limitación conocida del prototipo inicial, ya resuelta pero sin verificación explícita en el documento de estado.

### 4.2 Optimización multi-variable con algoritmos escalables `[feature]`

Reemplazar grid search (que solo escala a 1-2 dimensiones) por Bayesian optimization o algoritmos genéticos cuando el espacio de decisión tiene más variables. La interfaz del `optimization_tool` no cambia — se mantiene la misma firma (recibe params del spec, devuelve optimal + distribución). Solo cambia el motor interno.

_Resuelve:_ con 3 o más variables de decisión, grid search es intratable por la maldición de la dimensionalidad. Sin esto, llull se limita a problemas de pricing simple.

### 4.3 Skills engine: registro dinámico de capacidades y exposición MCP `[feature]`

**Nota terminológica — tools vs skills.**

En llull usamos una nomenclatura precisa:

- **Tool**: función atómica que hace una cosa concreta. Es técnica, interna, tiene firma tipada. Ejemplos: `monte_carlo_simulation`, `grid_search_optimization`, `pgvector_retrieval`. Es lo que el planner selecciona y ejecuta. Son las piezas de cómputo.
- **Skill**: capacidad de dominio con significado de negocio, que puede involucrar una o más tools orquestadas. Es lo que el spec declara, lo que el usuario entiende, y lo que se expone al mundo exterior via MCP. Ejemplos: "Proyección de demanda con modelo bayesiano", "Optimización de pricing bajo restricciones", "Análisis de impacto causal sobre ingresos".

Una skill puede ser una tool simple (la skill "simulación de escenarios" envuelve la tool `monte_carlo_simulation`), o puede ser una orquestación de varias tools (la skill "proyección de demanda" podría invocar ingesta de datos del cliente + modelo bayesiano de Inverence + post-procesamiento estadístico).

Esta distinción importa por tres razones: (1) los modelos de Inverence se productifican como **skills**, no como tools — un modelo bayesiano de demanda no es una función atómica, es una capacidad compuesta; (2) cuando haya múltiples agentes, cada uno tendrá acceso a un subconjunto de skills declarado en su configuración; (3) el MCP server expone **skills** al mundo exterior, no tools internas.

**El skills engine tiene tres partes:**

**Parte 1 — Contrato técnico de skill.**

Definir la interfaz estándar que toda skill debe implementar:

```yaml
# En el spec, sección skills:
skills:
  - name: demand_forecast_bayesian
    description: "Bayesian demand forecast using Inverence proprietary model"
    provider: inverence               # internal | inverence | external
    endpoint: null                    # null = in-process, URL = remote service
    mcp_exposed: true                 # exponer como MCP server
    params_schema:
      product_id: { type: string, required: true }
      horizon_months: { type: integer, default: 6, min: 1, max: 24 }
    output_schema:
      forecast: { type: array, items: float }
      confidence_interval: { type: object }
    when_to_use: "User asks about future demand or sales projections"
    autonomy: human_confirms          # auto | human_confirms | human_approves
```

Interfaz Python: toda skill implementa `execute(params: dict, spec: OrganizationalModelSpec) -> SkillResult`, donde `SkillResult` tiene `data`, `metadata`, `confidence`, y `explanation`.

**Parte 2 — Registro dinámico y descubrimiento.**

El planner descubre las skills disponibles **del spec, no del código**. Añadir una skill nueva es: (1) implementar la interfaz, (2) declararla en el spec, (3) reiniciar. El planner la descubre automáticamente en el prompt system con su `description` y `when_to_use`.

Esto es lo que permite que los modelos de Inverence se integren sin tocar el núcleo del agente: se envuelven en la interfaz de skill, se declaran en el spec, y el planner los usa como cualquier otra skill.

**Parte 3 — Exposición como MCP servers.**

Las skills marcadas con `mcp_exposed: true` se exponen automáticamente como MCP servers sobre la API FastAPI. El flujo:

```
Cliente MCP externo → MCP Server de llull → API REST → skill → tool(s) internos
```

Esto permite que un cliente con Conway, GPT, Gemini o cualquier otro agente MCP-compatible consuma las capacidades analíticas de llull sin usar el agente de llull. **llull como proveedor de capacidades analíticas, no solo como producto cerrado.**

**Flujo de productificación de modelos de Inverence:**

1. **Descubrimiento**: inventariar el modelo (tech stack, inputs, outputs, documentación, estado operativo)
2. **Envoltura**: contenedorizar el modelo con la interfaz de skill estándar (`execute(params, spec) -> SkillResult`)
3. **Registro**: declarar la skill en el spec del dominio correspondiente
4. **Exposición**: automática via MCP si `mcp_exposed: true`
5. **Orquestación**: el planner del agente la selecciona cuando la pregunta del usuario lo requiere

Este flujo es el mismo para todos los modelos, independientemente de su tecnología interna (R, Python, MATLAB, lo que sea). La interfaz de skill estandariza el acceso.

*Resuelve:* desacopla la capacidad de integrar modelos externos de conocer los modelos concretos. Posiciona a llull como plataforma de productificación del conocimiento acumulado de Inverence. Permite que los 30 años de modelos bayesianos, series temporales e inferencia estadística sean accesibles via interfaz conversacional y via MCP estándar.

**Dependencia externa no resuelta:** el catálogo real de modelos de Inverence — qué hay, en qué tecnologías, en qué estado de documentación, con qué interfaces actuales, en qué estado operativo (código vivo, conocimiento tácito, papers internos). Hasta conocer eso, no se pueden estimar ni planificar las integraciones concretas. Es razonable priorizar un inventario de esos modelos como primera tarea de descubrimiento al incorporarse al equipo, y dejar la integración concreta fuera del primer ciclo de planificación.

### 4.4 Motor de simulación paralelizado (intra-proceso) `[feature]`

Paralelizar los N runs Monte Carlo usando `multiprocessing`, `concurrent.futures` o `joblib` dentro del mismo proceso que ejecuta la simulación. Objetivo: reducir la latencia de una simulación individual cuando el número de runs es alto o el modelo subyacente es costoso de evaluar.

Enfoque deliberadamente **local, sin brokers ni workers externos**. No hay colas, no hay Celery, no hay Temporal. Es una optimización de cómputo dentro de un proceso, no una distribución de tareas entre procesos.

_Resuelve:_ en el prototipo, 500 runs añaden ~150ms y se nota poco. En producción con modelos más complejos o con miles de runs, la latencia se dispara si no se paraleliza. Es la primera línea de defensa contra el problema de rendimiento, antes de recurrir a arquitectura asíncrona.

**Conecta con 6.3 (arquitectura event-driven):** cuando el volumen de runs por simulación crezca mucho, o cuando una sola simulación tarde más de lo admisible incluso paralelizada, el siguiente paso natural es que cada batch de runs sea un job encolado a un broker y ejecutado por workers distribuidos. Esa evolución es aditiva sobre el motor paralelo local, no lo reemplaza: el motor local sigue siendo lo que ejecuta cada worker.

### 4.5 Scenario comparison avanzado `[feature]`

Herramienta que evalúa múltiples escenarios en paralelo y genera una comparativa estructurada (tabla de resultados, visualización, análisis de sensibilidad). Va un paso más allá del "simula con X" actual.

_Resuelve:_ el valor prescriptivo crece cuando el usuario puede preguntar "¿qué pasa en estos cinco escenarios?" y recibir una comparativa, no cinco respuestas independientes. Es un caso de uso natural que hoy no está cubierto.

### 4.6 Análisis causal automatizado `[feature]`

Herramienta que responde a "¿por qué cambió este resultado?" recorriendo el DAG causal hacia atrás desde la variable objetivo hasta identificar qué variables de decisión tuvieron más impacto. Explicabilidad nativa del modelo causal.

_Resuelve:_ es una capacidad diferencial frente a dashboards clásicos. El modelo causal lo permite, solo hay que exponerlo al agente como tool.

---

## 5. Arquitectura del agente

El núcleo de orquestación LangGraph y todo lo que lo rodea: planner, synthesizer, judge, memoria, estructura del grafo.

### 5.1 Judge offline sobre logs históricos `[feature]`

Evaluador automático que procesa periódicamente `agent_runs.jsonl` (o su equivalente en Postgres) y detecta patrones de baja calidad: drift en el judge score, respuestas inconsistentes con datos, routing incorrecto del planner. Genera informes agregados y alertas.

_Resuelve:_ el judge online ya existe y valida por run, pero no detecta degradaciones lentas del sistema a lo largo del tiempo. El offline es la pieza que cierra el loop de calidad.

### 5.2 Test suites automatizadas de evaluación `[feature]` ✅ v1 COMPLETADO — v2 (dataset completo + judge offline) en I2A

Colecciones de queries con respuestas esperadas (o con criterios de evaluación vía LLM-as-judge offline) que se ejecutan automáticamente en cada deploy. Incluyen casos representativos de cada tool (routing correcto), casos límite (queries ambiguas, datos faltantes), y casos de regresión (bugs detectados en producción que se añaden para que no vuelvan).

_Resuelve:_ el equivalente a tests de regresión pero para el sistema agentic. Sin esto, cualquier cambio en prompts o configuración puede degradar la calidad sin que nadie se entere hasta que lo vea un usuario.

### 5.3 Orquestación multi-agente con patrón Supervisor de LangGraph `[bloque] [v4 — descompuesto]`

El agente de decisión actual se convierte en un sub-agente especializado ("Decision Agent"), y se añade un nivel superior (Orchestrator Agent) que coordina con otros sub-agentes: Dashboard Agent (genera visualizaciones), Alert Agent (configura umbrales y notificaciones), Report Agent (exporta análisis a documento estructurado), Action Agent (ejecuta acciones en sistemas externos vía API).

**Patrón técnico declarado:** Supervisor de LangGraph (`langgraph-supervisor`), con handoffs vía `Command` objects y `AgentState` compartido. Esta decisión queda registrada en ADR-002. Razones: routing accuracy más alto que swarm, debugging y trazabilidad superiores, alineamiento con la disciplina de gobierno (capability graph + budgets) que llull necesita en sectores regulados. La graduación a swarm/network solo se considera si datos de producción demuestran que latencia es el cuello de botella y los agentes raramente fallan en routing.

**Subdivisión del bloque en tres features separadas** (recomendación que el propio inventario v3 anticipaba):

#### 5.3.a Mínimo viable de Bloque A — Supervisor + Decision Agent + Dashboard Agent `[feature] [v4]`

El Decision Agent es el prototipo actual envuelto como sub-agente. El Dashboard Agent recibe el resultado del Decision Agent (vía ObjectBus, 1.6) y genera una visualización adecuada al output (distribución de beneficio, comparativa de escenarios, análisis de sensibilidad). El Supervisor enruta entre ellos con structured output Pydantic. Es la primera demostración tangible de "el sistema no termina con el insight, acompaña en su comunicación".

_Resuelve:_ valor visible inmediato. La pregunta "¿cuál es el precio óptimo?" produce no solo el número sino el dashboard que el usuario quiere mostrar a su equipo. Es la mínima expresión del Bloque A que ya se puede demostrar a un cliente.

#### 5.3.b Capability Graph tipado `[feature] [v4]`

Tabla de declaraciones tipadas — un Pydantic model — que especifica para cada par (agente origen, agente destino) qué tipo de payloads pueden cruzar, con qué profundidad máxima de cadena, qué presupuesto máximo arrastran, y qué política de autorización se aplica. El Supervisor consulta el capability graph antes de cada handoff. Sin esto, multi-agente es código que crece sin gobernanza: cualquier agente puede invocar a cualquier otro de cualquier forma, lo que en sectores regulados es inaceptable.

```python
class PeerAuthorization(BaseModel):
    source: AgentType
    target: AgentType
    allowed_payload_types: list[type[BaseModel]]
    max_depth: int  # cap a profundidad de cadena
    max_budget_usd: Decimal  # presupuesto máximo cedido al peer
    authorization_policy: Literal["always", "human_confirms", "policy_check"]
```

Inspirado en el `CapabilityGraph` de la AI/Agent Architecture target. **Habilita** governance del multi-agente y previene clases enteras de bugs estructurales (helpers reconstruidos perdiendo contexto, recursión sin freno, exfiltración de datos cross-agent). Es el contrato que hace que el Bloque A sea auditable.

_Resuelve:_ governance del multi-agente. Sin esto, 5.3.a funciona pero no se puede llevar a un cliente regulado.

#### 5.3.c Resto de sub-agentes — Alert, Report, Action `[feature] [v4]`

Bajo demanda. Cada uno se incorpora cuando un cliente real lo justifica:
- **Alert Agent** se activa cuando un cliente piloto pide notificaciones programadas sobre thresholds de variables de decisión.
- **Report Agent** se activa cuando un cliente pide exports estructurados (PDF, DOCX, slide deck) de análisis recurrentes.
- **Action Agent** se activa cuando hay demanda real de "el sistema no solo recomienda, ejecuta" — el caso más sensible en términos de autonomía y de auditoría.

Cada uno se diseña respetando el capability graph (5.3.b) — no se incorporan por la puerta de atrás.

_Resuelve:_ extensibilidad real del producto. Los sub-agentes adicionales no son código nuevo masivo: son piezas pequeñas que se enchufan en una arquitectura ya gobernada.

### 5.4 Agentes async como tool del grafo `[feature]`

Tipo especial de tool que, en vez de ejecutar síncrona en el nodo `tool` del grafo, encola un job asíncrono y devuelve un acknowledgement estructurado. El usuario recibe "tarea lanzada, te aviso cuando termine", y cuando el worker completa el job emite un evento que reingresa en el grafo como un nuevo turno de conversación con el resultado.

_Resuelve:_ habilita que simulaciones grandes, optimizaciones multi-variable y generación de informes no bloqueen el hilo conversacional. Es el puente entre el agente y la capa event-driven (ver 6.3).

### 5.5 Ampliar la ventana de historial conversacional `[parche]` ✅ COMPLETADO

Actualmente el planner inyecta los últimos 3 turnos en el prompt. Para conversaciones más largas y análisis iterativos, ampliar a N turnos (configurable) o implementar una estrategia más inteligente: resumen de turnos antiguos + detalle de los recientes.

_Resuelve:_ tres turnos no alcanzan para análisis exploratorios profundos. Es un parche pequeño pero con impacto directo en la calidad de la experiencia multi-turno.

### 5.6 Modelos LLM configurables por nodo + LLMFactory con abstracción multi-proveedor `[feature] [v4 — ampliado]` ✅ v1 COMPLETADO — LLMFactory completo (budget guard + fallback chain) en I2A

Ya está parcialmente implementado en el prototipo (cada nodo puede usar un modelo distinto via env vars). Esta evolución lo convierte en una pieza enterprise-ready completa con tres componentes integrados:

**Componente 1 — Registry tipado de modelos** (Anthropic, OpenAI, Together AI, Bedrock, Vertex AI, Azure OpenAI, Ollama). Cada entrada lleva: provider, slot (`route | fast | code | thinking | embed`), version, cost-per-1k-tokens, capabilities (structured output, tool calling, context window, vision). Pydantic model persistido en Postgres, consultable en runtime.

**Componente 2 — Context-budget pre-flight guard.** Antes de cada llamada LLM, calcular tokens del prompt completo y si supera el límite del modelo seleccionado, aplicar reducción determinista de mensajes (descartar turnos antiguos respetando los slots activos del estado, ver 5.5). Nunca dejar que la llamada falle por overflow.

**Componente 3 — Fallback chain por slot, automatizable según presupuesto restante.** Cuando el budget guard (10.6) detecta que queda poco presupuesto en el run, downgrade automático al siguiente modelo de la chain del mismo slot (Sonnet → Haiku → reject). La chain se declara en el spec, no se hardcodea.

Inspirado en el `LLMFactory` + `budget_guard` de LlullGen (~684 LOC de código original con buena ingeniería que la auditoría reconoce, pero anclados a un contexto frágil). Reescritura limpia, no porting directo.

_Resuelve:_ (a) clave para residencia de datos y para mitigar vendor lock-in (alineado con 3.7 portabilidad); (b) prevención del problema "context window overflow" que aparece la primera vez que un cliente trae histórico largo; (c) control granular del coste por dimensión, alimentando 8.7 y 10.6.

### 5.7 Fallback robusto en el planner `[parche]` ✅ COMPLETADO — subsumed por LLMFactory pattern (ADR-003)

Ya existe un fallback básico a knowledge tool si el structured output falla. Conviene formalizar la estrategia de fallback: qué hacer si el modelo devuelve un params mal formado, si la tool seleccionada no aplica al contexto, si el judge rechaza la respuesta más de una vez. Cada caso debe tener una respuesta degradada definida, no un crash.

_Resuelve:_ robustez en producción. El prototipo se comporta razonablemente en el camino feliz pero no tiene una política explícita de qué hacer cuando el LLM falla de formas inesperadas.

### 5.8 Memoria persistente del agente sobre el dominio `[feature]`

Más allá de la memoria conversacional por sesión, el agente debe aprender patrones a nivel de dominio: qué queries son frecuentes, qué tools se usan más para qué intenciones, qué respuestas han sido bien recibidas. Esta memoria alimenta el prompt del planner para mejorar routing con el tiempo.

_Resuelve:_ el sistema mejora con el uso, no solo con cambios de código. Es una forma suave de personalización por cliente sin fine-tuning.

### 5.9 GroundedTokens — guardrail determinista anti-alucinación de entidades `[feature] [v4]`

Cuando una conversación se hace larga, el planner LLM puede emitir routing decisions o follow-up resolutions que mencionan entidades, geografías o métricas que el usuario nunca usó. Es una clase de fallo silencioso difícil de detectar.

GroundedTokens es un guardrail determinista en dos pasos: (1) **antes** de la llamada LLM, construye un set de tokens permitidos extraído **solo** del texto bruto de los turnos del usuario más el vocabulario del dominio declarado en el spec (geografías válidas, métricas certificadas, dimensiones declaradas, meses, locales); (2) **después** de la llamada, valida que los tokens emitidos por el LLM en `query_for_agent`, `entities`, `filters` están dentro del set permitido. Si el LLM inventa una geografía plausible que no estaba, el guardrail la elimina; si el over-stripping deja la query vacía, fallback al raw query del usuario.

Inspirado en el componente del mismo nombre en LlullGen, que su propia auditoría destaca como "the single architecturally serious memory-governance primitive in the codebase". Adaptación crítica: en LlullGen los vocabularios geo/métricas están **hardcodeados como literales en español** dentro de Python, sesgando el sistema a un dominio y un idioma. En llull se alimentan desde el spec por dominio y locale, alineado con el principio spec-driven y eliminando el sesgo.

_Resuelve:_ defense-in-depth contra alucinación de entidades, una clase de fallo que escala con la longitud de la conversación. Pieza fundamental del Bloque A multi-agente: cuando varios agentes pasan contexto entre ellos, el riesgo de drift semántico crece.

**Dependencia:** 1.5 (spec as data) para que los vocabularios vivan en el spec. **Relación:** complemento perfecto de 10.7 (guardrails de output del LLM).

### 5.10 Memoria analítica activa tipada `[feature] [v4]`

Pieza que captura una idea ausente en v3 y central en la Memory Architecture target de Alfred: el **estado analítico activo** entre turnos no es la conversación bruta ni un blob libre, es un objeto tipado con slots semánticos (intent activo, métricas activas, dimensiones activas, periodo activo, geografías activas, comparaciones activas, transformaciones aplicadas, ambigüedades pendientes, confirmaciones pendientes) y con provenance por slot (qué turno lo introdujo, con qué evidencia, con qué confianza).

Diseño:

```python
class ActiveAnalyticalState(BaseModel):
    session_id: UUID
    last_turn_id: int
    version: int                                    # append-only por versión
    intent: Intent | None
    metrics: list[ResolvedMetric]                   # tipadas, no strings
    dimensions: list[ResolvedDimension]
    period: TemporalScope | None
    geography: list[ResolvedGeo]
    comparisons: list[Comparison]
    transformations: list[Transformation]
    pending_confirmations: list[PendingConfirmation]
    frozen_slots: set[str]                          # slots pinneados por el usuario
    provenance: dict[str, SlotProvenance]
    # Para llull (no en LlullGen): estado decisional
    active_simulation_run: ObjectId | None          # ref al ObjectBus (1.6)
    active_optimization_run: ObjectId | None
    active_scenarios: list[ObjectId]
```

Existe un único `MemoryCoordinator` que es el único componente con derecho a mutar `ActiveAnalyticalState`. Los agentes lo consumen como inmutable (`frozen()`).

Diferencia clave con la Memory Architecture target de Alfred: en ella el estado cubre solo la dimensión BI/text-to-SQL (metrics, dimensions, period). En llull se amplía con la dimensión decisional: simulaciones activas, escenarios comparados, parámetros inyectados — porque tu sistema es prescriptivo, no solo descriptivo.

_Resuelve:_ continuidad real entre turnos sin depender de que el LLM "se acuerde" de la conversación. El planner consulta el estado tipado, no el transcript bruto. Habilita follow-ups precisos ("y si subo el marketing un 10%" sabe exactamente sobre qué simulación está iterando), corrección por el usuario (5.11), y multi-agente coherente (Bloque A).

**Dependencia:** 1.5, 1.6. **Habilita:** 5.3 (multi-agente coherente), 5.11, 10.5.

### 5.11 MemoryService — interfaz única de acceso a memoria `[feature] [v4]`

Protocolo Python tipado (en `core/protocols/memory.py`) que es la **única seam de acceso a memoria fuera del paquete `memory/`**. Orchestrator, agentes, rutas API consumen exclusivamente este protocolo — nunca leen `conversation_history` raw, nunca lanzan SQL contra `memory_store` directamente, nunca asignan atributos a `ActiveAnalyticalState`.

Métodos del protocolo:
- `get_active_state(session_id) -> ActiveAnalyticalState` (frozen)
- `propose_state_update(turn_input) -> StateProposal` (per-slot decisions: inherit/overwrite/clear/clarify/defer-to-llm)
- `commit_state_update(proposal) -> StateCommitResult` (emite MemoryEvents)
- `get_short_range_view(max_turns, max_chars) -> ShortRangeView` (para prompts que genuinamente lo necesiten)
- `get_session_objects() -> list[ObjectMetadata]` (catálogo del ObjectBus con grain contract)
- `read_audit(session_id, slot=None) -> list[StateTransition]` (replayable)

Lint en CI bloquea cualquier import de `memory.*` desde fuera de `memory/`, cualquier indexing de `conversation_history[...]` fuera de `memory/`, y cualquier asignación a atributos de `ActiveAnalyticalState` fuera de `memory.coordinator`. Excepciones declaradas en `governance/memory_boundary_exceptions.yaml` con razón y sunset (ratchet only).

Refinamiento del Session Service (6.1.f) original de v3: la separación service-vs-protocol importa: 6.1.f se mantiene como service externo (HTTP) cuando se extraiga del monolito; 5.11 es el protocolo Python interno que define el contrato.

_Resuelve:_ la auditoría del Memory System de LlullGen reporta como hallazgo crítico que ChartAgent salta toda la abstracción y lee `conversation_history[-4:]` directamente — y que cualquier agente puede hacer lo mismo porque no hay MemoryService. Llevar esa lección a llull desde día 1 es muy barato; arreglarlo después es muy caro.

**Dependencia:** 5.10. **Habilita:** governance, lineage por slot, debugging multi-agente.

### 5.12 Recursion guard y depth limits para multi-agente `[parche] [v4]`

Cap de profundidad de cadena en handoffs (`max_depth`) configurable por capability graph (5.3.b) y por defecto a 3. Cap de número total de handoffs por run (`max_handoffs_per_run`, por defecto 8). Detección de ciclos (A → B → A) con bloqueo y registro de incidente. Cuando se alcanza un límite, fallback a respuesta degradada del último agente válido + mensaje claro al usuario.

La auditoría del AI Layer de LlullGen ya documenta `DispatchDepthExceeded` como mecanismo defensivo. La industria recomienda explícitamente "track handoff count — a multi-agent system without a recursion guard is a production incident waiting to happen".

_Resuelve:_ una clase de fallo que solo aparece en producción multi-agente: dos agentes haciéndose ping-pong indefinido, o una cadena que crece descontroladamente. Sin esto, un bug en el routing puede consumir miles de dólares en LLM calls antes de que alguien lo detecte.

**Dependencia:** 5.3.b. **Relación:** trabaja en conjunto con los hard request-level budget ceilings (8.7.b) — uno limita profundidad, el otro limita gasto.

---

## 6. Capa de servicio y API

La transición del REPL actual a un servicio expuesto que puedan consumir otras aplicaciones y usuarios múltiples.

### 6.1 APIficación completa en servicios desacoplados `[bloque]`

Exposición de **todas las capas** del sistema como servicios independientes, no como un único monolito FastAPI. Cada servicio es responsable de una capa de la arquitectura, tiene su propio ciclo de vida (build, despliegue, versionado, tests) y se comunica con los demás por HTTP (o gRPC donde la latencia lo exija).

Esto es una consecuencia directa del principio de separación de concerns que atraviesa el prototipo. Las tools del agente dejan de ser funciones Python importadas en proceso y pasan a ser clientes de servicios remotos. El agente invoca `simulation_service.run(params)` en lugar de `from simulation import run`.

**Ventajas:**

- Cada servicio escala independientemente según su carga real.
- Un servicio puede caerse o reiniciarse con degradación controlada, sin tumbar el agente.
- Cada servicio es testeable en aislamiento con su propia suite.
- Los modelos propietarios de Inverence (ver 4.3) se integran como servicios más, mantenidos por sus propios equipos, con sus propios ciclos de vida. El agente los consume igual que consume a los servicios internos.
- El equipo puede crecer por servicios: cada persona o grupo responsable de uno, con autonomía operativa.

**Trade-offs:**

- Latencia adicional en cada tool call (HTTP interno). Mitigable con keep-alive, serialización eficiente y, si hace falta, gRPC.
- Complejidad operativa mayor: más servicios que desplegar, monitorizar, versionar.
- Los contratos API entre servicios exigen disciplina de versionado. No se pueden cambiar libremente.
- Descubrimiento y autenticación entre servicios se vuelven problemas de primer orden (service mesh o al menos mTLS, ver 7.6).

**Servicios que emergen de esta descomposición:**

#### 6.1.a Simulation Service `[feature]`

Motor Monte Carlo expuesto como servicio independiente. Endpoints para lanzar una simulación, consultar resultados, cancelar una simulación en curso. Consume el spec del Spec Service para conocer los parámetros del dominio. Puede ser invocado por el agente, por un job asíncrono, por un notebook de analista, o por otro sistema externo.

_Resuelve:_ desacopla el cómputo de simulación de todo lo demás. Permite escalar el servicio horizontalmente cuando las simulaciones son pesadas, sin escalar el resto del sistema.

#### 6.1.b Optimization Service `[feature]`

Motor de optimización (grid search hoy, Bayesian/genéticos después) expuesto como servicio. Puede invocar internamente al Simulation Service para evaluar candidatos, o tener su propio motor embedido según el algoritmo.

_Resuelve:_ mismo principio que 6.1.a. Desacopla la optimización y permite sustituir el algoritmo interno sin que el resto del sistema lo note.

#### 6.1.c Knowledge Service `[feature]`

RAG y gestión del índice vectorial expuestos como servicio. Endpoints para ingerir documentos, hacer queries semánticas, administrar el índice, gestionar permisos por documento. Encapsula la elección de vector store (pgvector, Qdrant, etc.) detrás de una interfaz estable.

_Resuelve:_ permite cambiar el vector store subyacente (migrar de pgvector a Qdrant, por ejemplo) sin que nada más se entere. Y permite que la ingesta de documentos sea un flujo independiente del flujo conversacional.

#### 6.1.d Spec Service `[feature]`

CRUD completo sobre specs: crear, leer, actualizar, eliminar, validar, versionar, hacer diff entre versiones, promover entre entornos. Este servicio es el dueño único del estado de los specs; todos los demás servicios consultan pero no modifican. Alimenta al DAG builder visual (3.1) y al generador conversacional (3.2).

_Resuelve:_ centraliza el gobierno del modelo de dominio. Cualquier componente que necesite saber cómo está modelado un dominio concreto pregunta aquí. Habilita spec-as-data (1.5).

#### 6.1.e Agent Service `[feature]` ✅ COMPLETADO — monolito modular FastAPI + LangGraph

Orquestación LangGraph que consume los servicios anteriores como tools remotas. Expone al exterior los endpoints conversacionales: lanzar queries, gestionar sesiones, consultar historia de interacciones. Este es el servicio "cerebro" que razona; el resto son "músculo" que calcula.

_Resuelve:_ concentra la lógica agentic en un solo sitio y la separa limpiamente del cómputo analítico y de la gestión de modelo. Permite cambiar el planner, el synthesizer o el judge sin tocar los servicios de cómputo.

#### 6.1.f Session Service `[feature]`

Gestión de sesiones y memoria conversacional, desacoplada del Agent Service. Endpoints para crear/listar/resumir/borrar sesiones, recuperar historia, gestionar contexto. Implementa internamente el patrón Redis caliente + PostgreSQL frío (ver 1.4).

_Resuelve:_ el estado conversacional es un concern propio con patrones de acceso propios (alta frecuencia de lectura-escritura, TTL, hidratación desde frío). Separarlo permite optimizarlo independientemente del resto.

#### 6.1.g Observability Service `[feature]`

Exposición de runs, métricas y dashboards. Recibe eventos de observabilidad del resto de servicios (via OpenTelemetry, ver 8.2) y los expone a consumidores: dashboards, alerting, audit logs, queries analíticas de calidad. Incluye los endpoints del dashboard multi-tenant (8.6).

_Resuelve:_ la observabilidad es transversal a todos los servicios pero necesita un punto único donde consultarla. Separarla evita que cada servicio tenga que exponer sus propias métricas al exterior.

**Consideración importante sobre el orden.** No es necesario (ni recomendable) crear los siete servicios de golpe. Lo razonable es empezar con el Agent Service como monolito modular que importa internamente los módulos de simulación, optimización, knowledge, etc., y extraer cada servicio a su proceso propio cuando haya una razón concreta para hacerlo (escalado independiente, equipo separado, modelo externo a integrar). El inventario registra la meta arquitectónica; el roadmap decidirá qué servicios se extraen en qué iteración.

### 6.2 WebSockets para streaming de respuestas y notificaciones async `[feature]`

Endpoint WebSocket que permite: (a) streaming de tokens del synthesizer en tiempo real para que el usuario vea la respuesta generándose, y (b) notificaciones cuando un job async termina (ver 5.4 y 6.3). Fallback a polling sobre GET /jobs/{id} para clientes que no soporten WS.

_Resuelve:_ latencia percibida (streaming de respuesta) y coordinación de tareas asíncronas (notificaciones). La experiencia conversacional requiere las dos.

### 6.3 Arquitectura event-driven con message broker `[bloque]`

Introducción de un message broker (Kafka si ya hay infraestructura por CDC, o Redis Streams / RabbitMQ si se quiere más ligero) y workers asíncronos (Celery o, mejor, Temporal o Prefect para workflows durables con estado). Tareas encoladas: simulaciones grandes, optimizaciones multi-variable, análisis comparativos, re-entrenamiento, generación de informes.

_Resuelve:_ cualquier tarea pesada bloquea el camino crítico conversacional si no existe esta capa. Solo se introduce cuando una tarea real rompe el SLA — no de entrada — pero la arquitectura del agente (5.4) debe contemplarla desde el principio para que la migración sea aditiva.

### 6.4 Endpoints administrativos y de diagnóstico `[parche]` ✅ COMPLETADO

Endpoints de health (`/healthz`, `/readyz`), diagnóstico (`/debug/spec`, `/debug/state`), y administración (`/admin/sessions`, `/admin/runs`) con control de acceso estricto. Imprescindible para operar en cualquier entorno no-juguete.

_Resuelve:_ sin esto no hay Kubernetes probes, no hay diagnóstico rápido en incidentes, no hay administración sin acceso directo a la base de datos.

### 6.5 Versionado de API `[parche]` ✅ COMPLETADO

Prefijo de versión en la URL (`/v1/...`) y política declarada de compatibilidad hacia atrás. Importante desde el primer día aunque solo haya una versión, para no tener que hacer breaking changes silenciosos después.

_Resuelve:_ cuando el primer cliente piloto tenga integraciones con llull, cualquier cambio incompatible sin versionado rompe su implementación.

### 6.6 Interfaz web con Streamlit `[feature]` ✅ COMPLETADO

Sustituir el REPL de terminal (`app.py`) por una aplicación web Streamlit que permita interactuar con el agente de forma visual. La interfaz incluye: chat conversacional con historial, sidebar con info de sesión y modelo activo, visualización del DAG causal del spec (networkx → plotly), y gráficos de resultados de simulación/optimización (distribuciones, comparativas). La lógica del agente no cambia — Streamlit es una capa de presentación que invoca el mismo grafo LangGraph.

No reemplaza la API REST (6.1.e) sino que la complementa: Streamlit es la interfaz para demos, consultores y usuarios internos; la API es para integraciones programáticas.

**Implementado:** `streamlit_app.py`. UX polish para demo con dirección: welcome block con 3 cards de ejemplo, mensajes staged durante el procesamiento, badge tool+latencia bajo cada respuesta, gráficos y métricas mostrados directamente (sin expander), detalles técnicos en expander colapsado. Desplegado en Streamlit Community Cloud con Neon (pgvector). Self-bootstrap: genera datos, entrena modelo y construye índice de conocimiento en el primer arranque.

_Resuelve:_ el REPL es suficiente para desarrollo pero no para mostrar el producto a clientes, consultores o dirección. Una interfaz visual reduce la barrera de entrada y hace tangible lo que el agente puede hacer. Además, es la pieza que permite hacer demos en vivo sin necesidad de explicar la línea de comandos.

---

## 7. Seguridad y multi-tenancy

Todo lo que hace falta para que llull sea aceptable en una empresa enterprise con requisitos reales: aislamiento entre clientes, control de acceso, integración con identidad corporativa, cifrado, audit.

### 7.1 Multi-tenancy con Row-Level Security de Postgres `[feature]`

Modelo de tablas compartidas con columna `tenant_id` en todas las tablas relevantes, y Row-Level Security nativo de PostgreSQL que aplica el filtrado en el motor de datos en lugar de en la aplicación. La aplicación setea `SET app.current_tenant = X` al inicio de cada request, y todas las queries subsiguientes quedan filtradas automáticamente.

_Resuelve:_ el multi-tenancy no es una feature que se añade — es una decisión de modelo de datos. Si se retrasa, después se paga con una reescritura. RLS además elimina la clase de bug "me olvidé de filtrar por tenant_id en esta query".

### 7.2 Modelo de roles RBAC con scoping por dominio `[feature]`

Roles por tipo de usuario (admin de tenant, analista de negocio, consumidor de decisiones, auditor) con capabilities granulares (leer spec, editar spec, ejecutar optimización, ver runs, exportar datos). Dentro de un tenant, un usuario puede tener acceso solo a ciertos dominios de decisión (pricing pero no HR).

_Resuelve:_ organizaciones grandes tienen separación estricta entre departamentos. Sin scoping por dominio, un analista de una línea de negocio vería datos y decisiones de otras.

### 7.3 Políticas de autonomía consultadas por el planner `[feature]`

El planner, antes de ejecutar una tool sensible, consulta la política de autonomía declarada en el spec (ver 3.5) y decide si ejecuta automáticamente, si requiere confirmación humana, o si la bloquea completamente. La política se aplica de forma transparente al usuario.

_Resuelve:_ integra las políticas del spec con el control de acceso. Es el puente entre "declarar qué está permitido" (3.5) y "hacerlo cumplir en runtime".

### 7.4 Autorización centralizada con Open Policy Agent `[feature]`

OPA como servicio de autorización centralizado. Las políticas se declaran en Rego, son versionadas, auditables, y testeables aparte del código. Cada request pasa por un check de OPA antes de ejecutar la acción solicitada.

_Resuelve:_ con RBAC distribuido por el código, las políticas se pierden y son inconsistentes. OPA las centraliza y permite razonar sobre ellas como un artefacto de primera clase.

### 7.5 SSO con OIDC y SAML `[feature]`

Integración con proveedores de identidad corporativos. OIDC sobre OAuth 2.0 como estándar moderno (Azure AD/Entra ID, Okta, Ping, Keycloak). Soporte adicional de SAML para clientes legacy (frecuente en administraciones públicas). Usando Authlib o FastAPI-Users. Nunca implementar autenticación propia.

_Resuelve:_ ningún cliente enterprise va a crear usuarios en un sistema nuevo — exigen integrar con su IdP. Sin SSO, no hay cliente enterprise.

### 7.6 Cifrado en tránsito y en reposo `[feature]`

TLS 1.3 en todas las conexiones, mTLS entre servicios internos. Cifrado en reposo delegado a la capa de storage (Postgres con TDE, volúmenes cifrados, object storage con SSE). Las claves, en un KMS (AWS KMS, Azure Key Vault, HashiCorp Vault para cloud-agnostic).

_Resuelve:_ requisito base no negociable para cualquier cliente enterprise. Sin esto no pasa ni una primera due diligence de seguridad.

### 7.7 Gestión de secretos con Vault `[feature]`

Nunca secretos en código ni en variables de entorno de imágenes Docker. HashiCorp Vault (o el KMS del cloud) con rotación automática de credenciales sensibles: API keys de LLMs, credenciales de bases de datos de clientes, tokens de conectores. Los servicios obtienen secretos en runtime con credenciales efímeras.

_Resuelve:_ fuga de secretos en logs, en imágenes públicas, en dumps de configuración. Es el segundo item de seguridad base después del cifrado.

### 7.8 Audit log append-only `[feature]`

Toda acción administrativa (cambios de spec, cambios de permisos, accesos a datos sensibles, promociones de modelos) queda en un log append-only que el cliente puede exportar. Incluye quién hizo qué, cuándo, desde qué IP, y el estado antes/después del cambio.

_Resuelve:_ requisito regulatorio en banca, salud y administración pública. No es opcional — un cliente sin audit log no puede venderse en esos sectores.

### 7.9 Mitigaciones específicas de riesgos AI-native `[feature]`

Tres riesgos propios de un sistema agentic que necesitan mitigación explícita: (a) prompt injection desde documentos del cliente inyectados en el RAG — separación estricta entre datos recuperados y system prompt, validación de outputs del LLM; (b) data leakage cross-tenant en el knowledge layer — el `tenant_id` como filtro en la query vectorial, nunca como post-filtro; (c) LLM como canal de exfiltración — soporte de modelos gestionados en el cloud del cliente o modelos self-hosted para quien lo exija (ver 5.6).

_Resuelve:_ los tres son vectores de ataque reales y específicos de este tipo de sistema, no cubiertos por las mitigaciones clásicas de seguridad web.

### 7.10 Soporte para despliegues dedicados (single-tenant físico) `[bloque]`

Para clientes que exijan aislamiento total (banca, defensa, ciertos casos de sector público), capacidad de desplegar una instancia completamente dedicada del stack con el mismo código pero infraestructura física aislada. Se resuelve con infra como código y despliegue parametrizado — no es un fork del producto.

_Resuelve:_ algunos clientes grandes no aceptan multi-tenancy lógico por política interna. Sin esta capacidad, quedan fuera de llull por defecto.

---

## 8. Observabilidad y operación

Todo lo que permite saber qué está pasando en el sistema, detectar problemas antes de que el cliente los sufra, y responder cuando algo falla.

### 8.1 Migración de JSONL a tablas de runs en Postgres `[parche]` ✅ COMPLETADO

El observer sigue funcionando igual, pero los runs se escriben a una tabla Postgres en lugar de a un fichero JSONL. Permite queries analíticas, filtros por tenant/usuario/dominio, y sirve como base para dashboards multi-usuario.

_Resuelve:_ JSONL no sirve para queries analíticas ni para multi-usuario. Es un cambio pequeño pero habilita la observabilidad real.

### 8.2 Métricas con OpenTelemetry + Prometheus + Grafana `[feature]`

Instrumentación del código con OpenTelemetry (estándar cloud-agnostic). Métricas técnicas clásicas (latencia, throughput, errores, uso de recursos) en Prometheus, dashboards en Grafana. Traces distribuidos para ver el flujo de una request a través de los componentes.

_Resuelve:_ sin observabilidad clásica, operar en producción es a ciegas. No es específico de llull, es el suelo de cualquier servicio serio.

### 8.3 Métricas específicas del sistema agentic `[feature]`

Además de las métricas técnicas, métricas propias: judge score promedio, tasa de reescrituras, distribución de tools, latencia por nodo del grafo, coste por query en tokens y en dinero, drift en la distribución de queries, tasa de fallback. Exportadas al mismo Prometheus y visualizadas en Grafana.

_Resuelve:_ son las métricas que permiten detectar degradación de calidad del agente, no solo problemas técnicos. Son la primera señal cuando algo empieza a fallar en el comportamiento del LLM.

### 8.4 Logging centralizado con propagación de run_id por contextvar `[feature] [v4 — ampliado]`

Logs estructurados (JSON) enviados a Loki (o equivalente: ELK, Datadog). Correlación por `run_id`, `session_id` y `tenant_id` para poder reconstruir el flujo completo de una interacción. Retención configurable por tenant.

**Pieza arquitectónica clave**: propagación de `run_id` (y `session_id`, `tenant_id`) vía Python `contextvars` en lugar de pasarlos como parámetro por cada función. Esto permite que cualquier log emitido en cualquier punto del código quede automáticamente correlacionado con el run en curso, sin acoplar las firmas de las funciones al sistema de observabilidad. Cada respuesta lleva adjunto sus propios logs (capturados con un handler per-query) además de exportarlos al store global.

Patrón inspirado en el `LlullLogger` de LlullGen, que su propia auditoría puntúa con 3/5 (lo más alto del codebase audit). Implementación limpia, no porting directo, alineada con OpenTelemetry para que `run_id` sea también el `trace_id` del span raíz.

_Resuelve:_ cuando algo falla en producción, sin logs centralizados la única opción es SSH a máquinas, y en Kubernetes eso no escala. Con `run_id` por contextvar, debugging de un incidente concreto es una query a Loki filtrando por `run_id`.

**Dependencia:** 8.2. **Habilita:** 10.5/10.10 (lineage), debugging multi-agente.

### 8.5 Alerting con Alertmanager + políticas por severidad `[feature]`

Alertas configuradas sobre las métricas de 8.2 y 8.3. Política por severidad: alertas críticas van a PagerDuty/OpsGenie, avisos a Slack, métricas de drift a email con frecuencia diaria. Runbooks asociados a cada alerta.

_Resuelve:_ sin alerting, los problemas se detectan cuando el cliente llama. Con alerting, se detectan antes.

### 8.6 Dashboard multi-tenant de observabilidad `[feature]`

Interfaz que permite a un admin de tenant (no solo al equipo de llull) ver el estado de sus propias sesiones, runs, y métricas de calidad. Es parte del valor del producto, no solo herramienta interna.

_Resuelve:_ transparencia hacia el cliente. Un cliente enterprise quiere poder auditar el comportamiento del sistema sin depender del proveedor.

### 8.7 Control de gasto LLM completo (multi-dimensional) `[feature] [v4 — ampliado y descompuesto]`

El control de gasto es **multi-dimensional**: tenant, run individual, slot de modelo, peer en multi-agente, y trazabilidad. Sin esto, una query patológica puede consumir 10+ llamadas LLM en stacked retries y aún así estar "dentro del budget mensual del tenant" — exactamente el problema que la auditoría del AI Layer de LlullGen reporta como **gap explícito** ("no per-request LLM-call cap; no cost-per-request cap; no wall-clock budget"). v3 cubría parcialmente solo la dimensión tenant. v4 cubre las seis dimensiones que un control completo necesita.

#### 8.7.a Cuotas y presupuestos por tenant `[feature]`

(Era el 8.7 original.) Cada query registra el coste en tokens y en dinero. Presupuestos configurables por tenant, con alertas cuando se acercan al límite y bloqueo cuando lo superan. Dashboards de coste agregado por cliente y por dominio.

_Resuelve:_ los LLMs tienen coste variable. Sin control, una sesión problemática puede disparar la factura. Y un cliente enterprise va a exigir visibilidad sobre su consumo.

#### 8.7.b Hard request-level budget ceilings `[feature] [v4]`

Cap **por run individual** independiente del cap por tenant: `max_llm_calls_per_run`, `max_wallclock_seconds_per_run`, `max_cost_usd_per_run`, `max_total_tokens_per_run`. Cuando un cap se alcanza, el run se aborta de forma controlada y devuelve la mejor respuesta parcial disponible más un mensaje claro al usuario ("este análisis ha alcanzado su presupuesto de cómputo, aquí va el resultado parcial").

Sin esto, un run patológico (planner decide mal y dispara 10 retries con stacked backoff) consume al ritmo más alto del proveedor sin freno. Es el gap más claro de la auditoría AI Layer y un riesgo que tu inventario v3 no contemplaba.

_Resuelve:_ runaway runs. Por defecto: 20 llamadas LLM, 60 segundos wallclock, $1 USD por run. Configurable por capability via spec.

#### 8.7.c Budget reservation antes de ejecutar `[feature] [v4]`

Estimación a priori del coste de un plan antes de empezar a ejecutarlo, basada en (a) el plan composable que el supervisor genera, (b) los tokens estimados del prompt + output esperado por nodo, (c) los precios per-1k-tokens del registry de modelos (5.6). Si la estimación supera el budget disponible (sea por tenant, por run o por capability), el sistema **rechaza el plan antes de empezar** y propone alternativas (downgrade de modelo via 8.7.d, simplificación de la query, o confirmación humana del gasto).

Implementa el patrón `BudgetAccount` que la AI/Agent Architecture target propone: cada `RunEnvelope` reserva su budget al entrar al sistema, no después.

_Resuelve:_ control proactivo, no reactivo. Mejor rechazar un plan caro al inicio que consumir budget en un análisis que no se completa.

#### 8.7.d Fallback chain por slot, según presupuesto restante `[feature] [v4]`

La chain de modelos por slot (ver 5.6) deja de ser solo "por error de proveedor" y se extiende a "por presupuesto disponible". Cuando el budget restante en el run cae por debajo de un umbral, downgrade automático del modelo al siguiente de la chain del mismo slot: Sonnet → Haiku → respuesta degradada con confirmación. La política es **declarativa en el spec**, no hardcoded.

```yaml
# En el spec, sección llm_slots:
llm_slots:
  thinking:
    chain:
      - { model: claude-opus-4.7, max_cost_usd: 0.50 }
      - { model: claude-sonnet-4.6, max_cost_usd: 0.10 }
      - { model: claude-haiku-4.5, max_cost_usd: 0.02 }
      - { action: reject_with_message, message: "Análisis demasiado complejo para el presupuesto actual" }
```

_Resuelve:_ degradación elegante. El sistema no falla, responde con el mejor modelo posible dentro del presupuesto. Crítico para clientes con cuotas estrictas.

#### 8.7.e Budgets declarados por capability/peer en multi-agente `[feature] [v4]`

Cuando el Decision Agent invoca al Dashboard Agent (5.3), el capability graph (5.3.b) declara qué fracción del budget restante puede transferirle. Tres modelos posibles: (a) **share** — el peer comparte el budget pool del run; (b) **slice** — el peer recibe un sub-presupuesto fijo; (c) **separate** — el peer tiene su propio account, útil para sub-agentes que viven en infraestructura propia (ej. modelos de Inverence productificados como skills 4.3 con su propio coste).

Sin esto, multi-agente significa multiplicación incontrolada del coste por run. Con esto, el coste multi-agente es predecible y declarado.

_Resuelve:_ governance de coste en multi-agente. Pieza necesaria de 5.3.b para que el Bloque A no sea un agujero negro presupuestario.

#### 8.7.f Cost lineage por run `[feature] [v4]`

Refinamiento de 10.5: cada run produce un breakdown explícito de coste por componente — routing LLM, Decision Agent (con desglose por nodo), Dashboard Agent, tools determinístas (con coste $0 pero tiempo de cómputo), retries por error, validaciones del judge. Todo indexado por `run_id`, exportable como parte del LineageRecord.

```python
class CostLineage(BaseModel):
    run_id: UUID
    total_cost_usd: Decimal
    total_tokens: int
    total_wallclock_ms: int
    breakdown: list[CostNode]  # cost por nodo del plan, con peer y depth

class CostNode(BaseModel):
    node_name: str        # "supervisor.route", "decision_agent.planner", etc.
    parent_node_id: str | None  # None para root
    model_used: str | None  # None para tools determinísticas
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    wallclock_ms: int
    retries: int
```

_Resuelve:_ permite optimizar coste por dimensión real (qué prompt es caro, qué tool es lenta, qué agente quema budget). Sin esto, el optimizar coste es a ojo.

**Dependencia:** 8.7.a-e + 10.5. **Forma parte de:** LineageRecord (10.5).

---

## 9. MLOps y gobernanza de modelos predictivos

Todo lo relacionado con entrenar, validar, versionar, desplegar y monitorizar los modelos ML clásicos que alimentan el sistema (el RandomForest de demanda hoy, muchos más mañana).

### 9.1 Versionado de datasets con DVC `[feature]`

Cada entrenamiento queda asociado a un hash concreto del dataset usado. Reproducibilidad real: "este modelo fue entrenado con estos datos exactos". DVC (o LakeFS) para gestionar versiones de datasets grandes fuera de Git.

_Resuelve:_ sin versionado de datos, la reproducibilidad es ilusoria. "Reentrenamos el modelo y ya no sale igual" es un problema conocido y resoluble.

### 9.2 Pipeline de entrenamiento reproducible en contenedores `[feature]`

El entrenamiento se ejecuta en contenedores con dependencias fijadas, no en la máquina de un ingeniero. Los hiperparámetros son parámetros del pipeline, no magic numbers en un notebook. Orquestación con Kubeflow Pipelines o Prefect sobre Kubernetes.

_Resuelve:_ entrenamiento artesanal no escala. Sin esto, no hay reentrenamientos automáticos y la curva de coste de mantener modelos crece lineal con el número de clientes.

### 9.3 Experiment tracking con MLflow `[feature]`

Cada entrenamiento registra automáticamente en MLflow: métricas, parámetros, artefactos (modelo serializado, gráficas de validación), hash del código, hash del dataset. Comparación entre experimentos desde la UI de MLflow.

_Resuelve:_ sin experiment tracking, elegir entre variantes de modelo es a ojo. Con tracking, es un acto explícito y auditable.

### 9.4 Validación automática pre-promoción `[feature]`

Antes de que un modelo nuevo sustituya al actual en producción, el pipeline lo compara contra el modelo vigente en un conjunto de test congelado y contra criterios de negocio (estabilidad de recomendaciones, comportamiento en escenarios límite, coherencia con restricciones del dominio). Si no supera los umbrales, el pipeline bloquea la promoción.

_Resuelve:_ impide que un modelo peor reemplace al actual por accidente o por métrica mal elegida. Es el gate de calidad del pipeline.

### 9.5 Model Registry con MLflow `[feature]`

Versionado formal de modelos con aliases (candidate, staging, production) y metadatos de promoción (quién la aprobó, cuándo, con qué métricas, con qué dataset). El serving siempre referencia modelos por alias, nunca por versión fija, para que la promoción sea transparente al código.

_Resuelve:_ es la pieza que hoy falta entre "entreno algo" y "promuevo algo con control". Sin registry, la promoción es copiar ficheros, y eso no escala.

### 9.6 Despliegue en shadow y canary `[feature]`

Patrones de despliegue seguro para modelos nuevos. Shadow: el modelo nuevo recibe tráfico real en paralelo al actual sin que sus resultados impacten al usuario, solo se comparan. Canary: un porcentaje pequeño del tráfico real va al nuevo modelo, con rollback automático si métricas empeoran.

_Resuelve:_ el patrón más seguro para llull porque los errores en modelos predictivos son silenciosos (el modelo sigue respondiendo, solo responde peor).

### 9.7 Monitorización de drift en producción `[feature]`

Métricas de drift en inputs (distribución vs entrenamiento), de performance (accuracy sobre labels reales cuando estén disponibles), y de negocio (las recomendaciones encajan con la realidad observada del cliente). Alertas cuando se cruzan umbrales.

_Resuelve:_ los modelos degradan con el tiempo sin que nadie toque nada. Sin monitorización de drift, el sistema empeora en silencio.

### 9.8 Triggers automáticos de reentrenamiento `[feature]`

El reentrenamiento no depende de que alguien se acuerde. Se activa por reglas: nuevo lote de datos disponible, drift significativo, degradación por debajo de umbral, o revisión programada. Es el paso de MLOps nivel 0 a nivel 1/2.

_Resuelve:_ modelos que se reentrenan solos cuando hace falta. Depende de 9.2 (pipeline reproducible) y 9.7 (drift detection).

### 9.9 Múltiples modelos predictivos por dominio `[feature]`

Pasar de "un RandomForest de demanda" a "una colección de modelos por dominio y por cliente": propensión, riesgo, forecast, scoring. El model registry gestiona la proliferación, el spec declara qué modelo usa cada variable.

_Resuelve:_ el prototipo tiene un modelo. llull en producción tendrá decenas o cientos. La arquitectura debe soportar esa proliferación sin cambiar el núcleo.

---

## 10. LLMOps y gobernanza del sistema agentic

Todo lo relacionado con gobernar la parte LLM del sistema: prompts, tools, configuración de routing, judge, evaluaciones.

### 10.1 Versionado de prompts con prompt registry `[feature]` ✅

Los prompts del planner, synthesizer y judge dejan de vivir en ficheros sueltos del repo. Viven en un prompt registry con versionado, diffs legibles, y asociación a métricas de evaluación. Cada cambio de prompt es un artefacto promovible con el mismo rigor que un modelo ML. LangSmith para empezar (gestionado, integrado con LangGraph), con plan de migración a alternativas self-hosted si el coste o las exigencias del cliente lo requieren.

_Resuelve:_ hoy cambiar un prompt es editar código y hacer commit. No hay diff semántico, no hay evaluación antes de promover, no hay rollback fácil. Esto es deuda técnica que escala con el tamaño del equipo.

**Completado 2026-05-10** — `prompts/` package (`models.py`, `registry.py`); `PromptRecord` con GovernableArtifact pattern (10.8-ready); ciclo de vida `draft→certified→deprecated`; `get_prompt_template(stage, fallback)` con fallback a template inline; `seed_prompts_from_code()` idempotente; migración 004 (tabla `prompts`, CHECKs semver+status), migración 005 (3 columnas `*_prompt_version` en `agent_runs`); 5 endpoints REST (`/v1/prompts`); `planner_prompt_version`, `synthesizer_prompt_version`, `judge_prompt_version` propagados por `AgentState` → `RunRecord` → `PostgresSink`; 220 tests pasan (15 nuevos en `tests/prompts/`, 10 en `tests/api/`).

### 10.2 Datasets de evaluación del sistema agentic `[feature]`

Colecciones curadas de queries con respuestas esperadas (para casos claros) o con criterios de evaluación por LLM-as-judge (para casos abiertos). Cubren: casos representativos por tool (routing correcto), casos límite (queries ambiguas, datos faltantes), casos de regresión (bugs de producción que se añaden para que no vuelvan). Se ejecutan en cada cambio de prompt, modelo o configuración.

_Resuelve:_ la base sobre la que funcionan 5.2 (test suites automatizadas) y 10.3 (evaluación pre-promoción). Sin estos datasets, las otras dos piezas no existen.

### 10.3 Evaluación offline pre-promoción de cambios agentic `[feature]`

Cualquier cambio en prompts, configuración de tools, o modelos LLM usados, dispara la suite completa de evaluación offline. Si la calidad degrada por encima de un umbral, el cambio no se promueve. Equivalente a 9.4 pero para el sistema agentic en vez de modelos ML.

_Resuelve:_ el gate de calidad del LLMOps. Sin esto, cambios que parecen inocuos pueden degradar silenciosamente el comportamiento del agente.

### 10.4 Versionado del spec como artefacto de despliegue `[parche]`

El spec pasa por el mismo rigor que el código y los modelos: PR, review, validación automática (ver 3.3), promoción entre entornos. Cambios al spec son eventos trazables con autor, fecha, motivación. No es trabajo nuevo — es aplicar al spec la disciplina que ya se aplica a todo lo demás, una vez existe 1.5 (spec as data).

_Resuelve:_ el spec es parte del comportamiento del sistema. Si no pasa por el mismo rigor que el código, es deuda técnica inmediata.

### 10.5 Lineage end-to-end por run `[feature]`

Cada run del agente queda atado a: versión del código, versión del spec, versión de cada modelo predictivo involucrado, versión de los prompts, hash de los datos consultados (con timestamp), tool elegida con razonamiento, resultado devuelto, respuesta sintetizada, puntuación del judge. Todo indexado por `run_id`, inmutable, exportable.

_Resuelve:_ la pregunta "¿por qué este cliente recibió esta recomendación exactamente?" debe tener una respuesta completa en cualquier momento, especialmente en sectores regulados. Sin lineage, esa pregunta no se puede responder.

### 10.6 Control de gasto LLM — referenciado desde sección 8.7 `[v4 — refactorizado]`

El control de coste y calidad con presupuestos configurables, que en v3 estaba duplicado parcialmente entre 8.7 y 10.6, queda consolidado en la sección 8.7.a–f del bloque Observabilidad. Se mantiene aquí como puntero por trazabilidad documental: el control es a la vez un asunto de observabilidad (medir el gasto) y de LLMOps (limitarlo, optimizarlo, declararlo). Los seis sub-items concretos viven en 8.7.

### 10.7 Guardrails de output del LLM `[feature]`

Validación estricta de outputs del LLM más allá del structured output actual: detección de alucinaciones por comparación con el ground truth de las tools, detección de respuestas fuera de dominio, filtros de contenido sensible. Algunos guardrails ya existen implícitamente en el judge, pero conviene formalizarlos como una capa reutilizable.

_Resuelve:_ el judge valida calidad, los guardrails previenen categorías específicas de fallo. Son complementarios. **Trabaja con 5.9 (GroundedTokens):** GroundedTokens es el guardrail anti-alucinación de entidades, 10.7 cubre el resto de categorías.

### 10.8 Registry pattern unificado para artefactos gobernables `[feature] [v4]`

Patrón arquitectónico transversal que recorre las 4 arquitecturas objetivo de Alfred y que en v3 estaba implícito en piezas dispersas (10.1 Prompt registry, 9.5 Model registry, 1.5 Spec as data, 4.3 Skills engine). Se hace explícito como pieza de governance.

**Contrato común que todo registry de llull cumple**: cada artefacto registrable lleva los mismos campos canónicos:

```python
class GovernableArtifact(BaseModel):
    id: str                    # identificador único humano-legible
    version: SemVer            # major.minor.patch
    status: Literal["draft", "certified", "deprecated"]
    owner: str                 # equipo o persona responsable
    created_at: datetime
    changed_at: datetime
    sunset_date: date | None   # cuándo deja de soportarse (si deprecated)
    replacement_id: str | None # qué lo sustituye (si deprecated)
    adr: str | None            # referencia al ADR que justifica la decisión
```

**Registries que adoptan el patrón**:
- `MetricRegistry` (alimenta 4.5, 4.6, ontología semántica)
- `DimensionRegistry` (alimenta análisis dimensional)
- `EntityRegistry` (alimenta GroundedTokens 5.9 y entity matching)
- `PromptRegistry` (10.1)
- `ModelRegistry` (5.6 + 9.5, para LLMs y modelos predictivos)
- `ToolRegistry` (4.3 — tools internas)
- `SkillRegistry` (4.3 — skills expuestas via MCP)
- `PolicyRegistry` (políticas SQL 2.10, autonomía 7.3, autorización 7.4)
- `BudgetRegistry` (8.7)
- `VocabularyRegistry` (vocabularios por dominio para 5.9)

**Storage GitOps**: cada artefacto vive en `/governance/<registry>/<artifact_id>.yaml` versionado en Git. PR + review + tests asociados. Al merge, un migrator sincroniza a Postgres con historial inmutable de versiones.

_Resuelve:_ governance unificada. Un cambio en un metric no es un commit suelto, es un PR con review, owner, tests asociados, ADR referenciado. Sin este patrón, cada artefacto se gobierna a su manera y la disciplina no escala.

**Dependencia:** 1.1, 1.5. **Habilita:** Lineage e2e (10.5), evals con CI gates (10.3), audit log (7.8).

### 10.9 Prompt capture infraestructura — exporter para evaluación y debugging `[feature] [v4]`

Captura activable (env flag o por sesión) del prompt completo enviado a cada LLM, con etiquetado por stage (`supervisor.route`, `decision_agent.planner`, `synthesizer`, etc.), formato legible, y exportación a Loki / al storage de runs. Es un complemento del prompt registry (10.1): el registry es la fuente de verdad de los prompts; el capture es el exporter de cómo se materializaron en cada run con sus variables instanciadas.

Inspirado en el componente homónimo de LlullGen (~735 LOC), reescritura limpia. El gap concreto que resuelve: hoy en el prototipo, cuando una respuesta es rara, no hay forma de inspeccionar el prompt exacto que produjo esa respuesta a posteriori. Con prompt capture, cualquier run pasado se puede reconstruir.

_Resuelve:_ debugging de producción y alimenta evals offline (10.3). Sin esto, las evaluaciones offline solo tienen los inputs y outputs, no el cómo (qué prompt concreto se envió).

**Dependencia:** 8.4. **Habilita:** 10.3 evals offline más ricas, debugging post-hoc.

### 10.10 LineageRecord tipado por respuesta `[feature] [v4]`

Refinamiento de 10.5 (que enunciaba la idea genéricamente): cada respuesta del agente lleva adjunto un `LineageRecord` tipado, exportable y verificable, que contiene la cadena completa de causación de esa respuesta:

```python
class LineageRecord(BaseModel):
    run_id: UUID
    response_id: UUID
    code_version: str
    spec_version: SemVer
    supervisor_routing: RoutingDecision
    plan: RunPlan                              # DAG ejecutado
    agents_invoked: list[AgentInvocation]      # con versiones de prompts y modelos
    tools_executed: list[ToolExecution]        # con params, outputs, duration
    metrics_used: list[ResolvedMetric]         # con sus IDs y versiones del MetricRegistry
    dimensions_used: list[ResolvedDimension]
    rules_applied: list[BusinessRuleId]        # con versiones
    policies_evaluated: list[PolicyDecision]   # políticas SQL, autonomía, autorización
    objects_consumed: list[ObjectId]           # qué entradas del ObjectBus se leyeron
    objects_produced: list[ObjectId]           # qué salidas se escribieron
    cost_lineage: CostLineage                  # 8.7.f
    judge_verdict: JudgeVerdict | None
    timestamps: dict[str, datetime]
```

El LineageRecord se persiste, se indexa por `run_id` y `response_id`, se exporta vía API de cliente, y es la fuente de verdad para responder a "¿por qué este cliente recibió esta recomendación?". Inspirado en el `LineageRecord` que recorre las 4 arquitecturas objetivo de Alfred.

_Resuelve:_ trazabilidad regulatoria completa. En sectores regulados (banca, salud, AAPP) la pregunta no es "¿es buena la respuesta?" sino "¿puedes demostrar cómo la generaste, con qué reglas, sobre qué datos, con qué versión de qué modelo?". Sin LineageRecord tipado, esa pregunta no se puede responder.

**Dependencia:** 10.8 (todos los registries), 1.6 (ObjectBus), 8.7.f (cost lineage), todos los items con versionado. **Habilita:** 7.8 (audit log enriquecido), 12.8 (onboarding regulado), portabilidad (3.7).

### 10.11 Golden eval harness con CI gates `[feature] [v4]`

Refinamiento de 10.2 + 10.3 con la nomenclatura precisa de las arquitecturas objetivo: per-domain (query → IR → plan → response shape) goldens, ejecutados en CI con tres gates separados que pueden fallar el deploy independientemente:

- **Routing-gate** — el supervisor enruta a los agentes correctos para queries representativas.
- **Plan-gate** — el plan generado por agente es coherente con su capability spec.
- **Response-shape-gate** — el output tiene la estructura, columnas, unidades, grain declarados.

Los goldens se versionan junto con el spec del dominio (3.6) y se promueven con él. Cuando un golden falla, el PR se bloquea con un diff legible mostrando qué cambió.

_Resuelve:_ regresión silenciosa de calidad. El gap más documentado en la auditoría AI Layer de LlullGen ("no labeled regression set exists. A pathological query can consume 10+ LLM calls via stacked retries with no ceiling"). Con esto, cualquier cambio que degrade routing, plan o output es detectado antes de merge.

**Dependencia:** 10.2, 10.8. **Refina:** 5.2.

---

## 11. CI/CD y disciplina de ingeniería

Pipeline de entrega del código, tests, build, despliegue por entornos. La base sobre la que funcionan MLOps y LLMOps.

### 11.1 Pipeline CI con linting, tests y build `[feature]` ✅ COMPLETADO

GitHub Actions o GitLab CI con etapas: linting (ruff, black, mypy), tests unitarios (pytest con cobertura mínima), tests de integración (contenedores efímeros con Postgres, Redis, Kafka), build de imágenes multi-stage firmadas con cosign, generación de SBOM. Bloqueante en cada PR a main.

_Resuelve:_ el suelo de cualquier proyecto serio. Sin CI no hay calidad consistente del código, y el ritmo de cambio se ralentiza al crecer el equipo.

### 11.2 Tests de integración end-to-end del agente `[feature]`

Tests que levantan el grafo completo con dependencias reales (Postgres de test, modelo dummy, FAISS de test) y validan que las queries canónicas producen las respuestas esperadas. Son lentos pero imprescindibles para detectar regresiones que los tests unitarios no cubren.

_Resuelve:_ una clase de bugs específica del sistema agentic: el grafo se compila bien, cada nodo por separado funciona, pero la combinación falla por contratos implícitos rotos.

### 11.3 Contenedorización y empaquetado reproducible `[feature]` ✅ COMPLETADO

Todos los servicios empaquetados en contenedores Docker multi-stage. Imágenes mínimas basadas en distroless o Alpine donde tenga sentido. Configuración por variables de entorno. Cero estado en las imágenes.

_Resuelve:_ base para Kubernetes, para despliegues reproducibles, y para la promesa cloud-agnostic.

### 11.4 Despliegue en Kubernetes con Helm `[feature]`

Kubernetes como plataforma de ejecución, Helm como gestor de paquetes para los despliegues. Valores configurables por entorno (dev, staging, prod) y por tenant donde aplique. Health checks configurados, recursos limitados.

_Resuelve:_ estándar de facto para orquestación de contenedores en producción. La alternativa (servicios en VMs o manejo manual) no escala.

### 11.5 Despliegue por entornos con promoción controlada `[feature]`

Tres entornos claramente separados: dev (desarrollo activo), staging (integración final, datos similares a prod), production (clientes reales). Promoción entre staging y prod con aprobación manual en las primeras fases, automatizable después. Rollback rápido con un solo comando.

_Resuelve:_ sin entornos separados y promoción controlada, los cambios llegan a producción sin validación suficiente. Es la base del CI/CD seguro.

### 11.6 Estrategia de despliegue rolling con health checks `[parche]`

Despliegues rolling por defecto (no big-bang). Health checks configurados para que Kubernetes no dirija tráfico a pods que todavía no están listos. Canary deployment para cambios sensibles (ver también 9.6 para modelos).

_Resuelve:_ minimiza downtime durante despliegues y permite rollback automático si el health check falla.

### 11.7 Infraestructura como código con Terraform `[feature]`

Toda la infraestructura cloud definida en Terraform. Permite reproducibilidad, revisión en PRs, rollback, y sobre todo despliegues dedicados para clientes que lo exijan (ver 7.10) sin fork del producto.

_Resuelve:_ hacer infra a mano es frágil y no auditable. Terraform convierte la infra en un artefacto versionado igual que el código.

### 11.8 Stack cloud-agnostic en la capa lógica `[bloque]`

Todos los componentes elegidos son portables: FastAPI, PostgreSQL, Redis, Kafka, MLflow, LangSmith (migrable), Kubernetes, OpenTelemetry. La decisión de cloud (AWS, Azure, GCP) es un mapping del stack lógico a servicios gestionados equivalentes, sin rediseño conceptual.

_Resuelve:_ es la propiedad arquitectónica que permite retrasar la decisión de cloud hasta que un cliente grande lo exija, y adaptarse cuando un cliente pida uno distinto.

---

## 12. Items implícitos y decisiones pendientes

Cosas que aparecen mencionadas en los documentos pero no están explícitamente listadas como mejoras, y decisiones de diseño que quedan abiertas.

### 12.1 Política explícita de retención de datos por tenant `[parche]`

Cuánto tiempo se guardan runs, sesiones, logs y métricas por tenant. Configurable, con políticas por defecto conservadoras y opción de borrado bajo petición (GDPR).

_Resuelve:_ requisito GDPR y exigencia de cualquier cliente enterprise. No es trabajo grande pero tiene que estar.

### 12.2 Estrategia de backup y disaster recovery `[feature]`

Backups regulares de Postgres con retención definida, replicación cross-zone, procedimiento de restauración probado. RPO y RTO declarados y cumplidos. Runbooks para los escenarios de fallo.

_Resuelve:_ sin backups nada es serio. Sin DR probado, los backups son ficción.

### 12.3 Estrategia de validación causal del DAG `[feature]`

Cómo se valida que el DAG refleja la realidad de la organización. Tres fuentes: conocimiento experto (consultor de Inverence con décadas en el sector), datos históricos (validar empíricamente las relaciones causales), y proceso iterativo (experto describe, LLM genera borrador, se refina visualmente). No es un item de código — es un proceso de producto.

_Resuelve:_ el DAG es una hipótesis, no un hecho. Sin proceso de validación, la calidad del producto depende de que el primer spec sea correcto por suerte.

### 12.4 Política de fallback entre proveedores de LLM `[parche]` ✅ v1 COMPLETADO — se subsume en LLMFactory completo (I2A)

Qué pasa si OpenAI cae. La arquitectura ya permite modelos configurables por nodo (5.6), pero falta una política explícita de failover automático a un proveedor alternativo, con alerting y retorno al proveedor primario cuando se recupere.

_Resuelve:_ dependencia crítica de un único proveedor externo. Los incidentes de los grandes proveedores de LLM son frecuentes.

### 12.5 Gestión de límites de rate limiting del LLM `[parche]` ✅ v1 COMPLETADO — se subsume en LLMFactory completo (I2A)

Cuando se alcanzan los rate limits del proveedor de LLM (por segundo, por minuto, por día), comportamiento definido: encolado con espera, degradación a otro modelo, rechazo de la query. Nunca crash silencioso.

_Resuelve:_ los rate limits son la causa número uno de fallos en sistemas LLM en escala. Hay que gestionarlos explícitamente.

### 12.6 Documentación operativa para el equipo `[feature]`

Runbooks por escenario de incidente, playbooks para tareas operativas frecuentes (rotación de claves, incorporación de nuevo cliente, promoción de modelo), diagramas arquitectónicos mantenidos, glosario del dominio. Documentación viva, no "documento final".

_Resuelve:_ el conocimiento en cabeza del arquitecto no escala. La documentación operativa es lo que permite que el equipo crezca sin perder velocidad.

### 12.7 SDK cliente para consumir la API `[feature]`

SDK Python (primero) y TypeScript (después) para que las integraciones de clientes no tengan que construir HTTP crudo. Incluye tipado, manejo de errores, streaming, retry automático.

_Resuelve:_ reduce fricción de integración con clientes. Un SDK bien diseñado convierte una integración de semanas en una integración de días.

### 12.8 Estrategia de onboarding de cliente documentada `[feature]`

Las tres fases: (1) definir el modelo causal del cliente — idealmente conversacional con LLM generando borrador del spec; (2) conectar datos reales — mapping asistido por LLM; (3) entrenar modelos predictivos sobre datos reales. Cada fase con criterios claros de "hecho". No es trabajo de código — es proceso de producto, pero condiciona el código.

_Resuelve:_ sin proceso definido de onboarding, cada cliente nuevo es una reinvención de la rueda. Con proceso, el tiempo de onboarding baja y es predecible.

---

## Resumen cuantitativo

- **Total de items**: 109 principales + 7 sub-items (servicios 6.1.a–g) = **116 items**
- **Items nuevos en v4** (etiquetados `[v4]` o `[v4 — ...]`): 19 items, distribuidos en:
  - Bloque 1 (Persistencia): +1 (1.6 ObjectBus)
  - Bloque 2 (Datos reales): +1 (2.10 SQL Execution Gateway)
  - Bloque 5 (Agente): +6 (5.3 descompuesto en 5.3.a/b/c, 5.6 ampliado, 5.9 GroundedTokens, 5.10 Memoria analítica activa, 5.11 MemoryService, 5.12 Recursion guard)
  - Bloque 8 (Observabilidad): +5 (8.4 ampliado, 8.7 descompuesto en 8.7.a–f con cinco sub-items nuevos)
  - Bloque 10 (LLMOps): +4 (10.8 Registry pattern, 10.9 Prompt capture, 10.10 LineageRecord, 10.11 Golden eval harness)
- **Por granularidad**:
  - `[parche]`: 15 items
  - `[feature]`: 89 items
  - `[bloque]`: 12 items
- **Por bloque temático**:
  1. Persistencia y estado: 6 items
  2. Ingesta y conexión con datos reales: 10 items
  3. Modelo de dominio y spec: 7 items
  4. Capa analítica y predictiva: 6 items
  5. Arquitectura del agente: 14 items (5.3 descompuesto en 5.3.a/b/c)
  6. Capa de servicio y API: 6 items principales + 7 sub-items
  7. Seguridad y multi-tenancy: 10 items
  8. Observabilidad y operación: 12 items (8.7 descompuesto)
  9. MLOps y gobernanza de modelos predictivos: 9 items
  10. LLMOps y gobernanza del sistema agentic: 11 items
  11. CI/CD y disciplina de ingeniería: 8 items
  12. Items implícitos y decisiones pendientes: 8 items

## Notas para el roadmap (actualizadas v4)

- **Dependencias fuertes ya visibles**: 1.1 (Postgres) sigue siendo prerequisito de casi todo. 1.5 (spec as data) es prerequisito de 3.1, 3.2, 3.6, 5.9 (vocabularios desde el spec), y 8.7.d (chains declaradas en spec). 6.1 (APIficación) sigue siendo prerequisito de UI, multi-agente y modelos externos. **Nueva dependencia clave en v4**: 1.6 (ObjectBus) habilita 5.3 (multi-agente sin recomputación), 5.10 (memoria analítica activa) y 10.10 (lineage).

- **La APIficación (6.1) tiene una secuencia interna.** Sin cambios respecto a v3.

- **El item 4.3 (mecanismo de tools externas) tiene una dependencia externa no resuelta** — el inventario real de modelos analíticos de Inverence. Sin cambios respecto a v3.

- **Dos ejes ortogonales a tener en cuenta al ordenar**: desbloqueo técnico vs requisito de cliente. Sin cambios respecto a v3.

- **El bloque 5.3 ya está descompuesto en v4**: 5.3.a (mínimo viable Bloque A) puede entrar en I3, 5.3.b (capability graph) es prerequisito de cualquier multi-agente con governance y por tanto va con 5.3.a, 5.3.c (Alert/Report/Action) queda como "Más allá — bajo demanda".

- **Items que podrían desaparecer si se adopta una tecnología externa**: si en algún momento se evalúa Managed Agents, buena parte de 5.4, 5.12, 6.3, 7.9 y partes de 9 y 10 se replantean. Sin cambios respecto a v3.

- **Conexión entre paralelización local (4.4) y distribución de tareas (6.3)**: sin cambios respecto a v3.

- **Decisión declarada en ADR-002**: motor de orquestación = LangGraph con patrón Supervisor. La alternativa (sustituirlo por el A2A custom de LlullGen) queda explícitamente descartada por las razones documentadas en el ADR.

- **Decisión declarada en ADR-003**: política de reutilización de componentes de LlullGen. Inspiración conceptual sí, porting de código no. Cada componente reutilizado se reescribe limpio sobre la arquitectura llull respetando el spec-driven y la disciplina de governance.

- **Cobertura del control de gasto en v4**: las seis dimensiones del control (tenant, run, slot, peer, lineage, recursion) están cubiertas por los items 8.7.a–f + 5.12. v3 cubría solo la dimensión tenant.

- **La taxonomía conceptual unificada de las arquitecturas objetivo** (registries tipados, lineage, evals con CI gates) está integrada en v4 como items 10.8 (registry pattern unificado), 10.10 (LineageRecord), 10.11 (golden eval harness con CI gates). Es una capa transversal de governance que recorre el inventario.
