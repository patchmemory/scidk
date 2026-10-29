# Stage 3 preflight: policy decisions requiring approval

Date: 2026-10-29. Base commit: `704ff43`, isolated branch
`design/knowledge-curation-20261029`. **Historical preflight, before implementation.**

The decisions below were approved in `codex_prompt_05.txt`. See
[the Stage 3 implementation report](knowledge-curation-stage-3.md) for the
implemented controls, validation, suspended paths and remaining limitations.
The remainder records the original preflight; its incomplete-status statements
refer to that earlier checkpoint.
The primary checkout's `codex_prompt_04.txt` authorizes Stage 3 but explicitly says
to stop rather than invent a new security policy when an architectural conflict
requires approval. No runtime code or policy records were changed in this preflight.

## Observed implementation

- `scidk/pipeline/store.py`: Resource records are `pipeline_source` rows in the
  existing settings database. They have neither a classification column nor
  per-principal access grants. Source paths, mappings and FAIR status are not
  classification approvals.
- `scidk/agent_tools/disclosure.py`: `load_policy(None)` returns an empty policy;
  the filter returns unmodified data for an empty policy. The stored policy only
  covers per-property modes. Unknown provenance is not withheld. The high-risk
  hook only checks `source_id` against an explicitly supplied withheld set.
  Filter metadata exposes counts/labels, which can themselves reveal information.
- `scidk/agent_tools/registry.py`: the context has a username but no authenticated
  principal proof, destination binding or current-support resolver. Dispatch
  reloads only sharing modes, executes handlers before filtering, and returns
  raw exception strings on handler errors. Graph/schema/count and SQL file-index
  tools do not enforce Resource authorization before execution.
- `scidk/agent_tools/context.py` and `scidk/web/routes/api_agent.py`: the HTTP
  adapter forwards the authenticated username when available, but no destination
  endpoint/model identity. Per-user tokens identify a user, not the external AI
  client or destination. Request-supplied endpoint names would not prove identity.
- `scidk/ai/provider_settings.py`: per-user endpoint/model/key configuration and
  Parley presets exist. Configuration is not an institutional disclosure approval.
  There is no approved destination registry or permitted-risk policy. Presets,
  localhost URLs and environment credentials must not imply approval.
- `scidk/mcp_server.py`: stdio dispatch creates an unbound ToolContext; it has no
  authenticated user or model destination. New proposal/privileged tools remain
  absent. Existing research read tools still need a refusal boundary.
- `scidk/web/routes/api_chat.py`: existing chat routes obtain graph/schema
  context directly, outside shared `run_tool`. `OpenAICompatibleProvider` can
  incorporate that schema into an outbound prompt. Hardening only the registry
  would not establish HTTP/chat/MCP parity or stop this outbound bypass.
- Stage 2 intentionally leaves superseded values physically present. Disclosure
  must resolve current accepted assertion support from the ledger and require
  applied acceptance receipts; graph presence or `curation_status` is insufficient.
  Legacy/unclassified facts must not acquire accepted/public status by inference.

Inspection was confined to source files. No research database, model endpoint or
production service was accessed. The primary checkout's existing uncommitted
work remains untouched. The planning source below was read from that checkout
because the isolated worktree does not initialize the `dev` submodule.

## Conflict: global prohibition versus endpoint-specific ceilings

`dev/plans/parley_and_resources.md`, “Data policy (MIT)” (around lines 231–234),
says the agent layer may carry **medium-risk or lower** data and **high-risk data
must never reach it**, including human-subjects data until effectively cleaned.
It also specifies a medium default on Resource creation.

The newly supplied Stage 3 prompt requires destination-specific permitted risk
levels and explicitly forbids sending high-risk data to low/medium-approved
endpoints, without resolving whether high-approved destinations may ever receive
high-risk data. It also requires unknown classification to deny, which prevents
using that earlier medium default as a disclosure approval for existing records.

**Recommended decision:** retain the global high-risk AI prohibition. Destination
approval can narrow permission to low or medium; it cannot relax that prohibition.
New or legacy Resources remain disclosure-unclassified until an authorized human
explicitly classifies them. A UI creation default of medium, if retained elsewhere,
is not sufficient evidence of completed classification. Do not implement or claim
an automatic human-subjects cleaning/compliance certification mechanism.

Approval should explicitly confirm this rule or replace it with the institution's
intended policy. No high-risk exception will be inferred from provider selection.

## Missing policy authority and proposed storage contract

The architecture approves fail-closed behavior but the existing code does not
supply the authoritative grants/classifications needed to compute an allowance.
Choosing those grants is a policy decision, not a property-filter implementation.

**Recommended decision:** use explicit, versioned administrative records in the
existing settings database, alongside current users/Resources/provider settings:

1. Resource classification: exact source namespace/Resource ID; `low`, `medium`
   or `high`; named existing admin who classified it; revision/time. No fallback
   from a source name, FAIR score, storage location or missing row.
2. Resource read/disclosure grant: existing user ID + exact Resource identity +
   explicit permission. No implicit blanket Resource access for ordinary users;
   no automatic AI disclosure permission for admins. Administrative review remains
   a separate capability. A missing/disabled user or absent grant denies.
3. Destination approval: exact normalized endpoint URL + exact model identifier;
   allowed risk ceiling of low or medium under the recommended global rule;
   explicit approval revision and named admin. No wildcard hosts, automatic
   localhost/Parley exemptions or provider-name-only approvals.
4. External-client binding: bind an existing per-user API-token ID to an approved
   destination/model identity server-side. A caller cannot raise its ceiling by
   supplying a URL/header. Unbound tokens may still authenticate for existing
   unrelated functions, but agent data tools refuse disclosure.

Only an explicitly configured named admin would manage these records through
local administrative configuration initially; no new credential system or policy
editing agent tool. Creation/migration is explicit and does not alter the canonical
scanner/import/profile pipeline. No policy schema or grants have been created.

This contract requires approval of the authority, default grant semantics and
client binding, not a request to approve individual test fixtures. If another
institutional policy registry should own these records, identify it instead.

## Implementation after these decisions

These technical controls follow the approved fail-closed objective and do not
require making legacy queries less secure for compatibility:

- Resolve a fresh immutable policy snapshot before execution, using the existing
  authenticated principal and server-verified destination binding. Missing,
  unreadable, stale or malformed policy refuses with one generic response.
- Disable arbitrary agent Cypher and any arbitrary SQL interface. Refuse existing
  global schema/count/file-summary tools until Resource-scoped templates can
  authorize every source before executing predicates/aggregates. Return no hidden
  IDs, labels, counts, result-shape differences or backend exception strings.
- Fixed templates must start from authorized Resource IDs and currently supported,
  applied ledger fact IDs. A property fact needs its own accepted support; accepting
  existence does not release all properties on a node. Different currently
  accepted property values or missing provenance withhold that fact.
- Authorize relationships and both endpoints, as well as every supporting evidence
  source. Keep epistemic status distinct from curation status. Historical/proposed/
  rejected/superseded assertions remain inspectable only through separately
  authorized human interfaces; no new agent-facing curation tools in this stage.
- Recheck citation IDs, locators, excerpts and metadata independently. A public
  fact cannot release restricted evidence. Property hiding must cover structured
  values and citations without leaking withholding counts.
- Apply the same gate to HTTP and chat tool dispatch. Gate direct legacy chat
  context construction before provider calls; refusing unsafe chat flows is
  preferable to silently sending their schema/research context. Do not retire
  concept graph functionality or assume all chat routes use the shared registry.
- MCP stdio, with no principal/destination binding, must refuse research reads
  consistently and must not discover proposal/review/materialization tools.
- Check actual configured provider endpoint/model on outbound calls; configuration
  changes invalidate approval matches. Preserve the existing provider engine.

Tests will use synthetic policy fixtures and temporary databases, exercise
HTTP/chat/MCP parity and denied execution (including no query/provider calls),
current accepted versus historical facts, endpoints/evidence/citations, scalar and
aggregate attempts, cross-user access, destination mismatch and policy failures.
No new projections, external ontology ingestion, autonomous graph commits or
Stage 4 work is authorized by this preflight.

## Current exposure assessment and completion status

**No Stage 3 security gate has passed.** Existing exposure risks above remain;
Stage 1/2 defaults and absence of new agent-facing curation tools are unchanged.
Do not treat this document as remediation or as authorization to disclose records.
No tests were run because no runtime implementation was changed; the Stage 2
report's 203 passed / 4 skipped / 2 deselected remains historical validation only.

Next action: review the recommended global risk rule and the proposed authoritative
classification/grant/destination/client-binding contract. Then implement Stage 3,
run the required adversarial/parity tests and produce its implementation commit.
Stage 4 must remain pending until the completed Stage 3 results are reviewed.
