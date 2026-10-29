# Stage 6: end-to-end validation and GUI readiness

Implemented after `codex_prompt_08.txt` authorized Stage 6, from Stage 5 commit
`a6f9aee`, in the existing isolated `design/knowledge-curation-20261029` worktree.
The authoritative vision and NCI demonstration plan were read from the primary
checkout and preserved. No GUI implementation, harvesting, production bootstrap,
operational ontology change or production database write was performed.

The backend is validated for the synthetic vertical slice and ready for GUI
implementation against the bounded interfaces, subject to the missing adapters
and deployment blockers below. This is not a verified production deployment or a
claim that the NCI demonstration interface already exists.

## Reproducible scenario and implementation

The [fixture runbook](../../tests/fixtures/knowledge_curation/README.md) is stored
at `tests/fixtures/knowledge_curation/README.md` (repository-relative path);
fixtures are `intake.csv`, `corroboration.json` and `catalog.json`. The executable
assembly and tests are `tests/knowledge_e2e/conftest.py` and
`tests/knowledge_e2e/test_vertical_slice.py`.

The CSV contains two synthetic work-order planning records, one CAC protocol and
one repeated name-only PI display name. The actual `MappingEngine` consumes the
unmodified SharePoint `aipt_intake_mapping.json` and `SHAREPOINT_TRANSFORMS`.
The test adapter consumes resulting node/relationship declarations. CACProtocol
selects Project identity within its Resource; the PI uses immutable upstream
RecordID plus mapping role and exact source scope. The legacy mapper's name
fallback is a match hint, not permission for a global Person merge. Two rows
share a Project reference but have distinct PI references; the same names in a
different Resource also stay distinct. Original source bytes, row locators,
source identifiers, derivation roots and the mapping file SHA-256 are retained
in reusable evidence. No scientific observations or acquisitions are invented.

The explicitly synthetic catalog resolves only the fields needed for the slice:
Person name/email, Project project_id/description/source, PI_OF directed from Person
to Project with a declared role vocabulary, and the approved fixture-only
SyntheticWorkOrder disease alignment property. Operational Person/Project/PI_OF
reconciliation is still a deployment blocker; the fixture is not an ontology
migration and must not be used to silently prefer a live YAML or SQLite catalog.

The slice submits through the shared authorized agent tools, previews and reviews
through real authenticated human session routes with an explicit reviewer grant,
and materializes through the existing internally authorized ReviewService.
Accepted existence never approves node properties. Rejected properties stay out
of the graph. Applied facts are read through shared scoped tools, with citations
and separately granted immutable decision history. Assertion references replay
idempotently within the ledger; entity/fact identities remain deterministic.
Existing provenance fields survive accepted property application.

The integration tests found one profile-boundary defect: Overview's explain_fact
could fall back to pending/rejected assertion summaries when the same user also
held Review metadata grants. The only runtime fix makes unsupported-state
inspection opt-in in AssertionAccess and enables it only for the Review profile
in the shared handler. Overview now returns generic refusal for every unsupported
fact, including pending, rejected, superseded and unapplied support. Supported
accepted facts still use the Stage 3 reader. This strengthens the existing
profile contract without changing the disclosure policy, ontology or schema.
The shared agent API document records the clarified behavior.

## Integration validation

Eight tests cover the cross-component boundaries rather than repeat the earlier
stages' unit tests:

| Scenario | Verified behavior |
| --- | --- |
| Mapping → human review → query | Real CAC/PI mapping; separate existence/properties/PI_OF; named reviewer and grant; rejection; preserved provenance; stable identities and idempotent replay; citations/history |
| Profile intersection | A user's Review grants cannot release pending/rejected data through Overview; accepted support is required |
| Transaction/recovery | Missing endpoints refuse; failed batches leave no partial graph/markers; committed graph without SQLite receipts is not accepted support; retry reconciles markers/receipts; another graph target refuses |
| Evidence/lifecycle | Independent synthetic evidence roots support one fact; conflicting acceptance refuses; superseding one support retains another; old graph bytes alone never confer support; explicit reviewed replacement and immutable history |
| Principal/transport boundary | Alice reads Resource A, Bob reads B; identical raw PI names do not merge across scopes; HTTP/chat/host-bound MCP agree; unbound MCP refuses; arbitrary scalar/count/predicate queries and human-decision attempts fail |
| Disclosure revocation | Evidence, property, endpoint reference, Resource grant, classification and destination ceiling changes immediately affect subsequent support queries; high-risk and missing classifications refuse |
| Three domains | System paths/hashes/typed traversal/tool links and actual source drift; Ontology endpoints/vocabulary/revision and explicit conflict blockers; selected MONDO concept and inferred/proposed alignment preserving raw bytes/evidence |
| Existing DMS boundary | Actual collector/generator/HTTP exporter over an accepted synthetic graph with zero files; human draft/placeholders; token refusal; supplied dataset_id does not scope the existing whole-graph collector |

The fake transactional adapter is reused from Stage 2. A retained value in this
adapter tests ledger independence; it is not evidence of live Neo4j behavior.
The existing opt-in Neo4j integration test remains guarded by all four explicit
SCIDK_CURATION_TEST_NEO4J settings, the disposable acknowledgement, and the
`scidk_curation_test_` database prefix. No production URI is inferred or accessed.

The MONDO demonstration uses the existing pinned, hand-curated offline subset,
not a verified upstream clinical release. It preserves the raw disease string,
exact original UTF-8 representation, citation and source derivation. The mapping
is inferred/proposed, with related semantics, and is never accepted or applied.

## GUI backend-readiness inventory

Target navigation remains **Overview → Files → Resources → Knowledge → Review →
Settings**. This stage changes none of those pages. The shared
[agent API contract](knowledge-curation-agent-api.md) remains the implementation
boundary; panels should not create their own curation or authorization logic.

| Surface | Existing backend to consume | Missing adapter or constraint |
| --- | --- | --- |
| Overview Ask SciDK | Chat functions/tools adapters, Overview profile, receipt-backed explain_fact, permitted System/Ontology contexts; existing per-user provider/session store | Free-form prompt/history provenance and a conversational provider loop are not implemented; legacy GraphRAG remains suspended. Fixed-result provider sends are available internally, not an unrestricted chat API. |
| Review contextual assistant | Review profile get_assertion with permitted evidence/current rationale and explicitly granted history; typed submit_assertion; human preview/review routes | No paginated source/status review queue or proposal-draft endpoint. Human materialization is an internal authorized service, not a GUI HTTP apply route. Add a human-only adapter with receipt/recovery semantics before presenting application as complete. |
| Knowledge Research | explain_fact for selected stable fact IDs; current accepted support distinct from review decisions | No source-scoped dataset listing/search, pagination, counts or graph expansion template. Legacy arbitrary SQL/Cypher cannot supply these. |
| Knowledge Ontology | get_ontology_context with canonical/configured external selectors and explicit blockers | Complete reconciled operational catalogs and trusted Resource bindings/grants must be supplied. Do not treat observed graph shape as ontology authority. |
| Knowledge System | get_system_context with bounded typed traversal, references, hashes, versions and scoped stale warnings | Host must configure selected sources and metadata grants; refreshed content needs refreshed grants. No recursive corpus ingestion. |
| Shared evidence inspector | get_assertion evidence_id/citation/version, permitted current rationale, separately granted decision history | Raw excerpts, source-record payloads and arbitrary evidence lookup are intentionally absent. Richer inspection needs a bounded authorized serializer, not the raw ledger API. |
| Sketch → curation | Typed proposal contract, source-scoped candidates, existing evidence, explicit Review capability and exact Resource proposal grant | A snapshot-to-proposal translator with evidence capture and canonical endpoint validation is still needed. A drawn label or edge is not evidence or an ontology definition. |

The test assembly is not a production source runner or startup configuration.
A production mapping-to-assertion adapter, evidence capture, catalog reconciliation,
trusted service wiring, profile/tool/proposal grants and destination approvals
remain explicit work. Flags remain default-off. Readiness for GUI development is
conditional on keeping these absent operations visibly unavailable.

## Existing Canvas, Resources and plugin boundaries

`scidk/services/canvas_service.py` persists per-user/context canvas sessions and
query libraries in the settings database; named layers use SavedMapsService.
`pipeline_source:<id>` is already a source-specific context. Schema-space elements
represent types, not automatically accepted research entities. Preserve those
context/user keys and deletion semantics in the redesign.

`scidk/web/routes/api_canvas.py` exposes sessions, layers, node search/expansion,
verification and Cypher/Python/RO-Crate exports. Its existing POST `/api/canvas/commit`
uses `build_commit_plan` and direct `write_declared_nodes`, matching by name. It
does not produce curation evidence, human review decisions or applied receipts.
The redesign must not repurpose that direct commit path for Sketch-to-curation
or advertise its raw graph helpers as agent tools. Existing behavior is preserved.
The future translator must retain raw sketch content and create separately
reviewable existence/property/relationship proposals.

Resources already owns source schema/mapping configuration through
`api_pipeline.py`: GET/PUT `/api/pipeline/sources/{id}/mapping` (mapping plus actual
engine validation), schema/Arrows import/export, columns, connection testing,
preflight/FAIR checks, and explicit run/schedule operations. `pipeline_mapping.js`
is the existing declarative mapping model; `pipeline_mapping.html` renders it.
Role IDs distinguish multiple mappings to one label. Partial mappings may be
saved but must validate before running. Keep these contracts and the canonical
scanner/import/profile pipeline; do not infer curation acceptance from legacy
pipeline merge output or silently change its name-based deduplication behavior.

`PluginTemplateRegistry` describes code-backed templates, configuration schemas,
categories (data_import, graph_inject, enrichment, exporter), versions and graph
behavior, separately from user instances. `api_plugins.py` exposes template
listing, instance configuration and execution; Resources uses data_import
filtering. These are existing human configuration/runtime services, not automatic
permission to fetch external data, add ontology definitions or commit proposed
knowledge. Reuse template metadata and instance/source identity in future adapters;
no plugin harvesting or template rewrite was performed here.

## NIH DMS Plan exporter readiness

Implementation is `plugins/nih_dms/routes.py`, `graph_facts.py`, `generator.py` and
`config.py`, with `tests/test_nih_dms_plan.py`. It is not part of a model provider
or the new agent tool registry.

Invocation is GET `/api/plugins/nih_dms/draft_plan`: Markdown by default,
`?format=json` for markdown/summary/filename, `?download=1` for an attachment.
Optional `sample_limit` explicitly weakens the exact file scan and is disclosed
in the generated draft; `deep=1` forces the per-label schema read. `/config`
describes supported fields/settings. Current UI is the Files header's Generate
DMS Plan Draft drawer (`files/_dms_panel.html`, `ui/static/js/dms.js`) with copy
and Markdown download; it does not pass a selected dataset identifier.

The collector consumes **whole-graph** entity/relationship counts, File format,
MIME and volume distributions, known modality/assay values, schema-layer property
names and sharing metadata, plus `publication.dms.*` settings. The renderer is a
pure function of GraphFacts. It generates draft NIH Elements 1, 3, 4 and 5;
Elements 2 (software/tools) and 6 (oversight) remain explicit investigator prompts.
People must decide repository, retention, sharing mode, access contact, software,
responsibilities and award/consent/privacy-specific details, complete placeholders,
and review the entire draft. Settings can fill repository/retention/mode/contact;
unset settings stay visible bracketed placeholders. There is also a legacy
settings-store boundary to verify: schema/sharing metadata uses the route's
read-only `SCIDK_SETTINGS_DB` connection, while publication settings are obtained
through `core.settings.get_setting`, whose current implementation resolves
`SCIDK_DB_PATH` (or cwd `scidk.db`). The new GUI must verify where publication
settings are actually saved/read before promising that those controls populate
the draft; this stage did not change the exporter or settings storage.
Name-based PHI detection is
a warning heuristic, not proof of de-identification or consent compliance.

A selected-dataset export is **not implemented**: a dataset_id argument currently
has no filtering effect. A new GUI button may open the existing whole-graph draft,
but it must say so. Supporting the preferred NCI Files → selected dataset → export
workflow requires a real selected-dataset collector/adapter with explicit scope,
not a cosmetic button or silently ignored parameter. The actual exporter operates
on synthetic graph fixtures in the existing tests; the new integrated test derives
a draft from synthetic accepted identity metadata with zero scientific files.
No real scientific measurements were invented to make a plan look populated.

Exporter role checks allow existing admin/user humans and Stage 3 middleware
blocks API-token/AI access. Its global aggregates, property values and schema
metadata do **not** pass new Resource/evidence/current-support disclosure gates.
Sharing modes are drafting input, not complete export authorization. Graph/connection
errors can contain operational details intended for the existing human route.
Do not send this output to an AI endpoint, mix restricted tenants, claim dataset
scope or claim it is safe under the new agent policy without a separately scoped
adapter. For an NCI fallback, use a wholly authorized synthetic/demo graph and
human-only access. Preserve honest graph-unavailable failures, draft wording,
placeholders, sampling warnings, copy/download and the human-review requirement.
No claim of automatic NIH compliance is appropriate. The exporter was not rewritten.

## Deployment and unverified behavior

Production catalog reconciliation, real SharePoint authorization/records, dataset
recognition on actual scientific files, live Neo4j transactional/recovery behavior,
provider/network behavior beyond existing fakes/loopback tests, real model answers,
production concurrency, large-graph performance, browser workflows and the redesigned
GUI have not been verified by this synthetic slice. The existing multi-writer
materialization limitation remains. Test-source bindings/capability setup must not
be copied as an implicit production authorization policy.

Before a live NCI demonstration, configure a curated authorized dataset/account,
source/evidence/context grants, approved actual provider destination, reconciled
ontology and safe human application workflow. Verify dataset-specific DMS scope
if claimed, and retain the plan's tested fallback build/recording. This report
supports GUI planning and backend contracts; it does not authorize deployment,
production imports, autonomous commits or starting the GUI before Stage 6 review.

## Test results

Focused Stage 6 suite: **8 passed, 0 failed, 0 skipped, 0 deselected** in
21.75 seconds. Final relevant regression: **666 passed, 0 failed, 1 skipped,
0 deselected** in 162.08 seconds, with 8 existing schema-intelligence deprecation
warnings. The broader suite was run once at completion. The earlier targeted
profile regression first demonstrated the Overview defect, then passed in the
focused and final broader suites after the minimal fix.

No browser tests were added or run. The skipped test was
`tests/curation/test_neo4j_optional.py::test_disposable_neo4j_transaction_and_marker_replay`:
explicit disposable configuration was not supplied. Real Neo4j is the only
opt-in external service in this selection. Provider tests use a temporary
loopback HTTP fixture and fake responses, not a real provider account; the broader
run required approval for that local server. No production behavior is certified.

Commands used `/home/patch/PycharmProjects/scidk/.venv/bin/python` in the isolated
worktree:

```sh
python -m pytest tests/knowledge_e2e -q -o addopts=''
python -m pytest tests/knowledge_e2e tests/agent_integration tests/knowledge \
  tests/security tests/curation \
  tests/pipeline/test_mapping_engine.py tests/pipeline/test_mapping_schema.py \
  tests/pipeline/test_runner.py tests/pipeline/test_mapping_ui.py \
  tests/pipeline/test_api_mapping.py tests/pipeline/test_canvas_context.py \
  tests/test_agent_tools.py tests/test_api_tokens.py tests/test_chat_api.py \
  tests/test_chat_fixes.py tests/test_chat_intent_routing.py \
  tests/test_llm_provider_settings.py tests/test_schema_intelligence.py \
  tests/test_concept_graph_mcp_seeding.py tests/test_mcp_tools_offline.py \
  tests/test_canvas_export_auth.py tests/test_plugin_template_registry.py \
  tests/test_nih_dms_plan.py -q -o addopts=''
```

The focused suite was rerun after standard CSV quoting preserved the intentionally
space-padded disease value without trailing line whitespace. Whitespace validation
passed. The primary checkout's existing modified submodule
and untracked prompts, vision/demo documents and specification were preserved.

## Changed files

Runtime changes are limited to `scidk/agent_tools/assertions.py` and
`scidk/agent_tools/knowledge.py` for the Overview support boundary. Documentation
updates are this report, `knowledge-curation-agent-api.md` and
`knowledge-curation-implementation-plan.md`. New isolated test files are
`tests/knowledge_e2e/{__init__.py,conftest.py,test_vertical_slice.py}` and
`tests/fixtures/knowledge_curation/{README.md,intake.csv,corroboration.json,catalog.json}`.
