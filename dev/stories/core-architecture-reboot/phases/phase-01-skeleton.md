id: phase:core-architecture-reboot/01-skeleton
story: story:core-architecture-reboot
order: 1
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: App boots with health endpoints and rclone diagnostics; SQLite initialized (WAL)
acceptance:
  - GET /health returns healthy for sqlite
  - GET /diag/rclone returns version or a clear error when missing
  - SQLite file created at default path with WAL mode enabled
selected_tasks:
  - task:ops/mvp/rclone-health-check
  - task:ops/mvp/sqlite-init-wal
links:
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
