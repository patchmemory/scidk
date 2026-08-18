# SciDK — Architecture & Status Handoff

_Snapshot date: 2026-06-22 · Branch: `production-mvp` @ `23ba225` (the de-facto trunk)_

> **Read this, not the root `README.md`.** The README has accreted ~2 years of per-cycle
> notes and is partly stale (e.g. it still claims "in-memory graph, Neo4j not wired" — false;
> Neo4j, a Concept Graph, and an MCP server are all wired in). This doc reflects the actual code.

---

## 1. What SciDK is
A Flask web app for **scientific data management on top of a knowledge graph**. It scans
filesystems (local, mounted, or rclone remotes), interprets files, builds a property graph in
Neo4j, and exposes an LLM chat interface (ReAct + GraphRAG) over that graph, plus an MCP server
so external agents (Claude Desktop, etc.) can query it.

## 2. Branch / repo topology (important)
- **`production-mvp`** is the real mainline — it contains all of `main` plus **320 commits** on top.
- **`main`** is a **stale snapshot frozen at 2026-03-02** (last PR `#52`). The PR→main review flow
  (PRs #32–#52, per `dev/README-planning.md`) stopped there. All March work (AI/Chat stack,
  scanner, Cytoscape fixes) was committed **directly to `production-mvp` and never PR'd into main**.
- **`dev/`** is a **git submodule** = the planning/docs repo (stories, phases, tasks, features;
  see `dev/README-planning.md`). It is NOT app runtime code.

## 3. Tech stack
- **Backend:** Python 3.12, Flask (app-factory + blueprints), Swagger/flasgger at `/api/docs`,
  `ProxyFix` for reverse-proxy/subpath deploys, gunicorn in prod (`restart_gunicorn.sh`).
- **Graph DB:** Neo4j 5 (`docker-compose.neo4j.yml`; Bolt 7687 / HTTP 7474). In-memory graph
  backend exists as a fallback (`SCIDK_STATE_BACKEND=memory`).
- **Relational/state:** SQLite with WAL — multiple DBs: `scidk.db`, `scidk_settings.db`,
  `scidk_path_index.db`. Auto-migrations run on boot (`scidk/core/migrations*`), reported via `/api/health`.
- **LLM:** pluggable providers — Ollama / Anthropic / OpenAI (`scidk/ai/provider_factory.py`,
  `llm_providers.py`). GraphRAG/embeddings stack is **optional** (`requirements-graphrag.txt`,
  PyTorch+CUDA, gated by `SCIDK_GRAPHRAG_ENABLED`).
- **Frontend:** server-rendered Jinja templates + vanilla JS; **Cytoscape.js** for graph viz
  (`scidk/ui/static/js/graph_utils.js`, `SciDKGraph`).
- **Tests:** pytest, 3 tiers via markers (`unit` / `integration` / `e2e`); Playwright for E2E.

## 4. App initialization — `scidk/app.py::create_app()`
Single application factory. Wires, in order:
1. Logging, channel defaults, ProxyFix, Swagger.
2. SQLite auto-migration; state-backend toggle (`sqlite` default).
3. **Graph backend** (`core/neo4j_config.create_graph_backend` → Neo4j or in-memory).
4. **Concept Graph driver** (optional, `SCIDK_CONCEPT_GRAPH_ENABLED=1`; graceful fallback to
   hard-coded intent classifier if unavailable).
5. Interpreter registry; FilesystemManager; FS providers (`local_fs`, `mounted_fs`, `rclone`).
6. Everything hung off `app.extensions['scidk']` (graph, concept_driver, registry, fs, providers,
   in-session registries for scans/tasks/directories, neo4j_config/state, rclone_mounts, settings).
7. Hydrate persisted state from SQLite (last scan, rclone mounts/settings, Neo4j creds).
8. Register **26 blueprints** (`web/routes/register_blueprints`); init auth middleware (RBAC).
9. **Plugin system**: label-endpoint registry, plugin-template registry, plugin-instance manager,
   plugin loader (discovers `plugins/`).
10. Backup scheduler (also runs Concept Graph weight-decay job).

## 5. Package layout (`scidk/`)
- **`ai/`** — LLM layer. `react_loop.py` (ReAct agent), `chat_graph.py`, `summarization.py`,
  `cypher_utils.py`, `mcp_tools.py`, `schema_context.py`, `provider_factory.py` / `llm_providers.py`.
- **`services/`** — business logic. Key ones:
  - `concept_graph_service.py` (~1k lines) — Concept Graph: semantic schema layer with weighted
    edges + decay, export/import, intent routing.
  - `schema_intelligence.py` (~675 lines) — editable schema intelligence (labels/profiles, embeddings).
  - `chat_neo4j_client.py`, `chat_service.py` — DB-persisted chat with permissions.
  - `graphrag/` (incl. `intent_classifier.py`) — LOOKUP vs REASONING routing, text-to-Cypher.
  - `neo4j_client.py`, `query_service.py`, `link_service.py` / `link_service_v2.py`,
    `label_service.py`, `fs_index_service.py`, `scan_index_service.py`, `commit_service.py`,
    `saved_maps_service.py`, `metrics.py`.
- **`web/routes/`** — 26 Flask blueprints (see §6). Pattern: `_get_ext()` to reach
  `app.extensions['scidk']`; background work uses threads with captured `app.app_context()`.
- **`core/`** — infra: migrations, neo4j/channel/rclone config, plugin loader + registries,
  backup manager/scheduler, alert manager, settings, logging.
- **`concept_graph/`** — `intents.yaml`, `schema.cypher` (Concept Graph seed/schema).
- **`interpreters/`, `labels/`, `schema/`, `scripts/`, `export/`** — file interpreters, label
  definitions, schema generation, script registry, exporters.
- **`mcp_server.py`** — standalone MCP server (`python -m scidk.mcp_server`), 5 read-only tools:
  `query_knowledge_graph`, `get_schema`, `summarize_dataset`, `get_label_profile`, `list_labels`.

## 6. HTTP surface — 26 blueprints (`scidk/web/routes/`)
UI (`ui.py`: `/`, `/datasets`, `/map`, `/chat`, `/settings`, …) + API blueprints:
`api_files`, `api_graph`, `api_maps`, `api_scripts`, `api_tasks`, `api_chat`, `api_queries`,
`api_neo4j`, `api_admin`, `api_interpreters`, `api_providers`, `api_annotations`, `api_labels`,
`api_integrations`, `api_links` (legacy) + `api_links_v2` (LinkRegistry), `api_settings`,
`api_auth`, `api_users`, `api_audit`, `api_alerts`, `api_logs`, `api_plugins`, `api_system`
(chat self-awareness), `api_results`.
_(The `web/routes/README.md` count of "9 blueprints / 91 routes" is outdated — it's 26 now.)_

## 7. Major subsystems delivered (newest → older)
- **AI / Chat stack (Mar 2026, production-mvp only):** Concept Graph (Phases 1–3: weighted edges,
  decay, MCP tools, export/import), Schema Intelligence editable UI, ReAct streaming chat with
  reasoning-block visualization, MCP server, Neo4j full-text indexes. Seed scripts at repo root
  (`seed_concept_graph*.py`, `seed_schema_embeddings.py`, `apply_concept_schema.py`).
- **Standalone filesystem scanner (Mar 2026):** `tools/scidk_scanner.py` + `_opt.py` —
  magic-byte detection + parallel enumeration; spec in `tools/SCIDK_SCANNER_SPEC.md`.
- **Cross-database transfer V2 (#51):** provenance, progress tracking, cancellation.
- **Security (#40):** multi-user auth + RBAC + DB-persisted chat with permissions.
- **Config backup/restore (#41) + auto-lock on inactivity (#44).**
- **Plugins:** `plugins/{example_plugin, example_ilab, table_loader, ilab_table_loader}` —
  UI-instantiable plugin templates + instances; the recent demo focused on the **iLab plugin +
  concept-graph seeding** (see the `dev` submodule branch `feature/ilab-plugin-and-demo-seeding`).
- **Providers:** rclone is core (feature flag removed, #31); FUSE mount manager under `./data/mounts/`.

## 8. How to run
```bash
pip install -e .[dev]                 # or requirements.txt (lite) / requirements-graphrag.txt (AI)
docker compose -f docker-compose.neo4j.yml up -d     # Neo4j (default creds neo4j/neo4jiscool)
scidk-serve                           # or: python -m scidk.app  → http://127.0.0.1:5000
python -m scidk.mcp_server            # MCP server for external agents
make unit | make integration | make e2e | make check   # tests
```
Key env: `SCIDK_STATE_BACKEND` (sqlite|memory), `SCIDK_PROVIDERS`, `NEO4J_URI`/`NEO4J_AUTH`,
`SCIDK_CONCEPT_GRAPH_ENABLED`, `SCIDK_GRAPHRAG_ENABLED`, `SCIDK_CHANNEL` (stable|dev), `SCIDK_BASE`
(subpath deploys). `.env` is auto-loaded via python-dotenv.

## 9. Open items / gotchas for the next agent
1. **main is stale.** Decide whether to back-merge the March AI/Chat + scanner work from
   `production-mvp` into `main`, or formally retire `main` in favor of `production-mvp`.
2. **`dev` submodule diverges** (47 local-only vs 8 pinned-only commits) on
   `feature/ilab-plugin-and-demo-seeding`. Reconcile before committing the superproject's `dev` pin.
3. **Stale root `README.md`** — large sections describe an earlier MVP; trust this doc + code instead.
4. **GraphRAG/AI features are optional and heavy** (PyTorch/CUDA) and degrade gracefully when off.
5. Repo root holds loose scripts/artifacts (`seed_*.py`, `*.db`, `htmlcov/`, `pytest_fully_output.txt`)
   that could use a cleanup pass.
</content>
