# Stage 5: secure shared agent integration

Implemented in the existing isolated `design/knowledge-curation-20261029`
worktree, based on Stage 4 commit `fa9e142`, after `codex_prompt_07.txt` authorized
this stage. The primary checkout's untracked vision and NCI demonstration plan
were read as authoritative inputs and preserved. No Stage 6 or GUI work began.

## Result

Five tools now contribute definitions and handlers to the canonical shared
registry: get_system_context, get_ontology_context, explain_fact, get_assertion
and submit_assertion. There is no parallel registry, auth system, model provider,
planner or graph database. HTTP, the new structured chat tool adapter and MCP
all dispatch through `registry.run_tool`. Runtime discovery is filtered through
the same configured capabilities; static inventory is not a permission grant.
The [backend contract](knowledge-curation-agent-api.md) documents all arguments,
responses, profiles, evidence/history semantics and future GUI consumers.

Overview and Review are declarative tool ceilings. A profile selector only narrows
explicit per-user/profile/tool grants; Overview cannot inspect assertions or
submit proposals, and no profile can review or materialize. Read tools require
an explicit `SCIDK_KNOWLEDGE_CONTEXT_ENABLED=True` Flask configuration value and
configured services. Submission additionally requires
`SCIDK_CURATION_ENABLED=True`. Direct trusted contexts use the corresponding
`knowledge_enabled` and `proposal_enabled` booleans, both default false.

Typed context handlers reuse Stage 4 traversal and authorization, with relevant
System freshness warnings filtered to the authorized traversal. Canonical and
explicitly configured external projections share the ontology handler. Operational
catalog reconciliation and restricted metadata grants remain required. Context
builders, snapshots and the static catalog remain trusted-local APIs, not safe
agent readers. No arbitrary source path, URL or query can be supplied to a tool.

Fact explanations reuse Stage 3 applied/current support checks. A bounded
assertion inspector additionally explains explicitly permitted unsupported ledger
states without presenting them as accepted facts. Legacy/unclassified and unknown
facts remain generic refusals. Inspection returns a safe claim projection, current
rationale, and permitted citation metadata; raw candidate identities, upstream
identifiers, excerpts and reviewer identities are withheld. Relationship endpoints
are checked independently. Non-raw properties and canonical sanitization cannot
be bypassed through inspection or proposal submission. Inspecting current assertion
metadata requires an explicit grant keyed by assertion ID; decision history needs
an additional immutable grant keyed by `AssertionAccess.history_grant_id`.

Proposal submission constructs a request-local Ledger evidence callback bound to
the authenticated user and current policy, retaining Stage 1 validation and actor-
scoped idempotency. Existing shared ledger callbacks are never mutated. Source,
evidence, property and referenced endpoint authorization is checked before the
write, including the prior assertion when a proposed supersedes lineage is used.
Proposals return a reference and validation receipt; no code path calls review,
accept, reject, supersede decision or materialization services. Existing Stage 2
human-only endpoints and outbox machinery are unchanged.

The provider adapter reuses `provider_settings.credentials`, per-user encryption,
`PolicyStore` and the existing OpenAI-compatible client. It sends only fixed,
freshly authorized tool results and permitted definitions, verifies the actual
configured endpoint/model before tool execution and again before transport,
and returns a generic receipt. It never trusts provider-generated text as a fact
or automatically executes provider tool calls. User prompts, conversation history
and unscoped graph/schema context are not accepted by this helper. Stdio MCP
advertises no tools and refuses calls; trusted hosting adapters can inject a
server-authenticated context, whose live policy is rechecked on every operation.

## Explicit optional setup and persistence

No deployment initialization, production write or bulk migration was performed.
The existing settings database optionally gains three tables only when a trusted
local administrator calls `CapabilityStore(settings_db).initialize(admin_id=...)`:
`agent_tool_schema` (extension version 1), `agent_tool_capability` (user/profile/tool)
and `agent_proposal_grant` (user/exact Resource). Stage 3 policy must already exist.
There is no initialization on read, no new credentials, and no capability-setting
agent or HTTP endpoint. Administration reuses enabled-admin checks, foreign keys
and existing auth audit logging. Missing extension tables deny tools.

A trusted application host must:

1. Initialize the optional capability extension explicitly in the intended
   nonproduction/deployment setup, using an existing administrator.
2. Reuse existing Source classifications, user Resource/evidence grants and exact
   destination approvals. Grant tools with `grant_tool(user_id, profile, tool,
   admin_id=...)`; separately grant proposal scopes with `grant_proposal(...)`.
3. Build Stage 4 projections from reconciled snapshots and trusted source bindings;
   add content-bound restricted context grants, assertion metadata grants and
   optional history grants as appropriate. Public metadata still needs Resource
   authorization. A proposal reference alone does not grant record inspection.
4. Construct `KnowledgeServices(system=context_service, ontologies={...},
   assertions=AssertionAccess(ledger, fact_disclosure), system_root=repository_root)`
   and place it in `app.extensions['knowledge_services']`. No production DB is
   inferred, opened or reconciled by this wiring. Configure the two feature flags
   explicitly only after synthetic validation. HTTP token and chat-session
   authentication continue to use the existing SciDK adapters.

Generated projections and profiles remain in memory/code. Only optional capability
administration writes settings policy, and only explicitly authorized proposals
append ledger assertions/submission receipts. Evidence creation is still trusted
internal functionality. Disabling flags removes new runtime discovery/execution;
existing historical ledger proposals are preserved. No scanner, import, profile
pipeline, catalog, graph or concept-graph data is rewritten.

## Security assessment and limits

Effective permission is the intersection of enabled existing user/role, profile
ceiling, explicit tool capability, exact source access/classification, raw property
mode, evidence/record metadata grants and approved bound destination. Proposal
scope permission and the second feature flag are additional requirements. Discovery
of submit_assertion also requires at least one usable proposal Resource grant.
For other tools, discovery advertises generic capability metadata only; concrete
source/property authorization is evaluated against each call's selected records.

Missing identity/provenance/policy/grants, disabled users, unknown profiles,
unbound tokens, unavailable services, mismatched settings instances and malformed
or inaccessible IDs fail closed. High-risk Resources always deny. API tokens can
reach only the existing agent adapters and the two new scoped chat adapter routes;
existing human API/export/settings protections remain. Anonymous/no-auth mode
never grants knowledge tools. Public repository content is not implicitly public.

No unscoped Cypher/SQL, aggregates, GraphRAG replies, embedding sends or legacy
schema tools were re-enabled. New handlers never trust Neo4j payloads and perform
no graph reads. Read-only results are bounded; strict shared JSON schemas reject
unexpected authority fields, wrong types and excessive arguments. Generic refusals
avoid source existence or backend error disclosure. An accepted assertion is not
advertised as an applied fact when current receipts/support fail verification.

Explicit grants authorize citation/rationale fields within their declared source
scope; they are not automatic semantic redaction of arbitrary text. Raw evidence
excerpts and candidate identity payloads are therefore excluded. Administrators
must keep evidence/decision provenance accurate. Policy is evaluated in fresh read
transactions; as in Stage 3, instantaneous revocation after the final check cannot
unsend already authorized network bytes. Provider I/O occurs after closing settings
transactions and does not follow redirects. No provider response is released by
the new fixed-result send helper.

Remaining blockers: operational catalog conflicts, absent legacy provenance and
missing configured Resource/context grants still prevent release. There is no
production bootstrap or stdio identity handshake, general discovery/listing/count
template, new evidence ingestion endpoint, raw evidence inspector or unrestricted
chat-history transport. The NCI demonstration needs a deliberately authorized,
curated dataset and account; UI readiness is not claimed. Existing concept-graph data and behavior are untouched. The shared static
catalog now includes the new definitions; internal inventory/seeding does not
bypass runtime discovery filtering.

## Validation

Final relevant regression: **504 passed, 1 skipped, 0 deselected**, with 8
existing schema-intelligence deprecation warnings, in 129.23 seconds. This includes
**52 new Stage 5 tests**. The initial focused suite passed 47 tests; subsequent
targeted checks verified independent flags, provider revocation, hidden proposal
references and current rationale visibility before the final broader run.
An initial regression exposed the obsolete Stage 3 invariant prohibiting all
assertion tool names; it was updated to preserve default-off refusal and the
human-decision prohibition, then the relevant suite was rerun successfully.
The skipped test is the explicit-disposable-Neo4j integration test, whose safety
configuration was not supplied. No tests were deselected.

```sh
python -m pytest tests/agent_integration tests/knowledge tests/security tests/curation \
  tests/pipeline/test_mapping_engine.py tests/pipeline/test_mapping_schema.py \
  tests/pipeline/test_runner.py tests/test_agent_tools.py tests/test_api_tokens.py \
  tests/test_chat_api.py tests/test_chat_fixes.py tests/test_chat_intent_routing.py \
  tests/test_llm_provider_settings.py tests/test_schema_intelligence.py \
  tests/test_concept_graph_mcp_seeding.py tests/test_mcp_tools_offline.py \
  -q -o addopts=''
```

Commands used the existing primary-checkout `.venv/bin/python` from the isolated
worktree. The broader run required approval for its temporary loopback HTTP
provider fixture. Git whitespace checks passed.
Tests use synthetic catalogs, temporary settings/ledger databases and fake graph
and provider adapters. No real provider or production graph is needed. The
superseded/conflicting support test injects a malformed historical decision in an
isolated fixture because normal Stage 2 review correctly prevents conflicting
acceptance; it verifies the independent disclosure boundary still refuses that
state. Tests also cover HTTP/chat/trusted-host MCP parity, unbound MCP discovery,
strict arguments, unauthorized discovery, independent endpoints, idempotency,
profile/flag restrictions, source/evidence/property denials, catalog blockers and
actual provider destination/revocation checks.

## Stage 6 recommendation

Review these interfaces first. Stage 6 should assemble the approved synthetic
vertical slice with reconciled catalog, bounded visible discovery and evidence
contracts, human review, and receipt-backed explanation. Add a production bootstrap
and any additional GUI-consumed read templates only with explicit provenance and
authorization tests. Keep stdio submission unavailable until a real authenticated
binding is designed. Preserve the tested NCI fallback and keep GUI, harvesting,
concept-graph changes and autonomous graph writes outside this stage.

## Changed files

- `scidk/agent_tools/assertions.py`
- `scidk/agent_tools/capabilities.py`
- `scidk/agent_tools/context.py`
- `scidk/agent_tools/facts.py` (documentation only)
- `scidk/agent_tools/knowledge.py`
- `scidk/agent_tools/profiles.py`
- `scidk/agent_tools/registry.py`
- `scidk/ai/provider_settings.py`
- `scidk/mcp_server.py`
- `scidk/web/auth_middleware.py`
- `scidk/web/routes/api_agent.py`
- `scidk/web/routes/api_chat.py`
- `tests/agent_integration/__init__.py`
- `tests/agent_integration/test_tools.py`
- `tests/security/test_disclosure.py`
- `tests/test_agent_tools.py`
- `docs/architecture/knowledge-curation-agent-api.md`
- `docs/architecture/knowledge-curation-implementation-plan.md`
- `docs/architecture/knowledge-curation-stage-5.md`
