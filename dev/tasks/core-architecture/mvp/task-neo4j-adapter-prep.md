id: task:core-architecture/mvp/neo4j-adapter-prep
title: GraphAdapter prep for Neo4j backend
status: Ready
owner: agent
rice: 3.3
estimate: 0.5–1d
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
  - tests
  - docs
  - demo_steps
dependencies: []
tags: [graph, neo4j, adapter]
story: 
phase: 
links:
  cycles: [dev/cycles.md]
  plan: [dev/plans/plan-2025-08-21.md]
  story: []
  phase: []
acceptance:
  - Interface defined with methods: upsert_dataset, add_interpretation, commit_scan, schema_triples, list_datasets
  - In-memory adapter parity validated by unit tests
  - Flag SCIDK_GRAPH_BACKEND toggles adapter selection at runtime
