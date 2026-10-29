# Stage 3: disclosure enforcement and agent security boundaries

Implemented after `codex_prompt_05.txt` approved the decisions in the
[policy review](knowledge-curation-stage-3-policy-review.md). Based on Stage 2
commit `704ff43`, in the same isolated development branch. Stage 4 was not begun.

## Result and changes

The [disclosure policy](agent-disclosure-policy.md) documents the authoritative
schema, administration, denial rules, supported fact reader, provider binding,
intentional suspensions and assurance limits.

- Added `scidk/agent_tools/security.py`: explicit policy setup/management using
  existing settings/auth/Resource records; exact classifications and per-user
  grants; approved endpoint/model ceilings; server-side API-token binding;
  separate restricted evidence-metadata grants; existing audit integration.
- Added `scidk/agent_tools/facts.py`: internal, bounded, read-only current-support
  resolver. It requires applied receipts, source permission, visible properties,
  visible relationship endpoints and permitted evidence/citation metadata. It
  rejects conflicting support and stored historical/legacy facts.
- Changed `agent_tools/disclosure.py`, `registry.py` and `context.py`: unproven
  arbitrary output/queries and all legacy unscoped handlers refuse before execution.
  Context construction no longer opens a graph driver or file index for refused
  calls. Discovery descriptions explicitly announce suspension.
- Changed `core/auth.py`, `web/auth_middleware.py` and `web/decorators.py`: carry
  the verified token ID and prevent API-token bypass through human-facing APIs.
  An admin role alone does not bypass the agent boundary. Named human session
  behavior and Stage 1/2 curation review remain separate.
- Changed `web/routes/api_chat.py`: refuse unscoped GraphRAG reply/context-to-model
  paths before queries, model calls or SSE responses. Changed
  `services/schema_intelligence.py` and `services/concept_graph_service.py` to
  suspend unscoped embedding sends without deleting concept metadata/routes.
- Changed `mcp_server.py`: both protocol and direct methods use the shared
  refusal boundary, with no unbound startup Neo4j connection.
- Changed `ai/provider_settings.py` and `ai/openai_compatible.py`: internal
  fixed-fact send helper, actual endpoint/model matching and refusal of redirects.
  The existing provider engine, settings and encrypted credentials are reused.
- Added `tests/security/test_disclosure.py`, `test_adapters.py` and package marker.
  Updated `tests/test_agent_tools.py`, `test_api_tokens.py` and `test_chat_api.py`
  to assert the new refusal contracts. Internal SQL helper coverage is retained
  separately from external agent execution. The former optional tests asserting
  unrestricted demo-graph agent output were replaced by offline forbidden-execution
  checks, rather than reported as passing old behavior.
- Included the historical policy-review document, this report, the policy guide
  and an updated implementation-plan checkpoint.

No production policy/schema/data writes, bulk migration, canonical pipeline edits,
new identity system, autonomous graph commits, ontology projections/imports,
concept graph retirement or new agent-facing curation tools were introduced.
Curation and knowledge-context flags remain default-off. Existing primary-worktree
changes and prompt files were not modified.

## Security behavior and accepted versus historical knowledge

The high-risk prohibition is unconditional. Missing policy/provenance/classification,
unknown/disabled principal, unbound token/MCP, absent source grant, unapproved
endpoint/model and unreadable/malformed policy all deny. Property masking cannot
make scalar projections, aggregates, predicates or raw errors safe after execution;
therefore arbitrary queries and current global summaries are unavailable.

The internal fact reader resolves latest append-only decisions and requires an
applied acceptance receipt for the same graph target and decision. It does not
use a graph node's presence or graph `curation_status` as acceptance evidence.
Superseded/rejected/proposed/pending or conflicting facts return the same generic
refusal as an unknown identifier. Another still-accepted supporting assertion can
continue to support the fact; epistemic status never changes because of acceptance.
Node existence does not release property/identity previews. Every relationship
endpoint and evidence source must pass disclosure, and restricted citations have
an additional grant. Output excludes withholding counts, source/evidence IDs,
locators, excerpts and internal graph identifiers.

HTTP tools, chat reply paths and MCP share the same refusal response without
backend execution. An API token cannot obtain a different result by calling a
human graph/export/settings endpoint or mixing a token with a cookie. A caller
cannot authorize a destination using model/endpoint headers. MCP has no identity
binding and receives no proposal or privileged capabilities.

Destination approval is evaluated against actual stored provider endpoint/model
configuration. Low-approved destinations cannot receive medium data; no destination
can receive high-risk Resource content. Changing user configuration, revoking
approval or deleting a token invalidates later disclosure. The fixed-content send
helper rechecks content and authority before sending through the existing client;
HTTP redirects do not forward that payload. Generic low-level provider libraries
remain trusted internal transport primitives, not self-authorizing data APIs.

## Validation

Final relevant suite, from the isolated worktree:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest \
  tests/security tests/curation \
  tests/pipeline/test_mapping_engine.py tests/pipeline/test_mapping_schema.py \
  tests/pipeline/test_runner.py tests/test_agent_tools.py tests/test_api_tokens.py \
  tests/test_chat_api.py tests/test_chat_fixes.py tests/test_chat_intent_routing.py \
  tests/test_llm_provider_settings.py tests/test_schema_intelligence.py \
  tests/test_concept_graph_mcp_seeding.py tests/test_mcp_tools_offline.py \
  -q -o addopts=''
```

**406 passed, 1 skipped, 0 deselected**, with 8 pre-existing schema-intelligence
datetime/SQLite deprecation warnings (62.09 seconds). The skip is the Stage 2
explicit-disposable-Neo4j integration test; no disposable graph was configured.
`git diff --check` is clean. No production/live graph result is inferred from the
optional test skip.

Fixtures use temporary settings/curation/file-index databases, synthetic sources,
fake graph adapters, network-call spies and the existing loopback fake Parley
server. The sandbox denied the loopback listener initially; the provider suite
was then rerun with execution approval. No real provider or research service was
contacted. Initial fixture import and old permissive-test expectation errors were
corrected before the final run. No passing claim is based on those failed runs.

Tests cover missing/legacy provenance, unknown/malformed policy, classifications
and ceilings, cross-user access, admin non-bypass, token/source/destination
revocation, hidden properties/identifiers, endpoint source permissions, current
versus historical/conflicting/unreceipted claims, restricted evidence/citations,
scalar/aggregate/SQL attempts, forbidden handler/query/provider calls, HTTP/chat/MCP
parity, direct MCP methods, embedding refusal, destination spoofing/config drift,
redirects, cross-settings-store confusion and policy availability during slow sends.
Stage 1/2 tests remain in the final suite without curation code changes.

## Remaining exposure risks and deliberate limits

1. Existing generic agent tools, file summaries, GraphRAG replies and unscoped
   embeddings are suspended, including in the demo. This is intentional, visible
   security behavior; safe replacements are not silently approximated. Internal
   fixed-fact helpers are not registered as a new agent capability.
2. Named human sessions and existing human APIs remain privileged. No-auth human
   interfaces and the legacy public auth-configuration/bootstrap route were not
   comprehensively hardened by this stage. Do not expose them to AI clients;
   authenticated deployment/network restrictions remain necessary. API tokens are
   specifically denied access outside the agent catalog/execution boundary.
3. Trusted local Python/SQL, raw database credentials and low-level provider
   transports can bypass application APIs. Do not give these to external agents.
   This implementation does not provide process-wide DLP or protect against a
   malicious server administrator or stolen human credentials.
4. Administrative source classification and provider approval must be correct;
   no automatic de-identification, compliance certification, model attestation or
   provider-retention guarantee is claimed. An approval may explicitly use HTTP;
   administrators remain responsible for approved transport/provider practices.
5. Policy reads use fresh transaction snapshots. Revocation affects subsequent
   operations, not content already sent. No settings lock spans provider network
   I/O. Constant-time response guarantees and timing-side-channel elimination are
   not claimed.
6. Policy provisioning is local administration only; no grant UI/HTTP endpoint was
   added. Audit records identify operation kind/admin/time, not complete immutable
   before/after policy snapshots. No existing Resources are automatically classified
   or granted. Missing setup keeps disclosure refused.
7. No live provider/disposable Neo4j verification, legacy provenance backfill,
   arbitrary-query scoping, file-index source joins or automatic graph drift
   reconciliation is claimed. Accepted facts are ledger claims with receipts,
   not a promise that unrelated privileged writers never changed graph storage.

## Stage 4 recommendation and rollback

After review, Stage 4 should add deterministic, versioned system/ontology
projections with typed links and source hashes. Give every source explicit
provenance/classification; do not infer that a repository path is public. Keep
projections and any future agent context endpoints default-off until the same
principal/destination/property gates pass. Do not re-enable legacy global queries
as a prerequisite. Registering curation tools belongs to the later controlled
integration stage, not this checkpoint.

Rollback must keep agent execution suspended rather than restoring permissive
post-query filtering. Preserve policy records, classification revisions, existing
audit logs and Stage 1/2 ledger history. Stopping the internal helpers or reverting
an integration must not delete accepted evidence or automatically relax grants.
No deployment changes were made. Stage 4 awaits user review of this report.
