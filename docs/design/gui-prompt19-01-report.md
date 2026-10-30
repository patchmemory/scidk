# Prompt 19.01: live runtime acceptance

The actual development graph-management gate passed against the operator-accessible
instance on **ki-ed3g, 127.0.0.1:5010**. Real login, existing labels, properties,
incoming/outgoing relationships, related-entity navigation, Maps and saved views
were exercised through Chromium against that running server. No fixture server,
FakeGraph, graph seeding, graph writes or model calls satisfied this gate.

Operator reproduction from ki-marvin is still to be confirmed by the operator;
the SSH client and the operator's existing browser tab were not observable here.
Governed Knowledge, Review and Ask remain blocked for the prerequisites below.
This is not a claim that all workspaces are fully integrated.

## Runtime inventory and discrepancy

| Item | Finding |
| --- | --- |
| Worktree / branch | `/home/patch/Projects/scidk-knowledge-curation`, `design/knowledge-curation-20261029` |
| Initial HEAD | `cfaea4a`, after Prompt 18.02 documentation |
| Existing app | PID **1252399**, loopback **5001**, started Oct 29 20:49:20; preserved |
| Existing launch | Current worktree, shared virtualenv Python, normal `create_app` / `app.run`; no explicit development assembly hook |
| Existing loaded revision | Not recorded; process predates the Prompt 18.02 commits. Exact loaded revision cannot be reconstructed safely |
| Initial free ports | 5002, 5003 and 5010; selected 5010 |
| New canonical app | PID **1314469**, loopback **5010**, profile `live-development-readonly` |
| Recorded startup | `b650f4be9a18c899dd022526bf2087a7de9da7f5`, `startup_dirty=false` |
| Source fingerprint | `d021a4f06bd8c7b5cbe5cf22d4447155062f86c1926129132c4ddbdf6cc262fe` |
| Python | Shared `/home/patch/PycharmProjects/scidk/.venv/bin/python`, Python 3.12.12; executable resolves to `/usr/bin/python3.12` |
| Private state | `.scidk-live-development`, mode 0700, ignored by Git; generated credential/config files mode 0600 |
| Authentication | New private settings store, named `development-operator`; explicit audited management-read grant only |
| Graph | Existing development `scidk-neo4j`, `bolt://localhost:7687`, explicit database `neo4j`, basic authentication |
| Connection identifier | `a90e99e182a7ec46e56cb8e0290662b7e41466d8ace717b5df2950bbd88c4635` |

The shared virtualenv's editable install resolves to the older
`/home/patch/PycharmProjects/scidk` checkout when launched outside this worktree.
The new wrapper pins the repository and cleans inherited configuration. The old
5001 process did not have recorded development assembly. Read-only inspection of
both existing settings stores found named users, but no management-grant table,
saved Neo4j profiles or persisted primary configuration. Dotenv files supplied a
development connection; initial `/proc` environment alone does not establish
configuration subsequently loaded by dotenv. These observations explain why
disposable GUI screenshots could not establish what the operator actually saw.

Source classification reused the prior explicit read-only authorization. Docker
inspection verified `scidk-neo4j` ownership by the earlier checkout's development
Compose project and its development data/log/import/plugin mounts. Existing
Neo4j, concept, chat and throwaway services were untouched. No database indexes,
constraints, records or operational settings were changed.

## Changes

- Added explicit `init`, metadata-only `sync-schema`, `start`, `status`, `stop`
  and `serve` commands using the existing `dev_gui.build_app` / `create_app`.
  Startup attaches graph configuration after isolated factory initialization,
  avoiding graph startup writes. It does not seed, refresh schema or grant access.
- Provisioned a named operator and audited `graph_management_read` grant for
  this exact connection in a new private store. Administrator status grants no
  graph authority. Entity/schema writes remain false; the live profile also
  rejects legacy/Pipeline mutation requests.
- Fixed Maps using the separate saved-profile registry while Entities used the
  configured primary. Both now identify the same permission-checked primary
  connection. No fallback graph or unrestricted Cypher was enabled.
- Corrected schema import for Neo4j multi-label nodes: individual `nodeLabels`
  become individual definitions, rather than an invalid combined label name.
  Imported 23 existing definitions into the private catalog. Two malformed local
  aliases from the initial import were removed only from that new catalog.
- Added named-administrator readiness diagnostics with redacted startup identity,
  reachability, exact grants and separate service statuses. The graph probe is
  fixed and bounded; an ungranted administrator cannot probe the graph.

The isolated infrastructure still has a scratch `graph_backend=memory` object.
Management reads and selected Maps nodes use the explicit existing Neo4j client;
an independent direct read matched the entity returned by the actual HTTP API.
No FakeGraph or governed-service stand-in is attached.

## Browser acceptance and readiness

Evidence: [redacted acceptance record](gui-prompt19-01-candidates/acceptance.json).
Chromium **152.0.7977.82**, real login form, actual already-running port-5010
server. The fixed backend read selected one existing Sample whose properties were
limited to `uuid` / `_imported_stub`, with only Sample/SampleType neighbors and
both relationship directions. These are existing imported metadata stubs, not
new fixtures or verified scientific assertions. No Person/Investigator records,
measurement contents or file bytes were inspected.

| Capability | Result | Evidence / exact limitation |
| --- | --- | --- |
| Named login | PASS | Actual generated operator account, normal login form |
| Labels and property types | PASS | Existing Sample schema, `uuid`, `OF_TYPE`; [capture](gui-prompt19-01-candidates/live-labels-1440x900.png) |
| Instances / properties / relationships | PASS | Existing Sample, expanded incoming and outgoing edges; [capture](gui-prompt19-01-candidates/live-entities-1440x900.png) |
| Related entity selection | PASS | SampleType inspector at [1440](gui-prompt19-01-candidates/live-inspector-1440x900.png) and [1024](gui-prompt19-01-candidates/live-inspector-1024x768.png) |
| Maps and return | PASS | Actual selected node, matching primary identifier; [1440](gui-prompt19-01-candidates/live-maps-1440x900.png), [1024](gui-prompt19-01-candidates/live-maps-1024x768.png) |
| Saved views | PASS | Save/load one new private metadata view; existing shared views untouched |
| Relationship discovery | PASS | Real backend discovery, including OF_TYPE; [capture](gui-prompt19-01-candidates/live-relationships.png) |
| Backend / authorization | PASS | Independent entity match, Neo4j connected, read true, writes false; [readiness](gui-prompt19-01-candidates/live-readiness.png); raw-query POST and entity PATCH returned 403 |
| Files & Datasets | PARTIAL | [Workspace available](gui-prompt19-01-candidates/live-files_datasets.png); new local store empty; actual storage browsing/annotations not claimed |
| Resources | PARTIAL | [Workspace available](gui-prompt19-01-candidates/live-resources.png); authorized but empty; no existing source state copied |
| Knowledge Graph / Entities / Sketch | BLOCKED | All three tabs visited; [capture](gui-prompt19-01-candidates/live-knowledge.png); existing trusted ledger, bound catalog, Resource/evidence provenance and explicit human grants unavailable |
| Review | BLOCKED | [Route inspected](gui-prompt19-01-candidates/live-review.png); governed service/source authority and reviewer grants absent |
| Ask SciDK | BLOCKED | [Overview inspected](gui-prompt19-01-candidates/live-ask.png); provider, exact destination/model approval, tool grant and authorized source context absent; no question/response/citation smoke claimed |

Existing interpreters remain available through the existing registry; none were
executed. Files/Resources availability does not establish imported institutional
state. Governed assembly must use the existing operational service contract with
real provenance; graph presence does not create Resource or evidence authority.
An administrator must configure and approve the exact local model destination,
context and tool/profile before an Ask smoke test. No paid Parley was invoked.

The private trace is
`.scidk-live-development/acceptance-6/live-private-trace.zip`. It contains session
cookies and stays in the private directory. Only inspected non-sensitive PNGs
and the redacted JSON were exported. Screenshots are candidates for human review;
no visual baseline was promoted. At 1024 pixels the existing three-column editor
is cramped; captured rows remain usable, and no GUI redesign was attempted.

Early live verifier attempts exposed sample-order assumptions, the editable-import
path, an empty saved-map list visibility assumption and the real relationship
discovery delay. The verifier was corrected to use a bounded eligible example,
pin imports, test meaningful controls and await the backend. Later captures wait
for layout and scroll the inspector into view. No synthetic fallback was used.

## Verification

Focused security/runtime checks: **22 passed** (`test_development_runtime`,
`test_graph_management`, `test_dev_gui`), including grant isolation, drift,
redaction, PID ownership, same-origin administration and live-profile write denial.

Relevant regression: **166 passed, 2 skipped in 212.88 seconds**. The run covers `tests/security`,
`tests/test_dev_gui.py`, `tests/pipeline/test_api_schema.py` and `tests/gui`, with
candidate recording. It began only after the real graph gate passed. Its fixture
browser results supplement the live acceptance above. The two skipped management
fixture cases require a separately supplied disposable Neo4j URI; the real
development graph was verified by the independent live acceptance instead.

Implementation commits:

- `12c51e25f3bd83142c42bb231856cd6fee22912f`: launcher, readiness, Maps fix,
  security tests and initial live verifier.
- `b650f4be9a18c899dd022526bf2087a7de9da7f5`: multi-label schema fix and saved views;
  this is the recorded running application revision.
- The subsequent evidence/handoff commit adds only the wrapper, verifier and
  documentation/artifacts; application source and its running fingerprint remain
  unchanged. Find that commit with `git log -- docs/design/gui-prompt19-01-report.md`.

## Operator handoff

Follow the [startup runbook](../demo/scidk-live-development-runbook.md) for exact
start/status/stop, private login retrieval, grant provisioning and restart steps.
From ki-marvin:

```bash
ssh -N -L 5010:127.0.0.1:5010 patch@ki-ed3g.mit.edu
```

Open **http://127.0.0.1:5010/login**. Verify profile, recorded revision, port and
connection identifier in **Verify development runtime and backend**, then follow
the existing Sample → related SampleType → Maps → inspector workflow.
The port-5010 runtime is left running. Port 5001 and all pre-existing services are
preserved. No dataset-generator work was started.
