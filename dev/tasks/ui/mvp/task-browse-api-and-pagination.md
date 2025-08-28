id: task:ui/mvp/browse-api-and-pagination
title: Browse API with parent_path listing and pagination
status: Ready
owner: agent
rice: 4.0
estimate: 1–2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: [task:core-architecture/mvp/sqlite-path-index]
tags: [ui, api, browse]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/03-browse-annotate
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-03-browse-annotate.md]
acceptance:
  - GET /api/scans/{scanId}/browse?path=/ returns direct children via index (no LIKE)
  - Sort by type DESC, name ASC; supports page_size and next_page_token
  - Filter by extension and type (index-backed)
