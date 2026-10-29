# Agent disclosure policy v1

Approved by `codex_prompt_05.txt`. Implementation checkpoint: Stage 3. This
policy governs agent/model disclosure, independently of authorized human review
or internal storage. It is not a certification of the institution's classifications.

## Authorization rule

Disclosure requires all of the following at the time of the read/send:

1. A named, enabled existing SciDK user, authenticated by the server adapter.
2. Exact Resource provenance, an explicit classification and that user's explicit
   Resource grant. Existing source names, FAIR scores, storage location, a default
   risk value or graph presence are not approvals.
3. An approved exact endpoint/model identity. External API tokens must be bound
   server-side to that identity. Session-based chat uses the current per-user
   provider configuration matched to an approval. Client headers, preset names,
   localhost, environment fallbacks and possession of an API key imply no approval.
4. Low/medium source risk at or below the destination ceiling. High-risk Resource
   data is globally prohibited from AI disclosure, without a provider exception.
5. Visible properties, current accepted support and an applied acceptance receipt
   for the configured graph target. Relationships require visible endpoints;
   property claims require separate acceptance from node existence.
6. Permitted supporting sources and separately authorized citation metadata.

Any missing/unavailable/unknown policy input denies. Administrators have no
implicit AI Resource access grant. Property preferences default to raw only
inside an otherwise complete, readable policy; a missing policy/table never means
public. Unknown property sharing modes deny. Human acceptance preserves the
assertion's original epistemic status, including inferred evidence.

## Administrative storage and setup

`PolicyStore` in `scidk/agent_tools/security.py` uses the existing settings
SQLite database, `auth_users`, `api_tokens`, `auth_audit_log` and `pipeline_source`.
No new identity system or canonical pipeline columns are introduced.

| Table | Authority |
| --- | --- |
| `agent_disclosure_schema` | Explicit policy schema version, currently 1 |
| `agent_resource_classification` | Exact namespace/Resource ID, risk, classifying admin, revision |
| `agent_resource_grant` | Existing user ID + exact Resource identity |
| `agent_destination_approval` | Exact endpoint/model, low/medium ceiling, approving admin, revision |
| `agent_token_destination` | Existing API-token ID → approved destination ID |
| `agent_evidence_grant` | Separate restricted citation-metadata grant per existing user/evidence ID |
| `agent_sharing` | Existing per-label/per-property raw/hidden preference table |

Initialization and policy management are explicit trusted local administrative
operations, not HTTP or agent tools. Initialization requires an existing enabled
admin and existing Resource/auth tables; reads use SQLite read-only mode and
never create a missing database. No production policy records were created by
this implementation. Example composition, using already identified test/local
records (not an instruction to classify real data):

```python
from scidk.agent_tools.security import PolicyStore

store = PolicyStore(existing_settings_db)
store.initialize(admin_id=existing_admin_id)
store.classify(namespace, existing_resource_id, 'medium', admin_id=existing_admin_id)
store.grant_resource(existing_user_id, namespace, existing_resource_id, admin_id=existing_admin_id)
store.approve_destination(destination_id, approved_base_url, approved_model, 'medium', admin_id=existing_admin_id)
store.bind_token(existing_token_id, destination_id, admin_id=existing_admin_id)
```

`grant_resource(..., allow=False)`, `grant_evidence(..., allow=False)` and
`revoke_destination(...)` revoke authority. Each administrative mutation checks
current admin role/enabled state and records operation kind/administrator/time in
the existing auth audit log in the same transaction. Resource/destination records
also carry their current approving admin and revision. Full before/after policy
snapshots are not an immutable history; audit operation details currently identify
the operation kind rather than a full record diff.

The server's existing API-token verifier now returns the matched token ID in
addition to the existing user fields. HTTP context construction authenticates
against that verifier; it never accepts a claimed username/model from tool JSON.
Disabled/deleted users, revoked tokens, missing bindings, deleted Resources and
revoked approvals fail on subsequent reads. There is no permission snapshot cache.

## Query and adapter boundaries

Existing generic graph/schema/count/file-index tools are suspended. They have
no source-aware execution template and cannot be made safe by filtering their
results. Their catalog descriptions say so. Even a valid principal/destination
receives the same refusal before handler execution, graph connection, predicate,
aggregate or file-index access. Arbitrary SQL strings are never accepted as a
new agent capability; existing SQL-backed aggregate/file tools are also refused.

`filter_for_agent` now refuses arbitrary preconstructed payloads, including maps
with plausible `source_id` hints, scalars, counts, backend errors and missing
provenance. `check_cypher` refuses all arbitrary Cypher. There are no withholding
counts, hidden labels, citation IDs, filenames or backend exception messages in
the refusal response:

```json
{"status":"refused","error":"SciDK cannot authorize disclosure for this operation."}
```

Existing API tokens are restricted by middleware to the agent catalog/execution
interface. They cannot bypass disclosure through human graph/SQL/export/settings
APIs, including public bootstrap routes or by adding a session cookie. Named
human sessions retain the existing human interfaces. Do not hand those sessions
to agents. The restriction applies to unbound as well as bound API tokens; it is
an intentional change from the former admin-token access to arbitrary APIs.

All four GraphRAG reply paths and the schema-embedding refresh path refuse before
context collection, graph query, provider construction or streaming. Unscoped
schema/concept embedding helpers also suspend network sends; local model URLs
receive no exception. Concept metadata/storage, route registration and history
remain intact; concept graph functionality was not deleted or replaced.

MCP stdio has no bound principal/destination and refuses all research execution.
Its direct class methods and protocol dispatch use the same registry boundary;
it no longer connects to Neo4j at startup just to refuse queries. Discovery
contains no proposal, review, acceptance or materialization tool.

## Current accepted facts and citations

`FactDisclosure.read_fact` is an internal bounded fixed-query reader, not a newly
registered tool or route. It reads the separate ledger in read-only transactions,
never trusts arbitrary Neo4j payloads, and requires a pinned graph binding and
matching acceptance receipts. Its SQL predicates select one requested fact and
the latest decision for each supporting assertion, capped at 50 supports.

| Stored state | Agent disclosure |
| --- | --- |
| Current accepted support + applied receipt + complete authorization | Minimal fact projection, preserving epistemic status |
| Accepted but pending/unreceipted | Withheld |
| Proposed, rejected or superseded with no other current support | Withheld even if the old graph value remains |
| Conflicting currently accepted property values | Withheld |
| Legacy graph fact without ledger support/provenance | Withheld |

Existence releases label/reference only, never candidate names, emails or other
unaccepted properties. An individual property requires its own accepted/applied
support and a visible target. Relationships recursively authorize both endpoints;
relationship properties authorize the relationship and its endpoints. Source
and property-policy checks precede serialization. Sanitization-dependent values
remain blocked rather than passed through on sanitizer failure.

Citation output is opt-in and limited to citation/version. Resource access is
checked for every supporting evidence source. Restricted evidence metadata additionally
requires an evidence grant; public metadata still requires source/destination and
property permission. Evidence IDs, URI, locator, excerpt, content hash, run refs,
source IDs and internal graph IDs are not exported by this reader. Fact reads
without citations do not release citation metadata or supporting assertion IDs.
Authorized humans can still inspect historical claims using the Stage 1/2
internal/review interfaces; their permissions are not agent acceptance capabilities.

`provider_settings.disclosed_fact_turn` is a matching internal fixed-content send
helper. It uses the existing provider settings and OpenAI-compatible transport,
rechecks the fact/policy, requires the same settings authority, and compares the
actual configured endpoint/model with approval. It accepts no arbitrary prompt,
schema/history or caller-built data envelope. Redirects are disabled in the
OpenAI-compatible client to prevent replaying content to an unapproved location.
No provider payloads or raw responses/errors are exported as authorized facts.
Settings read locks end before network I/O so a slow model cannot block revocation.

These helpers are tested infrastructure for future scoped integrations. No new
agent-facing curation capability is enabled in Stage 3.

## Assurance limits

This is an agent disclosure boundary, not process-wide data-loss prevention.
Human UI/API permissions, bootstrap security, anonymous/no-auth human interfaces,
server logs and privileged local Python/SQL execution require separate operational
controls. In particular, do not expose a no-auth human interface to external AI
clients or give agents human sessions, passwords, filesystem access or raw database
credentials. The existing public legacy auth-configuration route remains outside
this stage's human-interface audit; API-token requests are blocked from it.

Approvals trust an institution's administrator and the approved provider's
endpoint/model routing, retention and transport practices. The application does
not prove the underlying remote model's identity or certify de-identification.
Policy is checked per operation; revocation cannot unsend a request already in
flight. Timing side channels and adversarial provider behavior are not certified.
No live institutional provider/Neo4j deployment was tested. Legacy graph adoption,
provenance backfill, safe file-index templates, general query scoping and a safe
chat replacement remain future work; their current behavior is refusal.
