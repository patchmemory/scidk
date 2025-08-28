# Plan: Reboot Architecture (2025-08-28)

id: plan:reboot-architecture-2025-08-28
status: In progress
owner: agent
created: 2025-08-28
links:
  - dev/README-planning.md
  - dev/cycles.md
  - dev/stories/core-architecture-reboot/story.md
  - dev/features/research-objects/feature-ro-crate.md
  - dev/stories/providers-mvp-multi-source-files/story.md

Summary
- Clean reboot prioritizing: rclone for discovery, SQLite path-index for fast browsing + annotations, RO-Crate for referenced research objects, optional Neo4j projection via outbox only when semantics are needed.
- Ship in weekly vertical slices with a small demo per week. No migration constraints; prioritize minimal, clean foundations.

Objectives (now through v0.1.0)
1) Week 1: Project skeleton + health checks + rclone diagnostics
2) Week 2: rclone scan -> SQLite ingest (path index) with batch inserts
3) Week 3: Fast directory browse API, selections, and annotations
4) Week 4: RO-Crate (referenced) creation from selection + zip export
5) Week 5: Feature flag for Neo4j projection, outbox worker (optional)
6) Week 6: Hardening, telemetry, docs, and demo scripts

Principles
- SQLite is source of truth for scans, browsing, selections, annotations.
- Neo4j is optional and only for semantics; no cross-DB joins, no 2PC.
- Outbox event pattern for async, idempotent projection when enabled.
- Prefer small, demoable increments and clear acceptance criteria.

Acceptance (high level)
- Directory listing P95 ≤ 120 ms on 200k+ files (warm cache) via parent_path index.
- rclone-based scan succeeds for local path and at least one remote; clear errors when rclone is absent.
- Referenced RO-Crate generated from a selection with rclone:// URLs and basic metadata.
- Optional projection flag works; browsing unaffected if Neo4j is down.

Phasing and selected tasks
- Week 1 (Skeleton)
  - task:ops/mvp/rclone-health-check
  - task:ops/mvp/sqlite-init-wal
- Week 2 (Scan → SQLite)
  - task:core-architecture/mvp/sqlite-path-index
  - task:core-architecture/mvp/rclone-scan-ingest
- Week 3 (Browse + Annotate)
  - task:ui/mvp/browse-api-and-pagination
  - task:core-architecture/mvp/annotations-and-selections
- Week 4 (RO-Crate referenced)
  - task:research-objects/mvp/ro-crate-referenced
  - task:research-objects/mvp/ro-crate-zip-export
- Week 5 (Optional Projection)
  - task:core-architecture/mvp/outbox-projection-neo4j-flag
- Week 6 (Hardening)
  - task:ops/mvp/metrics-and-logging
  - task:ops/mvp/docs-quickstart

Notes
- This plan supersedes near-term priorities in dev/plans/plan-2025-08-21.md for the next two cycles; we will keep that document for historical context and feature cross-links.
- All new tasks link back to this plan id in their frontmatter.
