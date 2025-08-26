id: task:ops/mvp/error-toasts
title: Error toasts for browse/scan failures
status: Done
owner: agent
rice: 1.3
estimate: "0.25\u20130.5d"
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
- tests
- docs
- demo_steps
dependencies: []
tags:
- ops
- ux
- errors
story: story:providers-mvp-multi-source-files
phase: phase:providers-mvp-multi-source-files/00-contracts-local-mounted
links:
  cycles:
  - dev/cycles.md
  plan:
  - dev/plans/plan-2025-08-21.md
  story:
  - dev/stories/providers-mvp-multi-source-files/story.md
  phase:
  - dev/stories/providers-mvp-multi-source-files/phases/phase-00-contracts-local-mounted.md
acceptance:
- UI shows toast on non-2xx from /api/browse, /api/scan, /api/tasks
- Messages map structured error payloads { error, code, hint }
started_at: '2025-08-26T19:17:23Z'
branch: task/task-ops/mvp/error-toasts
completed_at: '2025-08-26T19:19:31Z'
tests_passed: true