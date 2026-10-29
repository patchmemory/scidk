# Prompt 15 Resources reuse and dataset reconciliation

This is a code/fixture reconciliation. No operational graph was queried, migrated
or declared accepted. Operational ontology compatibility remains unverified.

| Workflow | Existing implementation retained | GUI integration / limit |
|---|---|---|
| Resources | `/pipeline/sources`, `/pipeline/sources/<id>/schema`, `/pipeline/sources/<id>/mapping`; `pipeline_sources.html`, `pipeline_schema.html`, `pipeline_mapping.html` | Existing primary navigation and readiness link use these pages. |
| Source/schema/plugin templates | Pipeline routes, store, plugin registry and existing schema editor | Existing capabilities and deep links retained. No second registry/editor. |
| Mapping validation/FAIR | `tests/pipeline/test_api_mapping.py`, `test_api_fair_check.py`, existing engine and FAIR services | Existing builder retained; mapping GET/PUT JSON APIs exist. An arbitrary JSON-to-builder-to-JSON round-trip is **unavailable/unverified**; do not claim lossless support. |
| Runs/schedules/history | Existing pipeline runner/orchestrator and source pages | No replacement scheduler or new capability source operation. Authorization-dependent/unconfigured operations remain unavailable. |
| Annotations | Files `files/_annotate_panel.html`, `annotate.js`, existing attribution/collection/interpreter endpoints | `/annotations` redirects to `/datasets?panel=annotations`, opening the same drawer. Attribute/Collect/Interpret remain intact. Inspector button opens this workflow using **checked Files/collection** scope; inspector focus alone does not select files. |
| Legacy annotation reads | Existing `/api/annotations?file_id=...` | Inspector continues identity-filtered reads. No alternate annotation store. |

## Legacy identity versus governed identity

`api_annotation.py` documents collection `Dataset` nodes and direct `CONTAINS`
edges to `File` nodes. File identity is `(path, host)`; host is derived using
provider/root provenance. Properties use `filename` and `size_bytes`. Files with
the same path on different hosts must remain distinct. The older `/api/datasets`
checksum/index interpretation object is another concept, not automatically a
curated collection. Neo4j internal IDs, element IDs, display names and a browser
selection are insufficient evidence of accepted membership.

The curation ledger derives immutable candidate identity from source-scoped
identifiers under a pinned ontology. Evidence must include its source scope,
version/hash, citation, locator, method and visibility. Dataset existence, File
existence, each direct membership edge and exported properties require their own
accepted and currently applied support. Resource and restricted evidence grants
remain necessary; acceptance alone does not authorize disclosure.

`services/dataset_sharing.py` enforces this contract for the selected stable Dataset
reference, including each direct File membership and its path/size/extension
support. Legacy graph presence cannot substitute for that evidence. Missing
membership, unsafe paths, denied evidence, stale/rejected/retracted support or
unapplied acceptance keep DMS/package creation unavailable. No raw-graph fallback
or bulk dataset export was added.

## Explicit synthetic onboarding path

Reproduce in disposable fixtures with:

```bash
PYTHON_DOTENV_DISABLED=1 /home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest \
  tests/knowledge_e2e/test_prompt12.py tests/knowledge_e2e/test_review_workspace.py \
  -q -o addopts=''
```

The `datasets` fixture in `test_prompt12.py` uses a labeled fixture-only
Dataset/File/CONTAINS catalog. It creates source-scoped candidates and versioned
synthetic evidence, submits node/property/membership assertions, invokes the real
human-review preview/digest/decision HTTP contract as a named fixture reviewer,
and applies operations through FakeGraph. These decisions are explicit test
inputs, not automatic live human acceptance. Two source scopes verify selected
Dataset isolation. Existing tests exercise Markdown/ZIP provenance/manifest,
guided fields, support revocation and safe relative paths.

For a real authorized representative Dataset, an operator must first reconcile
the operational catalog (read-only), record source identity and evidence, obtain
any required ontology approval, submit proposals, have a named authorized human
review them, and apply using the existing materializer. Grant only necessary
Resource/evidence and exact model destinations. Then expose the ledger stable
entity reference on the existing Dataset browser record; never infer it from
legacy graph IDs. No live adapter or bulk migration was implemented.

Files → Dataset → Metadata is covered with synthetic legacy display fixtures.
The existing stable `entity_ref` links carry selected Dataset context to Knowledge
and Review; browser tests verify those affordances, Knowledge/Review use real
isolated ledger services, and sharing UI tests use explicit mocked display replies.
Backend fixtures verify the actual governed sharing boundary. A single live
Files-to-package institutional workflow remains blocked on operational identity,
evidence, ontology compatibility and service assembly; it is not claimed as tested.
