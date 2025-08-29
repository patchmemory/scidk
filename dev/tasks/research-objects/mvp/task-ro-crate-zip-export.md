id: task:research-objects/mvp/ro-crate-zip-export
title: Zip export for referenced RO-Crate directory
status: Ready
owner: agent
rice: 3.2
estimate: 0.5–1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: [task:research-objects/mvp/ro-crate-referenced]
tags: [ro-crate, export]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/04-ro-crate-referenced
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-04-ro-crate-referenced.md]
acceptance:
  - POST /api/ro-crates/{crateId}/export?target=zip returns a zip of the crate directory (metadata only)
  - Clear errors for missing crateId or inaccessible path
