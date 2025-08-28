id: task:ops/mvp/rclone-health-check
title: /diag/rclone endpoint (version + remotes or clear error)
status: Ready
owner: agent
rice: 3.5
estimate: 0.5–1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ops, rclone, health]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/01-skeleton
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-01-skeleton.md]
acceptance:
  - GET /diag/rclone returns {version, remotes: []} or {error, hint}
  - Handles missing binary gracefully and fast
