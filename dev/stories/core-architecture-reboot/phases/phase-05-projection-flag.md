id: phase:core-architecture-reboot/05-projection-flag
story: story:core-architecture-reboot
order: 5
status: Planned
owner: agent
created: 2025-08-28
updated: 2025-08-28
e2e_objective: Feature-flagged projection to Neo4j via outbox worker; browsing unaffected if Neo4j is down
acceptance:
  - Config flag projection.enableNeo4j=false by default; when true, outbox worker runs
  - Creating a dataset/RO triggers outbox event; worker MERGE-s nodes/edges in Neo4j keyed by IDs
  - Failed projections retry with backoff; processed_at set on success
selected_tasks:
  - task:core-architecture/mvp/outbox-projection-neo4j-flag
links:
  plan: [dev/plans/plan-2025-08-28-reboot-architecture.md]
