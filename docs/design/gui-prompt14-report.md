# Prompt 14 — Review workspace and contextual assistant

## Implementation status and checkout

Implemented `codex_prompt_14.txt` in
`/home/patch/Projects/scidk-knowledge-curation`, branch
`design/knowledge-curation-20261029`. The requested `codex_prompt14.txt` was
present as `codex_prompt_14.txt`; its handoff copy and follow-up requirements
were read as well.

Verified starting HEAD: `33eef1d8641b97b02e4490e67e13473f8f45d513`.
Implementation commit: `002747e43cb3bd16cb6ac61b619bc4e485dd9c95`. This report is committed separately so it
can record the exact implementation hash without a self-reference.

Existing untracked prompts, design inputs, demo/vision/roadmap documentation,
handoff directory/archive and local runtime files were preserved and excluded
from staging. No production configuration, database, service process, ontology,
legacy route or screenshot baseline was changed. Prompt 15 was not begun.

## Working experience

`/review` uses the existing GUI v3 shell when both strict boolean flags
`SCIDK_GUI_V3_ENABLED=True` and `SCIDK_REVIEW_WORKSPACE_ENABLED=True` are set in
the development Flask app. Both remain off unless explicitly configured; the
Review assistant additionally requires `SCIDK_REVIEW_CHAT_ENABLED=True`.
The original placeholder remains when the Review workspace flag is off.
These are application config booleans, not newly supported environment variables.
No running-server flag was changed by this task.

The queue supports node/property/relationship, domain, status, exact source
Resource ID and stable-context filtering. It inspects candidates through the
Stage 5 `AssertionAccess` contract before filtering or pagination. There are
20 permitted items per page and a 500-candidate/2 MiB discovery ceiling; exceeding
a ceiling refuses the operation. There are no inaccessible counts. Loading,
empty, connection, service, access and stale-decision states are explicit.
Reviewer assignment is explicitly unavailable because the ledger has no
assignment contract. This bounded adapter is not an indexed large-ledger queue.

The selected inspector displays the safe claim, stable assertion/fact IDs,
separate curation and epistemic statuses, ontology version, source Resource,
citations, pinned evidence version and access time, revision and current rationale.
Identity claims, raw source records and locators are not copied into previews.
Decision history is fetched only on request with its existing immutable-history
grant. Conflict IDs are returned only from an authorized human preview after
independently inspecting all referenced support and dependencies. No assertion
is relabelled confirmed because a human accepts it. Live freshness cannot be
determined by this ledger adapter; the UI says so and shows pinned provenance.

Human actions use the existing Stage 2 `ReviewService.preview/review` methods.
A fresh preview digest/revision, rationale and explicit confirmation are required.
Accept/reject/supersede retain the existing transition and conflict rules; stale
or repeated decisions return 409 without duplicate decisions/outbox records.
Supersession requires a separately authorized replacement supporting the same
fact. Immutable reviewer ID, rationale and timestamp remain in the existing
ledger, with atomic outbox insertion and the existing supplementary account audit.
The result says materialization is pending. No materialization route, automatic
worker or graph client was added. Administratively provisioned services and the
existing independently enforced evidence authorizer are still prerequisites.

## Assistant and proposals

Review reuses Overview's transport, stored provider settings, named user session,
per-turn disclosure checks and shared Stage 5 registry. The server fixes the
Review profile and `get_assertion` selection; request profiles, history, credentials,
model tool requests and decision calls are not accepted. Questions require
explicit consent to send them and the current authorized context to the approved
configured destination. The same permission, content and provider binding are
checked again after transport; stale responses are refused.

Bounded same-fact comparison supplies only independently authorized alternative
assertions and citations, without inaccessible identifiers or withholding counts.
It is labelled a permitted comparison rather than an exhaustive conflict report.
It has a 50-candidate/2 MiB ceiling. The assistant may explain disagreement and
draft suggestions as text, but cannot invoke submit, review or materialization.
Overview retains its fixed accepted-only profile and unsupported-fact refusal.
No new agent framework, session store or conversational history replay is added.

An advanced proposal form accepts an explicit assertion JSON document, pinned
ontology, existing evidence references, caller idempotency key and separate
submission consent. It delegates to the existing `submit_assertion` contract,
including tool, source and proposal-scope grants. Submission alone adds no
decisions or graph operations. The submitter is not automatically granted later
assertion-record disclosure. Automatic Sketch translation, evidence capture,
autonomous enrichment and agent acceptance remain unavailable.

## Navigation and accessibility

Knowledge's existing stable-ID Review links resolve to a bounded permitted queue
for an entity/fact or directly select an assertion. Review URLs preserve domain
and selected assertion on reload. Return to Knowledge uses stable entity/fact
references; Files provides both Knowledge and Review links only for datasets
with a stable `entity_ref`. Unstructured Sketch drafts have no assertion until a
governed proposal adapter exists; no draft ID is reinterpreted as accepted data.
Files drive-path/dataset reselection across full reloads remains future work.

Queue and inspector use native labelled controls, visible keyboard focus, live
status regions, Enter activation, and inspector heading focus after selection.
Advanced history/freshness/proposal fields use progressive disclosure.
The two-column view stacks at narrow widths and long stable references wrap.
New screenshots at 1440×900, 1280×800 and 1024×768 are candidates for human review;
no visual baseline was approved or replaced. Keyboard/label checks are focused
checks, not a claim of a complete accessibility audit.

## Credential-import audit and narrow fix

Before this change, `POST /api/llm/import-parley-env` used
`@require_role('admin', 'user')`, plus a single-user-count guard.
The decorator deliberately bypassed authentication on no-auth installations.
Consequently a single ordinary user or a no-auth caller could import host Parley
credentials into provider settings. Existing settings/model/test operations can
reuse a stored key, so importing host credentials into that caller's control
is a credential-security boundary failure even though responses only show a hint.
The import route also returned arbitrary exception text from the environment reader.
This was verified using synthetic credentials and source inspection; actual host
credential values were neither read nor reported.

The narrowly scoped fix requires an unlocked named administrator session, rejects
Authorization headers and cross-origin browser calls, retains the single-user
restriction, closes the auth handle and returns a generic import failure.
No-auth bootstrap and API-token paths cannot import host credentials.
The existing positive import test now uses a synthetic named administrator;
negative tests cover ordinary users, no-auth, token/header sessions, shared
installations, cross-origin and locked sessions, and sensitive exception output.
Other provider settings architecture and discovery endpoints remain unchanged.
Approved model discovery is never inferred by Review: disclosure still binds the
stored endpoint/model to an explicit Stage 3 destination approval.

## Files changed

| File | Responsibility |
| --- | --- |
| `scidk/services/review_workspace.py` | Queue, safe inspector, reviewer previews/decisions, assistant context and explicit proposals |
| `scidk/services/overview_chat.py` | Shared per-turn transport with server-bound profile and optional trusted context enrichment |
| `scidk/web/routes/ui.py` | Default-off Review page and human-session-only API dispatch |
| `scidk/ui/templates/gui/review.html` | Queue, inspector, confirmation, assistant and advanced proposal forms |
| `scidk/ui/static/js/review_workspace.js` | Filters, stale-request guards, context links, decisions and assistant interactions |
| `scidk/ui/static/css/review_workspace.css` | Review layout, wrapping and focus styling |
| `scidk/ui/templates/gui/files_inspector.html`, `scidk/ui/static/js/gui_slice.js` | Stable dataset-to-Review link |
| `scidk/web/routes/api_llm.py` | Narrow environment-import credential fix |
| `tests/knowledge_e2e/test_review_workspace.py` | Isolated real-policy/ledger/decision tests |
| `tests/gui/test_review_workspace.py` | Real loopback Review workflows, screenshots and keyboard/label checks |
| `tests/security/test_environment_import.py`, `tests/test_llm_provider_settings.py` | Negative import authorization and retained positive admin import coverage |
| `docs/design/gui-next-stage-followups.md` | Preserved Prompt 15–17 handoff and tracked Knowledge UX issues |
| `docs/design/gui-prompt14-report.md` | Implementation and validation report |

## Validation

The backend and browser suites use disposable databases and synthetic principals,
sources and evidence. Review backend operations are real, not mocked endpoints.
The focused browser fixture stubs only authentication status/auto-lock display
and provider transport; ledger authorization and human decisions use real services.
The Prompt 10 harness blocks external browser requests and fails on unexpected
browser errors. No paid live Parley calls, deployment or production writes ran.

Relevant broader backend regression, before the final assistant comparison
refinement and final focused security cases: **241 passed, 0 failed, 1 skipped,
0 xfailed**, 171.86s. The skipped test requires explicitly configured disposable
live Neo4j and was not enabled.

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e tests/curation tests/security tests/agent_integration tests/test_llm_provider_settings.py tests/test_gui_slice.py -q -o addopts=''
```

Full disconnected browser regression, after the UI changes and before the final
assistant comparison refinement: **43 passed, 0 failed, 0 skipped, 1 xfailed**,
102.71s. Known expected failure: GUI-004 Settings CDN dependency. Existing visual
baselines passed. Artifacts: `/tmp/scidk-prompt14-browser-regression`.

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui -q -o addopts='' --gui-artifacts /tmp/scidk-prompt14-browser-regression
```

Final focused results after the assistant comparison refinement:

- Backend Review, credential import and Overview isolation regression:
  **43 passed, 0 failed, 0 skipped, 0 xfailed**, 30.84s.
- Integrated Review browser workflows: **6 passed, 0 failed, 0 skipped,
  0 xfailed**, 19.59s. Artifacts: `/tmp/scidk-prompt14-review-final`.

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e/test_review_workspace.py tests/knowledge_e2e/test_prompt12.py tests/security/test_environment_import.py -q -o addopts=''
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui/test_review_workspace.py -q -o addopts='' --gui-artifacts /tmp/scidk-prompt14-review-final
```

JavaScript syntax and `git diff --check` pass. Initial development checks caught
incorrect fixture field assumptions and an accessible-name mismatch in the filter
selects; these were corrected before the passing regression. A superseded browser
run was terminated; the development server was not stopped or restarted.

## Remaining limitations and next passes

Provider-bound human disclosure is retained; a new human-only policy was not
invented. Production assembly must explicitly configure the ledger,
`KnowledgeServices`, review evidence authorization, grants and approved provider
destination. This task does not initialize those services in a running deployment.
The new API rejects anonymous/token/header sessions, unknown operations/fields,
cross-origin calls and raw query requests; role membership alone never grants
evidence or decision access. Existing legacy APIs retain their own contracts.

The UI records decisions but has no safe deployed materialization/worker adapter.
Source freshness, reviewer assignment, arbitrary evidence browsing/upload,
multi-fact automatic reasoning, Sketch-to-proposal translation, and Files return
selection adapters remain unavailable. Previously displayed human-visible data
cannot be recalled after grants are revoked; new retrieval and assistant replies
are reauthorized. No live Neo4j or live approved-provider behavior was verified.

The agreed next-stage requirements from
`scidk_prompt14_handoff/ux-and-security-followups.md` are preserved in
`gui-next-stage-followups.md`: Prompt 15 owns Resources/Annotations/legacy Dataset
reconciliation and the broader provider/security audit, including server-only
shared credential resolution and negative authorization tests across provider APIs.
Prompt 16 owns the crowded Knowledge toolbar, form-heavy Sketch, unclear refusal
wording, and unhelpful empty states, plus visual editing/context-trail work.
Prompt 17 owns the demo rehearsal, permitted real-provider/disposable-Neo4j
verification, Windows package checks and human screenshot approval. Controlled
Burn follows demo feedback. None of these later passes was started.

The handoff's user-reported cumulative Parley checkpoint is $12.17. No new account
total is available from this local test run; no live paid-provider smoke test ran.
