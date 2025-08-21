id: feature:core-architecture/scan-sessions-registry
title: Scan Sessions Registry
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Track scan sessions and provide a registry for UI/API access.
scope:
  - Session records with provider/root/path/recursive
  - API surfaces as needed for session listing
out_of_scope:
  - Long-term persistence beyond MVP
success_metrics:
  - Sessions are visible and usable during app lifetime
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
notes: |
  Source reference doc: dev/features/ui/feature-scan-sessions-ux.md.