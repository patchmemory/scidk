id: phase:core-architecture-reboot/03-browse-annotate
story: story:core-architecture-reboot
order: 3
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: Fast directory browse via parent_path index; selections and annotations persisted in SQLite
acceptance:
  - GET /api/scans/{scanId}/browse?path=/ lists direct children (type DESC, name ASC) with pagination
  - POST /api/selections creates a selection; items can be added/removed and listed
  - POST /api/annotations creates tags/notes; list annotations by file_id
selected_tasks:
  - task:ui/mvp/browse-api-and-pagination
  - task:core-architecture/mvp/annotations-and-selections
links:
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
