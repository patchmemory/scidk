# Phase: Core MVP

## Phase Summary
- ID: phase:core-architecture/mvp
- Vision: vision:core-architecture
- Status: in-progress
- Target Start/End: 2025-08-19 → 2025-09-15
- Goals:
  - Scan a directory, create Dataset nodes, run interpreters, cache results, serve via REST + basic UI.
- Non-Goals:
  - Production auth, distributed workers, multi-tenant.

## Deliverables
- Flask app factory; REST endpoints (/api/scan, /api/datasets, /api/interpreters, /api/chat).
- In-memory Knowledge Graph with versioned interpretations.
- FilesystemManager with PatternMatcher + Registry wiring.
- PythonCodeInterpreter via executor stub; TIFF Bash interpreter deferred to Alpha.
- Minimal UI: list datasets, dataset detail.

## Work Breakdown (Tasks)
- [task:core-architecture/mvp/app-factory] Flask App Factory — P0, Status done, Owner agent, ETA 2025-08-21
- [task:core-architecture/mvp/graph-inmemory] In-Memory Graph Adapter — P0, Status done, Owner agent, ETA 2025-08-22
- [task:core-architecture/mvp/filesystem-scan] Filesystem Scan + Dataset Node — P0, Status done, Owner agent, ETA 2025-08-23
- [task:core-architecture/mvp/registry-pattern] Interpreter Registry + PatternMatcher — P0, Status done, Owner agent, ETA 2025-08-25
- [task:core-architecture/mvp/interpreters-core] PythonCode + TIFF Bash — P0, Status done, Owner agent, ETA 2025-08-27
- [task:core-architecture/mvp/rest-ui] REST Endpoints + Minimal UI — P0, Status done, Owner agent, ETA 2025-08-29

## Milestones (Dates)
- M1: Graph + Scan roundtrip (2025-08-23)
- M2: Interpreters executing and caching (2025-08-27)
- M3: UI shows interpreted data (2025-08-29)

## Acceptance for Phase Completion
- Can scan a dir with mixed data; GET /api/datasets returns items; interpretations appear for .py files; additional formats deferred.

## Phase Risks
- Large scans causing memory pressure → batch processing and back-pressure.
- Non-deterministic interpreter selection → clear rule priority and deterministic fallback.
