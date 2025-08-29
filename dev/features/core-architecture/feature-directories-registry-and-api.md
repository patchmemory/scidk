id: feature:core-architecture/directories-registry-and-api
title: Directories Registry and API
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Track scanned directories/sources and expose them via API for UI consumption.
scope:
  - In-memory registry of scanned directories/sources
  - GET /api/directories returns session list
  - Integration with scan flow to upsert entries
out_of_scope:
  - Persistent storage across restarts
success_metrics:
  - Home shows Scanned Sources list after scans
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
notes: |
  Source reference doc: dev/core-architecture/mvp/directories-registry-and-api.md (legacy).