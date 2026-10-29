# Prompt 15 functional integration and readiness report

Worktree: `/home/patch/Projects/scidk-knowledge-curation`.
Branch: `design/knowledge-curation-20261029`.
Starting HEAD: `8d71d528169b12f69e9e714f7fbf9cb60ce3b727`.
Implementation commit: `a14701426be036226890dcea559126947ab8d6d0`.
The report is committed separately so it can name that exact immutable revision.

The worktree is at its permanent Projects path; Git metadata remains in the
original `/home/patch/PycharmProjects/scidk/.git/worktrees/` directory. `git worktree
list` shows no active `/tmp` worktree. User prompts, handoffs/ZIPs, vision/demo/
roadmap documents and the pre-existing untracked secret-key file were preserved
and excluded from the commits. No Prompt 16 work was begun.

## Delivered behavior

- Default-off, named-admin `/admin/chat-readiness` GET/POST: booleans and static
  remediation distinguish strict GUI/chat flags, configured provider, exact approved
  endpoint/model, KnowledgeServices, fixed-profile tool grants, usable Resource
  grants, selected context and its authorization. No provider calls, keys, model/
  endpoint values, hidden identifiers, restricted counts or internal exception
  text in the diagnostic response. It does not discover records. Connectivity is
  explicitly unverified; credential presence is separate and not required for
  a keyless local provider.
- Authenticated development launcher with isolated settings/index/scan/crate/
  relative stores, explicit Python booleans, prompted named-admin initialization,
  blocked dotenv/inherited graph setup, memory graph, disabled concept graph and
  scheduler. Default loopback port 5002 leaves port 5001 untouched. The tiny
  System-only hook uses a committed synthetic source with hash/git provenance,
  grants just that context and creates no research assertions, review decisions
  or graph writes. Real factory + named login + readiness were smoke-tested in
  disposable state without opening a listener.
- Existing OpenAI-compatible HTTP transport and fixed Overview/Review profiles
  retained. Synthetic System chat is tested through real policy/services and HTTP
  against a deterministic loopback fake provider, including Chromium. Overview
  remains accepted-only for research; Review's separately authorized assertion
  context is unchanged. No model-selected tools, arbitrary queries, autonomous
  loops, new history replay or direct Canvas commit path was introduced.
- Explicit local shared-usage grants pin enabled recipient, enabled named admin
  owner/issuer and exact owner endpoint/model. Credential remains in the existing
  encrypted per-user store and resolves only inside governed transport. Recipient
  settings/model discovery/testing and legacy providers never receive the owner's
  key. Usage grants do not confer model approval or Resource/evidence access.
  Revocation/account/destination/model checks and post-transport revalidation
  refuse stale replies. No schema migration or HTTP grant-management API.
- Resources retains Source → Schema → Mapping, templates, validation/FAIR and
  existing run/history/scheduling paths. `/annotations` opens the native Files
  Annotate drawer. Inspector entry explains that checked Files/collection define
  its scope; inspector focus does not silently select files. Existing annotation
  store, mapping engine and plugin registry remain in use.

Exact development commands, local model approval and System context selection:
[gui-development-startup.md](gui-development-startup.md).
Resources reuse map, identity reconciliation and synthetic human-review/apply path:
[gui-prompt15-reconciliation.md](gui-prompt15-reconciliation.md).

## Security assessment and explicit approval

A synthetic isolated audit reproduced ordinary-user retargeting of the global
credential registry URL while its server credential stayed attached. Configuration
imports could also mutate global grant settings. Work paused under Prompt 15's
security stop condition. User explicitly approved: **“Approve named-admin gates
and continue Prompt 15.”** The resulting server-side gates protect registry CRUD/
testing, configuration import/export and backup list/create/detail/restore/delete/
download. All require an unlocked named-admin cookie; no-auth, anonymous, ordinary
users, API tokens, named header sessions and cross-origin callers are denied.
Registry tests refuse redirects; global errors/test failures are generic and
responses are `no-store`. Existing backup contents/restore mechanics are retained;
backups are administrator material and this is not a backup-format redesign.

Personal `/api/llm/*` settings/models/testing require a named user and refuse
legacy/no-auth/API-token and cross-origin access. Named header sessions remain
supported for personal operations. Unknown owner/environment fields are rejected;
URL credentials/query/fragment are refused on save; a saved key is not sent to an
unsaved different URL. Presets expose no environment endpoint. Provider failures
and environment subprocess output are not returned; test replies expose bounded
status fields instead of raw provider content. Discovery remains distinct from
approved governed use. Environment import retains its single-user, named-admin
cookie-only boundary and explicit fixed Parley lookup, with bounded request fields.
No credentials were inspected or used in the running service.

The `scidk_prompt_15_02.txt` clarification is implemented: first-admin setup is
preserved through trusted local prompted creation; optional existing HTTP setup
requires an explicit private high-entropy Flask bootstrap token, loopback and
same-origin request, with serialized first-user creation. Absence of users confers
no admin rights. Once a user/legacy password exists, auth mutation requires named
admin. Regression tests cover bootstrap, transition, admin success, ordinary-user
and anonymous denial. The bootstrap token never becomes a session or authorizes
configuration/credential operations. Existing named admin/user distinction and
personal provider workflows are preserved. Legacy single-user configurations need
trusted local named-account provisioning for these sensitive routes.

This is a focused credential/configuration audit, not a claim that every legacy
SciDK route is governed. Legacy chat/direct graph functionality remains separate;
shared resolution is not installed there. No new raw fallback was added to the
accepted Knowledge/Review/sharing services.

## Changed implementation files

The exact 33-file implementation manifest is available with
`git show --stat a14701426be036226890dcea559126947ab8d6d0`.
Core additions: `scidk/web/named_session.py`, `scidk/ai/shared_provider.py`,
`scidk/services/chat_readiness.py`, `scidk/dev_gui.py`, `scidk/dev_system_demo.py`,
the readiness template/JavaScript and synthetic System fixture. Existing provider
settings, Overview transport, LLM/global-settings/UI routes, Files template,
provider-settings template and GUI inspector receive bounded adapters/guards.
Tests add `test_prompt15.py` in backend/browser suites,
`tests/security/test_provider_boundaries.py`, `tests/test_dev_gui.py`, and extend
existing auth/provider, browser workflow and stable Dataset-link assertions.
Documentation adds startup/reconciliation guides, candidate screenshots and the
preserved next-stage requirements. This report is the separate documentation commit.

## Validation

Use `/home/patch/PycharmProjects/scidk/.venv/bin/python`; all providers/data are
synthetic or explicitly mocked, with disposable SQLite and fake graph writers.

| Check | Result |
|---|---|
| Backend regression: `PYTHON_DOTENV_DISABLED=1 python -m pytest tests/security tests/knowledge_e2e tests/pipeline tests/test_dev_gui.py tests/test_llm_provider_settings.py tests/test_api_endpoint_registry.py tests/test_backup_automation.py tests/test_auth.py -q -o addopts=''` | **646 passed**, 157.99 s; no skips/xfails |
| Existing full browser regression: `PYTHON_DOTENV_DISABLED=1 python -m pytest tests/gui -q -o addopts='' --gui-artifacts /tmp/scidk-prompt15-gui-regression` | **46 passed, 1 xfailed**, 109.00 s; no skips |
| Additional shared owner/recipient disable, owner demotion/model change + credential/bootstrap/launcher focus | **18 passed**, 16.81 s |
| Final import/security/readiness/launcher + Dataset stable-link/sharing browser focus | **28 passed**, 25.00 s |
| Final expanded global-route denial and launcher scan/crate isolation checks | **18 passed**, 9.91 s |
| Real factory startup/login/readiness in isolated state, no listener/provider | Passed; missing configuration correctly reported |
| `git diff --check` | Passed |

Browser xfail is the pre-existing strict `GUI-004`: legacy Settings depends on
external Cytoscape; offline vendoring remains deferred. Frozen visual references
were not changed. Browser fixtures block outside requests. The System fake test
uses actual HTTP transport; sharing display controls and legacy attribution lists
use explicit mocked replies, while backend fixtures exercise governed sharing,
real ledger/review contracts and applied support. No live provider behavior or
operational Neo4j application is claimed. Early fixture/locator errors were fixed;
socket-restricted tests were rerun with permission for loopback servers.

Three committed screenshots in [gui-prompt15-candidates](gui-prompt15-candidates/README.md)
are **unapproved candidates**, with browser metadata. Full traces/request summaries
and regression images remain in `/tmp/scidk-prompt15-gui-regression`.

## Live blockers and remaining integration

Read-only observations of the existing port-5001 listener before these changes:
`/api/auth/status` reported `auth_enabled=false` with the legacy authenticated
bypass; `/overview` rendered no chat form and `/review` no workspace. Knowledge
and Resources pages rendered; `/annotations` was previously 404. These prove the
named-session and Overview/Review activation blockers. No server was restarted
or reconfigured; un-reloaded code cannot expose the new adapter/diagnostics.

KnowledgeServices/ReviewService assembly, exact endpoint/model approval, usable
credentials, actual source Resource/evidence grants and a selected permitted stable
context are **unverified live**, not assumed ready from rendered pages. Readiness
is admin-only and requires explicit strict `SCIDK_CHAT_READINESS_ENABLED=True` plus
GUI v3. The System-only hook supplies no Review assertions/backend or operational
Dataset. Review requires trusted, ontology-compatible service assembly.

Live dataset catalog/ontology reconciliation, accepted/applied stable identities
on legacy browser records, operational provenance/evidence grants and a unified
live Files → Dataset → Metadata → Knowledge → Review → sharing rehearsal remain.
Fixtures demonstrate the supported contracts; no legacy ID is silently curated,
no ontology is modified and DMS/packaging stay fail-closed. Arbitrary mapping JSON
round-trip and new capability source operations remain unavailable/unverified.

Prompt 16's toolbar/inspector/visual Sketch consolidation, generic empty/refusal
wording, and context-trail polish remain open. Prompt 17 retains human visual
approval, consented live Parley smoke test, disposable live Neo4j and Windows
PowerShell package validation. User-reported Parley checkpoint **$13.44 cumulative**
remains unverified; **no paid calls** were made. No production writes, bulk
migration, automatic human decisions or existing service restarts occurred.
