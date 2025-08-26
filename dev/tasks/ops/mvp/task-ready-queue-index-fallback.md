id: task:ops/mvp/ready-queue-index-fallback
title: CLI ready-queue falls back to dev/tasks/index.md when empty
status: Done
owner: agent
rice: 2.0
estimate: "0.25\u20130.5d"
created: 2025-08-26
updated: 2025-08-26
dor: true
dod:
- tests
- docs
- demo_steps
dependencies: []
tags:
- ops
- dev-cli
story: story:core-architecture
phase: phase:core-architecture/mvp
links:
  cycles:
  - dev/cycles.md
  plan: []
  story:
  - dev/cycles.md
  phase:
  - dev/cycles.md
acceptance:
- When no task files are Ready, `python dev_cli.py ready-queue` falls back to dev/tasks/index.md
  ready_queue.
- Fallback returns tasks in the order of the ready_queue and includes basic fields
  (id, rice).
- Existing behavior remains unchanged when there are Ready tasks in files.
started_at: '2025-08-26T19:30:53Z'
branch: task/task-ops/mvp/ready-queue-index-fallback
completed_at: '2025-08-26T19:31:59Z'
tests_passed: true