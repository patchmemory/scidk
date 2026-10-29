# Knowledge and curation architecture v0.1 — PROPOSED

Date: 2026-10-29. **Approved for isolated implementation with clarifications in
`codex_prompt_02.txt`; no production application authorized.**
Recommended contract version: `curation/0.1.0`; operational ontology revision:
`scidk-knowledge-0.1.0-proposed`, finalized only after catalog reconciliation.
This document is a proposal, not another editable operational schema.

## Ownership and storage decision

Keep three logical domains (`system`, `ontology`, `research`) on existing
infrastructure. No new graph database, model planner or orchestration engine.
Persist immutable assertions, reusable evidence and append-only decisions in an
isolated SQLite curation database, configured separately from the large file
index. This is a shared service ledger, not a fourth knowledge domain.
Accepted research facts materialize in the existing Neo4j graph. System and
ontology contexts start as deterministic projections; optional Neo4j caches
remain disposable and versioned. SQLite script dependencies remain authoritative.

Resolve ontology from the current YAML registry and administrator-maintained
label definitions. Export a normalized snapshot with source hashes and version.
Equal definitions coalesce; conflicting property types, identities, directions
or constraints produce errors. Observed graph shape is diagnostic, never an
implicit approval. Require administrator reconciliation for Person, Project,
PI_OF and any other label absent from the resolved catalog before materializing.
Once ownership is resolved, all contexts/validators consume that one adapter.

## Proposed ontology delta

Reuse Person, Project, Attachment and SUBMITTED, PI_OF, COLLABORATES_ON,
HAS_ATTACHMENT from the intake contract, subject to canonical catalog validation.
Reuse existing dataset and scientific labels; no synonymous leadership edges.
MeasurementRequest and Measurement remain distinct where already defined; intake
alone must never create actual acquisitions, sessions or measured results.

New logical record types:

| Record | Identity and core fields | Storage / classification |
| --- | --- | --- |
| CurationAssertion | assertion_id; domain; target_kind; subject_ref; target_ref; predicate; object_ref; property_key; proposed_value; candidate; epistemic_status; confidence; confidence_method; proposed_by; agent/model/version; method; ontology_version; created_at; evidence_refs; validity; supersedes | Immutable ledger; inherits most restrictive source access |
| EvidenceSource | evidence_id; source_type; source_id; URI/document ID; citation; version/date; accessed_at; content_hash; locator; run_ref; retrieval_method; visibility; excerpt; derivation_root | Immutable ledger; citation/locator can itself be restricted |
| CurationDecision | decision_id; assertion_id; expected_revision; action; reviewer_id; reviewed_at; rationale; superseded_by | Append-only ledger; authorized reviewers |
| MaterializationReceipt | assertion_id; decision_id; fact_id; graph target; operation_hash; applied_at; outcome | Ledger/outbox; restricted operational provenance |
| ExternalOntology | namespace; registry URI; version; citation; allowed identifier pattern; resolver; retrieved_at; visibility | Versioned registry record; no full imports |
| ExternalConcept | stable URI/accession; namespace; label; synonyms; source version; retrieval time; citation/evidence | Selected concepts only; never automatically accepted mappings |
| SystemKnowledgeEntry | id; kind; source path; symbol/section; source hash; Git revision; version applicability; permission; links | Generated context; explicit visibility required |

The persisted assertion's claim never changes. Current curation_status is derived
from decisions: proposed, accepted, rejected, superseded. Epistemic status is
independent: observed, inferred, confirmed. Changing a claim or epistemic status
requires a new assertion linked by supersession, preserving its history.

Proposed graph properties on newly curated facts: `fact_id`, `source_scope`,
`created_at`, `updated_at`, `curation_status`. Detailed evidence stays in the
ledger keyed by fact_id; no full citation arrays on each entity.
Node existence, each property and each relationship have different fact IDs.
Node acceptance does not approve its proposed properties.

No new research relationship type is needed for the first slice. Optional
projection edges DOCUMENTED_BY, IMPLEMENTED_BY, EXPOSED_VIA, REQUIRES and
VALIDATED_BY are **proposed system-domain semantics**, pending ontology review.
External alignment uses exact/close/broad/narrow/related values in assertions,
not unreviewed scientific graph edges.

## Identity and graph schema diff

Stable source entity reference: namespace + Resource ID + upstream immutable
record ID + role. Name-only Person candidates remain source-scoped and unresolved.
Email/ORCID are identity evidence, not blanket automatic cross-source merge
authority. Preserve original names, original term strings and source locators.
CAC protocol reuse requires the correct institutional scope. For exports without
upstream IDs, use immutable export hash + row locator; reordered exports need
explicit reconciliation, not a claim of stable row-index identity.

Use SHA-256 over canonical, versioned JSON for fact identity:

- Node: domain + canonical entity reference + existence marker.
- Relationship: domain + canonical subject + predicate + object + identity
  qualifiers (e.g. role/validity when these distinguish separate facts).
- Property: domain + target fact/entity reference + property key.

Conflicting property values share a target fact key but have distinct assertion
IDs. Normalize encoding and qualified references before hashing. Never depend
on Neo4j internal IDs. Multiple evidence sources support the same fact without
duplicating the relationship. Independent observations retain source lineage;
repeated model output from one source is not independent corroboration.

Proposed OpenCypher DDL, illustrative until resolved definitions generate it:

```cypher
// PROPOSED ONLY: curated nodes receive an additional scoped label.
CREATE CONSTRAINT scidk_curated_entity_ref_unique IF NOT EXISTS
FOR (n:SciDKCuratedEntity) REQUIRE n.entity_ref IS UNIQUE;
CREATE INDEX scidk_curated_fact_idx IF NOT EXISTS
FOR (n:SciDKCuratedEntity) ON (n.fact_id);
```

No CurationAssertion/EvidenceSource Neo4j labels or constraints are necessary for
the ledger-first slice. New curated nodes add SciDKCuratedEntity and entity_ref;
existing nodes can be adopted only through a reviewed identity mapping. Source
business-key constraints continue to come from canonical label definitions.
Relationship fact_id is enforced by transactional endpoint/type/qualifier MERGE
and a serialized materializer in the initial slice; do not rely on Enterprise-only
relationship uniqueness constraints. Multi-writer support requires a stronger
locking/constraint strategy before enabling concurrent materializers.

## Contract and validation

A node assertion has candidate.label, candidate.source_scope,
candidate.source_identifier and candidate.identity_claims and can exist before
any graph node does. Candidate properties are previews; accepting existence
does not set them without separate accepted property assertions.
A property assertion names target_ref, property_key and typed proposed_value;
relationship targets use stable fact IDs. A relationship assertion requires
subject_ref, predicate and object_ref, with accepted endpoints before application.

All proposals require explicit domain, actor (server-derived), active ontology
version, method, visibility/source scope and at least one existing authorized
evidence reference. Unknown fields, bad identifiers, invalid confidence (outside
0–1 or non-finite), wrong property types, undeclared predicates, invalid endpoint
labels/directions, unknown evidence and incompatible versions fail validation.
Proposals can reference candidate entities, but materialization blocks until their
identities and existence are accepted. Source evidence and business rules must
permit the claim; matching terminology alone does not confirm interpretation.

Preview returns validation errors, per-fact diff, dependency/conflict IDs,
ontology revision, source hashes and a deterministic preview digest. Submission
is idempotent under a caller key scoped to authenticated actor; reusing a key
with a different body returns 409. Server assigns immutable IDs and timestamps.

Review is propose → validate → human review → accept/reject → materialize.
Review requires expected_revision and preview digest; stale decisions return 409.
Store reviewer identity, rationale and timestamp atomically with an outbox item.
Revalidate ontology/source access and dependency state at review and application.
Acceptance can be pending materialization; never report it as applied prematurely.

Use one Neo4j transaction for the accepted batch and an in-graph operation marker
to reconcile a crash between graph commit and SQLite receipt. A retry checks the
operation hash; failed batches leave no partial graph facts. Reject endpoint
MATCH misses explicitly. Preserve original created_at and existing provenance;
update only the accepted property, reject null deletion unless explicitly reviewed.
Never call AnalysisContext's full-map replacement for curation. Existing direct
pipeline writes stay unchanged until separately tested integration is approved.

Contradictory claims coexist. A reviewer must resolve an active property conflict
before application; no last-writer-wins inference. Superseding one supporting
assertion must not delete a fact still supported by another accepted assertion.
Correction records the replacement and recalculates the supported view; revocation
does not erase history or indiscriminately delete legacy graph facts.

## API and permission contract

Feature flags `SCIDK_CURATION_ENABLED` and `SCIDK_KNOWLEDGE_CONTEXT_ENABLED`
default off. Unregistered routes return 404. Reuse Flask conventions, existing
sessions/tokens, stable user keys and audit logging. New capability checks extend
existing authorization; no new credentials or identity database.

| Operation | Contract / authorization |
| --- | --- |
| GET /api/curation/assertions | Cursor pagination and domain/status/target filters; only visible records |
| GET /api/curation/assertions/{id} | Claim, derived status, permitted evidence and decision history; hidden IDs return 404 |
| POST /api/curation/assertions/preview | Same typed input as proposal; no ledger or graph writes; authorized submitter |
| POST /api/curation/assertions | Validated proposal and evidence IDs; 201 or idempotent replay; explicitly granted proposal capability |
| POST /api/curation/assertions/{id}/review | accept/reject/supersede, expected_revision, rationale and digest; human reviewer capability |
| GET /api/ontology/context | Resolved definitions, directions, types, identifiers, hashes/version and catalog conflicts |
| GET /api/system-knowledge/context | Relevant manifest entries, bounded excerpts, authoritative paths/hashes and stale warnings |
| GET /api/curation/evidence/{id} | Only permitted citation fields; separate evidence-read check |

Malformed input returns 400, contract violations 422, unauthenticated 401,
forbidden capability 403, stale/conflicting write 409. No raw source payloads in
errors. Proposed initial mapping: users may read permitted accepted knowledge;
proposal submission requires an explicit existing-user grant; admin humans review
research claims, and admin humans additionally authorize ontology changes and
materialization. Grant implementation must use the current auth storage pattern.
Agents never receive review/accept/materialize capability. Anonymous/no-auth
instances cannot perform review; a named local reviewer must first be configured.

## Disclosure release gate

Before exposing new records, load Resource risk and user grants in the policy,
propagate trusted provenance to graph facts and ledger records, and require an
approved disclosure classification for the destination model. Missing Resource,
classification, principal or policy availability means withhold/refuse. Explicitly
public generated system entries may be read without Resource identity only when
their manifest declares a trusted public source and classification.

Evaluate relationships with both endpoints; apply the most restrictive source
and evidence policy. Redact citations, locators, filenames, excerpts, metadata,
counts and existence signals where revealing them violates access. A public
assertion is not allowed to expose a restricted evidence identifier. Recheck on
each read because source access may change after acceptance.

Arbitrary Cypher cannot be made safe solely by a post-result property filter:
predicates, scalars and aggregates can reveal withheld facts. For restricted or
unclassified sources, disable general graph-query tools until a trusted scoped
query implementation is available. New tools use bounded fixed templates with
authorization before execution and serialization. Restrict SQL tools equivalently.
Do not expose raw exception text through tools. Add endpoint approval to the
existing provider/context selection path; do not invent a provider engine.

MCP read tools: get_system_context, get_ontology_context, explain_fact,
get_assertion. Submit_assertion is advertised only for a principal with explicit
proposal permission. Existing stdio startup has no user binding; keep proposal
tools unavailable until it uses an existing SciDK user/token context. Registry,
HTTP and chat adapters must enforce the same capability and disclosure gates.

## Projections and external vocabulary

Seed a reviewed manifest with these eight essential entries: scan workflow
(scanner and scanner spec); import workflow (import pass module); intake mapping
(reference JSON/schema/README); interpretation (analysis context and transparency
doc); graph commit (commit service and Neo4j client); tool discovery (registry and
api_agent); ontology definitions (YAML registry/LabelService); disclosure
(disclosure module and role decorators). Do not claim absent script paths exist.
Each has identity, source path/symbol or section, content hash, Git revision,
applicable version, explicit visibility, permissions and typed links. Validate
paths, sections and registered tool names; mark stale on hash mismatch, missing
symbol or incompatible version and return authoritative references with warnings.
No recursive whole-repository document ingestion, runtime model or embeddings.

Register MONDO first, with version and source citation; use offline fixtures for
the demo. Extend the registry to OBI, MeSH, UBERON, ChEBI, CL, UO and OME
standards without assuming identical identifier schemes. Validate accession and
URI normalization per namespace; preserve original identifiers. Resolver adapters
must pin source version, timestamp and citation, enforce trusted endpoints and
avoid arbitrary URL fetching. PubMed is a literature source, not an ontology.
Only selected concepts are stored. A disease string produces an inferred,
proposed alignment assertion with match semantics and evidence, preserving the
raw intake value. It never silently becomes confirmed or accepted.

## Migration, rollback and approval scope

No bulk migration or scan-index schema changes. After approval, create only the
isolated ledger schema through an explicit versioned migration. Existing graph
facts remain legacy/unclassified until reviewed or safely withheld. Apply proposed
graph DDL only to an isolated test graph first; production requires separate
explicit approval. Store schema revision and pre-application preview artifacts.

Rollback disables feature flags and stops materialization; the ledger/history
remains intact. Optional projections may be discarded and regenerated. Reverting
materialized facts requires reviewed compensating assertions and receipts, not
bulk deletion by label. Drop new indexes/constraints only after dependency checks;
never remove existing institutional constraints or automatically reverse user work.

Approval requested for: ledger-first persistence; canonical catalog conflict
resolution policy; source-scoped identity policy; new curated identity properties
and scoped label/DDL; authenticated human-only review and capability mapping;
fail-closed agent disclosure restrictions; and the staged implementation plan.
Approval does not authorize production writes, bulk migrations, retirement or
scientific acceptance. Missing deployment mappings and script sources remain
explicit integration dependencies.
