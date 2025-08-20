# SciDK MVP - Run Instructions

This is a minimal runnable MVP to satisfy the current cycle's GUI acceptance: a simple Flask UI that can scan a directory and display datasets with basic Python code interpretation.

## Quick Start

1) Install dependencies (prefer a virtualenv):
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Initialize environment variables (recommended):
- bash/zsh:
```
# Export variables for this shell
source scripts/init_env.sh
# Optionally write a .env file for tooling
source scripts/init_env.sh --write-dotenv
```
- fish shell:
```
# Export variables for this shell
source scripts/init_env.fish
# Optionally write a .env file for tooling
source scripts/init_env.fish --write-dotenv
```

3) Run the server:
```
scidk-serve
# or
python -m scidk.app
```

4) Open the UI in your browser:
- http://127.0.0.1:5000/

5) Use the "Scan Files" form to scan a directory (e.g., this repository root). Python files will be interpreted to show imports, functions, and classes.

Note: The scanner prefers NCDU for fast filesystem enumeration when available. Install NCDU via your OS package manager (e.g., `brew install ncdu` on macOS or `sudo apt-get install ncdu` on Debian/Ubuntu). If NCDU is not installed, the app falls back to Python traversal.

## Troubleshooting
- Editable install error (Multiple top-level packages discovered): We ship setuptools config to include only the scidk package. If you previously had this error, pull latest and try again: `pip install -e .`.
- Shell errors when initializing env: Use the script matching your shell (`init_env.sh` for bash/zsh, `init_env.fish` for fish). Avoid running `sh scripts/init_env.sh`; instead, source it.

## Neo4j Password: How to Set/Change
- Choose your password before first start by setting NEO4J_AUTH in .env or your shell:
  - echo "NEO4J_AUTH=neo4j/StrongPass123!" >> .env
  - docker compose -f docker-compose.neo4j.yml up -d
- Change an existing password:
  - With container: scripts/neo4j_set_password.sh 'NewPass123!' --container scidk-neo4j --current 'OldPass!'
  - Local cypher-shell: scripts/neo4j_set_password.sh 'NewPass123!' --host bolt://localhost:7687 --user neo4j --current 'OldPass!'
- More details in dev/deployment.md (includes direct cypher-shell commands).

## API

### Filesystem Providers (MVP)
- Feature flag: set SCIDK_PROVIDERS to a comma-separated list (default: local_fs,mounted_fs)
- GET /api/providers → [{ id, display_name, capabilities, auth }]
- GET /api/provider_roots?provider_id=local_fs → list available roots/drives for the provider
- GET /api/browse?provider_id=local_fs&root_id=/&path=/home/user → { entries: [ { id, name, type, size, mtime, provider_id } ] }
- POST /api/scan { provider_id, root_id?, path, recursive? } → starts a scan using the provided path
  - Legacy: provider_id omitted defaults to local_fs and scans the local filesystem path
- POST /api/scan {"path": "/path", "recursive": true}
- GET /api/datasets
- GET /api/datasets/<id>

## Testing
We use pytest for unit and API tests.

Pytest is included in requirements.txt; after installing dependencies, run:
```
pytest
```

Conventions:
- Tests live in tests/ and rely on pytest fixtures in tests/conftest.py (e.g., Flask app and client).
- Add tests alongside new features in future cycles; see dev/cycles.md for cycle protocol.

## Notes
- This MVP uses an in-memory graph; data resets on restart.
- Neo4j deployment docs reside in dev/deployment.md, but Neo4j is not yet wired in the MVP code.

## Scanning progress and background tasks (ncdu/gdu)
- Current behavior: POST /api/scan runs synchronously and returns when complete.
- Near-term plan: run ncdu (or gdu) as a background task and expose polling endpoints:
  - POST /api/tasks (type=scan) → returns task_id; GET /api/tasks/<id> for status/progress; GET /api/tasks for list (multiple concurrent tasks supported).
  - When available, we will stream ncdu JSON and compute percent scanned by summing completed nodes; otherwise show a spinner and file count as it grows.
- For now, scanning prefers ncdu or gdu for fast enumeration when installed; otherwise falls back to Python traversal.

## Map page visualization tuning
- On /map you can:
  - Switch layouts (Force/breadthfirst/manual) and Save/Load positions.
  - Adjust Node size, Edge width, and Label font via UI sliders; enable High-contrast labels for readability.
  - Download the current schema as CSV.
  - Preview and download instances for File, Folder, and Scan labels as CSV (XLSX if openpyxl is installed).

## Neo4j integration
- Status: The app ships with docker-compose.neo4j.yml to run a local Neo4j, but the Flask app currently uses an in-memory graph.
- Next steps to enable Neo4j writes/reads:
  1) Add a GraphAdapter interface and a Neo4jAdapter implementing upsert_dataset, add_interpretation, commit_scan, schema_triples.
  2) Add config/feature flag (e.g., SCIDK_GRAPH_BACKEND=neo4j) to switch adapters.
  3) Map current in-memory structures to Neo4j schema: (:File), (:Folder), (:Scan) nodes and CONTAINS, INTERPRETED_AS, SCANNED_IN relationships.
  4) Use Cypher or APOC to compute schema triples for /api/graph/schema.
- Until then, data is not persisted to Neo4j. Use the CSV exports or the in-memory map for the demo.


## New in this cycle: Optional Neo4j schema endpoints and extra Instance exports

Neo4j-backed schema (optional; in addition to the default in-memory /api/graph/schema):
- GET /api/graph/schema.neo4j — Uses Cypher to return nodes and unique relationship triples with counts.
- GET /api/graph/schema.apoc — Uses APOC (apoc.meta.data and apoc.meta.stats). Returns 502 if APOC procedures are not available.

Environment variables required for Neo4j schema endpoints:
- NEO4J_URI (e.g., bolt://localhost:7687)
- NEO4J_USER
- NEO4J_PASSWORD
- SCIDK_NEO4J_DATABASE (optional; defaults to the driver/session default)

Notes:
- If the neo4j Python driver is not installed, these endpoints return 501 with an explanatory error.
- If Neo4j or credentials are not configured, these endpoints return 501. The app’s default in-memory /api/graph/schema remains fully functional.

Additional Instance export formats:
- GET /api/graph/instances.pkl?label=<Label> — Python pickle of the rows (application/octet-stream).
- GET /api/graph/instances.arrow?label=<Label> — Arrow IPC stream (requires pyarrow; returns 501 otherwise).
- Existing:
  - GET /api/graph/instances.csv?label=<Label>
  - GET /api/graph/instances.xlsx?label=<Label> (requires openpyxl; returns 501 otherwise)

Map page tweak:
- The Instances selector now defaults to the Scan label for a more demo-friendly starting point.
