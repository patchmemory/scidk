id: story:core-architecture-reboot
title: Core Architecture Reboot — rclone + SQLite Path Index + RO-Crate
status: In progress
owner: agent
created: 2025-08-28
updated: 2025-08-28
success: End-to-end flow: scan (rclone) → browse (SQLite) → select/annotate → create RO-Crate (referenced) → optional graph projection (flagged)
scope_in: [discovery, browse, annotations, selections, ro-crate, ops]
scope_out: [oauth, materialized exports, advanced UI]
links:
  phases:
    - dev/stories/core-architecture-reboot/phases/phase-01-skeleton.md
    - dev/stories/core-architecture-reboot/phases/phase-02-scan-sqlite.md
    - dev/stories/core-architecture-reboot/phases/phase-03-browse-annotate.md
    - dev/stories/core-architecture-reboot/phases/phase-04-ro-crate-referenced.md
    - dev/stories/core-architecture-reboot/phases/phase-05-projection-flag.md
    - dev/stories/core-architecture-reboot/phases/phase-06-hardening-docs.md
  related_features:
    - dev/features/research-objects/feature-ro-crate.md
    - dev/features/providers/feature-provider-registry-and-interface.md
  plans:
    - dev/plans/plan-2025-08-28-reboot-architecture.md

Narrative
- Reboot the stack around simple, fast primitives. Keep SQLite as the source of truth for browsing and annotations; generate standards-compliant RO-Crates; enable optional semantic projection later. Ship weekly, demo weekly.
