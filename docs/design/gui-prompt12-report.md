# Overview chat and selected-dataset sharing — Prompt 12

Prompt 12 authorizes the features outlined in Prompt 11. Implemented from
`a3d2b07` in the permanent `design/knowledge-curation-20261029` worktree.
Prompt history, vision and demo documents remain preserved as uncommitted inputs.
No security policy, ontology, source import, graph write or legacy route is changed.

## Activation and prerequisites

The host must set strict Flask configuration booleans, all defaulting off:

- `SCIDK_GUI_V3_ENABLED`: existing experimental GUI shell.
- `SCIDK_OVERVIEW_CHAT_ENABLED`: single-turn conversational Overview.
- `SCIDK_DATASET_SHARING_ENABLED`: dataset DMS preview and preparation ZIP.

These are application configuration values, not environment-variable parsers.
Existing `knowledge_services` assembly, `SCIDK_KNOWLEDGE_CONTEXT_ENABLED`, a named
unlocked human session, approved stored endpoint/model, source/evidence grants
and Overview tool grants are required. API tokens, anonymous sessions and auth-off
instances cannot use these endpoints. Setup never occurs on a page read or export.

## Overview

`POST /api/chat/overview` binds Overview on the server even with `?profile=review`.
The form accepts a current question, explicit provider-send acknowledgement and a
selected fact or System/canonical Ontology context ID. The backend accepts only
`explain_fact`, `get_system_context` or `get_ontology_context` as the fixed context
selector. Existing profile/tool grants and current-support checks apply.

The transport uses existing per-user provider configuration and the existing
redirect-refusing client. It freshly checks authorization and endpoint/model
before transport, and checks again before returning the answer and source context.
No legacy history, graph/schema aggregation, model-selected tools, autonomous loop,
Review inspection/proposals or decisions are enabled. Unknown JSON fields refuse.
Provider failures/refusals are generic; credentials and provider metadata never
return. The UI renders model text and sources as text, with an AI explanation
notice and expandable citations. Answers are not accepted facts.

This bounded first conversation requires a source ID; natural-language dataset
discovery and multi-turn history remain future work. Citations are provided in
the authoritative source panel; model-written citations are not independently
validated. A revocation after the final pre-send check cannot recall an in-flight
request; post-send revalidation suppresses the response when authorization changes.

## Dataset NIH DMS and sharing package

`POST /api/plugins/nih_dms/datasets/<entity_ref>/prepare` uses the selected stable
curation identity. A Neo4j element ID, path or display name cannot substitute.
One read-only ledger snapshot resolves the Dataset and its direct outgoing
`CONTAINS` File members. Every node, edge and exported property must be currently
accepted and applied to the bound graph, with authorized sources and evidence.
All candidates must pass; inaccessible or stale candidates refuse the whole
operation without exposing hidden counts. Maximum: 256 files, 128 candidate
properties per node, and 2 MiB of serialized provenance. There is no truncation or
whole-graph fallback. Generation is revalidated before returning a response.

The bounded field ceiling is Dataset `name`, `description`, `modality` and File
`relative_path`, `size_bytes`, `extension`, `sha256`. Each released field includes
its current fact support and permitted citations. Missing values remain unknown;
unknown file sizes are explicitly excluded from byte totals with a warning.
The existing NIH renderer receives only this scoped projection. All generated
prose is a draft for investigator review, including standards/access boilerplate.
No PHI scan, de-identification, consent determination or NIH compliance is claimed.

Repository, retention, sharing mode, contact, software and oversight are explicit
bounded investigator inputs, recorded separately from supported source facts.
This avoids the unresolved legacy split between `SCIDK_SETTINGS_DB` and
`SCIDK_DB_PATH`; the scoped route reads neither store for publication defaults.
The original whole-graph exporter and settings behavior remain compatible.

The three-step inspector guide previews the DMS draft/provenance before download.
Changing inputs or selecting another dataset resets download readiness. Missing,
unsafe or duplicate relative paths permit a DMS preview but disable packaging.

The ZIP contains a draft plan, manifest/provenance, plain-text relative file list,
README, Bash script and PowerShell script. File paths never become script source;
absolute paths, traversal, control characters, shell syntax, Windows reserved
names, alternate streams and case-insensitive collisions are refused. Scripts
list files, require typing COPY, reject source links/reparse points, require a new
destination and copy only listed regular files. They perform no upload, deletion,
source modification, credential handling or execution-policy bypass. Source file
contents are never read by the server or included in the ZIP.

The scripts are local preparation aids. Use a stable source tree and destination
under your control; concurrent filesystem mutation is not an adversarial security
boundary. Verify staged content, optional expected hashes, current permissions,
sensitive content and repository requirements before sharing. An offline package
cannot enforce subsequent revocations. Interrupted scripts may leave a partial
destination for manual inspection; they never clean it up automatically.

## Material limitations

- Recognized legacy Dataset nodes lack authoritative curation support. They remain
  unavailable for scoped export until an administrator reconciles the operational
  Dataset/File/CONTAINS ontology and an authorized intake/review process supplies
  stable identities, membership, relative paths and applied fact support. The test
  catalog is fixture-only and must not bootstrap production.
- Live Neo4j materialization/recovery and real provider responses remain unverified.
- The PowerShell script was reviewed but cannot be executed here: no PowerShell
  runtime is installed. Validate it on Windows before operational use.
- Existing GUI-004 (Settings CDN dependency), provisional visual references and
  outstanding human UX approval remain unchanged.

## Validation

Tests use real isolated ledger, human review, policy, session and HTTP adapters;
scientific records, graph transactions and provider replies are synthetic.
Two independent datasets/principals prove scope isolation. Additional checks cover
hidden fields, evidence revocation, superseded membership with retained graph
state, anonymous/token/disabled access, investigator validation, unknown paths,
Overview profile override attempts, forbidden history/provider overrides and
post-send revocation. The generated Bash artifact is executed against disposable
files, including spaces, unlisted files, links and an existing destination.

Browser checks use the real templates/JavaScript and intercepted synthetic replies
for enabled flows. The disconnected baseline suite retains its read-only fixtures
and external-request blocking. Initial browser startup was blocked by sandbox
socket restrictions; the approved run outside the sandbox completed successfully.
No visual references were replaced or accepted automatically.

Final focused regression: **201 passed, 0 failed, 0 skipped** in 126.22 seconds.
This includes the original browser compatibility test and **19 new backend/script
tests**. The first broader run encountered sandbox socket errors in the existing
provider tests; a test-fixture-only attempt to delete immutable history was also
corrected by assembling an absent-path fixture instead. The final approved run
above has neither failure.

Disconnected browser regression: **30 passed, 0 failed, 1 expected failure** in
41.24 seconds; the expected failure remains GUI-004. All 21 existing visual
references passed. After the final form/readiness adjustment, both new enabled
browser workflows passed again (**2 passed**, 6.18 seconds). Artifacts are in
`/tmp/scidk-prompt12-browser-verified` and `/tmp/scidk-prompt12-enabled-final`.

JavaScript syntax (`node --check` on both changed scripts) and Git whitespace
checks passed. PowerShell execution and live production integrations are not
included in these results.

Commands, using the existing primary checkout's virtual environment:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e tests/security/test_disclosure.py tests/agent_integration tests/test_nih_dms_plan.py tests/test_llm_provider_settings.py tests/test_gui_slice.py -q -o addopts=''
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui -q -o addopts='' --gui-artifacts /tmp/scidk-prompt12-browser-verified
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui/test_prompt12_workflows.py -q -o addopts='' --gui-artifacts /tmp/scidk-prompt12-enabled-final
```
