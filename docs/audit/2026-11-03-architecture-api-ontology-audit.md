# Architecture, API, and ontology documentation audit

**Date:** 2026-11-03  
**Audited ref:** `design/knowledge-curation-20261029` at `4ed3335`  
**Scope:** documentation authority, REST API contracts, ontology/schema reference, and test/documentation automation. This is an evidence-backed planning audit; it does not change runtime behavior.

## Executive finding

SciDK has useful documentation and an existing interactive API surface, but it does **not** yet have one trusted, maintained documentation system.

The principal risk is not missing prose. It is conflicting claims of currency:

- `scidk/app.py` configures Flasgger at `/api/docs` and emits `/apispec.json`.
- `docs/API.md` describes the REST API separately.
- `README.md` presents SciDK as a minimal MVP and includes endpoint and deployment guidance.
- `QUICKSTART.md` presents a different fresh-install workflow.
- `ARCHITECTURE_HANDOFF.md` explicitly warns that the README is partly stale, but is itself a dated snapshot of `production-mvp`.
- `docs/ROADMAP.md` contains a navigation model that no longer matches the current GUI.
- `docs/audit/DOCS_AUDIT.md` previously described several documents as current, despite the later handoff warning.

The first goal is therefore an **authoritative-source policy**, then generated documentation from those sources.

## Observed runtime architecture

| Concern | Current evidence | Proposed documentation authority |
|---|---|---|
| Application composition | `scidk/app.py:create_app()` | Developer architecture reference |
| Registered HTTP surface | `scidk/web/routes/__init__.py:register_blueprints()` | Generated route inventory |
| Interactive REST reference | Flasgger `/api/docs`, `/apispec.json` | OpenAPI contract |
| API narrative and workflows | `docs/API.md` | Authored guide, linked to OpenAPI rather than duplicate endpoint catalogue |
| Managed graph schema definitions | `scidk/services/label_service.py` | Versioned schema contract/snapshot |
| Observed primary-graph relationships | `scidk/services/relationship_summary.py` | Read-only observed-schema supplement |
| Concept Graph schema | `scidk/concept_graph/*.cypher`, intents/configuration | Separate internal-system schema reference |
| Source mappings | Pipeline mapping schema and configured Source instances | Mapping contract docs, not ontology definition |
| Filesystem inventory | `files.db` / external scan index | Inventory metadata docs; never ontology authority |

## API documentation assessment

### What already exists

- Flasgger is a declared runtime dependency and is initialized by the app factory.
- The interactive documentation route is `/api/docs`; the generated specification route is `/apispec.json`.
- The route registry currently imports and registers a large set of functional blueprints: UI, files, graph, maps, canvas, scripts, tasks, chat, queries, Neo4j, connections, admin, interpreters, providers, drives, annotations, labels, links, settings, auth, users, tokens, audit, alerts, logs, plugins, pipeline, platform, LLM, agent, RO-Crate, enrichment, and external-index routes.
- `docs/API.md` is useful as a human guide, but it duplicates endpoint behavior and response examples that can drift.

### Required next work

1. **Measure coverage before rewriting documentation.**
   - Enumerate Flask routes from the application map in a test.
   - Parse `/apispec.json`.
   - Report documented routes, undocumented routes, orphan spec paths, missing request schemas, and missing response/error schemas.
   - Exclude HTML/UI pages from the REST coverage denominator explicitly.

2. **Make OpenAPI the endpoint contract.**
   - Add route-level summary, tags, request schema, success schema, and known error schema for supported REST endpoints.
   - Define common response envelopes and error shapes once.
   - Mark deprecated aliases explicitly rather than silently documenting both as equal APIs.
   - Keep secrets, filesystem paths, and internal operational details out of examples.

3. **Keep `docs/API.md` as a guide, not the registry.**
   - Cover authentication concepts, pagination/filtering conventions, data ownership, safe examples, and API lifecycle.
   - Link endpoint details to `/api/docs` and checked-in OpenAPI artifacts.
   - Remove or mark examples that disagree with the generated contract.

4. **Publish safely.**
   - Treat the interactive "try it out" UI as an operator/developer facility, not as a public unauthenticated control plane.
   - Document which deployment profile exposes it and how authentication affects it.

## Ontology and schema documentation assessment

SciDK currently has several related but distinct things that must not be conflated:

1. **Managed research schema** — label definitions, properties, relationships, matching keys, and schema-sync metadata.
2. **Observed primary graph shape** — labels and relationship patterns currently present in Neo4j.
3. **Concept Graph schema** — SciDK’s internal AI/planning graph.
4. **Source mapping contracts** — how a configured source maps columns to schema concepts.
5. **Filesystem inventory** — files/folders/scans recorded in `files.db` or an external scan index.

Only the first is an ontology/schema authority for the research graph. The observed graph is evidence about use; it must not silently redefine the contract. Source mappings and filesystem rows are not ontology definitions.

### Recommended in-browser Schema Reference

Build a read-only **Knowledge → Schema Reference** in a later delivery, backed by a pinned managed-schema snapshot with an optional observed-graph supplement.

For each entity type/label it should show:

- name, description, stable identifier/matching key, source/provenance;
- properties, expected types, descriptions, required/optional status where available;
- outgoing and incoming relationship types with direction and target labels;
- controlled vocabulary or external-ontology mappings when explicitly configured;
- optional current observed counts and patterns, clearly labeled as observations;
- snapshot/version timestamp and export/download links.

It should never write graph state, browse raw `files.db` rows, or use a live external scan index as ontology authority.

## Documentation information architecture

Use four audiences and keep planning/session artifacts out of the primary navigation:

- **User guide:** Browse, Datasets, Collections, Knowledge, Review, Resources, Chat.
- **Operator guide:** install, deployment, authentication, graph connections, scan indexes, backups, monitoring, troubleshooting.
- **Developer guide:** application factory, blueprints, service boundaries, plugin/source contracts, testing, contribution workflow.
- **Reference:** OpenAPI, configuration/environment reference, schema/ontology snapshots, plugin contracts, changelog/deprecations.

Suggested top-level documentation additions:

```
docs/
  user/
  operator/
  developer/
  reference/
    api/
    ontology/
    configuration/
  decisions/
  audit/
```

Existing historical roadmaps, handoffs, and session notes should remain available but be clearly dated and non-authoritative.

## Documentation automation roadmap

### Phase A — establish the truth map

- Add a checked-in `docs/REFERENCE_SOURCES.md` naming each authoritative runtime/documentation source.
- Add a documentation status matrix: current, generated, historical, or pending verification.
- Add link checks and a stale-date/header check in CI.
- Do not rewrite every historical document in this phase.

### Phase B — API contract baseline

- Add a route-to-OpenAPI coverage report/test.
- Normalize common API error and pagination documentation.
- Generate a checked-in OpenAPI artifact for review/diffing, if its secret/path-safety is validated.
- Update `docs/API.md` to link to the generated source of truth.

### Phase C — schema reference foundation

- Define a versioned, read-only schema snapshot format from the managed schema definitions.
- Validate the snapshot in tests.
- Document the difference between managed schema, observed graph shape, Concept Graph, mappings, and inventory.
- Add the browser Schema Reference only after the contract is stable.

### Phase D — generated developer documentation

- Adopt MkDocs Material or Sphinx only after the information architecture is in place.
- **Recommendation:** MkDocs Material for the user/operator/developer site and Markdown-native authored guides; use autodoc-style extraction only for selected stable Python service/plugin interfaces. Do not generate an uncurated reference for every internal module.
- Publish local/static documentation first; decide later whether it is hosted separately.

## Immediate risks to resolve

- Conflicting claims that a document is "current".
- README/Quickstart/runtime requirement drift (for example, the package currently declares Python `>=3.12`, while Quickstart states Python 3.10+).
- Old navigation and route descriptions in roadmap/handoff material.
- Endpoint examples that may diverge from the runtime OpenAPI surface.
- Broad existing test failures and frozen visual baselines make documentation claims of verified behavior weaker until baselined.

## Definition of done for the documentation program

A contributor can answer all of these from one maintained documentation system:

1. What does SciDK own, and which data stores are inventories versus graph/schema authority?
2. Which REST routes are supported, how are they authenticated, and what responses/errors do they return?
3. What labels, properties, and relationships define the current research schema, and what version is being read?
4. How does a plugin template become a configured Source, mapping, run, Dataset/Collection, and graph representation?
5. Which documents are current, generated, historical, or planned?

## Deliberately deferred

- A public documentation hosting deployment.
- Full OpenAPI annotation of every route before coverage is measured.
- RDF/OWL publication or import as an ontology authority.
- Automated writes/migrations based on documentation or inferred graph shape.
- AI-generated ontology modifications.
