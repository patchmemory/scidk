# Task: Research Objects (RO-Crate) MVP

## Metadata
- ID: task:core-architecture/mvp/research-objects-ro-crate
- Vision: vision:research-objects
- Phase: phase:core-architecture/mvp
- Status: planned
- Priority: P1
- Owner: agent
- Created: 2025-08-19
- ETA: 2025-09-05
- Labels: [backend, graph, standards, ui]

## Goal
Make RO-Crate a first-class organizational unit in SciDK so users can create, view, and incrementally enrich Research Objects from the file browser.

## Context
Aligns with dev/vision/research_objects.md (RO-Crate as native dataset collection) and builds on core scanning and interpreting flows.

## Requirements
- Functional:
  - Create Research Object: POST /api/research-objects { name, description } → returns id and initial RO-Crate JSON-LD.
  - Add File to RO: POST /api/research-objects/<id>/files { path } → interprets file, records metadata, and updates hasPart.
  - List Research Objects: GET /api/research-objects → id, name, description, dateCreated, file_count.
  - Export RO-Crate: GET /api/research-objects/<id>/export?format=zip|json (zip can be deferred to Alpha if capacity constrained).
- Non-functional:
  - Standards-first: persist RO-Crate JSON-LD structure; keep mapping to graph simple and reversible.
  - Safety: do not move or copy large files during MVP; reference by path (with future copy-on-write option).

## Interfaces
- API:
  - POST /api/research-objects
  - POST /api/research-objects/<id>/files
  - GET /api/research-objects
  - GET /api/research-objects/<id>/export
- UI:
  - Files page: "Create Research Object" action; drag-and-drop to add files (stub is acceptable for MVP).
  - RO list/detail views: minimal pages listing basic metadata and files.

## Implementation Plan
- Steps:
  1. Data model: add ResearchObjectManager stub (in-memory or Neo4j adapter with minimal schema).
  2. REST routes in scidk/web/routes/research_objects.py with JSON responses; wire to manager.
  3. Minimal UI: add menu link and simple list/detail templates.
  4. Optional export: JSON-only for MVP; ZIP packaging can be deferred.
- Code Touchpoints:
  - scidk/core/research_objects.py
  - scidk/web/routes/research_objects.py
  - scidk/ui/templates/research_objects/*.html

## Test Plan
- Unit:
  - test_create_research_object_returns_id_and_graph
  - test_add_file_updates_has_part
- Integration:
  - Create RO; add a small file from a scanned directory; GET list shows file_count.
- Acceptance (DoD):
  - From UI, create RO and see it listed; add at least one file and view it on the RO detail page.

## Dependencies
- Requires: basic scan/interpret to extract minimal file metadata (size, mime, checksum) — see task:core-architecture/mvp/filesystem-scan.

## Risks & Rollback
- Risks: Over-scoping UI; keep to minimal list/detail.
- Rollback: Feature flag to hide RO navigation if incomplete.

## Notes
- Vision Alignment: dev/vision/research_objects.md provides UX flows and advanced features (Crate-O editor, smart suggestions). MVP targets the foundational subset to unblock user value and future enhancements.
