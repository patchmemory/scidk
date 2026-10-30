# Prompt 18 operational runtime and entity integration

**Outcome: partial implementation; operational entity browsing remains blocked.**
The real development graph was inspected read-only under the user's explicit
authorization. Its sampled records cannot yet be bound to governed Resource and
evidence authority. No synthetic result is claimed as operational completion.

Worktree `/home/patch/Projects/scidk-knowledge-curation`, branch
`design/knowledge-curation-20261029`, starting HEAD
`ba42c24` (Prompt 17 verification documentation). Tracked files were clean.
Existing untracked prompts, ZIPs, handoffs and vision/demo/roadmap documents were
preserved. The additional user authorization `scidk_prompt_18_01.txt` remains
untouched. No paid Parley calls, production writes, automatic migrations, schema
changes, service restarts or Prompt 19 work were performed.

## Root cause and implementation

The complete actual data-path diagram, inspection scope and source-binding
blocker are in
[`scidk-operational-entity-integration.md`](../architecture/scidk-operational-entity-integration.md).

Three distinct issues were found:

1. The normal factory connects legacy graph services but does not assemble
   KnowledgeServices or ReviewService. New explicit trusted-local
   `operational_knowledge.configure` / `assemble` reuses the existing Ledger,
   FactDisclosure, AssertionAccess, ReviewService and bounded LegacySnapshot.
   Startup verifies an existing graph binding and exact reconciled ontology
   version, refuses replacement/missing state, and never seeds decisions, grants,
   policy tables, graph records or receipts. No graph writer is attached.
2. Research initialization loaded layout preferences without retrieving records.
   Graph/Entities now request bounded authorized initial discovery. Deep-linked
   selections and private Sketch behavior remain. Research refusal text now
   identifies human purpose/Resource/evidence authority instead of AI approval.
3. The inspected legacy source has no demonstrated stable Resource/evidence
   binding. File/Folder `(path,host)` constraints establish possible source-local
   identity only; sampled Dataset metadata and propertyless CONTAINS edges do not
   establish governed provenance. No operational legacy adapter was enabled.

`POST /api/knowledge/readiness` supplies named same-origin administrator-only
configuration diagnostics, with no restricted record payloads, IDs, source names,
locators or counts. It distinguishes Knowledge/Review assembly, GUI/feature state,
the current administrator's explicit purpose/Resource/evidence grants, ledger
access/provenance and an honestly unprobed live graph. Administrator role confers
no content bypass. No page-read initialization or default-on feature flags were
introduced.

Exact startup commands and provisioning prerequisites are in
[`scidk-operational-startup.md`](../demo/scidk-operational-startup.md). They are
conditional on real existing governed state, not a claimed working import of the
inspected graph. The original disposable Prompt 17 seed/startup remains unchanged.

## Operational versus synthetic verification

**Scenario A — actual development Neo4j:** verified localhost configuration and
Docker Compose ownership/mounts under the authorized development checkout. Used
a standalone read-only driver with fixed bounded queries and transaction
timeouts. Labels/types/property names and key/constraint shapes were inspected;
no entity values, personal data, research content or storage bytes were read.
No governed entity payload from that source was returned or screenshotted.
The source is reachable; safe governed browsing is BLOCKED pending the explicit
source/record/relationship identity and matching evidence contract detailed in
the architecture report. This bounded sample does not characterize every record.

**Scenario B — existing disposable integrated fixture:** actual Prompt 17 ledger,
12 real synthetic reviewer decisions and applied simulation receipts, Dataset/
File memberships and original FakeGraph were reused through the new assembly.
Browser tests demonstrate initial entity discovery, inspection, permitted citation
and property display, Graph navigation, expansion, relationship filtering, related
File selection, distinct legacy/unverified status, purpose revocation clearing
records and actionable missing-service diagnostics. Native `/entities`, its Links
tab and `/map` still return pages. Prompt 17's original end-to-end browser test
also exercises Files → Knowledge stable context, Review and sharing.

Four populated screenshot candidates are committed under
[`gui-prompt18-candidates`](gui-prompt18-candidates/README.md), at desktop and laptop
sizes. They contain only synthetic records; no screenshot baseline was approved.

## Validation

Backend regression:

```bash
PYTHON_DOTENV_DISABLED=1 /home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest \
  tests/security tests/knowledge_e2e tests/pipeline tests/test_dev_gui.py \
  tests/test_llm_provider_settings.py tests/test_auth.py -q -o addopts=''
```

**661 passed, 206.22 seconds**, no skips/xfails. Coverage includes explicit
researcher/admin grants, missing/revoked purpose/Resource/evidence authority,
anonymous/no-auth/disabled/locked sessions, tokens/headers/cross-origin, hidden
properties, restricted metadata, human/AI isolation and unchanged AI checks.
New assembly tests verify existing receipts/relationships, revoked grants retained,
unchanged ledger bytes, duplicate assembly refusal, missing-ledger noncreation,
graph-target and ontology-pin refusal, and protected readiness diagnostics.

Focused final new browser acceptance: **2 passed, 8.21 seconds**,
`tests/gui/test_prompt18.py --gui-record-candidates --gui-artifacts
/tmp/scidk-prompt18-browser-v6`. Original Prompt 17 browser check independently
passed both viewport cases before the initial-discovery fix. The full GUI run
after that fix completed with **58 passed, 3 failed, 215.92 seconds** at
`/tmp/scidk-prompt18-full-gui`. Its three failures were the obsolete refusal-text
assertion and two copies of the earlier new-test File-name selector. Those tests
were corrected without further runtime changes. The exact failed set reran as
**3 passed, 12.05 seconds**, no skips/xfails, at
`/tmp/scidk-prompt18-corrected-gui`:

```bash
PYTHON_DOTENV_DISABLED=1 /home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest \
  tests/gui/test_knowledge_workspace.py::test_context_link_revocation_and_no_stale_inspector \
  tests/gui/test_prompt18.py -q -o addopts='' --gui-record-candidates \
  --gui-artifacts /tmp/scidk-prompt18-corrected-gui
```

Thus all 61 GUI cases have passing verification across the full run and corrected
targeted rerun; a single clean 61-case run is not claimed. `git diff --check`
passed. Candidate mode does not approve frozen visual baselines.

Early checks encountered sandbox-denied loopback/Chromium, then were rerun with
approval outside the sandbox. New browser test development corrected a missing
fixture import, expected count including legacy, selection by File type rather
than absent name, and waiting for search completion. The first browser failure
also exposed and led to the real missing initial-discovery fix. These failed
development attempts are not claimed as acceptance passes.

## Files changed and remaining decision

- `scidk/services/operational_knowledge.py`: explicit existing-state assembly and
  bounded diagnostics, with no operational graph query fallback.
- `scidk/web/routes/ui.py`: administrator readiness and actionable unavailable
  response; existing routes preserved.
- `scidk/ui/static/js/knowledge_workspace.js`: initial discovery and accurate
  human authorization messaging, with existing Prompt 16 presentation.
- `tests/knowledge_e2e/test_prompt18.py`, `tests/gui/test_prompt18.py`: actual
  integrated fixture regression and browser acceptance.
- `tests/gui/test_knowledge_workspace.py`: expected human refusal wording updated.
- This report, architecture/startup documents and four screenshot candidates.

Required administrator decision: approve an exact source-to-Resource association,
stable external Dataset/File/relationship keys, and actual matching versioned
evidence provenance for the selected development source. Reconcile its operational
ontology explicitly. Do not derive authority from a filesystem path, profile
name, scan UUID, admin role or Neo4j presence. This pass stops the legacy adapter
at that boundary, as required by the approved human-browsing policy.

Implementation commit: `90cdc32942cf39b6d2629fa15bd2e7c6dc975d80`.
This hash is recorded in a subsequent documentation-only commit. All tracked work
was committed; the pre-existing untracked inputs and additional user authorization
remain preserved outside the implementation commit.
