id: feature:core-architecture/filesystem-scan
title: Filesystem Scan
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Enumerate files for a given provider/root/path and create datasets with interpreter matches.
scope:
  - Scan endpoints wiring (/api/scan)
  - Enumeration logic with caps and recursion flag
  - Dataset creation/update semantics
out_of_scope:
  - Background scans (tracked as separate task)
success_metrics:
  - Can scan a directory and see datasets in UI
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
notes: |
  Source reference doc: dev/core-architecture/mvp/filesystem-scan.md (legacy).