id: feature:core-architecture/core-architecture-mvp
title: Core Architecture MVP Phase
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Deliver the minimum core needed to scan files, interpret content, and serve results via REST + minimal UI.
scope:
  - Flask app factory and REST endpoints (/api/scan, /api/datasets, /api/interpreters, /api/chat)
  - In-memory Knowledge Graph with versioned interpretations
  - FilesystemManager with PatternMatcher + Interpreter Registry
  - PythonCodeInterpreter (baseline); other interpreters tracked separately
  - Minimal UI pages: datasets list and dataset detail
out_of_scope:
  - Production auth, distributed workers, multi-tenant features
  - Background job scheduler (tracked elsewhere)
success_metrics:
  - Can scan a directory and produce Dataset nodes
  - Interpreters run and cache results; UI renders summaries
  - All MVP endpoints are reachable and return expected shapes
links:
  stories: []
  tasks:
    - task:core-architecture/mvp/filesystem-scan
    - task:core-architecture/mvp/graph-inmemory
    - task:core-architecture/mvp/registry-pattern
    - task:core-architecture/mvp/rest-ui
notes: |
  Derived from legacy doc dev/core-architecture/mvp.md (removed during cleanup). This feature captures the MVP phase deliverables, milestones, and acceptance in the standardized features/ folder.

Legacy phase details (for continuity)
- Phase ID: phase:core-architecture/mvp; Status: in-progress; Target: 2025-08-18 → 2025-09-15
- Deliverables: endpoints, in-memory graph, filesystem scan, interpreter registry, minimal UI
- Milestones: M1 Graph + Scan; M2 Interpreters + caching; M3 UI rendering
- Acceptance: scan mixed dir; GET /api/datasets; interpretations appear for .py; others deferred
- Risks: memory pressure on large scans; deterministic interpreter selection
