# Task: Filesystem Scan + Dataset Node

## Metadata
- ID: task:core-architecture/mvp/filesystem-scan
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: planned
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
  - scan_directory(path, recursive) using Path.rglob.
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
  2. Wire to Graph.upsert_dataset().
  3. POST /api/scan triggers scan.
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

## Dependencies
- Blocked by: [task:core-architecture/mvp/graph-inmemory]

## Risk & Rollback
- Risks: large directory stalls; add batch commit.
- Rollback: feature flag to disable scan endpoint.

## Progress Log
- 2025-08-18: Created task spec.
