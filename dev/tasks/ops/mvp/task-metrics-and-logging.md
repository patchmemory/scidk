id: task:ops/mvp/metrics-and-logging
title: Metrics endpoints and structured logging with scan/browse context
status: Ready
owner: agent
rice: 3.0
estimate: 1d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [ops, metrics, logging]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/06-hardening-docs
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-06-hardening-docs.md]
acceptance:
  - Metrics: scan throughput, rows ingested, browse P50/P95, outbox lag (if enabled)
  - Logs include task_id/scan_id and structured error responses
