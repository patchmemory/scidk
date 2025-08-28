id: task:core-architecture/mvp/annotations-and-selections
title: Selections and annotations tables + APIs (SQLite)
status: Ready
owner: agent
rice: 3.9
estimate: 1–2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: [task:core-architecture/mvp/sqlite-path-index]
tags: [sqlite, annotations, selections]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/03-browse-annotate
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-03-browse-annotate.md]
acceptance:
  - tables: selections, selection_items, annotations with indexes
  - POST /api/selections and POST /api/selections/{id}/items endpoints
  - POST /api/annotations and GET by file_id
