# Knowledge architecture assessment — Stage 0

Date: 2026-10-29. Scope: local inspection; no Neo4j connection or data migration.
Base: `feature/parley-and-resources`, `6c54eb0`.
Design branch: `design/knowledge-curation-20261029` in
`/tmp/scidk-knowledge-curation-20261029`.

## Checkout and inputs

The original checkout has an untracked `codex_prompt_01.txt`, an untracked
`docs/pipeline_scripts_spec.md`, and a modified `dev` submodule pointer.
`dev` is at `c36160f8fde075100af6022afea099ec6e679a0d` with untracked `reviews/`.
These changes are preserved and excluded from the design commit.
Recent parent commits cover LLM usage logging, encryption-key backup guidance,
MicroCT interpretation errors, scan completion ordering, and model selection.

Read the local `dev/plans/parley_and_resources.md`,
`docs/architecture/transparency-layers.md`, and untracked pipeline specification.
The latter two local inputs are not both reproducible from parent HEAD; the
assessment uses the working-copy specification as requested. No ancestor or
repository `AGENTS.md` was found by the instruction search.

## Inventory and dependencies

| Area | Observed implementation | Reuse / dependency |
| --- | --- | --- |
| Operational schema | `scidk/schema/registry.py` loads YAML definitions; `LabelService` manages SQLite `label_definitions` and imports graph schema | Reconcile these before strict ontology validation; never silently choose one on conflict |
| Bundled definitions | Only Sample, ImagingDataset, InstrumentRecord YAML definitions | Person/Project and PI_OF appear in mapping contracts, but are not bundled ontology definitions |
| Local definitions | Read-only SQLite query returned zero `label_definitions` rows | Cannot claim the institution's active ontology is available locally; live graph schema was not queried |
| Schema intelligence | `schema_intelligence.py` stores descriptions, rankings, relationship profiles and embeddings | Reuse descriptive context; rankings and inferred graph shape do not authorize schema changes |
| Intake | `aipt_intake_mapping.json`, `mapping_schema.json`, `mapping_engine.py`, `transforms.py` | Reuse validated mapping and RFC5322 transforms, preserve raw rows and mapping hashes |
| Source execution | `plugin_base.py`, runner, orchestrator, store, FAIR check, scheduler and run history | Plugins expose rows; mapping stays in Pipeline; use resolved declarations for proposals |
| Graph writes | `Neo4jClient.write_declared_nodes`, Neo4j adapter, commit service, dataset service | Existing direct writes remain; new reviewed facts need explicit transaction and receipt behavior |
| Analysis writes | `AnalysisContext` / graph helper inject script and execution provenance | MERGE followed by `SET n = $props` destroys unrelated properties and prior provenance |
| Shared tools | `agent_tools/registry.py`, graph/SQL handlers, `ai/mcp_tools.py` re-export | Single registry already serves HTTP, chat and MCP; extend it rather than duplicate definitions |
| Disclosure | `disclosure.py` supports raw/hidden properties and a withheld-source hook | Source classification, user access, endpoint approval and unknown provenance are not enforced end to end |
| Auth | middleware, per-user tokens, role decorators, `current_user_key` | Reuse identity and roles; review requires a real human identity even when instance auth is disabled |
| MCP | stdio server dispatches through shared registry | ToolContext has no authenticated principal by default; proposals must remain unavailable there until bound to existing SciDK identity |
| Concept graph | Separate driver defaults to port 7689; Concept_Label/Relationship/Tool metadata plus intent embeddings, weighted SATISFIES and decay | Retain metadata; archive planning behavior after dependency review, no new graph service |
| System transparency | SQLite script dependencies, `/api/system/*`, plugin/interpreter metadata | Keep authoritative operational dependencies in SQLite; generate a logical system projection |
| Scan pipeline | Scanner scripts, import pass module, scan Resource snapshot helper, dataset/enrichment services | Preserve canonical scripts; missing script sources block CLI-equivalence claims |

## Verified conflicts and risks

1. **Two schema catalogs.** YAML registry calls itself the schema source of truth;
   SQLite LabelService is separately editable and can pull observed graph shape.
   The prompt's assumption of one already resolved canonical ontology does not
   hold. Recommend a read-only resolution adapter that reports conflicts and
   blocks affected proposals until an administrator resolves ownership.
2. **Person identity.** The reference mapping uses `[email, name]` as a preferred
   merge key. Name-only values can merge distinct people. Introduce source-scoped
   candidates in the new proposal path; do not rewrite historical identities.
3. **Project identity.** CAC protocol is the primary key; fallback includes row
   index. It converges only for a stable export ordering. Use source record IDs
   where available; pin immutable export hash and row locator otherwise.
4. **Relationship provenance.** Declared writes use endpoint/type MERGE without a
   stable relationship fact ID or evidence references. They autocommit and count
   attempted writes even when endpoint MATCH finds nothing. The runner explicitly
   documents partial writes; it cannot implement atomic curation materialization.
5. **Property history.** Declared node writes assign individual properties, rather
   than replacing the full map, but can still overwrite existing values. Analysis
   writes explicitly replace the map. Neither preserves a universal review ledger.
6. **Disclosure fails open for missing provenance.** `load_policy` only loads
   property modes, not Resource risk. `withheld_sources` defaults empty, and
   `run_tool` reloads policy. A record with no `source_id` survives even if a
   withheld-source policy is supplied. Empty policy returns the entire result.
   Aggregates, scalar projections, relationship endpoints and error strings also
   require controls before disclosure; filtering serialized nodes alone is
   insufficient. Local `pipeline_source` schema has no dedicated risk field.
7. **Permissions differ from the desired contract.** Existing decorators allow
   actions when authentication is disabled. Agent ToolContext carries a username
   but no proposal/review capability or approved model endpoint classification.
8. **Missing deployment inputs.** No Work Orders v0.5 mapping was found in the
   inspected plugin/docs/demo/pipeline/review paths. `tools/` contains scanners and
   their spec, but not standalone import/profile/interpret/commit/report scripts.
   Do not reconstruct these independently. Use the existing SharePoint mapping
   for a fixture slice, pending the actual mapping and canonical script sources.
9. **Documentation assumptions differ.** Transparency architecture reserves SQL
   for infrastructure; this design keeps that ownership and exposes a generated
   logical graph. The earlier plan shows interpret → commit without a distinct
   universal assertion review; the new curation path makes review explicit.

## Retirement dependency inventory

Do not unregister or delete anything in this stage.

| Candidate | Known callers/dependents to reconcile before retirement |
| --- | --- |
| Intent classification and execution planning | `api_chat.py` legacy graphrag routes, intent-to-legacy adapter, concept service and fallback classifiers |
| SATISFIES weights, feedback and decay | concept feedback/decay routes, service export/import/seed functions, application maintenance registration |
| Separate concept driver | `scidk/app.py` startup extension, concept CLI, seed scripts and Docker compose |
| Concept settings and embedding refresh | settings partials, chat API management routes, schema intelligence embedding retrieval |
| Tool seeding | canonical registry consumed by concept service and `test_concept_graph_mcp_seeding.py`; retain registry independent of embeddings |
| Portability/export | concept export/import API, CLI and connection tests; preserve metadata and historical exports |

The chat blueprint is still registered. Legacy functions and settings partials
remain present; file existence alone does not prove every partial is visible.
Retirement needs route/UI runtime checks plus the existing chat benchmark decision.

## Validation and next dependencies

Offline baseline on parent HEAD in isolated worktree:

```text
tests/pipeline/test_mapping_engine.py
tests/pipeline/test_mapping_schema.py
tests/pipeline/test_runner.py
tests/test_agent_tools.py
-k 'not graph_tools'
119 passed, 3 skipped, 2 deselected (4.22s)
```

Used the original checkout's `.venv/bin/python`; default pytest addopts disabled.
Skipped/deselected graph cases are not passing results. No production service,
external ontology lookup, scanner migration, or bulk file index access occurred.
This establishes a limited baseline, not validation of the proposed architecture.

Implementation dependency order: approve ontology ownership and identity policy →
ledger/validation/review → disclosure enforcement → projections and registry →
agent proposal integration → fixture materialization and security demonstration.
Approval questions and concrete contracts are in
[the proposal](knowledge-curation-proposal-v0.1.md).
