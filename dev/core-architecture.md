# Core Architecture

## Vision Summary
- ID: vision:core-architecture
- Owner: Platform Team
- Last Updated: 2025-08-18
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
- [phase:core-architecture/mvp] MVP — Status: planned, Target: 2025-09-15
- [phase:core-architecture/alpha] Alpha — Status: planned, Target: 2025-10-31

## Risks & Mitigations
- Risk: Neo4j operational overhead → Mitigation: provide Docker Compose and Singularity recipes; document env, resources, and backups.
- Risk: Interpreter execution safety → Mitigation: sandbox stub with timeouts; hardening in Alpha.

## Graph Backend
- We standardize on Neo4j (v5 LTS) as the knowledge graph backend with APOC and neosemantics (n10s) enabled by default.
- Deployment: run alongside SciDK using Docker Compose or Singularity (see dev/deployment.md).
- Connectivity: configure via NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.
- Semantic/ETL support: APOC for utilities and import/export; n10s for RDF/OWL handling and JSON-LD.

## Open Questions
- What minimum schema is required to support Plugin MVP?
