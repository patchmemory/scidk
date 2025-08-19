# Task: Filesystem Scan + Dataset Node

## Metadata
- ID: task:core-architecture/mvp/filesystem-scan
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: done
- Priority: P0
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-23
- Labels: [backend, graph]

## Goal
Create basic Dataset nodes for all files and insert into Graph.

## Context
Aligns with dev/vision/core_architecture.md FilesystemManager section.

## Requirements
- Functional:
  - scan_directory(path, recursive) using NCDU as the preferred scanner (export mode), with a safe Python fallback when NCDU is unavailable.
  - create_dataset_node with universal metadata (path, size, checksum, mime, timestamps).
  - upsert into Graph, idempotent by checksum.
- Non-functional:
  - Scans 10k files/min on SSD baseline; memory safe.

## Interfaces
- API: POST /api/scan { path, recursive }
- Data: Node Dataset {path, filename, extension, size_bytes, created, modified, mime_type, checksum, lifecycle_state}

## Implementation Plan
- Steps:
  1. Implement FilesystemManager with create_dataset_node and scan_directory.
  2. Prefer NCDU runner to enumerate files; fall back to Python traversal if NCDU is not present or parsing yields no results.
  3. Wire to Graph.upsert_dataset().
  4. POST /api/scan triggers scan.
- Code Touchpoints:
  - scidk/core/filesystem.py
  - scidk/core/graph.py
  - scidk/api/routes_datasets.py

## Test Plan
- Unit:
  - test_scan_creates_datasets
  - test_checksum_idempotency
- Integration:
  - Scan tmpdir with dummy files; GET /api/datasets shows entries.
- Acceptance (DoD):
  - Running a scan produces ≥ 1 dataset and persists across repeated scans without duplication.

## Telemetry & Docs
- Metrics: log per 1000 files; duration metrics.
- Docs: update README and dev/core-architecture/mvp.md with results.
- Notes: NCDU preferred; install via your package manager (e.g., macOS: `brew install ncdu`, Ubuntu/Debian: `sudo apt-get install ncdu`). Falls back to Python traversal if NCDU is not found.

## Dependencies
- Blocked by: [task:core-architecture/mvp/graph-inmemory]

## Risk & Rollback
- Risks: large directory stalls; add batch commit.
- Rollback: feature flag to disable scan endpoint.

## Progress Log
- 2025-08-18: Created task spec.
- 2025-08-18: Implemented FilesystemManager with create_dataset_node and scan_directory; wired to InMemoryGraph; exposed POST /api/scan and UI scan form.
- 2025-08-18: Validated DoD manually by scanning repo and viewing datasets in UI.
- 2025-08-18: Updated scan implementation to select interpreters via registry.select_for_dataset (rule precedence) instead of extension-only mapping; keeps scan behavior consistent with API interpretation.
