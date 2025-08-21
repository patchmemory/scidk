id: task:ui/mvp/tasks-ui-polling
title: Files page polling for background Tasks
status: Ready
owner: agent
rice: 3.8
estimate: 0.5–1d
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ui, tasks, scan]
story: story:providers-mvp-multi-source-files
phase: 
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-21.md]
  story: [dev/stories/providers-mvp-multi-source-files/story.md]
  phase: []
acceptance:
  - Files page creates scan tasks via POST /api/tasks and polls GET /api/tasks/<id>
  - Progress bars reflect running status and completion
  - Cancel is shown and works when status=running (POST /api/tasks/<id>/cancel)
