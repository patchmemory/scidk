# Disposable integrated SciDK demonstration

Use branch `design/knowledge-curation-20261029`. This is an authenticated local
**simulation**, not an operational research deployment or live Neo4j validation.
It uses the approved, unchanged synthetic Dataset/File/CONTAINS test catalog.
MRI and microCT artifacts contain fictional plain text, not image acquisitions;
modality/study/investigator descriptions are synthetic names and evidence citation
metadata, not additional accepted ontology properties.

## First startup

Leave existing 5001/5002 services untouched. Choose an unused port and a new private
state directory. The following explicit `seed_reviewed` hook opts into acceptance
of the bundled synthetic facts as the named development reviewer. It creates 12
actual decisions and applies their outbox operations through the tested fake graph
writer, plus one proposed name revision. It never inserts fabricated receipts.
Do not use an operational settings database or an existing application directory.

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python -m scidk.dev_gui \
  --state-dir /tmp/scidk-prompt17-demo --init-admin demo-admin \
  --configure scidk.dev_integrated_demo:seed_reviewed --port 5003
```

Enter a new matching password of at least 12 characters at the prompts. Visit
`http://127.0.0.1:5003/login`, sign in as `demo-admin`, then open
`http://127.0.0.1:5003/demo/prompt17`. No password or API key belongs in command
arguments, a shell history entry, screenshots, or a committed file.

The normal factory runs with separate settings/index/scans/crates and memory graph,
dotenv and scheduler disabled. The integrated hook replaces filesystem providers
with a single local provider confined to `synthetic-files` under this state.
Mounted drives and inherited rclone remotes are not available through that registry.
Graph environment configuration is refused by the launcher. Do not add a drive,
configure an operational graph, import a backup, or run external intake.

State files: `scidk_settings.db`, `files.db`, `prompt17-ledger.sqlite`,
`prompt17-manifest.json`, `prompt17-simulation.json`, `synthetic-files/`, `logs/`.
The simulation JSON persists actual fake-writer nodes, edges and operation markers.
Keep the entire directory private and disposable; never commit it. The manifest
contains local fixture references, not credentials. The hook requires the checkout
and its development dependencies because it reuses the tested FakeGraph.

## Provider-independent human walkthrough

1. With no provider configured, open Files & Datasets. The only demo drive is the
   synthetic file root. Browse its MRI/microCT folders and fictional text files.
   Switch to Datasets, search **Synthetic**, and select the phantom study.
2. Inspect Metadata and Provenance. This is a development-only, governed collection
   search adapter over the real ledger. It is not an automatic scanner-to-ledger
   ingestion pipeline. Legacy File scanning/annotation functionality remains the
   existing implementation; collection results use stable ledger references.
3. Follow **Knowledge** from the Dataset inspector. The selection opens its inspector;
   expand to show both accepted File members. Graph and Entities display current
   permitted support. Search **legacy phantom** to see the separate explicitly
   source-bound snapshot labeled legacy/unreviewed and unverified, without receipts.
   Its existence is not curation acceptance. No operational legacy graph is read.
4. Sketch remains private: place/connect drafts, save and reopen. References are
   reauthorized. It does not commit scientific facts. Existing workspace tests
   cover those actions; screenshot candidates are not visual approval.
5. Use the demo landing page's **Review proposed revision** link. Examine claim,
   evidence and citation, then prepare a decision. Reject the proposed name with
   a rationale and explicit confirmation to retain the seeded accepted name.
   Replaying a stale preview is denied. Decisions do not apply graph changes;
   no materialize control is provided in this Review UI. Seeded facts have real
   applied receipts for the simulated target; new decisions remain pending.
6. Return to Files → Datasets and select the phantom study. Prepare for Sharing,
   complete investigator-supplied details, preview the NIH DMS **draft**, then
   download the package. It contains only this accepted/applied Dataset's two
   direct File members, a manifest, provenance, README, Bash and PowerShell scripts.
   It contains no data bytes or upload action. Never use a whole-graph fallback.
7. Extract the ZIP into a separate directory and inspect `files.txt` and scripts.
   Run `bash prepare.sh /tmp/scidk-prompt17-demo/synthetic-files /tmp/scidk-demo-staged`
   from the extracted package; the destination must be new. Review the two paths
   and type `COPY`. Compare copied bytes with the source before any sharing.
   The unchanged demo catalog has no sha256 property: hashes are not invented.
   PowerShell is included and statically inspected; actual Windows execution is
   unverified. Do not relax execution policy to run it.
8. Resources, Annotations and Interpreters retain their native routes. The synthetic
   evidence Resource is visible, but its `synthetic-demo` plugin is not a runnable
   source importer. Source → Schema → Mapping is regression-tested with existing
   CSV services separately; do not claim this seed was produced by that builder.

Only explicitly granted users may browse. The seeded administrator has explicit
purpose, Resource, evidence and reviewer grants; admin role does not grant access.
Ordinary-user positive and denied cases are covered by disposable integration
tests. Adding another user does not grant access automatically. Human policy is
managed locally through `HumanPolicyStore.initialize` and `grant_purpose`, plus
the existing exact Resource/evidence grants, never through an AI tool. Purpose
changes are audited and revocable; allowed ceilings are low/medium only.

## Ask SciDK with the free local fake

Start the existing deterministic fake in another terminal:

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python -m scidk.dev_system_demo --port 5010
```

In personal AI settings select custom URL `http://127.0.0.1:5010/v1`, model
`synthetic-demo`, no key. Save. Model discovery is not destination approval.
Explicitly approve only that exact local fake destination through trusted local
configuration:

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python - <<'PY'
from scidk.core.auth import AuthManager
from scidk.agent_tools.security import PolicyStore
db = '/tmp/scidk-prompt17-demo/scidk_settings.db'
auth = AuthManager(db)
try:
    admin = auth.get_user_by_username('demo-admin')
    assert admin and admin['enabled'] and admin['role'] == 'admin'
    PolicyStore(db).approve_destination('prompt17-local-fake',
        'http://127.0.0.1:5010/v1', 'synthetic-demo', 'low', admin_id=admin['id'])
finally:
    auth.close()
PY
```

Open Overview, ask **Find synthetic phantom**, keep My accessible knowledge,
explicitly check consent, then Ask SciDK. No node ID is needed. Inspect retrieved
facts/citations separately from the fake's constant interpretation. The fake does
not perform scientific reasoning and never forwards a request. To demonstrate its
specific constant System explanation, choose System documentation and ask
**Explain the synthetic System workflow**. Human browsing still works if personal
provider settings or destination approval are removed; Ask refuses.

## Opt-in real Parley smoke procedure — NOT executed

This is an operator-run, single-request smoke test, pending separate approval for
paid access. Model discovery previously reported by the user is not this test.

1. Obtain approval for the exact endpoint/model, explicitly synthetic System
   context and a small cost budget. Choose the cheapest suitable approved model
   from current operator-visible pricing, not an assumed model name or price.
   Set an account/provider spending cap when supported. Without a credible price
   bound or spending control, keep this step BLOCKED and use the fake.
2. Use only this disposable instance. Configure the personal provider via the
   existing named-user settings; use the named-admin environment importer only
   when appropriate. Never copy keys into terminal commands, test fixtures, logs,
   exports or screenshots. Do not alter shared credential or global config gates.
3. Through trusted local `PolicyStore.approve_destination`, approve the exact
   normalized endpoint and exact model at **low** risk, using the seeded admin's
   ID. Replace the fake approval deliberately; neither a preset nor model listing
   approves the new destination. Keep the tiny synthetic Resource grants only.
4. Overview → System documentation → **Explain the synthetic System workflow**.
   Inspect the tiny context through Knowledge first. The call sends only the
   fixed System context/question; no history, legacy snapshot or raw graph.
   Existing discovery bounds are three sources/48 KB, 30-second transport timeout,
   and 1,200 output tokens maximum. Price that worst case before consenting; the
   application does not enforce a dollar-denominated budget or report billing.
5. Explicitly check consent and submit **once**. Do not automatically retry.
   Record status, model, elapsed time and usage/cost only when returned by the
   provider. Stop on refusal, timeout, unexpected context or budget uncertainty.
   Verify linked citations, then revoke the temporary approval and restore the
   local fake. Never interpret a successful response as institutional approval.

No paid request was made during implementation. Starting spend was user-reported
$17.93 cumulative; no billing access or independent verification is claimed.

## Restart, shutdown and fallback

Stop only the foreground port-5003 process with Ctrl-C, and the separate fake if
started. Never kill the 5001/5002 services. Restart with the same clean environment
and command above, omitting `--init-admin` and replacing the hook with
`scidk.dev_integrated_demo:configure`. This reads existing state; it never reseeds
decisions or restores revoked grants. A second `seed_reviewed` invocation refuses.

For a clean repeat, choose a different new state directory. Preserve the old one
for review; cleanup is simply deleting that explicitly disposable directory later,
after stopping its processes and confirming it contains no needed work. Do not
reset the worktree or delete unrelated temporary directories.

If integration is unavailable, use the preserved port-5002 System-only launcher
documented in `docs/design/gui-development-startup.md`, or show the recorded
synthetic candidates with their labels. Operational graph integration, structured
multimodal ontology, automatic ingestion, real provider access and Windows remain
separate verification steps. Do not begin the Controlled Burn.
