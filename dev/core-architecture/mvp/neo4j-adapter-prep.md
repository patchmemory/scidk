# Task: Graph Interface Boundary & Neo4j Adapter Prep

## Metadata
- ID: task:core-architecture/mvp/neo4j-adapter-prep
- Vision: vision:core-architecture
- Phase: phase:core-architecture/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-28
- Labels: [graph, neo4j, docs]

## Goal
Define the Graph interface boundary and outline steps to migrate from InMemoryGraph to a Neo4j-backed adapter, without switching runtime yet.

## Requirements
- Identify the minimal interface used by the app (current calls in scidk/core/graph.py and its consumers):
  - upsert_dataset, get_datasets, get_dataset_by_id
  - add_interpretation, get_interpretations_for_dataset
  - schema_summary (optional)
- Propose an Adapter interface (class or protocol) and a Neo4jGraphAdapter skeleton API shape.
- Document migration steps (config flags, environment variables) in dev/deployment.md and cross-link here.

## Plan
- Survey code to confirm surface.
- Draft adapter interface and discuss mapping to Neo4j schema (labels, rels, indexes).
- Document rollout plan: feature flag to switch adapter; environment variables to configure Neo4j.

## DoD
- dev/deployment.md gains a "Migration Plan: InMemoryGraph → Neo4jAdapter" section with steps and risks.
- This task references the plan and outlines the adapter API.

## Progress Log
- 2025-08-18: Drafted scope and DoD; write-up to be added during next cycle.
- 2025-08-18: Completed prep documentation. Added "Migration Plan: InMemoryGraph → Neo4jAdapter" to dev/deployment.md with interface boundary, feature flag plan, rollout steps, and risks; cross-linked from this task. Status set to done.
