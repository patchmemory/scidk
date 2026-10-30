# Explicit development Knowledge startup

**Scenario A is blocked:** inspected legacy entities have no established binding
to governed Resources/evidence. The command below works for **already provisioned
governed state**; it does not import that graph or supply the missing binding.
Do not use production state. No AI provider is required for human browsing.

## Existing governed state

The administrator supplies a dedicated development settings store with named
authentication and existing explicit human policy, exact Resource/evidence
grants, classifications and any reviewer grants. Supply an already migrated
curation ledger with its actual graph binding and receipts, plus a reconciled
catalog snapshot pinned to the assertions' ontology version. No migration,
grant, review decision or graph application occurs during assembly.

Create a private administrator-owned manifest, for example
`/tmp/scidk-development/knowledge.json`, with actual values:

```json
{
  "ledger_path": "existing-ledger.sqlite",
  "catalog_path": "reconciled-catalog.json",
  "ontology_version": "EXACT_EXISTING_ONTOLOGY_VERSION",
  "graph_target": "EXACT_EXISTING_LEDGER_GRAPH_TARGET"
}
```

Paths are relative to the manifest, or absolute. Catalog format is the existing
`Ontology([], definitions)` LabelService snapshot list. A different version fails
startup; do not substitute a synthetic catalog for operational definitions. Mixed
historical ontology versions currently require administrator reconciliation.
An optional `legacy_path` names a bounded JSON list in the unchanged Prompt 17
LegacySnapshot contract (`record_key`, `source_scope`, `evidence_id`, `label`,
`properties`). Matching evidence must already exist in this **same ledger**.
This snapshot supports entities only, never unsupported legacy edges. Its records
require independent explicit record grants as well as source/evidence authority.

Use the existing authentication initialization if this development state has no
users yet (password is prompted); do not reuse operational settings:

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python -m scidk.dev_gui \
  --state-dir /tmp/scidk-development --init-admin development-admin --port 5003
```

That initializes authentication only. Stop this newly created development server
yourself before restarting it with the completed provisioning; it does not create
the ledger or disclosure policy. For explicit audited policy provisioning, trusted
local administration uses existing `PolicyStore.initialize`, `classify`,
`grant_resource`, `grant_evidence`, `HumanPolicyStore.initialize`, and
`grant_purpose(user_id,'research_browse','low',admin_id=...)`. Review additionally
uses `review_read` and existing `curation.human_reviewer_user_ids`. These are
separate authorized administrative actions, never inferred from admin role or
performed by the startup hook. Grant only actual approved sources/records.

After those prerequisites, launch on a verified unused port:

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  SCIDK_KNOWLEDGE_MANIFEST=/tmp/scidk-development/knowledge.json \
  /home/patch/PycharmProjects/scidk/.venv/bin/python -m scidk.dev_gui \
  --state-dir /tmp/scidk-development \
  --configure scidk.services.operational_knowledge:configure --port 5003
```

The launcher enables the redesigned GUI in this instance, uses memory backend for
legacy graph services and retains local Files/Resources routes. It refuses
inherited graph configuration; do not add `.env` loading or a live graph override.
This avoids the normal factory's graph startup writes. No automatic scanner to
ledger intake or live operational legacy Maps population is claimed.

For an existing trusted local assembly with in-memory reconciled ontology rather
than JSON, call `assemble(app, ledger_path=..., ontology=..., graph_target=...,
legacy_records=...)` from the existing `--configure module:function` mechanism.
It refuses replacement of already attached Knowledge or Review services.

## Readiness and browsing

Log in as a named administrator and open the browser console on the same origin:

```javascript
await (await fetch('/api/knowledge/readiness', {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
})).json()
```

Check `knowledge_service`, `review_service`, `ui`, `research_enabled` and
`purpose_grant`. `resource_grants` and `evidence_grants` check the current admin's
own permissions across a bounded existing evidence set; false does not mean that
every source is inaccessible. Without purpose authority they are `not_checked`.
`source_access=ledger_readable` and `provenance=ledger_evidence_available` mean
ledger access only. `empty_or_limit` requires administrator investigation.
`live_graph=not_probed` is deliberate. No restricted names, paths or records are
returned; this is not a grant-management endpoint or a bypass.

Visit `/knowledge?domain=research&view=entities`. Initial discovery lists at most
25 authorized records, with pagination. Select an entity for current properties
and provenance, Show in Graph, Expand selected, then filter relationships under
Graph tools. Stable Files/Dataset links reauthorize the selected reference.
Missing services give a 503 with this runbook/readiness action; missing or revoked
authority refuses without revealing protected existence. Legacy records show
legacy/unreviewed and unverified; only actual accepted/applied support gets that
status. Graph presence never establishes acceptance.

## Source-binding decision required for the inspected development graph

Supply the exact Resource association and actual evidence provenance for each
selected source, a stable Dataset identity contract, and independently supported
membership identities. File `(path,host)` uniqueness is only a candidate identity
within an approved source, not Resource authority. Do not mint ledger evidence
from that observation or grant an entire graph. No operational snapshot has been
created and no graph entities have been imported.

## Preserved disposable simulation

The complete reproducible **synthetic** startup and explicit seed decision remain
in `scidk-integrated-demo-runbook.md`. Prompt 18 tests reuse that same actual
ledger, ReviewService, receipts and simulated graph with the new assembly; no
second fake graph or synthetic workaround for Scenario A was added.
