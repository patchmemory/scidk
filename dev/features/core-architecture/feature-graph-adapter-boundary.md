id: feature:core-architecture/graph-adapter-boundary
title: Graph Adapter Boundary (InMemory vs Neo4j)
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Define a clean GraphAdapter interface to enable switching between in-memory and Neo4j backends.
scope:
  - Adapter interface: upsert_dataset, add_interpretation, commit_scan, schema_triples, list_datasets
  - Feature flag for backend selection
  - Parity tests across implementations
out_of_scope:
  - Full migration tooling
success_metrics:
  - Backend can be switched without affecting routes or UI
links:
  stories: []
  tasks: [task:core-architecture/mvp/neo4j-adapter-prep]
notes: |
  Implementation guidance and deployment notes: dev/ops/deployment-neo4j.md
