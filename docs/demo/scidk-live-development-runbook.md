# Live SciDK development runtime

Use the **port-5010 instance** on ki-ed3g. The existing port-5001 server is a
separate, unrecorded startup and has not been restarted or modified.

## Open the running instance

On **ki-marvin**, keep this SSH tunnel running:

```bash
ssh -N -L 5010:127.0.0.1:5010 patch@ki-ed3g.mit.edu
```

Open **http://127.0.0.1:5010/login**. On ki-ed3g, obtain the generated username
and password from the private file:

```bash
cat /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development/operator-login.json
```

This file is mode 0600 inside a mode-0700 directory, excluded from Git. It is
intended for the operator, not for screenshots, reports or shared logs. The named
account is `development-operator`; its administrator role does not confer graph
access. An explicit audited read grant was provisioned for this exact connection.
No graph entity-write, schema-write, Resource/evidence or AI grants were issued.

If local port 5010 is occupied on ki-marvin, use
`ssh -N -L 15010:127.0.0.1:5010 patch@ki-ed3g.mit.edu` and open
`http://127.0.0.1:15010/login` instead.

## Start, verify, stop and restart

Run these commands **on ki-ed3g**. The private state survives ordinary process
restarts. Do not rerun initialization or delete state to restart.

```bash
cd /home/patch/Projects/scidk-knowledge-curation
/home/patch/Projects/scidk-knowledge-curation/scripts/scidk-live start \
  --state-dir /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development
```

The wrapper pins this repository in `PYTHONPATH` and starts with a clean environment;
the shared virtualenv's editable package otherwise resolves to the other checkout
when invoked from elsewhere. `start` refuses an occupied port or an already-running instance. It launches the
existing `scidk.dev_gui.build_app` / `scidk.app.create_app` path, not another factory.
It binds only 127.0.0.1:5010, disables scheduler/concept-graph startup, and records
its Git revision, dirty state and application source fingerprint at startup.
Graph configuration is attached **after** the isolated factory to prevent startup
backfills or constraint changes. Startup does not import schema, seed records,
regrant permissions or assemble fake Knowledge/Review services.

Verify the owned process:

```bash
/home/patch/Projects/scidk-knowledge-curation/scripts/scidk-live status \
  --state-dir /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development
```

After login, open **Verify development runtime and backend**, or
`/admin/development-readiness`. Check:

- Profile `live-development-readonly`, recorded revision and active port 5010.
- Graph backend `Neo4j`, explicit database `neo4j`, reachability `connected`.
- The same connection fingerprint in readiness, Entities and the Maps selector.
- Management read `true`; entity/schema write `false`.
- Governed/Review/AI readiness reported separately, without inferred grants.

The readiness graph probe is a fixed bounded read returning only whether a node
exists. It never returns entity names, properties, credentials or private paths.
An ungranted administrator gets `configured_but_unauthorized` and `not_probed`,
not a fabricated connectivity result. Other states include not configured,
unreachable, authorized but empty, provenance unavailable and ready.

To stop **only this new instance**, then restart with the same `start` command:

```bash
/home/patch/Projects/scidk-knowledge-curation/scripts/scidk-live stop \
  --state-dir /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development
```

The stop command verifies the PID's module, state directory and process start
identity before signaling it. It never stops port 5001, Docker or other services.
Private startup diagnostics are in `.scidk-live-development/server.log`.

## Browse the actual development graph

1. Open Knowledge → **Entities & Labels**. The local schema catalog was imported
   read-only from the existing localhost:7687 development graph, not a fixture.
2. Select **Sample** or **SampleType** to see property types and relationships.
   Existing imported Samples have `uuid` / `_imported_stub` metadata; their
   scientific kind is shown when no display name exists. They are unreviewed
   legacy records, not accepted assertions or a newly generated dataset.
3. Use **Pull from Neo4j** in Instances, with **Show relationships** enabled. The
   browser uses the current authorized graph client. Expand a relationship badge
   and select a related entity. Incoming/outgoing edges depend on the chosen
   existing record; first-page order does not guarantee both directions.
4. Select **Open in Graph**. Maps identifies the **configured development primary**
   using the same fingerprint, database and backend as Entities. Use **Return to
   entity inspector** to return to that selected record.
5. Saved Maps support Save and Load in this separate private settings store.
   Loading saved query text does not execute it. Raw Run remains disabled.

The acceptance trace uses one bounded existing Sample with incoming and outgoing
relationships, independently located by a fixed read-only backend query and
matched to the GUI result. No test records were created. No Person/Investigator
records, scientific measurement contents or storage bytes were inspected.

The legacy `graph_backend=memory` scratch object remains for isolated Files/Sketch
infrastructure. **Management instance reads and the selected Maps entity use the
explicit live Neo4j connection.** The readiness probe and independent acceptance
comparison verify this distinction; no FakeGraph is attached.

## Provision or refresh a new development state

The current state is already provisioned. These are explicit administrator
commands for a **new, absent** state directory, not normal restart steps:

```bash
/home/patch/Projects/scidk-knowledge-curation/scripts/scidk-live init \
  --state-dir /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development \
  --source-env /home/patch/PycharmProjects/scidk/.env --database neo4j \
  --operator development-operator --port 5010 --confirm-development-source --grant-read
```

The two confirmation flags explicitly authorize this user's management read grant
for the exact URI/user/database/auth-mode fingerprint. Authentication and audit
use the existing AuthManager and ManagementPolicyStore. No admin bypass or
implicit startup grants are added. Credentials stay in the original environment
file; the runtime reads only the graph fields and checks for connection drift.
URI/database/user/auth-mode changes refuse startup rather than inheriting grants.
Password rotation for the same connection does not require copying credentials.

Import/refresh **schema metadata only** into the new private local catalog:

```bash
/home/patch/Projects/scidk-knowledge-curation/scripts/scidk-live sync-schema \
  --state-dir /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development
```

This reuses LabelService with fixed read-only queries, transaction timeouts and a
metadata result bound. It writes only the private schema catalog, not graph
records, constraints, indexes or operational settings. Restart does not require
this refresh. Multi-label nodes contribute definitions to their individual labels.

For grant revocation/regranting, trusted local administration uses
`ManagementPolicyStore(settings_db).grant(user_id, connection_key,
'graph_management_read', admin_id=administrator_id, allow=False/True)` on **this
private settings store**. Resolve IDs with its existing AuthManager and the
fingerprint in its private `runtime.json`. Each change is audited and checked on
subsequent requests; do not grant additional write or disclosure authority for
this activation. The live profile additionally rejects graph-mutating legacy and
Pipeline HTTP operations, even for an administrator.

## Readiness limits and safe fallback

Files/Datasets and Resources use new local stores. Existing institutional storage,
scans, annotations, source credentials and shared saved maps were not copied.
Their workspaces can be opened; importing operational state requires separate
approval. Interpreters remain the existing registry, with no automatic execution.

Governed Research and Review remain blocked until an administrator supplies an
existing ledger with valid graph binding, reconciled ontology/catalog, actual
Resource/evidence provenance and explicit human/reviewer grants. Use the existing
`operational_knowledge` assembly contract described in
[the operational startup guide](scidk-operational-startup.md); do not create false
receipts or convert graph presence to accepted assertions. That assembly is not
automatically attached to this read-only profile.

Ask SciDK is blocked in this state: no provider configuration, exact endpoint/model
approval, tool grant or authorized source context was imported. Before a real
question, an administrator must configure a local provider, approve that exact
destination/model, explicitly authorize source context and tool/profile use, and
verify these through `/admin/chat-readiness`. An AI smoke response/citation is
not claimed, and no model or paid Parley call was made.

If a live service is unavailable, use the status/readiness page to report the
specific blocker. The safe fallback is the actual read-only management workflow
or the existing local Files/Resources interfaces—not a replacement fixture graph.
Do not reseed, reset or restart existing servers to conceal a blocker.

## Reproduce browser acceptance

```bash
cd /home/patch/Projects/scidk-knowledge-curation
PYTHON_DOTENV_DISABLED=1 /home/patch/PycharmProjects/scidk/.venv/bin/python \
  scripts/verify_live_development.py \
  --state-dir /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development \
  --artifacts /home/patch/Projects/scidk-knowledge-curation/.scidk-live-development/acceptance-next
```

Use a new artifact directory each run. The script connects to the **already
running operator instance**, uses its real login form and services, and refuses
an unexpected runtime profile or connection fingerprint. Cookie-bearing traces
remain private. Only reviewed non-sensitive screenshot candidates are committed;
visual baseline approval remains pending.
