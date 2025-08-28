id: task:ops/mvp/sqlite-init-wal
title: Initialize SQLite database file and enable WAL mode
status: Ready
owner: agent
rice: 3.6
estimate: 0.5d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ops, sqlite]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/01-skeleton
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-01-skeleton.md]
acceptance:
  - DB file created at configured path (default ~/.scidk/db/files.db)
  - WAL mode pragma verified; simple SELECT 1 passes in health check
