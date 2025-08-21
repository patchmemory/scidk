# Neo4j Adapter Implementation Notes

- Prep work is defined in dev/core-architecture/mvp/neo4j-adapter-prep.md (legacy) and feature doc dev/features/core-architecture/feature-graph-adapter-boundary.md.
- Deployment guidance preview exists in dev/ops/deployment-neo4j.md (Migration Plan section)

Implementation outline:
1. Define adapter class with methods per feature boundary
2. Wire to settings/feature flags
3. Implement minimal Cypher for upsert and interpretation linkage
4. Add tests with mocked driver
5. Update dev/ops/deployment-neo4j.md with enablement instructions (link back to this doc)
