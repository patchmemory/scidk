# Knowledge curation implementation and validation plan

The v0.1 proposal was approved with clarifications in `codex_prompt_02.txt`
and implementation was authorized to continue on 2026-10-29.
The [assessment](knowledge-curation-assessment.md) records observed limitations.
[Implementation stage 1](knowledge-curation-stage-1.md) is complete: isolated
ledger/validation and 30 new passing tests. Stages 2–6 remain pending.
The historical design-stage completion report below predates this approval.

## Focused implementation commits after approval

1. **Ledger and contract:** add a curation service, explicit isolated SQLite
   migration, immutable evidence/assertion storage, append-only decision events,
   deterministic fact IDs, canonical ontology adapter and validation. Test all
   three target kinds, candidate entities, evidence lineage, conflicts, version
   mismatches, invalid identifiers and types, source-scoped Person identities.
2. **Review and materialization:** isolated routes behind default-off flag; reuse
   authentication/audit facilities, explicit human reviewer capabilities, preview
   digest and optimistic concurrency. Add transactional Neo4j materializer and
   recoverable operation receipts/outbox. Test permissions, replay, stable edge
   IDs, provenance preservation, MATCH misses, rollback and crash reconciliation.
3. **Disclosure gate:** resolve Resource classification and principal/model policy;
   withhold unknown provenance, restrict unsafe Cypher/SQL projections and
   aggregates. Test nodes, relationships/endpoints, assertion/evidence/citation
   content, errors and metadata, source-policy changes, no-auth review rejection,
   missing/unreadable policy and unapproved destination endpoints.
4. **Generated contexts:** versioned small manifest and deterministic excerpts;
   resolved ontology context, selected-concept registry with MONDO fixture. Test
   path/symbol/hash drift, permissions, schema conflicts, normalized external
   identifiers, source versions and preservation of original intake strings.
5. **Shared agent integration:** add controlled context/explanation/status tools
   to the canonical registry, typed authorized proposal tools, HTTP/chat/MCP parity.
   Keep MCP proposal discovery off without authenticated existing-user binding.
   No review/accept/materialize agent tool. Test bypass attempts and denied sources.
6. **Vertical slice and documentation:** fixture intake → mapped declaration →
   proposals → review → graph → permitted fact/citation query. Publish runnable
   offline demo instructions, complete contracts and known limitations. Compare
   existing pipeline tests; preserve canonical scanner behavior and CLI sources.

Each commit includes focused tests and rollback notes. No route unregistration,
concept graph deletion, AI planner changes, UI rewrite or full ontology import.
Future enrichment plugins submit the same evidence/assertion contracts; implement
no harvesting in this slice.

## Offline acceptance scenario

Use a synthetic SharePoint row shaped like the existing reference mapping until
an authorized, de-identified real intake record and Work Orders v0.5 mapping are
available. Do not copy local institutional source records into committed tests.
Reuse the existing mapping engine and transforms rather than emulate its logic.

1. Resolve a CAC Project identity and parse PI Archived. A PI with no email gets
   a source-scoped candidate, never a global name merge. Record immutable export
   hash, row locator and mapping revision as reusable evidence.
2. Produce separate Person-existence, Person-name and PI_OF proposals. Return
   an honest validation blocker if canonical Person/Project/PI_OF definitions
   have not yet been reconciled. Proposed relationships do not appear in graph.
3. Preview, accept existence/property/relationship separately with a named
   authorized human. Reject a conflicting unsupported property. Materialize only
   accepted facts, with accepted endpoints, stable edge identity and receipts.
4. Replay application and attach a second source: one relationship remains and
   both evidence records survive. Supersede a claim without erasing decisions or
   removing other accepted support. Exercise a process crash between graph and
   ledger commits using a test adapter.
5. An agent explains the accepted PI_OF fact and permitted citations; another
   principal cannot retrieve restricted evidence, identifiers, excerpts or counts.
   Strip provenance deliberately and verify refusal. Try a scalar Cypher query
   and an aggregate inference; both must fail the restricted query gate.
6. Return a scan workflow documentation reference with hash; change the fixture
   document and demonstrate stale detection. Return one canonical outgoing
   relationship definition with allowed endpoint labels and ontology revision.
7. Register a pinned MONDO fixture and propose a disease alignment. Raw intake
   text remains, and the mapping stays proposed/inferred until human review.

Use temporary SQLite databases and fake graph adapters by default. Optional
integration tests require an explicitly configured disposable Neo4j, never infer
safety from a localhost URL. Never set production credentials in a test command.

## Completion report for this design stage

Files added: the assessment, v0.1 proposal and this plan. Runtime code, pipeline
behavior, schema definitions and stored scientific facts are unchanged.
Baseline: 119 passed, 3 skipped, 2 deselected across mapping engine/schema,
runner and agent-tool tests (see assessment for scope). No new runtime tests are
claimed, because no implementation exists yet. Design documents are manually
checked against inspected source; graph DDL is illustrative and unapplied.

Blockers: user approval of v0.1; canonical schema reconciliation; missing Work
Orders v0.5 and standalone pipeline sources; authorized real demonstration row;
approved endpoint classification policy; explicit disposable graph configuration
for optional integration verification. A synthetic fixture can exercise the
foundation while deployment inputs are obtained.

Deferred: bulk external ontology ingestion, bibliographic scraping, generalized
concurrent graph materialization, legacy provenance backfill, ontology RDF/OWL
export, concept-route retirement and major curation UI work.

Security: the existing disclosure behavior is insufficient for exposing the new
records. Feature flags alone do not establish authorization. The disclosure gate
must pass before agent integration is released. Existing agent exposure is not
claimed remediated by these design documents.

Next action: approve or revise the proposal, then implement ledger/validation
first in the isolated branch. Production Neo4j writes require separate approval.
