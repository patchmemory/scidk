id: task:ops/mvp/error-toasts
title: Error toasts for browse/scan failures
status: Ready
owner: agent
rice: 1.3
estimate: 0.25–0.5d
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ops, ux, errors]
story: 
phase: 
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-21.md]
  story: []
  phase: []
acceptance:
  - UI shows toast on non-2xx from /api/browse, /api/scan, /api/tasks
  - Messages map structured error payloads { error, code, hint }
