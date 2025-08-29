id: task:ops/mvp/docs-quickstart
title: Developer quickstart and demo script for v0.1.0
status: Ready
owner: agent
rice: 2.2
estimate: 0.5–1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - docs
  - demo_steps
dependencies: []
tags: [docs]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/06-hardening-docs
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-06-hardening-docs.md]
acceptance:
  - Fresh install to first crate in < 30 minutes documented
  - Demo script: scan → browse → select → create RO-Crate → zip export
