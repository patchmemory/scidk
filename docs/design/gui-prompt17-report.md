# Prompt 17 integrated research workflow release candidate

Worktree: `/home/patch/Projects/scidk-knowledge-curation`.
Branch: `design/knowledge-curation-20261029`.
Starting HEAD: `19d4764075bf98ae0f02dfbfc044a90583f0ecc0`.
Prompt 16 implementation `ea4ab107a410d873ac5516fadaa4895ba92c9de1` was preserved.
Implementation commit: `9ce0674beca5375ead3b5a4d20e46cea9851559e`.
This report is committed separately so it can record that exact implementation
revision. The final report commit hash is supplied in the completion message.

The explicitly synthetic integrated vertical slice is demonstrable. It uses the
production application factory, actual GUI routes, real authorization/ledger/
ReviewService/sharing services, persisted simulated graph application and a real
HTTP call to a deterministic loopback fake. It is not operational Neo4j, automatic
scientific ingestion, complete multimodal ontology or live Parley verification.

## Authorized decisions and preservation

All required Prompt 17 inputs and referenced design/architecture documents existed
and were read. No missing input was invented. The initial tracked tree was clean;
existing untracked prompts, handoffs/ZIPs and vision/demo/roadmap inputs remain
uncommitted. The user authorized renaming `scidk_prompt_16_02.txt` to
`scidk_prompt_17_01.txt`; its contents were preserved and approve the human policy.
The operator separately approved the narrow disposable synthetic catalog exception
documented in `gui-prompt17-ontology-decision.md`. No broader ontology change was
inferred. Existing bundled YAML and the base synthetic catalog are unchanged.

The existing `.scidk_secret.key` contents were never read. It remains untracked
and now matches a root-specific ignore entry. No running 5001/5002 service was
modified or restarted. No production grants, operational research data, graph
writes, remote provider requests or backup imports were performed. Controlled Burn
work was not begun.

## Implementation

`human_policy.HumanIdentity` is separate from AI `BoundIdentity`; AI PolicyStore
rejects it. Explicit trusted-local `HumanPolicyStore` setup and audited purpose
grants support `research_browse` and `review_read`, each with low/medium ceilings,
revision and revocation. No role, login or provider settings imply a grant.
Human Research, private Research canvas, Review inspection/preview/decisions and
local selected-dataset sharing use strict named unlocked same-origin cookie
sessions and current human purpose authority. Resource/classification/evidence/
property checks and existing reviewer permissions remain mandatory. Actual
ReviewService owns decisions, stale revisions and outbox state. AI Overview,
Review assistant and proposal paths retain destination/model approval, credentials,
consent and pre/post-transport revalidation. Human System/Ontology tool contexts
retain their previous provider-bound contract in this slice.

`human_legacy.LegacySnapshot` supports explicitly supplied immutable snapshots,
not unrestricted graph queries. It bounds records/bytes, validates the existing
ontology, derives stable source-bound record identities, requires actual matching
ledger evidence and independent record/evidence access, and withholds locator
fields and hidden properties before search. It must belong to the same Ledger as
the Research serializer. Legacy values are labeled legacy/unreviewed with
unverified materialization and epistemic status, never accepted/applied. AI
discovery does not consume these snapshots. No operational legacy adapter was
enabled without reliable source bindings.

`dev_integrated_demo` is an explicit hook for the preserved `dev_gui` launcher on
a separate port (runbook uses 5003). Fresh `seed_reviewed` is the local operator's
opt-in to bundled synthetic decisions; ordinary `configure` never reseeds or
restores revoked grants. It seeds two fictional MRI/microCT text artifacts,
Dataset/File/property/membership assertions and versioned evidence, records 12
actual authorized decisions, and applies their operations through the existing
tested FakeGraph. Application receipts come from the real materializer. Simulation
nodes/edges/operation markers persist across restarts. One proposed name revision
and one independently authorized legacy record demonstrate their distinct states.

The approved unchanged Dataset/File/CONTAINS fixture extension was extracted from
Prompt 12 into `tests/fixtures/knowledge_curation/dataset_catalog.json`, reused by
both old tests and the demo. No accepted modality/investigator/study schema fields
were invented: those descriptions remain fictional names and citation provenance.
The demo replaces home/mounted/rclone discovery with one confined synthetic local
provider. The existing Files Dataset search is adapted narrowly in that hook to
the actual governed ledger, without arbitrary graph access.

Integration testing also fixed fresh-state auto-lock settings reads, selected
Knowledge deep-link inspection, and misleading legacy trust text. Prompt 16 styling,
navigation, Cytoscape/Sketch, Files, Resources and annotation implementations were
preserved. Source/schema/mapping remains the existing builder, not a new framework.

## Verification

Use `/home/patch/PycharmProjects/scidk/.venv/bin/python` with
`PYTHON_DOTENV_DISABLED=1`, `-q -o addopts=''`. Browser/fake-provider tests need
loopback sockets and Chromium; they ran outside the restrictive sandbox with
authorization, using disposable state only.

| Check | Result |
|---|---|
| Relevant backend regression: `tests/security tests/knowledge_e2e tests/pipeline tests/test_dev_gui.py tests/test_llm_provider_settings.py tests/test_auth.py` | **650 passed**, 202.03 s; no skips/xfails. Includes the 16 initial Prompt 17 policy and two integrated service tests. |
| Full GUI regression: `tests/gui --gui-record-candidates --gui-artifacts /tmp/scidk-prompt17-final-candidates` | **59 passed**, 146.31 s; no skips/xfails. |
| Final policy, synthetic assembly and legacy-boundary checks: `tests/knowledge_e2e/test_prompt17.py tests/knowledge_e2e/test_prompt17_demo.py tests/knowledge_e2e/test_prompt17_legacy.py` | **25 passed**, 24.98 s, after the final same-ledger binding check. Includes seven additional legacy/sharing/confinement cases. |
| Final production-factory browser check after that binding check: `tests/gui/test_prompt17.py` | **2 passed**, 15.04 s; both required viewports. |
| `git diff --check` | Passed before commit. |

Security checks cover missing/revoked purpose/Resource/evidence grants, ceilings,
high/unknown classification, ordinary users, admins without Resource grants,
reviewers without evidence access, anonymous/no-auth/disabled/locked sessions,
tokens/headers/cross-origin, stale decisions, hidden fields, disallowed AI
destinations, transport-time revocation and human/AI identity isolation. New legacy
tests cover hidden search, record revocation, mismatched source evidence, rejected
locator/unbounded input, ledger misassembly, absence from AI discovery and local
filesystem/symlink escape refusal. Sharing tests use actual supported membership;
the generated Bash script runs on the real synthetic bytes and copies only the
listed files. PowerShell was inspected statically; Windows execution is unverified.

Early integration runs exposed a missing candidate identity role, a locked-session
status expectation (423), missing test chat blueprint, fresh-state auto-lock error
and selected-link inspection issue; these were corrected. Preliminary regressions
were interrupted when the catalog exception was approved so service assembly could
proceed; they are not claimed as completed checks. The completed results above
supersede those runs.

Sixteen integrated screenshot candidates are preserved in
`gui-prompt17-candidates/`, covering Overview, Files/Datasets, Graph/Entities/Sketch,
Review, Resources and sharing at 1440×900 and 1024×768. Local full-run traces,
request/error logs and browser metadata are under `/tmp/scidk-prompt17-final-candidates`.
Selected candidates were visually inspected; operator review and approval of
actual behavior remain pending. No existing visual baseline was auto-approved.

## Demo readiness and deployment blockers

The exact walkthrough and per-step PASS/PARTIAL/BLOCKED evidence are in
`docs/demo/scidk-integrated-demo-runbook.md` and
`docs/demo/scidk-demo-acceptance.md`.

- **Operational in disposable simulation:** named login, provider-independent
  governed human browsing, honest legacy snapshot, accepted membership expansion,
  permitted Review evidence/confirmation, stale-decision protection, scoped DMS
  draft/ZIP and Bash preparation, and no-ID Ask with loopback fake citations.
- **Live configuration required:** a fresh isolated instance with assembled
  services and explicit human purpose/Resource/evidence/reviewer grants. Existing
  servers do not gain grants or service assembly automatically. Exact endpoint/
  model approval and personal/shared credential authority remain separate for AI.
- **Production/ontology blockers:** approved operational catalog reconciliation,
  reliable legacy source/record identities, accepted/applied real membership and
  verified graph target. No real disposable Neo4j verification was performed.
- **Remaining GUI/workflow integration:** automatic Files/scanner/Resources intake
  into governed assertions; structured multimodal/investigator/study relationships
  under approved schema; operational legacy adapter; full source-builder ingestion
  into this slice; a separately authorized materialization UI if desired. Review
  decisions currently show pending application accurately. Existing private Sketch
  remains separate from assertion submission.
- **Unverified:** Windows execution, live Parley and full institutional workflow.
  The unchanged catalog supplies no sha256 property, so expected hashes are not
  invented. Resources/Annotations/Interpreters are retained and regression-tested
  separately; the seed Resource is not advertised as a runnable importer.

No paid request was made. The $17.93 starting cumulative Parley spend was reported
by the user and is not independently verified. No billing access or exact dollar
enforcement is claimed. The runbook provides an opt-in single-request real smoke
procedure with exact destination/model approval, tiny synthetic System context,
explicit consent, spending-control prerequisite, existing timeout/token limits
and no automatic retries. No permission for a paid call has been assumed.
