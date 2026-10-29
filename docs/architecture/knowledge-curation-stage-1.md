# Stage 1: isolated ledger and validation

Implemented 2026-10-29 after approval in `codex_prompt_02.txt` and confirmation
to continue. Branch: `design/knowledge-curation-20261029`.

The `scidk.curation` package is deliberately unregistered. Importing it opens no
connections, creates no schema, and adds no routes, tools or startup hooks.
`migrate(path)` explicitly initializes a separate SQLite ledger and refuses a
database containing unrelated tables. It does not infer the file-index path.
No graph connection is made by this package.

Implemented contracts:

- Versioned canonical Unicode JSON and deterministic entity/fact IDs. Name and
  email claims cannot merge source-scoped candidates. Property values do not
  participate in property fact IDs, so contradictory assertions coexist.
- Immutable evidence/assertions and append-only decision/submission records,
  enforced by SQLite update/delete triggers, foreign keys and unique revisions.
  Actor-scoped idempotency is serialized in one transaction. Reads are explicitly
  internal; they are not a disclosure-safe serialization interface.
- Strict proposal fields, evidence existence/access checks through a mandatory
  trusted-caller callback, source scope, ontology revision, domain, confidence,
  candidate identity, property types and relationship endpoints/direction.
  Accepting an assertion never changes its immutable epistemic status.
- A read-only ontology adapter takes explicit YAML/LabelService snapshots. It
  preserves constraint/sanitization metadata, hashes source snapshots, coalesces
  equal definitions, and raises reconciliation errors for differences. YAML files
  are parsed individually so duplicate labels cannot silently overwrite one
  another. No live SQLite catalog is opened automatically.

No operational Person/Project/PI_OF definitions were invented. Those labels are
synthetic fixtures only; undeclared operational labels remain blocked. All
same-label differences, including metadata or constraints absent in one catalog,
are conservative conflicts rather than an implicit preference for either catalog.
Evidence from another source Resource requires a separate source-scoped assertion;
multiple exports/evidence roots within the same scope are supported. Future
cross-Resource reconciliation must preserve source-specific identities and policy.
Relationship property validation uses explicit declared relationship schemas;
undeclared relationship properties fail closed.

Validation command (original checkout's Python, isolated worktree):

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest \
  tests/curation tests/pipeline/test_mapping_engine.py \
  tests/pipeline/test_mapping_schema.py tests/pipeline/test_runner.py \
  tests/test_agent_tools.py -k 'not graph_tools' -q -o addopts=''
```

Result: **149 passed, 3 skipped, 2 deselected**. Of these, 30 passing tests are
new foundation cases. Skipped/deselected graph cases are not claimed verified.
Tests use synthetic catalogs, temporary SQLite databases and no Neo4j service.
They cover concurrent replay, mutation rejection, independent evidence roots,
conflicting claims, supersession lineage, catalog conflicts, stale revisions,
source-scoped identity, domain separation, and node/relationship properties.

Stage 2 remains unimplemented: authorized review, preview/concurrency contract,
materialization outbox/receipts and graph transactions/crash reconciliation.
Decision writes in tests exercise storage directly, not a review authorization
API. Stage 3 must still establish disclosure enforcement before agent exposure.
The existing agent disclosure implementation is unchanged by this stage.

Rollback: revert this additive package/tests/docs commit. Nothing imports it from
app startup. Preserve any intentionally initialized ledger as audit history;
never delete it as an automatic rollback. No production writes, bulk migration,
scanner/import changes or deployment changes were performed.
