id: task:core-architecture/mvp/sqlite-path-index
title: SQLite path-index schema and migrations (WAL enabled)
status: Ready
owner: agent
rice: 4.2
estimate: 1–2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [sqlite, schema, performance]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/02-scan-sqlite
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-02-scan-sqlite.md]
acceptance:
  - files table with columns: path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, etag, hash, remote, scan_id, extra_json
  - indexes: (scan_id, parent_path, name), (scan_id, file_extension), (scan_id, type)
  - WAL mode enabled; migration script and DAO created
