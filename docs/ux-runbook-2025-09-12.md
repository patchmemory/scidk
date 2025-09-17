# UX Test Runbook — release/ux-test-2025-09-12 (tag: ux-2025-09-12)

This runbook describes how to start the app for UX testing, which feature flags to use, and a minimal smoke plan to validate the build.

Branch: release/ux-test-2025-09-12
Tag: ux-2025-09-12

Environment defaults are channel-aware (dev/beta enable more features by default). Explicit env vars always override.

## 1) Environment variables

Recommended for UX testing:
- SCIDK_CHANNEL=dev
  - Enables convenient defaults (providers include rclone when available, mounts UI on, file index WIP on).
- SCIDK_DB_PATH="scidk.db" (optional)
  - SQLite path for runtime state/index. WAL mode is enabled automatically when possible.
- SCIDK_RCLONE_MOUNTS=1 (optional; requires rclone installed)
  - Enables rclone mount manager API and UI sections.
- SCIDK_FEATURE_FILE_INDEX=1
  - Ensures file index features are enabled for scan and browse previews.
- SCIDK_ENABLE_INTERPRETERS and/or SCIDK_DISABLE_INTERPRETERS
  - Comma-separated ids, e.g., SCIDK_DISABLE_INTERPRETERS=json,csv
  - Effective view available under /api/interpreters?view=effective.
- SCIDK_FORCE_RCLONE=1 (optional)
  - If rclone binary not found, this bypasses soft-disable of rclone provider (use with care).

Testing/CI specific:
- SCIDK_DISABLE_SETTINGS=1
  - Prevents persistence of interpreter toggles when running automated tests to keep hermetic runs.

Neo4j (optional; for graph projection testing only):
- NEO4J_URI=bolt://user:pass@localhost:7687
- NEO4J_AUTH=none (or provide user/password via NEO4J_AUTH or envs)
- SCIDK_NEO4J_DATABASE=neo4j

## 2) Starting the app

- Python: 3.10+
- Install deps: pip install -r requirements.txt
- Start: python start_scidk.py or `FLASK_APP=scidk.app:create_app flask run` (if configured).
- Default UI: http://localhost:5000/
- Health: GET http://localhost:5000/api/health — verifies SQLite path and WAL.

Example env:
```
export SCIDK_CHANNEL=dev
export SCIDK_DB_PATH=$(pwd)/scidk.db
export SCIDK_RCLONE_MOUNTS=1
export SCIDK_FEATURE_FILE_INDEX=1
python start_scidk.py
```

## 3) Smoke checklist (APIs)

Rclone interpretation settings and chunked reinterpretation are available and should be validated as part of smoke.

1) Metrics endpoint
- GET /api/metrics
- Expect JSON with keys: scan_throughput_per_min, rows_ingested_total, browse_latency_p50, browse_latency_p95, outbox_lag

2) Providers and roots
- GET /api/providers — list enabled providers
- GET /api/provider_roots?provider_id=local_fs — should return at least root "/"

3) Selective scan dry-run (non-destructive)
- POST /api/scan/dry-run
  Body:
  {
    "path": "/path/to/folder",
    "recursive": false,
    "include": ["*.py"],
    "exclude": ["*.ipynb"],
    "max_depth": 2,
    "use_ignore": true
  }
- Expect JSON: status=ok, total_files, total_bytes, files[]

4) Scan and browse basic
- POST /api/scan { "path": "/path/to/folder", "recursive": false }
- GET /api/datasets — expect items
- GET /api/browse?provider_id=local_fs&root_id=/&path=/path/to/folder — expect entries

5) Search
- GET /api/search?q=<token>
- Expect results with matched_on including 'filename' or 'interpreter_id' for known files

6) Interpreters toggles
- GET /api/interpreters — list metadata
- GET /api/interpreters?view=effective — effective enablement view
- POST /api/interpreters/<id>/toggle {"enabled": false} — disable, then GET effective to verify

7) Rclone mounts (optional)
- Ensure rclone installed: `rclone version`
- With SCIDK_RCLONE_MOUNTS=1:
  - GET /api/rclone/remotes
  - POST /api/rclone/mounts to create mount (read-only recommended in UX):
    {
      "name": "ux_test",
      "remote": "myremote:",
      "subpath": "",
      "path": "./data/mounts/myremote",
      "read_only": true
    }
  - GET /api/rclone/mounts — verify mount listed and status hydrated

8) Rclone interpretation settings
- GET /api/settings/rclone-interpret — returns defaults or persisted values
- POST /api/settings/rclone-interpret { "max_files_per_batch": 1200 } — value is saved and clamped to ≤ 2000; GET reflects it

9) Chunked reinterpretation (for scans with many files)
- Create or pick a scan with many files (preferably provider_id=rclone)
- POST /api/interpret/scan/<scan_id> with { "max_files": 150 } — response includes next_cursor when more remain
- Subsequent POSTs with { "after_rowid": <next_cursor> } continue processing until next_cursor is null

10) Neo4j connectivity (optional)
- POST /api/settings/neo4j with uri/user/password/database
- POST /api/settings/neo4j/connect — expect connected true/false and backoff behavior on auth failures

## 4) Persistence validation

- After running a scan, stop the app and restart.
- Verify:
  - GET /api/directories returns previously scanned directories ordered by last_scanned (SQLite-backed).
  - GET /api/scans lists records (SQLite-backed); details readable.
  - GET / (Home) shows Last Scan Telemetry populated; survives restart (telemetry.last_scan persisted to SQLite settings).
  - Rclone mounts (if created under flag) persist their definitions and hydrate runtime status post-restart (GET /api/rclone/mounts).

## 5) Known flags and defaults

- Channel defaults: SCIDK_CHANNEL=dev sets providers to local_fs,mounted_fs,rclone (if available), enables mounts UI and file index WIP.
- Soft rclone disable: if rclone missing and not forced, rclone is removed from SCIDK_PROVIDERS when not explicitly set by user.
- Commit from index default: SCIDK_COMMIT_FROM_INDEX=1 (can be overridden).

## 6) Basic troubleshooting

- /api/health shows SQLite path, WAL journal_mode, and basic select(1) status.
- /api/metrics provides throughput and latency signals; if empty, exercise /api/scan and /api/browse to generate samples.
- Neo4j auth failures incur backoff; see /api/settings/neo4j and /api/settings/neo4j/connect responses.

## 7) Hand-off notes

- Release branch: release/ux-test-2025-09-12
- Tag: ux-2025-09-12
- Merge strategy: Topic branches integrated with feature flags; persistence and selective scanning kept safe for UX. After UX sign-off, merge release branch into master via PR (avoid squash to preserve merge history), or cherry-pick subset if needed.
