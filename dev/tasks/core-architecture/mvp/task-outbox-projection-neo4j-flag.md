id: task:core-architecture/mvp/outbox-projection-neo4j-flag
title: Feature-flagged outbox projection to Neo4j (optional)
status: Ready
owner: agent
rice: 2.4
estimate: 1–2d
created: 2025-08-28
updated: 2025-08-28
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [projection, neo4j, outbox]
story: story:core-architecture-reboot
phase: phase:core-architecture-reboot/05-projection-flag
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
  story: [dev/stories/core-architecture-reboot/story.md]
  phase: [dev/stories/core-architecture-reboot/phases/phase-05-projection-flag.md]
acceptance:
  - Flag projection.enableNeo4j=false by default; when true, background worker runs
  - Outbox table created; worker MERGE-s File/Dataset and HAS_PART in Neo4j
  - Retries with backoff; processed_at recorded
