# Stage 4: generated system and ontology contexts

Implemented on the isolated `design/knowledge-curation-20261029` branch after
Stage 3 (`099a5ac`) and approval of `codex_prompt_06.txt`. The user separately
approved a fixture-only ontology for the MONDO alignment example. Operational
scientific labels, relationship types and the Stage 1 contract are unchanged.

## Components and usage

`scidk.knowledge.projection.system_projection(repository_root, bindings)` builds
23 entries, including eight workflow roots, from an explicit manifest. It reads
only selected files, hashes their bytes, records Git HEAD and applicability
`knowledge-context/1`, and validates AST declaration names and Markdown headings.
No source content, configuration values, repository recursion or embeddings are
included. Transparency documentation and the canonical tool-registry source are
reused as references. A reference to discovery does not re-enable suspended tools.

`projection.traverse('workflow:csv-import', depth=3, limit=128)` returns the intake
README, CSV reader, mapping engine, mapping schema, permission documentation and
policy implementation, connected by DOCUMENTED_BY, IMPLEMENTED_BY, REQUIRES and
VALIDATED_BY. Tool discovery uses EXPOSED_VIA. Scan snapshot import is identified
separately from CSV intake. These are generated projection relationships, not new
canonical operational predicates or assertions written into a scientific graph.

Traversal is deterministic outgoing breadth-first traversal, bounded to depth 6,
256 results, 512 projection nodes and 4096 edges. Exceeding a result bound refuses
rather than producing a silently incomplete context. `snapshot()` and traversal
return defensive copies. `freshness(root, revision=..., applicability=...)` warns
on missing/changed files, missing symbols/headings, Git or applicability changes.
Missing files have `valid=false` and no content hash; they are never represented
as valid authoritative sources. Paths and symlinks escaping the repository refuse.
`compare(regenerated_projection)` detects snapshot changes, including SQLite and
external source revisions that cannot be checked against filesystem paths.
Freshness is an explicit trusted-local operation; no background watcher is added.

`scidk.knowledge.ontology.ontology_projection(yaml_paths, sqlite_snapshot,
bindings=..., revision=...)` reuses Stage 1 `Ontology` parsing/reconciliation.
Label, property and relationship nodes have navigable source/target endpoint
links, types, identity keys/indexes, vocabularies, source hashes and ontology
version. Incoming declarations are interpreted according to their direction.
Missing endpoints, catalog disagreement and inconsistent endpoint property
metadata produce explicit validation blockers. Conservatively, **the entire
catalog is non-authoritative when any definition is unresolved**; it exposes no
resolved label nodes until reconciliation. No production catalog is opened, no
catalog is preferred silently and observed Neo4j shape is never consulted.
Deployments must supply complete, explicitly reconciled snapshots. Known bundled
`Sample` references `Study`, which is absent from the bundled slice; older observed
YAML/SQLite disagreements remain deployment blockers rather than being repaired
in this stage. No claim is made to have audited a live operational catalog.

`scidk.knowledge.external.ExternalRegistry` stores a bounded selection of concepts
and pinned registration metadata. `mondo_fixture()` loads the committed offline
subset. It accepts MONDO CURIEs, OBO identifiers and the configured exact URI
prefix, rejecting arbitrary URLs, invalid accessions and ambiguous term matches.
It records namespace, source URI, version, identifier pattern, resolver metadata,
retrieval timestamp, citation, visibility, label, synonyms and provenance.
Registration is atomic and cannot replace an existing namespace pin. There is no
network resolver. The registry supports opaque resource-kind/metadata fields and
separate OBO versus identity identifier styles; the literature fixture test
illustrates that PubMed is not forced into OBO semantics. MeSH, OBI, UBERON,
ChEBI, CL, UO, OME, Reactome and WikiPathways adapters are future work, not claimed
implemented formats. There is a 128-selected-concept bound per registration.

The MONDO record is explicitly a hand-curated demonstration subset pinned to
`offline-demo-2026-10-29`, **not a verified upstream release or clinical mapping**.
It makes no claim of an actual remote retrieval. `propose_alignment` preserves
raw input in a structured property value and derived evidence, with
pinned concept and registry metadata. Exact local label/synonym matching proposes
only `related` semantics; it does not assert scientific equivalence. It submits
an `inferred` property assertion via the existing ledger and leaves its curation
status `proposed`. It neither accepts nor materializes anything.

The executable synthetic Work Order example is
`tests/knowledge/test_contexts.py::test_work_order_alignment_is_fixture_only_proposed_inferred`.
Its isolated `SyntheticWorkOrder.disease_alignments` list property is the
user-approved test ontology. No such definition is installed operationally.
A caller must supply an explicitly declared suitable property and existing target;
Stage 1 rejects undeclared operational properties. The intake evidence scope must
match exactly; its original citation/version/derivation root remain intact, while
MONDO citation/provenance is added as derived content. Stage 1 canonical JSON
normalizes text to NFC; `original_utf8_hex` additionally preserves the exact
original UTF-8 bytes, including decomposed Unicode and surrounding whitespace. No unrelated `notes` or
ICD-10 diagnosis field is repurposed, and no alignment contract kind is invented.

## Security and persistence

Builders, snapshots, freshness and traversal are trusted-local APIs. They are not
agent authorization boundaries and must not be exposed directly. The sole new
disclosure service is internal `ContextService(..., enabled=False)`. Enabling it
requires an explicit trusted configuration decision; no routes, agent tools,
provider sends or automatic application wiring were added.

`ContextService.read(start, server_bound_identity)` freshly resolves Stage 3
`PolicyStore` and approves the authenticated principal, exact Resource scope,
classification, source grant and bound destination before returning anything.
Every source inside every returned node must have its own explicit scope. Missing
policy, provenance, hash, grant, approval or identity yields the same generic
refusal. High-risk sources always deny. Public external metadata still requires
Resource classification and a source grant; repository docs default restricted.

System bindings map manifest IDs to existing Resource scopes. Ontology bindings
map `catalog` and each source path (or `sqlite:Label`) to existing scopes; all
catalog sources are conservatively attached to each definition, including depth-0
queries. There is no automatic Resource creation or classification. Every restricted
node additionally requires an existing Stage 3 evidence-metadata grant keyed by
`ContextService.grant_id(node)`. That immutable content digest binds grants to
revision, provenance and exact projection metadata; regeneration requires fresh
grants when content changes. This deliberately conservative internal convention
uses the existing grant table, with no migration or new policy default.

Property policies apply to each serialized node field (`KnowledgeContext` for
system/external entries, canonical label or predicate for ontology definitions),
and each nested canonical entity/relationship property. Non-raw modes refuse the
whole context rather than masking structural dependencies. Conflict diagnostics
require authorizing all projection nodes and their sources. Errors never reveal
withheld paths, identifiers or counts. Metadata grants are not implied by a source
grant or administrative role. The service performs no network send; Stage 5 must
bind and recheck the actual provider endpoint/model before transport, as Stage 3
does for its fixed-fact helper. MCP remains without authenticated identity binding.

Committed manifests and the offline fixture are persisted files. Graphs, source
snapshots, registry instances and diagnostics are generated in memory. Only an
explicit caller of `propose_alignment` persists evidence/assertions to its supplied
isolated ledger. Settings policy remains the existing Stage 3 store. No production
DB writes, new service/database, migrations or graph materialization occur.
Rollback is to omit/disable this package; no operational schema rollback is needed.

## Validation and next stage

Final focused suite: **46 passed, 0 skipped, 0 deselected** (12.69 seconds).
The broader regression run: **451 passed, 1 skipped, 0 deselected**, with 8
existing deprecation warnings (74.21 seconds). The broader run included the
initial 45 Stage 4 tests; the final focused run additionally covered exact UTF-8
preservation through Stage 1 Unicode normalization. No broad suite was repeated.
All tests use
synthetic intake/catalogs and temporary auth/policy/ledger databases. The optional
Neo4j test remains opt-in for explicitly disposable infrastructure.

Stage 5 should add narrowly typed context tools only after review, binding real
HTTP/chat identity, exact source scopes and actual destination configuration.
Keep proposal discovery/MCP disabled until equivalent authenticated policies exist.
Do not route arbitrary graph results through these projection readers. An operator
must reconcile operational catalogs and approve context source/metadata grants
before enabling definitions for agents.

The existing concept graph's canonical tool-definition catalog and schema/tool
link patterns could support a future authorized projection adapter. Its current
separate Neo4j planner, embedding search and unscoped schema are not a security
boundary and are not used here. Concept-graph behavior is unchanged; suspended
Stage 3 paths remain suspended. Stage 5, GUI changes and plugin harvesting have
not begun.

Validation commands (from the isolated worktree, using the existing `.venv` Python):

```sh
python -m pytest tests/knowledge -q -o addopts=''
python -m pytest tests/knowledge tests/security tests/curation \
  tests/pipeline/test_mapping_engine.py tests/pipeline/test_mapping_schema.py \
  tests/pipeline/test_runner.py tests/test_agent_tools.py tests/test_api_tokens.py \
  tests/test_chat_api.py tests/test_chat_fixes.py tests/test_chat_intent_routing.py \
  tests/test_llm_provider_settings.py tests/test_schema_intelligence.py \
  tests/test_concept_graph_mcp_seeding.py tests/test_mcp_tools_offline.py \
  -q -o addopts=''
```

The broader run used approval for its temporary loopback HTTP provider fixture;
no real provider or production database was used. The single skipped test was
the opt-in disposable Neo4j integration test. Primary-checkout uncommitted files
were preserved.
