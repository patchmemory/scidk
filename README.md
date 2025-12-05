# SciDK MVP - Run Instructions

This is a minimal runnable MVP to satisfy the current cycle's GUI acceptance: a simple Flask UI that can scan a directory and display datasets with basic Python code interpretation.

## Quick Start

1) Install dependencies (prefer a virtualenv):
```
python3 -m venv .venv
# bash/zsh:
source .venv/bin/activate
# fish:
source .venv/bin/activate.fish
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
python3 -m scidk.app
```

4) Open the UI in your browser:
- http://127.0.0.1:5000/

5) Use the "Scan Files" form to scan a directory (e.g., this repository root). Python files will be interpreted to show imports, functions, and classes.

Note: The scanner prefers NCDU for fast filesystem enumeration when available. Install NCDU via your OS package manager (e.g., `brew install ncdu` on macOS or `sudo apt-get install ncdu` on Debian/Ubuntu). If NCDU is not installed, the app falls back to Python traversal.

## Troubleshooting
- Editable install error (Multiple top-level packages discovered): We ship setuptools config to include only the scidk package. If you previously had this error, pull latest and try again: `pip install -e .`.
- Shell errors when initializing env: Use the script matching your shell (`init_env.sh` for bash/zsh, `init_env.fish` for fish). Avoid running `sh scripts/init_env.sh`; instead, source it.

## End-to-End (E2E) tests

These tests run in a real browser using Playwright and pytest. The test suite automatically starts the Flask app on port 5001 with safe defaults and no external Neo4j connection.

Prereqs (once per machine):
- Python virtual environment activated.
- Install dev dependencies and Playwright browsers.

Commands:
```
# Install dev deps (if not yet installed)
pip install -e .[dev]

# Install Playwright browsers (Chromium, Firefox, WebKit)
make e2e-install-browsers  # or: python -m playwright install --with-deps

# Run headless E2E tests
make e2e                   # or: pytest -m e2e tests/e2e -q

# Run headed with inspector (debug mode)
make e2e-headed            # or: PLAYWRIGHT_HEADLESS=0 PWDEBUG=1 pytest -m e2e tests/e2e -q

# Parallel execution (if pytest-xdist is installed; falls back to serial)
make e2e-parallel
```

Notes:
- The E2E test fixture sets:
  - SCIDK_PORT=5001
  - NEO4J_AUTH=none
  - SCIDK_PROVIDERS=local_fs
  - SCIDK_DB_PATH=sqlite:///:memory:
- Ensure port 5001 is free before running, or adjust the fixture if needed.
- For verbose logs during a failing test, use: `make e2e-debug` or `pytest -m e2e -vv -s`.

## Neo4j Password: How to Set/Change
- Testing default: The testing Neo4j database uses password `neo4jiscool`. Set this in the app Settings or via environment.
- Choose your password before first start by setting NEO4J_AUTH in .env or your shell (example uses testing default):
  - echo "NEO4J_AUTH=neo4j/neo4jiscool" >> .env
  - docker compose -f docker-compose.neo4j.yml up -d
- Change an existing password:
  - With container: scripts/neo4j_set_password.sh 'NewPass123!' --container scidk-neo4j --current 'neo4jiscool'
  - Local cypher-shell: scripts/neo4j_set_password.sh 'NewPass123!' --host bolt://localhost:7687 --user neo4j --current 'neo4jiscool'
- More details in dev/ops/deployment-neo4j.md (includes direct cypher-shell commands).

### Troubleshooting Neo4j Unauthorized errors
- If you see "The client is unauthorized due to authentication failure" when committing:
  1) Ensure Settings → Neo4j has User=neo4j and Password=neo4jiscool (or your actual DB password).
  2) Or set env NEO4J_AUTH=neo4j/neo4jiscool before starting the app, or update .env and restart.
  3) Confirm Browser and app use the same DB: SHOW DATABASES; and :use neo4j.
  4) Retry Commit to Graph.

## API

### RO-Crate (Planned MVP)
- Endpoints to be implemented next:
  - GET /api/rocrate — Generate minimal RO-Crate JSON-LD for a selected directory (depth=1, capped)
  - GET /files — Stream file bytes for viewer previews/downloads
- See dev/features/ui/feature-rocrate-viewer-embedding.md for contracts and UI integration plan.

### Filesystem Providers (MVP)
- Feature flag: set SCIDK_PROVIDERS to a comma-separated list (default: local_fs,mounted_fs)
- GET /api/providers → [{ id, display_name, capabilities, auth }]
- GET /api/provider_roots?provider_id=local_fs → list available roots/drives for the provider
- GET /api/browse?provider_id=local_fs&root_id=/&path=/home/user → { entries: [ { id, name, type, size, mtime, provider_id } ] }
- POST /api/scan { provider_id, root_id?, path, recursive? } → starts a scan using the provided path
  - For provider_id=rclone: MVP supports a metadata-only scan (records the session without local file enumeration).
  - Legacy: provider_id omitted defaults to local_fs and scans the local filesystem path
- POST /api/scan {"path": "/path", "recursive": true}
- GET /api/datasets
- GET /api/datasets/<id>

Rclone provider (optional):
- Enable by installing rclone and setting SCIDK_PROVIDERS=local_fs,mounted_fs,rclone (or include rclone among others).
- UI: See docs/rclone/quickstart.md (README-ready snippet: dev/features/providers/README-snippet-rclone.md).
- API:
  - GET /api/providers will include { id: "rclone", ... } when enabled.
  - GET /api/provider_roots?provider_id=rclone lists rclone remotes (uses `rclone listremotes`).
  - GET /api/browse?provider_id=rclone&root_id=<remote>:&path=<remote>:<folder> lists entries via `rclone lsjson`.
  - Optional browse flags: `recursive=true|false` (default false), `max_depth=1..N` (default 1), `fast_list=true|false` (default false). The provider retries automatically without fast-list if unsupported by a backend.
  - POST /api/scan { provider_id: 'rclone', path: '<remote:path>' } records a metadata-only scan.
- If rclone is not installed or a remote is misconfigured, API returns a clear error message with HTTP 500 and {"error": "..."}.
- Optional FUSE mount flow with safe defaults: see docs/rclone/mount-examples.md and dev/ops/rclone/systemd/rclone-mount@.service.

### Rclone Mount Manager (MVP, feature-flagged)
- Enable the feature: set `SCIDK_RCLONE_MOUNTS=1` (or `SCIDK_FEATURE_RCLONE_MOUNTS=1`). When enabled, the rclone provider is auto-enabled for remote validation even if not listed in `SCIDK_PROVIDERS`.
- UI: Settings → Rclone Mounts section appears. Create a mount by entering `remote`, optional `subpath`, a `name`, and submit (read-only by default).
- Safety: Mountpoints are restricted under `./data/mounts/<name>`; remotes are validated against `rclone listremotes` output.
- Endpoints (enabled only when the feature flag is set):
  - GET `/api/rclone/mounts` — list managed mounts
  - POST `/api/rclone/mounts` with JSON `{ remote, subpath, name, read_only }` — starts `rclone mount` targeting `./data/mounts/<name>`
  - DELETE `/api/rclone/mounts/<id>` — unmounts and stops the process
  - GET `/api/rclone/mounts/<id>/logs?tail=N` — returns last N log lines
  - GET `/api/rclone/mounts/<id>/health` — checks process alive and that the path is listable
- Requirements: rclone must be installed and on PATH. Works on Linux/macOS. On Windows, use `rclone cmount` with WinFsp; current UI targets Linux/macOS primarily.

### Background Tasks (MVP)
- POST /api/tasks { type: 'scan', path, recursive? } → { task_id }
- GET /api/tasks → list all tasks (most recent first)
- GET /api/tasks/<task_id> → details including status, progress, and scan_id when completed
- POST /api/tasks { type: 'commit', scan_id } → start a background commit to graph (in-memory + optional Neo4j)

## Rclone scan and SQLite ingest (MVP)

- Enable rclone provider: export SCIDK_PROVIDERS="local_fs,mounted_fs,rclone".
- SQLite path index is created at SCIDK_DB_PATH (default ~/.scidk/db/files.db) and uses WAL mode.
- Trigger a scan via HTTP:
  - POST /api/scans with JSON {"provider_id":"rclone","root_id":"remote:","path":"remote:bucket","recursive":false,"fast_list":true}
- Check progress/status:
  - GET /api/scans/<scanId>/status → { status, file_count, folder_count, ingested_rows, by_ext, ... }
- Browse the scan snapshot (virtual root):
  - GET /api/scans/<scanId>/fs
- Notes:
  - Wrapper uses `rclone lsjson` with --recursive or --max-depth 1, and optional --fast-list.
  - Batch insert to SQLite in 10k rows/transaction; rows include both files and folders.

## Testing
We use pytest for unit and API tests.

Pytest is included in requirements.txt; after installing dependencies, run:
```
python3 -m pytest -q
```
Notes:
- If your shell doesn't expose a global `pytest` command (common in fish), using `python3 -m pytest` is the most reliable.
- You can still run `pytest -q` if your PATH includes the virtualenv's bin directory.

Conventions:
- Tests live in tests/ and rely on pytest fixtures in tests/conftest.py (e.g., Flask app and client).
- Add tests alongside new features in future cycles; see dev/cycles.md for cycle protocol.

## Notes
- This MVP uses an in-memory graph; data resets on restart.
- Neo4j deployment docs reside in dev/ops/deployment-neo4j.md, but Neo4j is not yet wired in the MVP code.

## Documentation
- Delivery cycles and planning protocol: dev/cycles.md
- RO-Crate Viewer embedding plan (Crate-O): dev/features/ui/feature-rocrate-viewer-embedding.md
- Describo integration (product vision): dev/vision/describo-integration.md

## Scanning progress and background tasks (MVP)
- Current options:
  - Synchronous: POST /api/scan runs immediately and returns when complete.
  - Background: POST /api/tasks with { type: 'scan', path, recursive } enqueues a background scan and returns { task_id }. Poll GET /api/tasks/<id> for status/progress; GET /api/tasks lists recent tasks.
- Progress: For Python traversal, progress reports files processed vs. total; percent reflects processed/total when determinable.
- Enumeration: Scanning prefers ncdu or gdu when installed; otherwise falls back to Python traversal.
- Future: When reliable streaming from ncdu/gdu is in place, percent will be computed from streamed JSON for better fidelity.

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

## New in this cycle: Commit to Graph — SCANNED_IN consistency and verification
- Commit now writes both File→SCANNED_IN→Scan and Folder→SCANNED_IN→Scan for recursive and non-recursive scans.
- Cypher simplified: MERGE Scan once; two independent subqueries for files and standalone folders; proper WITH scoping and unique return aliases.
- Post-commit verification runs automatically; Files page Background tasks shows: attempted, prepared, verify ok/fail with counts.
- Neo4j configuration UX: Settings Save no longer clears password on empty; added explicit Clear Password; supports NEO4J_AUTH=none and URI-embedded creds; backoff after repeated auth failures.
- Tests: added mocked-neo4j unit test for commit and verification; password persistence test.


## Dev CLI (self-describing)

The development CLI helps agents and humans navigate common workflows. It is self-describing and supports machine-friendly outputs.

Key features:
- argparse-based subcommands with consistent help
- meta-commands for discovery: `menu` and `introspect`
- global flags: `--json`, `--explain`, `--dry-run`
- JSON envelope for all command outputs (when `--json` is used)

JSON envelope schema:
```json
{
  "status": "ok|error",
  "command": "<name>",
  "data": {},
  "plan": {},
  "warnings": []
}
```

Quick start:
- List commands (human): `python3 -m dev.cli menu`
- List commands (JSON): `python3 -m dev.cli menu --json`
- Full introspection (metadata for agents): `python3 -m dev.cli introspect` or `python3 -m dev.cli --json introspect`

Global flags (place before the subcommand unless noted):
- `--json`    Emit structured envelope for agents
- `--explain` Show what would happen (no side-effects)
- `--dry-run` Simulate without side-effects (returns a plan)

Available commands:
- `ready-queue`
  - Summary: Show ready tasks sorted by RICE (DoR true)
  - Examples:
    - `python -m dev.cli ready-queue`
    - `python -m dev.cli --json ready-queue`
- `start [task_id]`
  - Summary: Validate DoR, create/switch branch, print context
  - Behavior: If task_id not provided, auto-picks top Ready task
  - Examples:
    - `python -m dev.cli start story:foo:bar`
    - `python -m dev.cli --explain --json start` (plan only, no side effects)
- `context <task_id>`
  - Summary: Emit AI context for a task
  - Examples:
    - `python -m dev.cli context story:foo:bar`
    - `python -m dev.cli --json context story:foo:bar`
- `validate <task_id>`
  - Summary: Validate Definition of Ready (DoR)
  - Output (JSON): `{ ok: bool, missing: [fields] }`
  - Examples:
    - `python -m dev.cli validate story:foo:bar`
    - `python -m dev.cli --json validate story:foo:bar`
- `complete <task_id>`
  - Summary: Run tests, print DoD checklist, and next steps
  - Examples:
    - `python -m dev.cli complete story:foo:bar`
    - `python -m dev.cli --explain --json complete story:foo:bar`
- `cycle-status`
  - Summary: Show current cycle status from dev/cycles.md
  - Examples:
    - `python -m dev.cli cycle-status`
    - `python -m dev.cli --json cycle-status`
- `next-cycle`
  - Summary: Propose next cycle using top Ready tasks
  - Examples:
    - `python -m dev.cli next-cycle`
    - `python -m dev.cli --json next-cycle`
- `merge-safety [--base <branch>]`
  - Summary: Report potentially risky deletions vs base branch
  - Examples:
    - `python -m dev.cli merge-safety`
    - `python -m dev.cli --json merge-safety`
    - `python -m dev.cli --json merge-safety --base origin/main`
    - Plan only: `python -m dev.cli --json --dry-run merge-safety --base origin/main`
- `dev-sync [--from <branch>]`
  - Summary: Synchronize dev/ directory from a shared/base branch into the current branch
  - Behavior: Restores dev/ from SCIDK_DEV_SHARED_BRANCH, SCIDK_BASE_BRANCH, or the specified --from branch
  - Examples:
    - `python -m dev.cli dev-sync`
    - `python -m dev.cli --json dev-sync`
    - `python -m dev.cli --json --explain dev-sync`
    - `python -m dev.cli --json dev-sync --from origin/main`

Environment variables for dev sync:
- `SCIDK_DEV_SHARED_BRANCH`: Preferred source branch to pull dev/ from (e.g., `origin/main` or `main`). If unset, the CLI falls back to `SCIDK_BASE_BRANCH`, then `origin/main`, `main`, etc.

Notes for agents:
- Prefer `menu --json` for a quick navigable overview of commands.
- Use `introspect` to obtain full metadata about args/options, side-effects, and conventions.
- Place `--json` before the subcommand to ensure the envelope applies to the whole invocation, e.g., `python -m dev.cli --json ready-queue`.


## Neo4j in Docker with Workspace on port 7474

We ship a docker-compose file that runs Neo4j and the official Neo4j Workspace UI. The UI is exposed on the classic port 7474, while the database Bolt port remains 7687.

Quick start:

```
# Optional: set password (default is neo4j/neo4jiscool)
export NEO4J_AUTH=neo4j/neo4jiscool

# Optional: override host directories (defaults are under ./data/neo4j)
export NEO4J_HOST_DATA_DIR=${NEO4J_HOST_DATA_DIR:-./data/neo4j/data}
export NEO4J_HOST_LOGS_DIR=${NEO4J_HOST_LOGS_DIR:-./data/neo4j/logs}
export NEO4J_HOST_PLUGINS_DIR=${NEO4J_HOST_PLUGINS_DIR:-./data/neo4j/plugins}
export NEO4J_HOST_IMPORT_DIR=${NEO4J_HOST_IMPORT_DIR:-./data/neo4j/import}

# Start services in background
docker compose -f docker-compose.neo4j.yml up -d

# Open the Workspace UI
# Login with user neo4j and the password above
http://localhost:7474/
```

Notes:
- We do NOT mount or write to system paths like /var/lib/neo4j on the host. By default we persist under the repository at ./data/neo4j, which works without root.
- You can override the host directories per environment using NEO4J_HOST_* variables shown above (use absolute or relative paths you own).
- The compose file exposes only Bolt (7687) from the Neo4j server. The Workspace container serves the web UI at host port 7474.
- If port 7474 or 7687 are occupied on your machine, stop the conflicting service or adjust the port mappings in docker-compose.neo4j.yml.
- Volumes and mount points follow Neo4j Docker guidance: we bind host dirs to /data, /logs, /plugins, and /import inside the container so your graph persists across restarts.
- Avoid mounting anything under /var/lib/neo4j inside the container. The entrypoint changes ownership in that path and can cause permission issues. Stick to /data, /logs, /plugins, and /import.
- The Workspace UI image is hosted on GitHub Container Registry (GHCR) as ghcr.io/neo4j/neo4j-workspace:latest. If you previously tried neo4j/neo4j-workspace on Docker Hub and saw "pull access denied", update and use the provided compose file.

Manage lifecycle:
```
# Stop containers
docker compose -f docker-compose.neo4j.yml down

# Stop and remove all data (DANGER: wipes the graph)
docker compose -f docker-compose.neo4j.yml down -v
```

Connect SciDK to this Neo4j:
```
export NEO4J_URI=bolt://localhost:7687
export NEO4J_AUTH=${NEO4J_AUTH:-neo4j/neo4jiscool}
# Optional named database
echo "SCIDK_NEO4J_DATABASE=neo4j" >> .env

# Start SciDK
scidk-serve
# or
python -m scidk.app
```
