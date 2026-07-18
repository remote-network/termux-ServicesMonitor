# Graph Report - termux-ServicesMonitor  (2026-07-18)

## Corpus Check
- 11 files · ~4,435 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 139 nodes · 251 edges · 7 communities (6 shown, 1 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 28 edges (avg confidence: 0.74)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2734d63f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Services Monitor
- Configurarlo como servicio de `termux-services`
- crear_resumen

## God Nodes (most connected - your core abstractions)
1. `FakeSession` - 21 edges
2. `FakeResponse` - 17 edges
3. `cargar_ajustes()` - 10 edges
4. `TestComprobarServicio` - 10 edges
5. `Services Monitor` - 10 edges
6. `ConfigError` - 9 edges
7. `comprobar_servicio()` - 9 edges
8. `main()` - 9 edges
9. `TestConstruirServicio` - 9 edges
10. `servicio()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `TestComprobarServicio` --uses--> `FakeResponse`  [INFERRED]
  tests/test_checker.py → tests/_fakes.py
- `TestMonitorRun` --uses--> `FakeResponse`  [INFERRED]
  tests/test_monitor.py → tests/_fakes.py
- `TestNotifier` --uses--> `FakeResponse`  [INFERRED]
  tests/test_notifier.py → tests/_fakes.py
- `TestComprobarServicio` --uses--> `FakeSession`  [INFERRED]
  tests/test_checker.py → tests/_fakes.py
- `TestMonitorRun` --uses--> `FakeSession`  [INFERRED]
  tests/test_monitor.py → tests/_fakes.py

## Import Cycles
- None detected.

## Communities (7 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.12
Nodes (16): 1. Crear el servicio a partir del ejemplo, 2. (Opcional) Logging con `svlogger`, 3. Comandos de control, 4. Mantenerlo vivo y arranque automático, Archivos que genera el script, Configuración, Credenciales y ajustes globales (`.env` o variables de entorno), Ejecutar como servicio de `termux-services` (+8 more)

### Community 1 - "Community 1"
Cohesion: 0.13
Nodes (19): Any, Event, ahora(), cargar_estado(), comprobar_servicio(), crear_mensaje_estado(), crear_resumen(), evaluar() (+11 more)

### Community 2 - "Community 2"
Cohesion: 0.12
Nodes (9): FakeResponse, FakeSession, Dobles de prueba para no tocar la red real., Devuelve respuestas (o lanza excepciones) de una cola configurable., servicio(), TestComprobarServicio, ajustes(), TestMonitorRun (+1 more)

### Community 3 - "Community 3"
Cohesion: 0.17
Nodes (20): Exception, Namespace, Ajustes, cargar_ajustes(), ConfigError, configurar_logging(), construir_servicio(), construir_servicios() (+12 more)

### Community 4 - "Services Monitor"
Cohesion: 0.13
Nodes (3): TestCargarAjustes, TestConstruirServicio, TestConstruirServicios

### Community 5 - "Configurarlo como servicio de `termux-services`"
Cohesion: 0.17
Nodes (4): Path, cargar_dotenv(), Carga variables de un archivo .env SIN pisar las ya definidas en el entorno., TestEstado

## Knowledge Gaps
- **13 isolated node(s):** `Qué hace `services_monitor.py``, `Requisitos`, `Instalación`, `Credenciales y ajustes globales (`.env` o variables de entorno)`, `Lista de servicios (`services.json`)` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Are the 15 inferred relationships involving `FakeSession` (e.g. with `TestComprobarServicio` and `.test_activo()`) actually correct?**
  _`FakeSession` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `FakeResponse` (e.g. with `TestComprobarServicio` and `.test_activo()`) actually correct?**
  _`FakeResponse` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TestComprobarServicio` (e.g. with `FakeResponse` and `FakeSession`) actually correct?**
  _`TestComprobarServicio` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Qué hace `services_monitor.py``, `Requisitos`, `Instalación` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.11764705882352941 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1339031339031339 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.12477718360071301 - nodes in this community are weakly interconnected._