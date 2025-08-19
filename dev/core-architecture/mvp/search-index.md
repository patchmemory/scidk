# Task: Basic Search Index (MVP)

## Metadata
- ID: task:core-architecture/mvp/search-index
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: done
- Priority: P2
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-18
- Labels: [search, indexing]

## Goal
Provide a basic in-memory search index over Datasets and Interpretations to power simple keyword search in the UI (file name, extension, interpreter_id, and small payload snippets).

## Requirements
- Index fields: dataset filename/path, extension, mime_type; interpretation interpreter_id and selected keys (flattened).
- Build/refresh index on scan and on new interpretation; full rebuild endpoint for MVP.
- API: GET /api/search?q=term returns top N matches (id, type, snippet).
- UI MVP: add a simple search input on Home that calls /api/search and shows results list.
- Tests: unit tests for indexing and simple queries.

## Plan
1. Implement a simple indexer class (dict-based inverted index) in core.
2. Wire into existing flows (scan and interpret) to update index.
3. Expose /api/search route; add minimal UI on Home.
4. Add tests.

## DoD
- Searching for a known filename or interpreter_id returns relevant datasets.
- Index updates on new scans/interpretations without app restart.
