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
