id: task:core-architecture/mvp/rclone-scan-ingest
title: rclone lsjson scan and batch ingest into SQLite
status: Ready
owner: agent
rice: 4.3
estimate: 2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: [task:core-architecture/mvp/sqlite-path-index]
tags: [rclone, discovery, ingest]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/02-scan-sqlite
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-02-scan-sqlite.md]
acceptance:
  - Wrapper for rclone lsjson with --recursive and optional --fast-list
  - Batch insert records (10k/txn) mapped to path-index schema
  - POST /api/scans and GET /api/scans/{id}/status implemented with progress counters

demo_steps:
  - Export env to enable rclone provider: |
      export SCIDK_PROVIDERS="local_fs,mounted_fs,rclone"
  - Start Flask app (example): |
      python -c "from scidk.app import create_app; app=create_app(); app.run(port=5001)"
  - Trigger a scan via HTTP: |
      curl -s -X POST http://localhost:5001/api/scans \
        -H 'Content-Type: application/json' \
        -d '{"provider_id":"rclone","root_id":"remote:","path":"remote:bucket","recursive":false,"fast_list":true}'
  - Poll status: |
      curl -s http://localhost:5001/api/scans/<scanId>/status | jq .
  - Browse the scan snapshot (virtual root): |
      curl -s 'http://localhost:5001/api/scans/<scanId>/fs' | jq .

docs:
  - Rclone scanning uses `rclone lsjson`; when recursive=false, both folders and files may be returned.
  - Ingest persists rows into SQLite at SCIDK_DB_PATH (default: ~/.scidk/db/files.db) in WAL mode.
  - Status endpoint returns file_count (files only), folder_count (top-level when non-recursive), and ingested_rows (files + folders inserted).
