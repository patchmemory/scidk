# Stage 2: authorized review and recoverable materialization

Implemented in the existing isolated `design/knowledge-curation-20261029`
worktree, following `codex_prompt_03.txt`. Stage 3 has not been started.

## Changes and API contracts

| File | Responsibility |
| --- | --- |
| `scidk/curation/review.py` | Authorized previews, optimistic review, dependency/conflict validation, atomic decisions/outbox and serialized application/receipts |
| `scidk/curation/auth.py` | Existing named admin sessions plus explicit existing-user grants; excludes API tokens and legacy/anonymous sessions |
| `scidk/curation/materializer.py` | Explicit-driver Neo4j adapter; one write transaction for the full batch and operation markers |
| `scidk/curation/migrations.py` | Explicit append-only schema v1 → v2 migration adding outbox, receipts and immutable graph-target binding |
| `scidk/curation/ledger.py` | Recognizes v2; migration remains explicit and refuses unrelated/future databases |
| `scidk/curation/ontology.py` | Returns validated property metadata to enforce storage/sanitization policy; changes no ontology definitions |
| `scidk/web/routes/api_curation.py` | Human-only review blueprint and generic error responses |
| `scidk/web/routes/__init__.py` | Registers that blueprint only with `SCIDK_CURATION_ENABLED=1` |
| `tests/curation/test_{api,review,materializer,migrations,neo4j_optional}.py` | Security, state machine, transaction/recovery and optional disposable-driver verification |
| `tests/curation/__init__.py` | Local fixture import package |
| `docs/architecture/knowledge-curation-{stage-2,implementation-plan}.md` | This handoff and updated stage status |

Routes are absent by default. Enabling registration alone creates no database,
graph connection, migration, worker or agent tool. A host must explicitly attach
`ReviewService(ledger, granted_user)` as `app.extensions['curation_review']` before
serving requests. An enabled but unconfigured service returns 503 to an authorized
human. The ledger's evidence callback must independently check that current user
against the source policy; a permissive test callback is not a deployment policy.

- `POST /api/curation/assertions/{assertion_id}/preview`: previews an existing
  assertion for human review. Returns claim, per-fact proposal diff, current
  revision, ontology/evidence hashes, dependencies, accepted conflict/support IDs,
  and a deterministic `preview_digest`. This is a ledger proposal diff; current
  graph values are checked inside the application transaction. This route is
  distinct from the future proposal-body preview API in the architecture plan.
- `POST /api/curation/assertions/{assertion_id}/review`: requires JSON fields
  `action` (`accept`, `reject`, `supersede`), `expected_revision` (integer),
  `preview_digest`, and nonempty `rationale`. Supersession additionally requires
  `superseded_by`, an existing non-rejected replacement for the same fact. Unknown
  fields fail. Returns decision/revision/operation IDs, derived curation status,
  and `materialization_status: pending` (200). It never reports graph application.
- Malformed JSON/non-object bodies: 400. Missing named authentication or disabled
  auth: 401. Invalid human grant/API credentials/cross-origin request: 403.
  Stale revision/digest, repeat decisions or conflicting accepted support: 409.
  Contract/access validation: generic 422. Unconfigured/unavailable service or
  unexpected failures: generic 503. Source values and exception strings are not
  returned in errors.

No submit, public read, graph-query or materialize HTTP routes were introduced.
No tools were added to the shared agent registry or MCP.

## Authorization and audit assessment

The existing `require_admin` decorator intentionally bypasses authorization when
instance auth is disabled; curation does not use that bypass. Each request checks
`AuthManager.is_enabled()`, a valid unlocked **named multi-user session cookie**,
the user's current enabled/admin role and explicit grant. Authorization headers,
including valid admin API tokens, are rejected. Legacy single-user sessions do
not satisfy the named existing-user requirement. Requests with an incompatible
Origin or cross-site fetch metadata are rejected.

Explicit human grants are JSON integer user IDs under
`curation.human_reviewer_user_ids` in the existing settings database's
`interpreter_settings` table. No new identity/credential database or user table
was added. The list defaults empty; malformed grants deny. Provisioning these
privileged grants is an explicit local administrative operation, not a new HTTP
or agent capability. No grants were configured in an existing deployment.

The service's mandatory authorization callback is rechecked at preview, review
and materialization. Production composition uses `granted_user` in an app
context, and the HTTP boundary derives reviewer IDs from the existing session,
never request JSON. Direct service APIs are trusted internal Python interfaces;
an agent must not be given Python execution or reviewer session credentials.
Human identity relies on administrators granting actual human accounts and
protecting their sessions; the existing auth system has no biometric/user-presence
proof. Per-user evidence authorization is separate and rechecked at every stage.

HTTP reviews also call the existing `AuthManager.log_audit` using username,
decision ID and client IP. Full rationale, immutable reviewer ID and decision
history remain in the ledger; the existing audit logger is best effort and not
the source of transaction correctness. Every decision and its outbox item commit
in the same SQLite transaction. Tests inject an outbox failure and verify neither
record commits.

## Application transaction and recovery

`ReviewService.materialize(operation_ids, reviewer=..., graph=...)` is an explicit
internal operation, not a worker launched at startup. It holds a SQLite
`BEGIN IMMEDIATE` writer lock while it validates decisions, evidence authorization,
ontology revision, conflicting support, accepted/materialized dependencies and
receipts. A separate SQLite transaction first durably binds the ledger to one
explicit graph target, before any graph I/O. This binding survives a crash before
the first receipt and cannot be changed or deleted. All receipts must match it.
Within a batch, accepted dependencies may be applied in the same transaction;
otherwise a prior applied acceptance receipt is required. An actual graph MATCH
miss or ambiguous match still aborts, even when the ledger had an endpoint receipt.

`Neo4jMaterializer` requires a supplied driver, explicit database and stable target
identity. It discovers no environment credentials and applies no DDL. Provision
the approved `SciDKCuratedEntity.entity_ref` uniqueness constraint, and an
operational `SciDKCurationOperation.operation_id` uniqueness constraint, on an
explicit disposable graph before deployment testing. No constraints were applied
by this implementation run. This operational marker is the approved crash-recovery
mechanism, not a new scientific ontology type.

The adapter uses one `session.execute_write` transaction for all facts and their
operation markers. Nodes precede relationships, then properties, irrespective of
input ordering. Node acceptance writes existence and operational provenance only;
names/email/other identity claims stay in the ledger. Relationships MERGE on
accepted endpoints/type/deterministic fact ID (which includes identity qualifiers).
Properties set only their individual key and `updated_at`; there is no full-map
replacement. Existing creation time, unrelated properties and provenance survive.
The property adapter obtains a write lock with a self-dependent SET before
comparing the stored value, preventing a concurrent writer from changing it
between comparison and application. Unsupported existing values cause a conflict.
Only previously applied, explicitly superseded values of that same property fact
are eligible for a reviewed correction. Operational provenance keys are protected.
Null deletion and undeclared/invalid properties fail validation.

Each graph transaction stores operation ID, immutable operation hash and outcome
in an operational marker. After successful graph commit, SQLite records receipts.
If the process dies between commits, SQLite rolls back its receipts but the graph
marker persists. A retry checks the hash, skips the already applied fact and
records the missing receipt. The marker's original outcome remains authoritative
for recovery even if that decision was superseded before retry. A still-unapplied,
now-obsolete acceptance is marked obsolete without writing its fact.

Curation status derives solely from append-only decisions. Epistemic status never
changes on acceptance. Supersession records replacement lineage without deleting
facts or evidence. Another accepted assertion can continue to support the same
fact. Different accepted property values cannot coexist; supporting conflicting
assertions must first be explicitly superseded before a correction can apply.

## Validation

Run from the isolated worktree with temporary SQLite and synthetic catalogs:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest \
  tests/curation tests/pipeline/test_mapping_engine.py \
  tests/pipeline/test_mapping_schema.py tests/pipeline/test_runner.py \
  tests/test_agent_tools.py tests/test_api_tokens.py \
  -k 'not graph_tools' -q -o addopts=''
```

**203 passed, 4 skipped, 2 deselected** (14.89 seconds).
The curation suite contributes 68 passing tests (30 foundation cases and 38 new
Stage 2 cases), plus one skipped optional Neo4j integration test. Three skips
come from the existing agent suite; two existing `graph_tools` cases are
explicitly deselected. The 16 existing API-token tests are also included.
`git diff --check` reports no whitespace errors.

Coverage includes real existing-auth/session/settings/audit integration on a
minimal Flask app, both service-level transactional fake graphs and the actual
Neo4j adapter's driver boundary, concurrent submissions/reviews/materialization,
stale previews, separate node/property acceptance, missing graph endpoints,
idempotency, property conflicts, preserved legacy provenance, nondestructive
supersession, rollback, crash/reconciliation including supersession during the
crash gap, revoked access, changed ontology, malformed grants and explicit migration.

The optional Neo4j test requires `SCIDK_CURATION_TEST_DISPOSABLE=1` plus all of
`SCIDK_CURATION_TEST_NEO4J_URI`, `_DATABASE`, `_USERNAME`, `_PASSWORD` (full shared
prefix). Database names must start `scidk_curation_test_`. It never assumes a
localhost graph is safe and cleans up only its own UUID-scoped nodes/markers.
The optional test was not executed against any Neo4j instance in this run.

## Limits, rollback and Stage 3 recommendation

- This is a single-ledger, serialized materializer. The SQLite writer lock spans
  graph I/O; another writer may time out and must retry. Multiple independent
  ledgers/materializers for one graph are unsupported. No distributed atomic
  commit or generalized multi-writer protocol is claimed.
- Supersession changes the supported ledger view and never deletes graph data.
  A superseded property may remain physically present until an accepted correction
  is applied. Raw graph projections must not be treated as a current accepted
  knowledge API; Stage 3 must consult current ledger support. No automatic legacy
  node adoption, compensating deletion or orphan graph cleanup is implemented.
- Research assertions materialize to Neo4j; system/ontology domains remain logical
  projections. Scientific catalog reconciliation is still required for actual
  Person/Project/PI_OF inputs. No operational ontology was changed.
- Non-`none` sanitization rules block materialization until a reviewed fail-closed
  sanitizer is available. The existing sanitizer explicitly passes through on
  failure, which is inappropriate here. Homogeneous scalar lists are supported
  by the Neo4j adapter; nested/mixed lists are refused.
- No live Neo4j syntax/constraint/network verification is claimed without the
  opt-in disposable integration test. No production writes or bulk migrations,
  canonical pipeline changes, concept-graph retirement or deployment changes
  occurred. Existing primary-worktree changes remain untouched.
- Source/disclosure enforcement, model destination approval and safe bounded
  agent query serialization still belong to Stage 3. Keep this feature default-off
  and keep all new records out of agent tools until that gate passes. Stage 3
  should include current-support checks, both relationship endpoints, provenance
  propagation, protected citations/metadata, and scalar/aggregate query refusals.

Rollback disables `SCIDK_CURATION_ENABLED`, stops explicit materialization and
removes the service extension. Preserve ledger decisions/outbox/receipts and graph
markers for recovery. There is no automatic downgrade or deletion of audit history;
reverting source must not attempt to open a v2 ledger with the old v1 service.
No approval to begin Stage 3 is inferred from Stage 2 completion.
