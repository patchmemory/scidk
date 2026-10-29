# Shared knowledge tools and GUI-facing contracts

Stage 5 backend contract, `knowledge-tools/1`. These are scoped interfaces over
existing curation services, not a second GUI business layer or chat engine.
All new capabilities are disabled until explicitly configured by a trusted host.

## Discovery, identity and assistant context

| Consumer | Discovery | Execution |
| --- | --- | --- |
| External HTTP agent | GET `/api/agent/tools`, `/api/agent/functions.json`, `/api/agent/openapi.json` | POST `/api/agent/tools/{name}` |
| Existing per-user chat / future GUI panels | GET `/api/chat/functions.json` | POST `/api/chat/tools/{name}` |
| MCP | `list_tools` via `ScidkMcpServer.tool_definitions()` | `call_tool` via `dispatch()` |
| Trusted provider adapter | `openai_functions(ctx=...)` | `provider_settings.disclosed_tool_turn(ctx,name,args)` |

All adapters use `registry.run_tool`; discovery uses
`registry.available_tool_definitions`. `TOOL_DEFINITIONS` and
`get_tool_definitions()` remain static catalogs for trusted internal consumers,
including existing platform inventory/concept-graph seeding. Static membership
is never runtime authorization. No arguments accept user, endpoint, model,
settings path, file path, profile permissions or graph query text as authority.

HTTP agent calls require a real API token bound to an approved destination.
Chat supports that token or a named, unlocked existing user session whose stored
provider endpoint/model is approved. GUI panels can use the chat adapter with
their existing session; it performs no LLM call or session-history read. A cookie
on the external HTTP adapter cannot substitute for a token/destination binding.
The optional `?profile=overview|review` selector is validated through stored
per-user/profile/tool grants. It selects an already granted context and cannot
grant permissions. The server default is `SCIDK_ASSISTANT_PROFILE='overview'`.
A profile in the JSON tool arguments is rejected. MCP uses its host-bound profile.

The immutable profile definitions live in `agent_tools/profiles.py`:

| Profile | Allowed ceiling |
| --- | --- |
| overview | get_system_context, get_ontology_context, explain_fact |
| review | Overview capabilities plus get_assertion, submit_assertion |

Neither profile contains legacy queries, human review or materialization tools.
There are no dataset discovery/aggregate templates yet; their inclusion in a
future Overview experience is not permission to use suspended SQL/Cypher tools.

Stdio MCP remains unbound and advertises **zero tools**. Environment variables,
tool arguments and claimed identities cannot bind it. Only a trusted hosting
adapter may construct an authenticated `ToolContext` and pass it to
`ScidkMcpServer(tool_context=...)`. Policy is still freshly checked on discovery
and calls. There is no stdio credential or network authentication scheme added.

## Tool contracts

All arguments are JSON objects with no unexpected keys. Shared validation rejects
wrong types (including booleans used as integers), bounds, oversized requests
(64 KiB of canonical JSON) and missing required fields. Traversals accept depth
0–6 and result limit 1–128; defaults are 3 and 128. An excessive result refuses,
never silently truncates structural dependencies.

| Tool | Required arguments | Optional arguments | Successful response |
| --- | --- | --- | --- |
| get_system_context | entry_id | depth, limit | status, context: version, nodes, typed edges, metadata, scoped freshness warnings |
| get_ontology_context | entry_id | catalog (default canonical), depth, limit | status, context: version, nodes, typed edges, ontology_version and blockers |
| explain_fact | fact_id | include_evidence (default true) | status, fact: current applied support or authorized unsupported assertion statuses |
| get_assertion | assertion_id | include_history (default false) | status, assertion: assertion_id, fact_id, bounded claim, curation_status, revision, rationale, evidence, optional decision_history |
| submit_assertion | assertion, caller_key | none | status, assertion_id, submission_status=recorded, validation=valid, ontology_version |

`catalog` is an explicit configured selector, such as `canonical` or `MONDO`;
it is not a URL or catalog path. No source is fetched on demand.

Example permitted System query:

```json
{"entry_id":"workflow:csv-import","depth":3,"limit":128}
```

Nodes contain Stage 4 authoritative references, hashes, revision, applicability,
visibility and source scopes only after every referenced source and metadata grant
has passed. Warnings identify only entries in the authorized result, including
changed/missing files, symbols/headings and version drift. Regenerating a context
with changed content requires new restricted metadata grants.

Ontology contexts expose canonical definitions and endpoints or explicit blockers.
They never modify the ontology. An unresolved catalog has no authoritative label
nodes. Selecting external concepts requires an explicitly configured Stage 4
registry projection with its own Resource provenance and visibility policy.

Accepted `explain_fact` results are the Stage 3 current-support serializer, including
applied receipt verification, matching graph binding, current ontology revision,
endpoint access, nonconflicting property values and optional permitted citations.
A graph object's existence does not prove acceptance. Proposed, superseded,
rejected, conflicting or unapplied support is never described as a currently
accepted fact. If all relevant assertion records are separately authorized,
an unsupported result uses `curation_status=not_currently_supported` and
`assertion_statuses`; it does not return raw candidate values. Unknown, inaccessible
and legacy/unclassified facts are indistinguishable refusals. A retained old
Neo4j value never overrides ledger decisions.

The assertion inspector returns the claim domain/type/version/epistemic status
and a bounded projection of its target. Node identity claims, raw upstream record
identifiers, actor/reviewer IDs, locators, URIs and evidence excerpts are omitted.
A property value requires a declared type, raw property sharing and
`sanitize=none`. Both relationship endpoints and their evidence are checked
independently, including for unaccepted proposals. `accepted` on an assertion
means a review decision; use `explain_fact` to establish currently applied fact
support. Proposed assertions have null rationale. A permitted reviewed assertion
contains the current decision's rationale. History requires an additional
content/revision-bound grant, not just permission to read the current record.

Evidence items contain only `evidence_id`, `citation` and `version`, with exact
source and evidence metadata grants plus `EvidenceSource` field policies. The
stable evidence ID is supplied only to explicitly permitted inspectors so it can
be reused in a typed proposal; it is not an unrestricted evidence-fetch capability.
A hidden evidence field refuses the whole record. The shared evidence inspector
uses `get_assertion`, without adding an excerpt/raw-payload endpoint.

Submission accepts the unchanged `curation/0.1.0` assertion body and existing
permitted evidence IDs. It requires Review-profile tool permission, both feature
flags and a separate proposal grant for the exact Resource. It validates the
current ontology, evidence authorization, target fields and independent endpoint
access before writing via `Ledger.submit`. It does not create evidence, definitions,
review decisions, receipts or graph operations. Actor identity is derived as
`agent-user:{authenticated_user_id}`; client-supplied authors are not authority.
Idempotency keys are user-scoped across transports. Replays return the same
reference; different bodies with the same key refuse. `submission_status=recorded`
describes the submission receipt, not the assertion's possibly later review state.
An optional Stage 1 `supersedes` lineage link requires access to the prior assertion
and never performs the human supersede decision.

## Minimal GUI consumption

| Future GUI surface | Existing shared backend |
| --- | --- |
| Overview central chat | Overview profile discovery, explain_fact, permitted system/ontology context; existing user provider configuration |
| Review contextual assistant | Review profile, selected assertion via get_assertion, explicit proposal capability if granted |
| Knowledge System | get_system_context with workflow root and bounded traversal |
| Knowledge Ontology | get_ontology_context with canonical or configured external selector; render blockers explicitly |
| Knowledge Research | explain_fact with selected stable fact_id; no unrestricted dataset listing/counts |
| Shared evidence inspector | permitted get_assertion.evidence and current rationale; explicit history request/grant when needed |

Panels should render epistemic status, curation status and current applied support
separately. A refusal must not be rendered as evidence that an ID exists or as a
zero count. Do not synthesize a second review workflow in the assistant. Existing
Stage 2 human review endpoints retain their named-human/session-only controls.

The chat tool adapter executes structured requests only. Existing per-user chat
session/provider storage is unchanged. No free-form chat loop, unscoped history,
new UI, autonomous provider tool-call execution or GraphRAG re-enablement is added.
The internal provider helper sends only a freshly authorized fixed tool result
and permitted definitions through the existing OpenAI-compatible client, binds the
actual stored endpoint/model twice, and refuses redirects using that client.
It returns only a send receipt, not provider text as trusted knowledge. Free-form
conversational integration still requires safe prompt/history provenance.

## Error handling

Successful tool results use `status=success`. Authorized malformed outer arguments
return `status=error` with `Invalid tool arguments.`. Missing records, inaccessible
content, invalid proposal contracts, conflicts, missing configuration/policy and
backend failures use the Stage 3 generic `status=refused` envelope. This intentionally
avoids distinguishing undeclared IDs from withheld ones. HTTP tool execution uses
200 for structured success/refusal/error, 400 for malformed JSON and 404 for
unknown HTTP tool names. Existing authentication/role middleware can return
401/403/423 before execution. The stricter proposal contract failure envelopes
avoid disclosing source/ontology existence through fine-grained validation errors.
