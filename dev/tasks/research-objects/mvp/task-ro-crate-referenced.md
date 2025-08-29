id: task:research-objects/mvp/ro-crate-referenced
title: Referenced RO-Crate generation from selection
status: Ready
owner: agent
rice: 4.1
estimate: 1–2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: [task:core-architecture/mvp/annotations-and-selections]
tags: [ro-crate, metadata]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/04-ro-crate-referenced
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-04-ro-crate-referenced.md]
acceptance:
  - Create ro-crate-metadata.json with root Dataset and DataEntities for files; contentUrl=rclone://remote/path
  - Include name, size, mime_type, modified_time, and checksum if available
  - Writes to ~/.scidk/crates/{crateId}; returns crateId and path via API
