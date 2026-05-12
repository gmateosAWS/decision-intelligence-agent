# ADR-004 — Stack de frontend de la plataforma llull

| Campo | Valor |
|---|---|
| **Estado** | Propuesta |
| **Fecha** | 2026-05-12 |
| **Autor** | Gustavo Mateos (Architect) |
| **Decisores** | Architect (autor), CEO Inverence (revisión) |
| **Supersede** | — |
| **Superseded by** | — |
| **Relacionada con** | ADR-002 (LangGraph orchestration), ADR-003 (reutilización LlullGen) |

---

## Contexto

La interfaz visual actual de llull es una aplicación Streamlit (`ui/` package, item 6.6 del inventario) desplegada en Streamlit Community Cloud. Esta interfaz ha cumplido su propósito: hacer demos en vivo, permitir interacción visual con el agente sin requerir conocimiento técnico del consumidor, y servir como vehículo para presentar el prototipo a dirección y a clientes potenciales.

Streamlit no es, sin embargo, el frontend de producto. Es una capa de presentación rápida que tiene limitaciones estructurales conocidas para el destino al que llull se dirige:

1. **Aspecto visual constreñido.** Toda app Streamlit se reconoce a primera vista como Streamlit. El sistema de tematización es limitado y la inyección de CSS es frágil entre versiones.
2. **Modelo de interacción request/rerun.** El ciclo de re-ejecución completa del script con cada interacción del usuario es funcional para dashboards pero no encaja con experiencias conversacionales con streaming, edición visual de modelos causales (DAG builder, item 3.1 — Iteración 3), o paneles de control con múltiples áreas independientes que se actualizan de forma asíncrona.
3. **Componentes complejos limitados.** No existe un equivalente Streamlit nativo a un editor de grafos tipo React Flow, command palettes, data tables con virtualización, o sheets/modales con composición libre. Cuando se necesitan, hay que importar componentes custom comunitarios de mantenimiento irregular.
4. **Multi-tenancy y SSO empresarial** (items 7.1, 7.6, 7.7 del inventario) requieren un frontend con control real sobre routing, sesión y autorización del lado cliente. Streamlit puede convivir con esto a base de parches, pero no es su modelo.

Necesitamos declarar formalmente el stack de frontend de la plataforma llull para producto, por tres razones:

1. **Técnica.** El frontend condiciona items concretos del roadmap v4: 3.1 (DAG builder visual, Iteración 3), 6.2 (WebSockets/SSE para streaming del agente, item del inventario), 7.6/7.7 (SSO, RBAC desde UI), y la forma de consumir la API REST `/v1/...` que ya existe (item 6.1.e). También condiciona el sistema de diseño con el que se construirán todas las pantallas futuras.

2. **Coherencia con la dirección de producto.** El CEO ha referenciado explícitamente shadcn/ui y tweakcn como referencias del tipo de interfaz que quiere para llull. La decisión debe quedar registrada con su rationale y con las decisiones complementarias (framework de aplicación, lenguaje, estado servidor, editor de grafos) que se derivan de adoptar shadcn como sistema de componentes.

3. **Estructura de repositorios.** Esta decisión condiciona también si el frontend vive en el mismo repo que el backend (monorepo) o en un repo separado. Conviene declararlo ahora con criterio, antes de que la elección se haga por inercia.

## Opciones consideradas

Cinco dimensiones de decisión, evaluadas explícitamente.

### Dimensión 1 — Framework de aplicación

#### Opción A — Next.js 14+ con App Router [DECISIÓN]

Framework React con renderizado server-side, App Router (basado en React Server Components), streaming nativo, route handlers para BFF ligero, y soporte de primera clase para Tailwind y shadcn/ui. Es la elección por defecto asumida por toda la documentación moderna de shadcn/ui desde 2024.

#### Opción B — Vite + React Router

Stack puramente cliente, más simple de configurar, sin server-side rendering. Menor superficie de framework, mayor control. Pierde streaming SSR nativo y route handlers; el resto se puede suplir.

#### Opción C — Remix

Filosofía web-standards, excelente data loading. Cuota de mercado y disponibilidad de talento menor que Next.js. Menos ejemplos shadcn oficiales.

### Dimensión 2 — Sistema de componentes

#### Opción A — shadcn/ui [DECISIÓN]

Colección de componentes React + Tailwind que se copian al repo del proyecto mediante CLI (`npx shadcn@latest add ...`). Filosofía "owned components, not dependency": cada componente es código fuente versionado dentro del propio repo, modificable sin restricciones. Theming mediante CSS variables.

#### Opción B — Material UI / Mantine / Chakra

Librerías tradicionales con componentes empaquetados como dependencia. Más completas out-of-the-box, menos personalizables sin "luchar contra el framework". Estética reconocible que aleja del aspecto distintivo deseado.

#### Opción C — Componentes desde cero sobre Tailwind

Máximo control, máximo coste. No hay razón para construir desde cero lo que shadcn ya entrega como base modificable.

### Dimensión 3 — Tematización

#### Opción A — tweakcn como herramienta de diseño + CSS variables como mecanismo [DECISIÓN]

Editor visual web (tweakcn.com) para definir tokens de diseño (colores, radius, tipografía, sombras) sobre shadcn/ui. Exporta un bloque CSS con variables que se pega en `app/globals.css`. Todos los componentes shadcn ya añadidos al repo heredan el tema automáticamente.

#### Opción B — Tema manual en `globals.css` sin herramienta visual

Más control granular, mucho menos productivo para iteración visual rápida con stakeholders no técnicos. tweakcn no cierra esta puerta: el output es CSS estándar, editable manualmente después.

### Dimensión 4 — Editor visual de DAG

#### Opción A — @xyflow/react (anteriormente React Flow) [DECISIÓN]

Librería de referencia para editores de grafos en React. v12 renombrada a `@xyflow/react`. Soporte completo de nodos custom, edges custom, layout algorítmico (con `dagre` o `elkjs` integrables), minimap, controles. Coexiste sin fricción con shadcn/ui y Tailwind.

#### Opción B — D3.js directo

Más bajo nivel, más control, mucho más coste de implementación. Justificable solo si las necesidades exceden lo que React Flow cubre, que no es el caso para el DAG builder del item 3.1.

### Dimensión 5 — Estructura de repositorios

#### Opción A — Repo separado `llull-front`, independiente de `llull` (backend) [DECISIÓN]

Dos repos con ciclos de release independientes. El contrato entre ambos es la API REST `/v1/...` (item 6.1.e). Los tipos TypeScript del cliente se generan desde el OpenAPI de FastAPI (`openapi-typescript` u `orval`), de modo que el frontend consume tipos derivados del contrato, no del código fuente del backend.

#### Opción B — Monorepo (Turborepo o Nx)

Un solo repo con `apps/backend` (Python) + `apps/frontend` (Node). Permite cambios atómicos cross-stack y compartir paquetes internos. Aporta complejidad de tooling (Node + Python en el mismo CI, configuración de Turborepo, gestión de permisos por path) sin beneficio real cuando los stacks son disjuntos y solo hay dos servicios.

## Análisis

### Por qué Next.js App Router

Tres razones concretas:

- **Server Components y streaming nativo** encajan con la naturaleza del producto: respuestas del agente que llegan en chunks (SSE/WebSocket), explicaciones que se generan progresivamente, visualizaciones que se calculan en el servidor. Es un patrón nativo, no un parche.
- **Es el stack documentado por defecto de shadcn/ui.** Toda la documentación oficial, todos los blocks pre-construidos y todos los ejemplos asumen Next.js App Router. Salirse de ahí significa traducir continuamente.
- **Disponibilidad de talento.** Next.js es el framework React más demandado en el mercado actual. Cualquier desarrollador frontend que llegue al proyecto entra sin curva inicial.

Vite + React Router se descarta porque pierde el streaming SSR y los route handlers, que son útiles tanto para BFF ligero (proxy autenticado contra el FastAPI de llull) como para SEO de la futura landing pública. Remix se descarta por menor cuota de mercado de talento y menor cantidad de ejemplos shadcn oficiales — no es peor técnicamente, pero introduce fricción innecesaria.

### Por qué shadcn/ui

La filosofía "owned components" alinea con la disciplina arquitectónica del proyecto. En lugar de depender de versiones de una librería externa, cada componente vive en `components/ui/` del repo, es modificable, es revisable en code review como cualquier otro código, y no añade superficie de dependencia que pueda romperse en un upgrade. Es el mismo principio que ya aplicamos en otros lugares: tener control sobre los seams arquitectónicos (RunSink Protocol, MemoryService, runner), no depender de cajas negras.

Material UI, Mantine y Chakra se descartan porque su estética es reconocible y aleja del aspecto distintivo que el CEO ha pedido como referencia. Construir componentes desde cero sobre Tailwind se descarta porque shadcn ya entrega la base correcta como punto de partida modificable.

### Por qué tweakcn

Es una herramienta de productividad de diseño, no una decisión técnica fuerte: el output es CSS estándar y el proyecto no queda atado a la herramienta. Permite a stakeholders no técnicos (en particular, al CEO o a un diseñador futuro) iterar sobre el theme visualmente sin tocar código. El theme se exporta una vez, se commitea en el repo, y a partir de ahí se mantiene como cualquier otro asset.

### Por qué @xyflow/react

Es el estándar de facto para editores de grafos en React. El DAG builder del item 3.1 (Iteración 3 del roadmap) es exactamente el caso de uso para el que xyflow está diseñado. Construirlo desde cero con D3 o con SVG manual es trabajo sin retorno cuando ya existe la solución madura.

### Por qué repo separado

Cinco razones concretas:

- **Ciclos de release muy distintos.** Backend con iteraciones de arquitectura profundas (multi-agente, ObjectBus, governance) y CI/CD afinado para Python + Postgres + integration tests reales. Frontend con iteraciones rápidas en visual y UX. Mezclarlos significa pipelines de CI más largos y permisos cruzados que no aportan.
- **Stacks tecnológicos disjuntos.** Backend = Python + uv/pip-tools + ruff + mypy + pytest. Frontend = Node + pnpm + ESLint + TypeScript + Vitest/Playwright. No comparten un solo tooling. Un monorepo aquí solo aporta complejidad sin beneficio real.
- **Contrato ya existente.** La API REST `/v1/...` es el contrato entre ambos. El cliente TypeScript se genera desde el OpenAPI del FastAPI. Esto funciona igual de bien con dos repos y obliga a una disciplina de contrato más limpia.
- **Política y permisos.** Cuando el repo actual (personal del architect) se forke a `llull` bajo Inverence, mantener el frontend en repo separado permite scoping explícito de permisos por equipo.
- **Reversibilidad.** Migrar de dos repos a monorepo cuando aparezca un trigger real es una operación mecánica de 1-2 días. Por defecto, conviene empezar con la opción menos comprometida.

Monorepo se reconsidera si emergen los disparadores documentados en la sección "Revisión".

### Riesgos asumidos

- **Acoplamiento al ecosistema shadcn / Tailwind / Next.js.** Si alguno cambia significativamente de licencia, pricing o dirección, hay coste de migración. Mitigación: shadcn es código vendoreado en el propio repo, no una dependencia; Tailwind es open source con governance distribuida; Next.js tiene cuota de mercado dominante. El riesgo combinado es bajo.
- **Curva de aprendizaje de App Router** vs Pages Router para desarrolladores con experiencia previa solo en este último. Mitigación: la documentación oficial es buena y App Router es el patrón asumido por todo el ecosistema desde 2024.

## Decisión

**Adoptamos el siguiente stack de frontend para la plataforma llull:**

| Capa | Tecnología | Notas |
|---|---|---|
| Framework de aplicación | **Next.js 14+ con App Router** | TypeScript strict mode |
| Lenguaje | **TypeScript** | `strict: true` en `tsconfig.json` |
| Sistema de componentes | **shadcn/ui** | Componentes vendoreados en `components/ui/` |
| Estilado | **Tailwind CSS** | Configuración estándar de shadcn |
| Tematización | **tweakcn** como herramienta, **CSS variables** como mecanismo | Output exportado a `app/globals.css` |
| Editor visual de DAG | **@xyflow/react** | Para el DAG builder del item 3.1 |
| Gestión de estado servidor | **TanStack Query (React Query)** | Estándar de facto con shadcn |
| Cliente HTTP | **`fetch` nativo** + cliente TS generado desde OpenAPI | Sin axios |
| Generación de tipos | **`openapi-typescript`** o **`orval`** sobre el OpenAPI de FastAPI | Cliente regenerable en CI |
| Streaming del agente | **SSE como primera opción**, WebSocket si hace falta bidireccionalidad real | Item 6.2 del inventario |
| Testing | **Vitest** (unit) + **Playwright** (e2e) | |
| Linting / formato | **ESLint** + **Prettier** | |
| Package manager | **pnpm** | |

Detalles operativos:

- **Estructura de repositorios: dos repos independientes.** `llull` para backend/plataforma (fork del repo actual cuando entre en Inverence), `llull-front` para el frontend de producto. El contrato es la API REST `/v1/...` ya existente.
- **Identidad visual: dependencia explícita.** El logo `||u||` está confirmado como elemento de marca presente y reutilizable (ver código de referencia en sección "Identidad visual" más abajo). La paleta, tipografía y resto de tokens de diseño quedan pendientes de guía formal por parte de Inverence. Hasta entonces, el theme tweakcn se mantiene en un default neutro (escala de grises + un acento provisional), sin inventarse identidad corporativa.
- **Streamlit no se elimina.** La app actual sigue viva mientras `llull-front` no cubra el mismo terreno funcional. Es la misma estrategia que ADR-002 con el grafo actual: lo nuevo es aditivo, no sustitutivo.
- **Co-existencia durante la transición.** Tanto Streamlit como `llull-front` consumen la misma API REST de llull. No hay duplicación de lógica de negocio; ambas son capas de presentación sobre el mismo Agent Service (item 6.1.e).
- **Primera pantalla de validación.** El primer hito de `llull-front` es replicar el chat conversacional contra `POST /v1/query`, con streaming de respuesta y badge tool+latencia. Esto valida el stack completo (Next.js + shadcn + theme + cliente TS generado + streaming) sobre una superficie controlada antes de extenderse a más pantallas.

## Identidad visual — código de referencia actual del logo

Para preservar la identidad gráfica existente y permitir replicación 1:1 en el frontend nuevo, el logo actual de la app Streamlit se define así:

```python
LOGO_FULL = (
    '<span style="font-family: Georgia, serif; font-size: 52px; '
    'font-weight: 400; letter-spacing: -2px; line-height: 1;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
)

LOGO_COMPACT = (
    '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">'
    '<span style="font-family: Georgia, serif; font-size: 26px; '
    'font-weight: 400; letter-spacing: -1px;">'
    '||<span style="font-weight: 700;">u</span>||</span>'
    '<span style="font-size: 15px; color: #6b7280;">Decision Intelligence Agent</span>'
    "</div>"
)
```

Características preservables en el frontend nuevo:

- Tipografía Georgia serif (acento clásico) sobre el resto del producto en sans-serif moderna.
- Las pleca verticales `||` con peso regular (400) y la `u` con peso bold (700).
- Letter-spacing negativo para que el conjunto se lea como una sola unidad visual.
- Versión compacta con subtítulo en gris `#6b7280` (token shadcn `muted-foreground`).

En `llull-front` se materializa como componente React `<LlullLogo variant="full" | "compact" />` con los mismos parámetros.

## Consecuencias

### Positivas

- **Dirección visual del producto queda declarada.** Las próximas iteraciones de UI no son negociaciones puntuales: hay un sistema de diseño, una herramienta de tematización, y un destino arquitectónico claro.
- **Streamlit se preserva como lo que es:** capa de demo y desarrollo rápido, no destino. Cero presión de tener que migrar inmediatamente.
- **El DAG builder del item 3.1 (Iteración 3) queda implementable directamente** sobre @xyflow/react sin decisiones intermedias.
- **El contrato API REST se refuerza como seam arquitectónico.** Al consumirse desde un frontend externo con tipos generados, cualquier ruptura de contrato se detecta en CI del frontend.
- **Identidad visual existente queda preservada** sin pérdida en la transición.
- **Disponibilidad de talento.** Next.js + shadcn + TypeScript es el stack más demandado actualmente; cualquier desarrollador frontend que llegue al proyecto entra sin curva.

### Negativas asumidas

- **Mayor superficie de mantenimiento.** Dos repos, dos pipelines de CI, dos sets de dependencias a actualizar. Es coste real, asumido conscientemente como precio de tener un frontend de producto en lugar de un Streamlit indefinidamente.
- **Curva inicial.** El architect no tiene experiencia previa en Next.js App Router. Mitigación: stack documentado masivamente, primera pantalla acotada como validación, el riesgo es de plazos no de viabilidad.
- **Coste de generar el primer theme distintivo.** Sin guía de identidad formal, el primer theme será necesariamente provisional. Mitigación: el theme es regenerable; lo que se construya con shadcn no depende del theme concreto, solo de que existan las CSS variables.

### Neutras / a monitorizar

- **Política de versionado de Next.js.** Vercel ha tenido cambios de pricing y de dirección del framework en los últimos años. Pinear versión mayor en `package.json` y revisar minor updates de forma deliberada.
- **Madurez de @xyflow/react v12.** La librería es estable, pero el rename desde "reactflow" es reciente. Documentar la versión adoptada y revisar breaking changes en upgrades.
- **Performance de SSR con streaming del agente bajo carga.** Cuando aparezca tráfico real piloto, medir tiempos de Time-to-First-Byte y ajustar estrategia de streaming si hace falta.

## Items del inventario afectados

Esta decisión condiciona la implementación de los siguientes items:

- **3.1** — DAG builder visual (Iteración 3), implementado con @xyflow/react.
- **6.1.e** — API REST como contrato entre frontend y backend. Refuerzo de su rol como seam.
- **6.2** — WebSockets / SSE para streaming del agente. SSE como primera opción.
- **6.6** — Interfaz Streamlit, que se conserva durante la transición sin presión de migración inmediata.
- **7.6, 7.7** — SSO y RBAC desde la UI, implementables con NextAuth.js o similar sobre Next.js.
- **12.8** — Proceso de onboarding documentado, que asumirá pantallas de `llull-front` como vehículo.

## Referencias

- shadcn/ui: documentación oficial — https://ui.shadcn.com
- tweakcn: editor visual de temas para shadcn — https://tweakcn.com
- @xyflow/react (anteriormente React Flow): https://reactflow.dev
- Next.js App Router: documentación oficial.
- Inventario llull v4 — items 3.1, 6.1.e, 6.2, 6.6, 7.6, 7.7, 12.8.
- Roadmap llull v4 — Iteración 3, paquete "DAG builder y onboarding".
- ADR-002 — Decisión sobre orquestación que define el Agent Service (6.1.e) como seam encapsulado, condición previa para que un frontend externo pueda existir.

## Revisión

Esta decisión se revisa cuando:

- **Estructura de repositorios:** si el número de servicios deployables crece a 3 o más, o si emerge un paquete de tipos/utilidades que necesita compartirse entre múltiples servicios, reevaluar monorepo (Turborepo/Nx).
- **Framework de aplicación:** si Vercel cambia significativamente pricing, licencia o dirección de Next.js de forma que afecte al proyecto, evaluar migración a Vite + React Router o Remix.
- **Sistema de componentes:** si emerge un sistema alternativo a shadcn/ui con tracción equivalente y ventajas técnicas claras, evaluar adopción. El coste de migración es bajo porque los componentes ya están vendoreados.
- **Editor de grafos:** si las necesidades del DAG builder exceden lo que @xyflow/react cubre (p.ej. visualización 3D, grafos de más de 10.000 nodos en cliente), reevaluar.
- **Streaming:** si SSE muestra limitaciones reales bajo carga piloto, migrar a WebSocket.

Fuera de estos disparadores, la decisión se considera estable.
