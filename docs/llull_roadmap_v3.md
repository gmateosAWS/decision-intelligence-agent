# Roadmap llull — del prototipo al producto

**Propósito.** Ordenar los 95 items del inventario en iteraciones con criterio de entrega claro, priorizando por desbloqueo técnico (qué habilita a qué), después por valor entregado (qué puede demostrarse al final), y con ataques puntuales al factor riesgo (qué conviene validar pronto).

**Cómo leerlo.** Este documento se lee junto al inventario, al que referencia por códigos (1.1, 6.1.e, etc.). No duplica las descripciones — las referencia. Cuando necesites el detalle de un item, abre el inventario al lado.

**Estructura.** Primero el grafo de dependencias (para entender por qué las cosas van donde van), luego las cuatro iteraciones (I1, I2A, I2B, I3) con su contenido y justificación, y al final los items que quedan fuera.

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

---

## Tabla resumen de dependencias críticas

| Item                         | Depende de                | Desbloquea                                      |
| ---------------------------- | ------------------------- | ----------------------------------------------- |
| **1.1** PostgreSQL           | nada                      | 1.2, 1.5, 7.1, 8.1, y transitivamente casi todo |
| **1.5** Spec as data         | 1.1                       | 3.1, 3.2, 3.3, 3.6, 6.1.d, 10.4                 |
| **6.1.e** Agent Service      | nada (porta el prototipo) | 6.4, 6.5, 7.5, UI, multi-usuario                |
| **7.1** Multi-tenancy        | 1.1                       | 7.2, 7.9 (data leakage cross-tenant)            |
| **8.1** Runs en Postgres     | 1.1                       | 5.1, 10.2, 10.5                                 |
| **11.1** Pipeline CI         | nada                      | 11.3, 11.4, 11.5, calidad del código            |
| **2.1** Conectores batch     | nada                      | 2.2, 2.5, 2.6 (y validación con datos reales)   |
| **9.3** MLflow               | nada                      | 9.1, 9.2, 9.4, 9.5, 9.7, 9.8                    |
| **10.2** Datasets evaluación | 8.1                       | 5.2, 10.3                                       |

---

## Las cuatro iteraciones

Cada iteración tiene: un **criterio de entrega** (qué se puede demostrar al final que antes no se podía), un **listado de items** agrupados en paquetes funcionales, y una **justificación** de por qué ese item va ahí y no en otro sitio.

La Iteración 2 original se ha subdividido en **I2A** (datos reales + calidad del agente, validación interna) e **I2B** (seguridad enterprise + operación, apertura a cliente externo). La lógica: validar primero que el producto funciona con datos reales en entorno controlado, antes de invertir en la capa de seguridad que lo abre al exterior.

---

## ITERACIÓN 1 — Fundación productiva

### Criterio de entrega

Al final de esta iteración, llull es un **servicio desplegable con API REST, persistencia en PostgreSQL, búsqueda vectorial sobre pgvector, specs versionados en base de datos, pipeline CI funcional, los primeros tests del sistema agentic, y una interfaz web visual (Streamlit) que permite hacer demos sin necesidad de terminal**. Todavía no tiene multi-tenancy ni datos reales de cliente, pero un ingeniero o un consultor puede interactuar con él vía API o vía web, desplegar cambios con confianza, y empezar a medir la calidad del agente sistemáticamente.

Es el paso de prototipo/demo a un sistema con base técnica seria sobre la que se empieza a construir el producto.

### Paquete 1A — Base de persistencia (parcialmente completado)

| Item                              | Estado |
| --------------------------------- | ------ |
| **1.1** PostgreSQL                | ✅ Hecho (PostgresSaver, SQLAlchemy, Alembic, Docker Compose, dual-backend SQLite fallback) |
| **1.2** pgvector                  | ✅ Hecho (knowledge_documents con vector(1536), cosine search, FAISS fallback) |
| **8.1** Runs en Postgres          | ✅ Hecho (agent_runs table, dual-write JSONL+Postgres, metrics read from Postgres) |
| **1.5** Spec as data              | ⬜ Siguiente (Feature B) |
| **1.3** Ruta a Qdrant documentada | ⬜ Pendiente (ADR a escribir tras 1.5) |

### Paquete 1B — API y servicio

| Item                                       | Justificación                                                                                                                                                                                                |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **6.1.e** Agent Service (monolito modular) | Porta el prototipo a FastAPI como monolito modular. Todavía no extrae servicios — los módulos internos siguen importados en proceso. Expone los endpoints conversacionales, de sesiones, de runs y de specs. |
| **6.4** Endpoints admin/health             | Imprescindible para cualquier despliegue real. Se añade junto al Agent Service.                                                                                                                              |
| **6.5** Versionado de API                  | Se decide ahora (prefijo `/v1/`) para no tener que romper compatibilidad después.                                                                                                                            |

### Paquete 1C — Disciplina de ingeniería

| Item                                 | Justificación                                                                                                                                                                   |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **11.1** Pipeline CI                 | Linting, tests unitarios, tests de integración con Postgres de test, build de imagen. Debe existir desde el primer commit del sistema productivo.                               |
| **11.3** Contenedorización           | Dockerfile multi-stage. Base del despliegue.                                                                                                                                    |
| **5.2** Test suites del agente (v1)  | Primera versión: 10-15 queries canónicas con respuestas esperadas, ejecutadas en CI. No es el dataset completo de 10.2 todavía — es el mínimo para detectar regresiones graves. |
| **5.7** Fallback robusto del planner | Política formal de qué hacer cuando el LLM falla. Se hace ahora porque afecta a cómo se comporta el sistema en tests y en producción.                                           |

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
| **6.6** Interfaz web con Streamlit    | ✅ Hecho (`streamlit_app.py`, 574 líneas, chat + DAG + gráficos) |

### Items que no entran en la Iteración 1 y por qué

- **Multi-tenancy (7.1)**: requiere 1.1, pero además requiere diseñar el schema con `tenant_id` desde cero. Si se hace a medias (schema sin RLS, "ya lo pondremos"), la deuda es enorme. Preferible cerrar Postgres con un schema limpio en I1 y añadir RLS como primer paso de I2.
- **SSO (7.5)**: requiere que haya una API que proteger. Se activa en I2 cuando el Agent Service ya esté estable.
- **Datos reales (2.1)**: se podría meter, pero la I1 ya tiene mucho peso. Meterlo aquí dispersa el foco. En I2 es el primer paquete.
- **MLflow (9.3)**: es independiente y podría ir aquí, pero aporta poco valor hasta que haya datos reales y múltiples modelos. En I2 o I3 tiene más sentido.

---

## ITERACIÓN 2A — Datos reales y calidad del agente (piloto interno)

### Criterio de entrega

Al final de esta sub-iteración, llull puede **ingerir datos reales de un cliente (Excel/CSV/SQL), mapearlos al spec asistido por LLM, validarlos semánticamente, crear specs conversacionalmente, y tiene un proceso de evaluación de calidad del agente reproducible y automatizado**. Es el sistema que el equipo interno de Inverence puede usar para validar con datos reales de un cliente candidato, antes de abrirlo al exterior. Todavía no tiene multi-tenancy ni SSO — opera en un entorno controlado interno.

Es el paso de sistema con base técnica seria a sistema que demuestra valor con datos reales.

### Paquete 2A.1 — Datos reales del cliente

| Item                                              | Justificación                                                                                                                                              |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **2.1** Conectores batch (Excel, CSV, SQL)        | El primer cliente va a tener Excel. Es lo mínimo para validar el producto con datos reales.                                                                |
| **2.2** Data Mapping Layer asistida por LLM       | Sin esto, hay que reescribir el spec a mano para cada cliente. Con esto, el onboarding es asistido.                                                        |
| **2.5** Validación semántica (Great Expectations) | Expectations declarativas sobre los datos antes de que entren al motor. Bloquea drift silencioso. No necesita Kafka — funciona sobre los conectores batch. |
| **2.6** Data bindings en el spec                  | Cada variable del spec sabe de dónde vienen sus datos. Conecta ingesta con modelo de dominio.                                                              |

### Paquete 2A.2 — Modelo de dominio operativo

| Item                                       | Justificación                                                                                                                                                                                                                                                                                      |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **3.2** Generador conversacional de specs  | El consultor describe el dominio en lenguaje natural, el LLM genera el borrador. Reduce drásticamente el tiempo de onboarding. No necesita el DAG builder visual (viene en I3).                                                                                                                    |
| **3.3** Validación automática del spec     | Impide que un spec mal formado llegue al runtime. Condición necesaria para que 3.2 sea usable por no-técnicos.                                                                                                                                                                                     |
| **3.5** Políticas de autonomía en el spec  | Añadir `autonomy_policy` al spec. Es un parche pequeño con impacto alto: el primer cliente querrá saber quién controla qué.                                                                                                                                                                        |
| **3.7** Portabilidad del modelo de dominio | Principio de diseño + endpoints de exportación: spec, modelos, mappings, runs, evaluaciones en formatos abiertos (YAML, JSON, ONNX, Parquet). Se implementa en I2A porque informa el diseño de todo lo que toca datos de cliente. Argumento comercial directo: "en llull tu conocimiento es tuyo". |
| **4.3** Registro de tools externas con MCP | El contrato técnico de tools, expuestas como MCP servers. Independiente de conocer los modelos de Inverence concretos. Posiciona a llull en el ecosistema abierto y permite que clientes con otros agentes (Conway, GPT) consuman las capacidades analíticas de llull.                             |

### Paquete 2A.3 — Evaluación y calidad

| Item                                                | Justificación                                                                                                                          |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **10.2** Datasets de evaluación del sistema agentic | Colección curada de queries para testing. Habilita 5.2 (test suites v2), 10.3 y 5.1.                                                   |
| **5.2** Test suites v2 (ampliación)                 | Ampliar las 10-15 queries de I1 a un dataset completo con casos por tool, límite y regresión. Ejecutado en CI y en evaluación offline. |
| **5.1** Judge offline sobre logs históricos         | Procesamiento periódico de runs para detectar degradaciones. Depende de 8.1 (runs en Postgres, hecho en I1).                           |
| **10.3** Evaluación offline pre-promoción           | Gate de calidad para cambios en prompts, tools o modelos LLM. Depende de 10.2.                                                         |

### Paquete 2A.4 — Parches y mejoras del agente

| Item                                                      | Justificación                                                                                    |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **3.6** Versionado semántico del spec                     | Cada spec con versión major.minor.patch. Los runs quedan atados a la versión.                    |
| **10.4** Versionado del spec como artefacto de despliegue | PR, review, validación automática, promoción entre entornos. Aplica la disciplina de I1 al spec. |
| **10.1** Prompt registry                                  | Los prompts del planner/synthesizer/judge versionados y evaluables. Primer paso real de LLMOps.  |

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
- **Multi-agente (5.3)**: requiere servicios extraídos, que no se habrán hecho todavía. Es I3+.
- **Redis para memoria (1.4)**: optimización que solo se justifica con cientos de sesiones concurrentes. El primer piloto no va a tenerlas.
- **Conectores REST, data warehouses (2.8, 2.9)**: se construyen cuando aparezca el cliente que los necesita, no antes.
- **MLflow (9.3)**: es independiente y podría ir aquí, pero aporta poco valor hasta que haya datos reales y múltiples modelos. En I3 tiene más sentido.

---

## ITERACIÓN 3 — Producto diferencial

### Criterio de entrega

Al final de esta iteración, llull tiene su **capacidad diferencial más visible desplegada: el DAG builder visual, la primera extracción de servicios, scenario comparison, análisis causal, MLOps básico con MLflow, observabilidad completa, y el inicio del pipeline de gobernanza de modelos**. Es el sistema que se presenta al mercado como producto, no como piloto.

Además, se abordan las primeras piezas de escalado (Redis para memoria, paralelización de simulaciones, WebSockets) y las primeras piezas de gobernanza formal (RBAC, OPA, lineage).

### Paquete 3A — DAG builder y onboarding avanzado

| Item                                                    | Justificación                                                                                                                                                                |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **3.1** DAG builder visual                              | La feature de producto más visible. Editor visual con React Flow o D3.js. Depende de 1.5 (spec as data, hecho en I1) y de 6.1.d (Spec Service).                              |
| **6.1.d** Spec Service (primera extracción de servicio) | Se extrae ahora porque el DAG builder necesita una API dedicada para specs. Es el primer servicio que sale del monolito.                                                     |
| **12.8** Proceso de onboarding documentado              | Las tres fases formalizadas: modelo causal, datos reales, modelos predictivos. Con 3.1, 3.2, 2.1, 2.2, la herramienta está completa; falta el proceso documentado alrededor. |

### Paquete 3B — Capacidades analíticas avanzadas

| Item                                     | Justificación                                                                     |
| ---------------------------------------- | --------------------------------------------------------------------------------- |
| **4.2** Optimización multi-variable      | Bayesian o genéticos. Desbloquea dominios con más de 2 variables de decisión.     |
| **4.4** Motor de simulación paralelizado | Multiprocessing/joblib. Primera línea de defensa de rendimiento.                  |
| **4.5** Scenario comparison              | Comparativa estructurada de múltiples escenarios. Valor prescriptivo alto.        |
| **4.6** Análisis causal automatizado     | "¿Por qué cambió este resultado?" recorriendo el DAG. Capacidad diferencial real. |

### Paquete 3C — MLOps

| Item                                           | Justificación                                                  |
| ---------------------------------------------- | -------------------------------------------------------------- |
| **9.3** Experiment tracking con MLflow         | Ancla de la cadena de MLOps.                                   |
| **9.5** Model Registry con MLflow              | Versionado formal de modelos con aliases y promoción.          |
| **9.1** Versionado de datasets con DVC         | Reproducibilidad de entrenamientos.                            |
| **9.2** Pipeline de entrenamiento reproducible | Contenedores con dependencias fijadas. Sobre Kubeflow/Prefect. |
| **9.4** Validación automática pre-promoción    | Gate de calidad para modelos.                                  |

### Paquete 3D — Escalado y rendimiento

| Item                                      | Justificación                                                                                                    |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **1.4** Redis para memoria caliente       | Se introduce si el piloto de I2 ha mostrado contención en Postgres con sesiones concurrentes. Si no, se pospone. |
| **6.2** WebSockets                        | Streaming de respuestas y notificaciones async. Mejora la experiencia del usuario.                               |
| **5.4** Agentes async como tool del grafo | El patrón de tool asíncrona. Prepara para event-driven sin introducirlo todavía.                                 |

### Paquete 3E — Gobernanza avanzada

| Item                                      | Justificación                                                                                           |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **7.2** RBAC con scoping por dominio      | Sobre el multi-tenancy de I2. Roles y capabilities granulares.                                          |
| **7.3** Políticas de autonomía en runtime | El planner consulta la política del spec antes de ejecutar tools sensibles.                             |
| **7.4** OPA como servicio de autorización | Centralización de políticas. Depende de que haya un modelo de permisos (7.2).                           |
| **10.5** Lineage end-to-end por run       | Cada run atado a versión de código, spec, modelos, prompts y datos. Cierra la trazabilidad regulatoria. |

### Paquete 3F — Observabilidad completa

| Item                                         | Justificación                                                                |
| -------------------------------------------- | ---------------------------------------------------------------------------- |
| **8.4** Logging centralizado con Loki        | Logs estructurados, correlación por run_id/session_id.                       |
| **8.5** Alerting con políticas por severidad | Alertas sobre métricas técnicas y del agente.                                |
| **8.6** Dashboard multi-tenant               | Visibilidad para el admin del cliente sobre sus propias sesiones y métricas. |
| **8.7** Gestión de coste y cuotas por tenant | Control de gasto por cliente.                                                |

### Paquete 3G — Mejoras del agente

| Item                                                 | Justificación                                                                |
| ---------------------------------------------------- | ---------------------------------------------------------------------------- |
| **5.8** Memoria persistente sobre el dominio         | El agente mejora con el uso.                                                 |
| **10.6** Control de coste y calidad con presupuestos | Límites por prompt, tool, tenant.                                            |
| **10.7** Guardrails de output del LLM                | Más allá del judge: detección de alucinaciones, respuestas fuera de dominio. |
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
| **5.3** Orquestación multi-agente                   | Requiere servicios extraídos, contratos estables, y un caso de uso claro de "acción post-decisión".                                                                       | Un piloto donde el usuario pida actuar sobre la recomendación (dashboard, alerta, informe) dentro del flujo. |
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
│  │ Runs en Postgres│ │ Endpoints admin  │ │ Fallback robusto         │   │
│  │ Ruta Qdrant doc.│ │ Versionado API   │ │                          │   │
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
│  │ Datos reales      │ │ Modelo dominio   │ │ Evaluación             │   │
│  │                   │ │                  │ │                        │   │
│  │ Conectores batch  │ │ Generador conv.  │ │ Datasets evaluación    │   │
│  │ Mapping Layer LLM │ │ Validación auto. │ │ Test suites v2         │   │
│  │ Great Expectations│ │ Políticas auton. │ │ Judge offline          │   │
│  │ Data bindings     │ │ Portabilidad (*) │ │ Eval. pre-promoción    │   │
│  │                   │ │ Tools MCP (*)    │ │                        │   │
│  └───────────────────┘ └──────────────────┘ └────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ Mejoras: versionado spec · spec como artefacto · prompt reg.     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
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
│  │ DAG builder       │ │ Analítica avz.   │ │ MLOps                  │   │
│  │                   │ │                  │ │                        │   │
│  │ Editor visual     │ │ Optim. multi-var │ │ MLflow tracking        │   │
│  │ Spec Service      │ │ Paralelización   │ │ Model Registry         │   │
│  │ Onboarding doc.   │ │ Scenario comp.   │ │ DVC datasets           │   │
│  │                   │ │ Análisis causal  │ │ Pipeline reproducible  │   │
│  │                   │ │                  │ │ Validación pre-prom.   │   │
│  └───────────────────┘ └──────────────────┘ └────────────────────────┘   │
│  ┌───────────────────┐ ┌──────────────────┐ ┌────────────────────────┐   │
│  │ Escalado          │ │ Gobernanza       │ │ Observab. completa     │   │
│  │                   │ │                  │ │                        │   │
│  │ Redis memoria     │ │ RBAC + OPA       │ │ Logging (Loki)         │   │
│  │ WebSockets        │ │ Lineage e2e      │ │ Alerting               │   │
│  │ Async tools       │ │ Autonomía runtime│ │ Dashboard multi-tenant │   │
│  │                   │ │                  │ │ Coste por tenant       │   │
│  └───────────────────┘ └──────────────────┘ └────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │ Agente: memoria dominio · guardrails · presupuestos · docs       │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  MÁS ALLÁ — Bajo demanda / señal de mercado                              │
│                                                                          │
│  CDC + Kafka · Ontologías · Multi-agente · Extracción servicios          │
│  Event-driven · Despliegues dedicados · Shadow/canary · Drift/retrain    │
│  Terraform · SDK cliente · Generación spec desde datos                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Notas finales

**Sobre la subdivisión de la Iteración 2.** La I2 original concentraba demasiados ejes para un equipo pequeño: datos reales, seguridad, evaluación y operación. La subdivisión en 2A y 2B permite obtener feedback real más rápido. I2A valida con un consultor interno de Inverence que el producto funciona con datos reales. Ese feedback puede redirigir prioridades antes de invertir en la capa enterprise de I2B. Si todo va bien, el equipo trabaja I2A e I2B de forma consecutiva pero con un punto de revisión entre ambas. Si I2A revela problemas graves (el mapping no funciona, el generador conversacional produce specs inutilizables, la validación semántica bloquea datos válidos), se itera sobre I2A antes de abrir I2B.

**Sobre el tamaño de las iteraciones.** La Iteración 1 es la más acotada y la que más impacto tiene por item. La I2A es manejable (15 items, foco en producto y calidad). La I2B es más pesada en infraestructura (13 items, foco en seguridad y operación). La Iteración 3 es donde llull se diferencia — pero solo es posible si I1, I2A e I2B están sólidas.

**Sobre la flexibilidad.** Este roadmap no es un compromiso contractual. Es un mapa del terreno con una ruta recomendada. Si un cliente aparece antes de lo esperado y exige algo de I3 (digamos, el DAG builder), se adelanta. Si un riesgo se materializa (digamos, que el proveedor de LLM cambia su pricing), se reordena. Las iteraciones tienen criterio de entrega, no fecha. Eso da flexibilidad sin perder dirección.

**Sobre lo que queda fuera.** Los items del bloque "más allá" no están descartados — están diferidos hasta que haya una señal clara que los active. La señal está documentada para cada uno. Eso significa que nadie tiene que "recordar" que había que hacer CDC; cuando el primer cliente pida streaming, se mira el inventario, se lee la señal, y se planifica.

**Sobre la integración con Managed Agents.** Este roadmap es independiente de la decisión sobre Managed Agents. Si se decide incorporarlos (parcial o totalmente), los items que más se ven afectados son: 6.1.e (Agent Service), 5.4 (async tools), 6.3 (event-driven), y partes de 7.9 (seguridad AI-native) y 8 (observabilidad). El inventario y el roadmap se actualizarían para reflejar qué items asume Managed Agents y cuáles siguen siendo propios. Esa es una conversación separada que se puede tener cuando el inventario y el roadmap estén estabilizados.
