# Moved: Neo4j Adapter Implementation

This legacy MVP doc has been reorganized. See the canonical design note:
- dev/design/graph/neo4j-adapter-impl.md

## Metadata
- ID: task:core-architecture/mvp/neo4j-adapter-impl
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: planned
- Priority: P0
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-09-06
- Labels: [graph, neo4j]

## Goal
Implement a Neo4j-backed GraphAdapter that matches the existing InMemoryGraph interface and can be enabled via a feature flag, without removing the default in-memory mode.

## Context
- Prep work is defined in dev/core-architecture/mvp/neo4j-adapter-prep.md
- Deployment guidance preview exists in dev/deployment.md (Migration Plan section)

## Requirements
- Interface parity with current usage:
  - upsert_dataset(dataset_dict) -> dataset_id
  - get_datasets(limit?, offset?) -> list
  - get_dataset_by_id(dataset_id) -> dict | None
  - add_interpretation(dataset_id, interpreter_id, result_dict) -> interpretation_id
  - get_interpretations_for_dataset(dataset_id) -> list
  - schema_summary() -> dict (best-effort)
- Feature flag: GRAPH_BACKEND=inmemory|neo4j (default: inmemory). On invalid config or connection errors, fall back to inmemory with a warning.
- Configuration via env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DB (optional)
- Minimum schema:
  - (:Dataset {id, path, filename, extension, size_bytes, created, modified, mime_type, checksum, lifecycle_state})
  - (:Interpretation {id, dataset_id, interpreter_id, created_at, status, payload})
  - (:Dataset)-[:INTERPRETED_AS]->(:Interpretation)
  - Indexes: Dataset(checksum), Dataset(id), Interpretation(dataset_id)
- Safe JSON storage for payload (stringified) for MVP.

## Plan
1. Define GraphAdapter protocol/class boundary in scidk/core/graph.py; keep InMemoryGraph as implementation. 
2. Implement Neo4jGraphAdapter using neo4j Python driver (bolt) with simple queries and indexes.
3. Add adapter selection in app startup (env flag) with try/except fallback to InMemoryGraph.
4. Provide schema initialization routine (idempotent index creation) on first use.
5. Update dev/deployment.md with enablement instructions (link back to this task).
6. Add tests that run core graph operations against the Neo4j adapter if NEO4J_URI is available (skipped otherwise).

## DoD
- With Neo4j running locally (docker-compose.neo4j.yml), setting GRAPH_BACKEND=neo4j allows the app to:
  - upsert datasets, retrieve them, add and fetch interpretations.
- Fallback to InMemoryGraph when Neo4j is unreachable.
- Basic schema_summary returns counts for Dataset and INTERPRETED_AS relationships.
- Tests for adapter parity added or marked to run conditionally.

## Risks & Mitigations
- Connection failures → Fallback to inmemory with clear logs.
- Query performance → Keep MVP queries simple; add indexes.
- JSON payload size → Limit payload size or compress later; MVP stores as text.

## Progress Log
- 2025-08-18: Drafted implementation task; scheduled for next cycle.
