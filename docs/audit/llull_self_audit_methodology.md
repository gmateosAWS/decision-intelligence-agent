# Metodología de auto-auditoría arquitectónica · plataforma llull

**Propósito.** Proporcionar al architect un instrumento de auto-evaluación de la arquitectura de llull equivalente (en rúbrica y rigor) al que el CEO de Inverence aplica a LlullGen. Permite ejercitar **antes** de cada revisión externa los mismos criterios que serán evaluados, identificar derivas de calidad temprano, y mantener una traza temporal de la madurez del sistema.

**Cobertura.** Cuatro capas, una pasada, **86 dimensiones totales**, con discriminación explícita entre gaps planificados (cubiertos por inventario / roadmap / ADRs) y gaps no planificados (riesgo real). La rúbrica está calibrada al estado de prototipo y se mueve con el sistema: el mismo prompt produce diagnósticos cada vez más exigentes a medida que el roadmap avanza.

---

## 1. Principios de diseño de la rúbrica

### 1.1 Cuatro capas, una rúbrica por capa

Las cuatro capas que el CEO de Inverence audita en LlullGen son las cuatro que llull debe auditar también:

| Capa | Pregunta que responde la auditoría | Dimensiones |
|---|---|---|
| **Codebase & Architecture** | ¿La estructura del código sostiene crecimiento? | 28 |
| **AI / Agent Layer** | ¿El sistema agentic está bajo control? | 20 |
| **Conversational & Analytical Memory System** | ¿La continuidad multi-turno es real, no sólo prompt? | 22 |
| **Ontology & Semantic Knowledge Layer** | ¿El conocimiento de negocio es manipulable, no implícito? | 16 |

Cada capa tiene su propia rúbrica con dimensiones específicas que **no se inventan** — están extraídas directamente del corpus de auditorías que el CEO ha producido sobre LlullGen, transportadas a llull preservando la nomenclatura para que la traducibilidad cruzada esté garantizada.

### 1.2 Escala 0–5, calibración consistente

Cada dimensión se puntúa con la escala canónica del CEO:

```
0  absent / dangerously weak
1  poor / mostly ad hoc
2  partial / fragmented
3  functional but uneven
4  strong
5  excellent / mature and governable
```

Reglas operativas de calibración:

- **0 nunca por ausencia legítima en fase actual.** Si la capacidad está en el roadmap y todavía no se ha acometido, la dimensión se puntúa según el "andamio" actual, no el "vacío esperado". La gradación entre 0 y 5 captura la madurez del andamio.
- **5 reservado para piezas que un auditor externo aceptaría sin observaciones.** Las puntuaciones se desplazan por defecto hacia la mediana; un 5 requiere evidencia convincente, no ausencia de problemas.
- **Decimales no permitidos.** Forzan la decisión binaria entre dos niveles vecinos. Si dudas entre 2 y 3, evalúa: ¿está el comportamiento descrito en el nivel inferior? Si sí → 2.

### 1.3 Evidencia con file:line, no paráfrasis

Toda afirmación de la auditoría debe estar respaldada por evidencia concreta del repositorio en el formato `path/to/file.py:line_range`. No vale "el código tiene errores" — vale "agents/workflow.py:161 captura `Exception` y serializa el mensaje sin clasificar el tipo de fallo".

Razones:
1. **Auditabilidad.** Cualquier persona puede verificar la afirmación abriendo el fichero.
2. **Diff entre auditorías.** Cuando el código cambia, la evidencia obsoleta se detecta automáticamente.
3. **Resistencia a paráfrasis.** Evita el sesgo de "esto suena mal" sin que esté sustentado.

### 1.4 Discriminador de gaps — el añadido específico a la rúbrica de Alfred

Esta es la **adaptación más importante** respecto al instrumento de Alfred sobre LlullGen. El CEO audita LlullGen como si fuera un producto en producción y reporta cualquier capacidad faltante como gap. En llull aún estamos en fase prototipo: la mayoría de capacidades enterprise no están implementadas todavía y eso **no es un fallo** si están en el plan.

Por tanto, cada hallazgo de capacidad faltante se clasifica en una de tres categorías:

| Categoría | Significado | Acción |
|---|---|---|
| 🟢 **Cubierto-implementado** | La capacidad existe en el código, con calidad ≥ 3/5 | Reportar y reforzar |
| 🟡 **Cubierto-planificado** | La capacidad no está en el código pero está en inventario/roadmap/ADR con referencia explícita | Reportar como pendiente, con cita al item/iteración/ADR. **Sin penalización al score si la posición en el roadmap es coherente con la fase actual.** |
| 🔴 **Gap real** | La capacidad no está implementada **y** no está en inventario/roadmap/ADR | Reportar con severidad. **Estos son los hallazgos críticos del audit.** |

Este discriminador exige al auditor leer activamente:
- `docs/llull_inventario_v4.md` (116 items)
- `docs/llull_roadmap_v4.md` (4 iteraciones)
- `docs/adr-001-pgvector-over-qdrant.md`
- `docs/ADR-002-langgraph-orchestration.md`
- `docs/ADR-003-llullgen-component-reuse-policy.md`

Antes de declarar un hallazgo como 🔴, el auditor confirma con `grep` o búsqueda directa que el ítem efectivamente no está cubierto. La trazabilidad al item del inventario es obligatoria para hallazgos 🟡.

### 1.5 No charitable, evidence-first

El tono del auditor es el del CEO en sus reports:

- **No charitable.** Si una pieza está mal, se dice. Si está bien, también — sin floritura.
- **Evidence-first.** Cada afirmación con cita.
- **Genuine craft is acknowledged.** El audit del Codebase de LlullGen tiene una sección entera dedicada a las fortalezas reales del sistema. La auditoría de llull hace lo mismo.
- **No prescribe la solución cuando no se ha pedido.** El campo "to reach next level" es minimalista y enuncia una dirección, no un diseño completo.

---

## 2. El prompt monolítico

El prompt vive en `llull_audit_prompt.md` y tiene la siguiente estructura:

1. **Rol e instrucciones generales** del auditor.
2. **Material de referencia** que el auditor debe leer antes de empezar (inventario, roadmap, ADRs).
3. **Instrucciones de evidencia y discriminación de gaps** (sección 1.3 y 1.4 de esta metodología, condensadas).
4. **Las cuatro rúbricas dimensionales completas** (28 + 20 + 22 + 16 = 86 dimensiones).
5. **Schema del output requerido** (markdown estructurado + scorecard HTML).
6. **Reglas de cierre y firma del auditor.**

El prompt está diseñado para ejecutarse contra:
- **Un repositorio Git completo** (path local, no URL).
- **El conjunto de docs de governance** (`docs/llull_inventario_v4.md`, `docs/llull_roadmap_v4.md`, `docs/ADR-*.md`) que vive dentro o junto al repo.

Salida esperada: dos artefactos atómicos, **un único fichero markdown** y **un único fichero HTML** con scorecard visual.

---

## 3. Cadencia y uso recomendado

### 3.1 Antes de cada review externa

Ejecutar el self-audit **al menos una semana antes** de cualquier review programada con el CEO. Tiempo suficiente para corregir los hallazgos críticos que la rúbrica detecte. La regla operativa: "no llegues a una review con un hallazgo 🔴 que tu propio audit detectó hace una semana".

### 3.2 Cada vez que cierras una iteración del roadmap

Al cerrar I1, I2A, I2B, I3 — el self-audit es parte de la definición de "hecho" de la iteración. La iteración no se cierra hasta que la rúbrica confirma que las capacidades prometidas están en el nivel ≥ 3/5 que un cliente externo aceptaría.

### 3.3 Mensualmente como marker temporal

Aunque no haya cambio significativo en el código, ejecutar el self-audit cada 4-6 semanas crea una traza temporal que permite detectar derivas. Si una dimensión baja de 3 a 2 sin haber tocado nada, hay deuda que está saliendo a la superficie.

### 3.4 Antes de incorporar nuevo equipo

El self-audit es el documento que mejor explica a un nuevo desarrollador "dónde estamos" y "qué está bajo control". Mejor que cualquier README.

---

## 4. Outputs esperados

### 4.1 Fichero markdown principal

`{repo}/audit_reports/{YYYY-MM-DD}_llull_self_audit.md` con la estructura:

```
# llull · Self-Audit · {fecha} · {commit hash corto}

## Executive Summary
- Overall maturity score (promedio ponderado de las 4 capas): X.XX / 5
- Hallazgos 🔴 críticos: N
- Hallazgos 🟡 planificados: M
- Hallazgos 🟢 confirmados: K

## Layer 1 — Codebase & Architecture (28 dimensions)
[Tabla con 28 filas: Dimension · Score · Rationale · Evidence · To reach next level · Gap category]

## Layer 2 — AI / Agent Layer (20 dimensions)
[…]

## Layer 3 — Conversational & Analytical Memory (22 dimensions)
[…]

## Layer 4 — Ontology & Semantic Knowledge (16 dimensions)
[…]

## Critical Findings (🔴)
[Lista detallada de hallazgos no contemplados, con severidad]

## Planned Gaps (🟡)
[Lista de capacidades pendientes con referencia explícita a item/iteración/ADR]

## Genuine Strengths
[Sección equivalente a la "real strengths" del audit del CEO]

## Comparison with previous self-audit
[Diff entre scores, dimensiones que han subido / bajado, gaps cerrados]

## Auditor signature
[Fecha, commit hash, modelo LLM usado, parámetros]
```

### 4.2 Scorecard HTML visual

`{repo}/audit_reports/{YYYY-MM-DD}_llull_self_audit.html` con:

- Heatmap de las 86 dimensiones agrupadas por capa, color por score (0=rojo intenso → 5=verde intenso).
- Línea temporal de la madurez global si hay audits previos en `{repo}/audit_reports/`.
- Lista de hallazgos 🔴 destacada visualmente.
- Versión imprimible / one-pager.

### 4.3 Archivo paralelo en docs/

Cada audit se guarda en `audit_reports/` con timestamp. Las auditorías son artefactos versionados — no se sobreescriben. El histórico permite el `Comparison with previous self-audit`.

---

## 5. Calibración del primer audit

El primer audit (este) sirve también como **baseline**. Establece el punto de partida contra el que se medirán las futuras ejecuciones. Por tanto:

- Las puntuaciones del baseline deben ser realistas. Tendencia natural en un primer audit: ser demasiado generoso porque "está en mi cabeza" o demasiado crítico porque "soy yo el responsable de las carencias". El instrumento corrige esto pidiendo evidencia con file:line para cualquier afirmación.
- El baseline debe identificar **al menos** los hallazgos 🔴 que un auditor externo encontraría. Si el baseline reporta cero hallazgos 🔴, la calibración es defectuosa.
- El baseline establece las "fortalezas genuinas" iniciales. Estas son piezas que, en futuros audits, deben mantener su nivel — perderlas es una alarma.

---

## 6. Limitaciones declaradas

- El instrumento detecta lo que es visible en el código y los docs. **No detecta** problemas de producto, de UX, de mercado, de equipo. Es un instrumento técnico.
- El discriminador 🟢/🟡/🔴 depende de la fidelidad del inventario / roadmap. Si el inventario está desactualizado, hallazgos 🟡 reales pueden parecer 🔴. Por eso el inventario y el roadmap son artefactos vivos que se actualizan en cada iteración.
- La rúbrica de Alfred sobre LlullGen es el referente. Si Alfred actualiza su rúbrica para LlullGen, este instrumento también se actualiza para mantener la traducibilidad.
- Un self-audit no sustituye un audit externo. Captura el 80%; el 20% requiere ojos ajenos. Por eso el ciclo es "self-audit antes de external review", no "self-audit instead of external review".
