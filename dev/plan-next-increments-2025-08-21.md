# Plan: Next Increments (2025-08-21)

id: plan:next-increments-2025-08-21
status: In progress
owner: agent
created: 2025-08-21
related:
- dev/cycles.md (Status Snapshot 2025-08-21)
- dev/stories/story-mvp-multi-provider-files-and-interpreters.md (Done)
- README.md (New in this cycle sections)

Overview
- This document records the near-term plan and acceptance criteria for the next increments. It consolidates our previously discussed objectives so the plan is durable inside the repo.

Objectives
1) Background scanning tasks with progress (Tasks API) and UI polling
2) RcloneProvider behind a feature flag (SCIDK_PROVIDERS)
3) Browse UX improvements: breadcrumbs, keyboard navigation, paging polish
4) Optional: GraphAdapter abstraction to select in-memory vs Neo4j persistence
5) Hardening: validation, timeouts, caps, logging, structured errors
6) DevEx and docs: CLI entry, configuration precedence, deployment notes

Data structures (in app.extensions['scidk'])
- tasks: { task_id: { id, type: 'scan', status: 'queued|running|succeeded|failed|canceled', progress: { percent?, files_seen, bytes_seen, started_at, updated_at }, result?, error?, scan_id? } }
- scan_fs: unchanged (per-scan index cache)

Backend endpoints (Tasks)
- POST /api/tasks { type: 'scan', provider_id, root_id?, path, recursive? } → { task_id }
- GET /api/tasks → [{ id, type, status, progress }]
- GET /api/tasks/<id> → full details
- POST /api/tasks/<id>/cancel → cooperative cancel

Implementation notes (MVP)
- Use threading.Thread for IO-bound scans.
- Progress: update files_seen/bytes_seen; percent may be null for Python fallback.
- Safety: max running tasks via env SCIDK_MAX_BG_TASKS (default 2).
- Caps: respect MAX_FILES_PER_SCAN; enforce timeouts where appropriate.

RcloneProvider (feature-flagged)
- Feature flag: SCIDK_PROVIDERS=rclone,local_fs,mounted_fs
- status(): verify rclone on PATH
- list_roots(): rclone listremotes → ["gdrive:", ...]
- list(): rclone lsjson <remote:path> --max-depth 1 → entries
- open(): rclone cat <remote:path>
- enumerate_files(): rclone lsjson <remote:path> --recursive (respect caps)

Browse UX
- Optional endpoint: GET /api/breadcrumbs → breadcrumb parts
- Ensure /api/browse includes next_page_token; env BROWSE_PAGE_SIZE

GraphAdapter (optional)
- SCIDK_GRAPH_BACKEND=in_memory|neo4j (planned)
- Adapter methods: upsert_dataset, add_interpretation, commit_scan, schema_triples, list_datasets

Hardening & Observability
- Input validation for provider_id/root_id/path
- Size/time caps for previews and subprocesses
- Structured errors: { error, code, details?, hint? }
- Logging includes task_id/scan_id context

Developer Experience & Docs
- CLI: scidk-serve entry point available (documented)
- Config precedence documented; Neo4j notes in dev/deployment.md

Acceptance criteria
- Background tasks
  - [x] POST /api/tasks returns task_id; status transitions to running and completes for scan tasks (test added) — 2025-08-21
  - [x] Progress updates during scan; polling works (validated by tests/test_tasks_scan.py) — 2025-08-21
  - [ ] Max concurrent tasks enforced; cancel works
- RcloneProvider
  - [ ] /api/providers lists rclone when feature-flagged; /api/provider_roots shows remotes
  - [ ] /api/browse works with a remote; pagination stable
  - [ ] /api/scan works with provider_id=rclone
  - [ ] Clear error when rclone not installed or remote missing
- Browse UX
  - [ ] Breadcrumbs render; paging UI consistent
- GraphAdapter
  - [ ] Backend toggle works in code; tests pass for both
- Hardening
  - [ ] Caps/timeouts enforced; structured errors returned
  - [ ] Logs include task_id/scan_id context

Initial tasks and ordering
1. Background Tasks API (foundation) — 2–3 days
2. RcloneProvider (feature-flagged) — 2–3 days
3. Browse UX polish — 1–2 days
4. Hardening/logging — 0.5–1.5 days
5. GraphAdapter (optional) — 2–4 days

Notes
- Background tasks are non-persistent (lost on restart) for MVP.
- Rclone variability: normalize errors; test with mocked subprocess.
- Progress fidelity: start simple (files_seen), improve later with ncdu/gdu when streamed JSON is feasible.

Progress Log
- 2025-08-21 09:39 local: Added Background Tasks lifecycle test (tests/test_tasks_scan.py); updated README with Background Tasks API; endpoints verified via pytest.
- 2025-08-21 09:45 local: Cross-linked plan from dev/cycles.md; documenting UI polling pattern for tasks in dev/ui/mvp/tasks-ui-polling.md.
