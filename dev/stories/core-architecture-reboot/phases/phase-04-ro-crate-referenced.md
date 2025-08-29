id: phase:core-architecture-reboot/04-ro-crate-referenced
story: story:core-architecture-reboot
order: 4
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: Create a referenced RO-Crate from a selection with rclone:// URLs; optional zip export
acceptance:
  - POST /api/ro-crates { selection_id | files, metadata } → returns crateId and path under ~/.scidk/crates
  - ro-crate-metadata.json contains root Dataset and selected files as DataEntities with contentUrl
  - POST /api/ro-crates/{crateId}/export?target=zip returns a downloadable ZIP of metadata directory
selected_tasks:
  - task:research-objects/mvp/ro-crate-referenced
  - task:research-objects/mvp/ro-crate-zip-export
links:
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
