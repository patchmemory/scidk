# MVP Architecture Overview (Revised — Interpreter‑centric)

This document aligns the MVP architecture with the Interpreter Management System and current repository terminology. Interpreters are lightweight, read‑only metadata extractors that understand specific file formats.

## Core UI Areas
- Home / Scan: start scans via POST /api/scan (or background via /api/tasks)
- Files / Browse: explore scan snapshot via GET /api/scans/<id>/fs
- Interpreters: render per‑file insights (Python, CSV, IPYNB for MVP)
- Map: view schema and export instances
- Interpreter Settings: configure interpreter assignments/rules and registration
- Rclone Mounts (feature‑flagged): manage safe local FUSE mounts
- Background Tasks: monitor async scan/interpret/commit

## Key APIs (MVP)

### Filesystem providers
- GET /api/providers
- GET /api/provider_roots?provider_id=<id>
- GET /api/browse?provider_id=<id>&root_id=<root>&path=<path>[&recursive=false&max_depth=1&fast_list=false]
- POST /api/scan
- GET /api/datasets, GET /api/datasets/<id>

### Scans
- GET /api/scans/<scanId>/status
- GET /api/scans/<scanId>/fs
- POST /api/scans/<scanId>/interpret
  - Body: { include?, exclude?, max_size_bytes?, after_rowid?, max_files?, overwrite? }
  - Returns: { status, processed_count, error_count, filtered_by_size, filtered_by_include, filtered_no_interpreter, next_cursor }
- POST /api/scans/<scanId>/commit
  - Returns commit summary including optional Neo4j verification fields

### Background tasks
- POST /api/tasks { type: 'scan' | 'commit' | 'interpret', ... }
- GET /api/tasks, GET /api/tasks/<task_id>

### Interpreters: registry and execution
- GET /api/interpreters → list available interpreters { id, name, runtime, supported_extensions, metadata_schema }
- GET /api/interpreters/<interpreter_id>
- POST /api/interpreters → register new interpreter { name, runtime, extensions, script, metadata_schema, ... }
- POST /api/interpreters/<interpreter_id>/test → run test on a sample file { file_path } → { status, result, errors, warnings, execution_time_ms }

### Graph: schema and instance exports
- GET /api/graph/schema
- GET /api/graph/schema.neo4j (optional; 501 if driver/misconfig)
- GET /api/graph/schema.apoc (optional; 502 if APOC unavailable)
- GET /api/graph/instances.csv?label=<Label>
- GET /api/graph/instances.xlsx?label=<Label> (requires openpyxl)
- GET /api/graph/instances.arrow?label=<Label> (requires pyarrow)
- GET /api/graph/instances.pkl?label=<Label>

### Rclone Mount Manager (feature‑flagged)
- GET /api/rclone/mounts, POST /api/rclone/mounts, DELETE /api/rclone/mounts/<id>
- GET /api/rclone/mounts/<id>/logs?tail=N, GET /api/rclone/mounts/<id>/health

## Interpreter Settings
- File type assignments: map extensions → interpreters (e.g., .py → Python Interpreter)
- Pattern rules: conditional selection (e.g., OME‑TIFF for /microscopy/*.tif)
- Custom interpreters: register/upload user interpreters
- Execution config: timeouts, caching, parallelization, sampling
- Neo4j connection: URI/auth; used by optional schema endpoints and commit flows
- Feature flags summary: active providers and enabled features

## Mental Model
- Home → POST /api/scan, poll status
- Browse → GET /api/scans/<id>/fs
- Interpreters → POST /api/scans/<id>/interpret, then read results
- Map → GET /api/graph/schema* and /api/graph/instances.*
- Interpreter Settings → GET/POST /api/interpreters
- Rclone Mounts → /api/rclone/mounts*

## Feature Flags & Env
- SCIDK_PROVIDERS: local_fs,mounted_fs[,rclone]
- SCIDK_RCLONE_MOUNTS or SCIDK_FEATURE_RCLONE_MOUNTS: toggles Mount Manager
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_AUTH
- Optional deps: openpyxl, pyarrow

## Out of Scope (MVP)
- Persistent graph storage by default (Neo4j planned)
- Full RO‑Crate export and direct file streaming endpoints
- Advanced interpreter features (remote/distributed, full audit trails)

## E2E Next Steps
- Add E2E coverage for interpreter execution pipeline (register → test → apply to scan).
