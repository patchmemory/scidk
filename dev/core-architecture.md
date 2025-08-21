# Moved: Core Architecture Vision

This vision document has moved. See the canonical version:
- dev/vision/core_architecture.md

## Vision Summary
- ID: vision:core-architecture
- Owner: Platform Team
- Last Updated: 2025-08-21
- Related Docs: dev/vision/core_architecture.md

## Problem & Value
- Problem: Scattered files lack a unified infrastructure for discovery, interpretation, and querying.
- Target Users: Researchers, Core Staff, PIs
- Value Stories: See dev/vision/ux_stories.md (e.g., file discovery, data understanding, fast answers)

## Scope (In / Out)
- In: FilesystemManager, Knowledge Graph adapter (Neo4j), Chat stub, Interpreter & Plugin registries, REST API, minimal UI.
- Out: Full auth, external schedulers (until Alpha), multi-tenant concerns.

## Success Metrics (north stars)
- TTFQ (time to first query) < 10 min on fresh install.
- Scans ≥ 10k files/min on local FS (MVP baseline).
- 95% of interpreter runs cached with versioning.

## Phases
- [phase:core-architecture/mvp] MVP — Status: in-progress, Target: 2025-09-15
- [phase:core-architecture/alpha] Alpha — Status: planned, Target: 2025-10-31

## Risks & Mitigations
- Risk: Neo4j operational overhead → Mitigation: provide Docker Compose and Singularity recipes; document env, resources, and backups.
- Risk: Interpreter execution safety → Mitigation: sandbox stub with timeouts; hardening in Alpha.

## Graph Backend
- Default: The app currently uses an in-memory graph for MVP. Data resets on restart.
- Optional Neo4j: Optional schema endpoints and a Commit-to-Graph API are available. When configured, you can query schema via Neo4j and commit scan results (File/Folder → SCANNED_IN → Scan) for verification.
- Configuration: Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, and optional SCIDK_NEO4J_DATABASE; NEO4J_AUTH=none is supported. See dev/deployment.md and README “Neo4j integration”.
- Future: A GraphAdapter toggle (SCIDK_GRAPH_BACKEND=in_memory|neo4j) is planned to switch persistence without changing flows.

## Open Questions
- What minimum schema changes are needed to support provider metadata and lineage (e.g., RcloneProvider)?
