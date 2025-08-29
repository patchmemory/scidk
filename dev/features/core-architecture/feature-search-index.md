id: feature:core-architecture/search-index
title: Search Index and API
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Provide a simple search over scanned datasets (filename/path and interpreter_id).
scope:
  - In-memory index structure over datasets
  - GET /api/search?q=
  - Match fields: id, path, filename, extension, interpreter_id, matched_on
out_of_scope:
  - Full-text or vector search
success_metrics:
  - Home search UI returns expected datasets
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
notes: |
  Source reference doc: dev/core-architecture/mvp/search-index.md (legacy).