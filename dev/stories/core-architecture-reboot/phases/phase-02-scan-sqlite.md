id: phase:core-architecture-reboot/02-scan-sqlite
story: story:core-architecture-reboot
order: 2
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: Start a scan via rclone and see rows ingested into SQLite with path-index schema
acceptance:
  - POST /api/scans returns scanId and starts a background job
  - GET /api/scans/{scanId}/status shows running→complete with counts
  - SQLite files table populated with path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, remote, scan_id
selected_tasks:
  - task:core-architecture/mvp/sqlite-path-index
  - task:core-architecture/mvp/rclone-scan-ingest
links:
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
