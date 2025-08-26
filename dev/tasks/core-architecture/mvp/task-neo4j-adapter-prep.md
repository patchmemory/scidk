id: task:core-architecture/mvp/neo4j-adapter-prep
title: GraphAdapter prep for Neo4j backend
status: Done
owner: agent
rice: 3.3
estimate: "0.5\u20131d"
created: 2025-08-21
updated: 2025-08-21
dor: true
dod:
- tests
- docs
- demo_steps
dependencies: []
tags:
- graph
- neo4j
- adapter
story: story:providers-mvp-multi-source-files
phase: providers-mvp-multi-source-files/neo4j-prep
links:
  cycles:
  - dev/cycles.md
  plan:
  - dev/plans/plan-2025-08-21.md
  story: []
  phase: []
acceptance:
- Interface defined with methods: upsert_dataset, add_interpretation, commit_scan,
    schema_triples, list_datasets
- In-memory adapter parity validated by unit tests
- Flag SCIDK_GRAPH_BACKEND toggles adapter selection at runtime
started_at: '2025-08-26T19:12:59Z'
branch: task/task-core-architecture/mvp/neo4j-adapter-prep
completed_at: '2025-08-26T19:13:11Z'
tests_passed: true