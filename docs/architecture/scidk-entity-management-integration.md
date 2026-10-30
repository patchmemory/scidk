# Prompt 18.02 entity-management integration

Status: implemented under the explicit authorization correction in `scidk_prompt_18_02_b.txt`.
The original preflight findings below explain why the legacy login boundary was replaced.

## Original capability inventory (preflight)

| Capability | Existing route / component | Read/write and existing authority | Dependency / actual verification | Proposed Knowledge placement |
|---|---|---|---|---|
| Label list and definitions | `/entities`, `/labels`, `labels.html`, `api_labels.py`, `LabelService` | Shared SQLite catalog reads; general login only when enabled | Real disposable service read verified; operational catalog not accessed | First-class Labels navigation |
| Label/property/schema editor | `/api/labels` POST, `/api/labels/<name>` DELETE; same template/service | Shared schema writes; no separate per-user management grant | Disposable ordinary-user create/delete verified; not appropriate for governed multiuser access | Existing editor, after explicit schema-management authority |
| Entity-instance table and properties | `/api/labels/<name>/instances`; `LabelService.get_label_instances` | Returns raw node properties; general login, no Resource/property policy | Operational Neo4j required; source profile can fall back to primary; not exercised against operational records in this pass | Existing Labels instance table |
| Incoming/outgoing relationships | Same endpoint with `with_relationships=true`; instance inspector | Raw relationship properties and neighboring labels/element IDs; no endpoint/evidence permission checks | Existing service query supports both directions; actual interaction remains unverified | Reuse existing inspector, with authorized graph context |
| Inline entity property editing | PATCH/PUT `/api/labels/<name>/instances/<id>` | Direct legacy graph mutation; no role or per-source write grant in route | Neo4j required; no operational edits performed | Existing inline editor after write authority; never curation acceptance |
| Schema synchronization and transfer | `/api/labels/<name>/push`, pull/batch routes, transfer-to-primary | Schema/data writes; general login only in inspected routes | Multiple source/target profiles; not executed | Existing advanced controls; separately authorize every destination |
| Link/relationship definitions | `/entities?tab=relationships`, `/links`, `links.html`, links JS, `LinkService`, `api_links.py`, `api_links_v2.py` | Shared definition CRUD, graph discovery/preview/execution; not uniformly scoped | Actual operational interactions not verified in this pass | First-class Relationships / Links navigation |
| Raw graph query | `/api/neo4j/query` in `api_links.py` | Caller-supplied Cypher to selected configured profile through execute_read; no source-grant check | Not executed; read transaction routing alone is not disclosure authority | Do not enable through governed APIs or management grant by implication |
| Map visualization | `/map`, `map.html`, `api_graph.py`, Cytoscape | Legacy schema/graph access; not Stage 3 serialization | Route implementation inspected; no browser or live-data acceptance in this pass | First-class Maps navigation only after management boundary resolution |
| Saved maps | `/api/maps/saved`, `SavedMapsService` | Shared settings-store list/save/delete routes do not pass a user owner | Existing implementation inspected; no isolation claim | Existing saved-view controls with explicit shared-store authority |
| Canvas | `/api/canvas/*`, `CanvasService` | Some session ownership exists; graph search/expand uses direct graph; commit has admin-role check | Role-only commit does not establish Resource authority | Reuse existing Canvas; preserve per-user drafts; direct writes separately granted |
| Governed records | `/api/knowledge/research/*`, `knowledge_workspace.py` | Named same-origin human purpose + Resource/evidence/property checks; accepted/applied receipts or bounded source-bound legacy snapshot | Prompt 18 verification documented separately | Distinct Governed records view; no substitution for management |
| Governed Review / AI | ReviewService and existing AI adapters | Review purpose/reviewer authority vs separate AI disclosure authority | Existing Prompt 17–18 tests, no change here | Preserve distinct workflows |

Labels and Links templates declare overlapping global JavaScript names. Reuse
their current full-page navigation rather than combining their scripts or using
an iframe. The current `/entities` route already does this through
`_entities_tabs.html`. Preserve the redesigned shell and add explicit Knowledge
return context. Scientific names/properties should be primary display labels;
Neo4j element IDs may serve only transient legacy lookup, never external identity.

## Historical unsafe boundary (corrected)

Before this change, `web/auth_middleware.py:check_auth` authenticated sessions but did not authorize
Labels/Links operations by Resource, purpose, property or graph-management grant.
`api_labels.py` routes call the existing services directly. There was no same-origin check
in those routes. API tokens are restricted by a separate middleware, but
that does not fix ordinary cookie-session authority.

A standalone disposable Flask application used the **actual AuthManager,
authentication middleware, Labels blueprint, LabelService and migrated SQLite
schema**, without importing the production factory or creating a Neo4j client.
An ordinary `role=user` with no human-purpose, Resource, evidence or reviewer
grants could:

- POST a new label with an explicit foreign Origin header: **200**.
- GET that shared schema definition: **200**.
- DELETE it: **200**.
- An anonymous GET correctly returned **401**.

The preflight cross-origin probe proved the server lacked an Origin guard; it does not claim
that browser SameSite behavior permits every cross-site exploit. The mutation
occurred only in disposable `/tmp` SQLite state, which was cleaned up. No
operational graph or catalog was modified. Entity graph edits were identified by
code inspection, not executed.

## Approved authorization contract

Introduce explicit, audited, revocable management authority separate from
`research_browse`, Review and AI disclosure. Bind each grant to a configured
development graph connection/database and distinguish read, graph write, and
shared schema/link-definition write privileges. Require named unlocked same-origin
cookie sessions. Do not infer grants from admin role, existing login, AI approval
or accepted assertions. Cross-profile reads, transfer destinations and graph
expansion must each be authorized; missing profile resolution must not silently
fall back to a different graph. Shared saved-map/catalog access must be covered
explicitly. Raw query access is not implicitly included.

Enforce the approved boundary on the **existing APIs**, including direct calls;
checking only Knowledge links cannot secure the underlying services. Reuse their
operations and validation after authorization, and retain destructive confirmation.
The first-class navigation remains unavailable for users without the applicable
grant. The approved correction changes legacy single-operator/no-auth behavior:
management APIs now deny by default. Policy initialization and grants require
explicit trusted local administration.

This resolves management authority without fabricating governed provenance.
Prompt 18's missing operational Resource/evidence/source-identity contract still
blocks disclosure through governed records and AI retrieval.


## Implemented capabilities and evidence

The table above records the original boundary. The following table records the
integrated boundary; it supersedes the proposed placement and unverified status.
All management operations require `graph_management_read` for the exact approved
development connection in addition to any write permission listed below.

| Capability | Reused implementation | Integrated behavior / authority | Verification |
|---|---|---|---|
| Labels and entity instances | `/entities?tab=entities`, `/labels`, `labels.html`, `LabelService`, `/api/labels/*` | First-class Research tools navigation; schema and instance reads | Real SQLite and synthetic Neo4j; both browser sizes |
| Properties and property types | Original label editor and instance table | First-class Properties link; inline property edits require `graph_entity_write` | Actual PATCH, refresh and persisted value in Neo4j |
| Schema definition CRUD | Existing Labels editor/API | `graph_schema_write`; deletes, batch deletes and removal of existing schema fields require confirmation | Positive/negative real-service tests |
| Relationship exploration | Original instance relationship query/table | Incoming/outgoing types, scientific neighbor names, related entity selection | Both directions and neighbor navigation exercised in browser |
| Relationship definitions | `/entities?tab=relationships`, `/links`, existing Links JS/service/API | Shared definitions require schema-write; discovery no longer silently promotes definitions | Actual graph discovery and relationship list in browser |
| Graph selection and return | `/map`, original Cytoscape workspace and Canvas node addition | Re-fetch exact selected instance; scientific name; return to original inspector | Browser checks node data and return context |
| Saved maps and Canvas drafts | Existing `/api/maps/saved`, `/api/canvas/session` | Management-read for view state; saved maps remain shared; delete requires schema-write and confirmation | Saved map creation/list; source Canvas cleanup/isolation tests |
| Raw Cypher | Existing query routes | Denied; grants never authorize arbitrary Cypher; saved query text is inert view metadata | Negative boundary test; Run control disabled |
| Unsafe bulk/background operations | Pull-all/batch pull, push-all, transfer, link execute/run, discovered import, CSV import, enrich | Denied until worker authority and destination scoping are implemented | Explicit fail-closed API checks |
| Cross-profile operations | Existing Neo4jClient and profile loader | Actual target checked again before connect/session/write; absent profile cannot fall back; profile-ignoring overwrite/push denied | Actual mismatched client rejected before network |
| Governed records, Review and AI | Existing Prompt 17–18 services | Separate Resource/evidence/purpose/reviewer/AI grants; management never supplies them | Relevant backend and GUI regression suites |

No new entity-creation or unrestricted relationship mutation API was added.
Existing synchronous property editing and shared definition editing are retained.
Legacy preview with external/API sources or free-form WHERE clauses is denied.
Some legacy advanced buttons remain visible and return a refusal; visibility
never substitutes for API authorization. Arbitrary existing deployments and
advanced graph import/execution are not certified by this recovery.

## Provisioning an isolated development instance

Use `scidk.dev_gui` with a fresh state directory and a named administrator, as
specified in `docs/demo/scidk-operational-startup.md`. For management-only runtime
assembly, pass `--configure scidk.services.graph_management_policy:configure` and
set `SCIDK_GRAPH_MANAGEMENT_MANIFEST` to an administrator-owned JSON file:

```json
{"development":true,"uri":"bolt://127.0.0.1:32768","user":null,"database":"neo4j","auth_mode":"none"}
```

That localhost port is an example disposable graph, never a production default.
For basic auth, specify `user`, `auth_mode:"basic"`, and `password_env` naming a
credential environment variable. The database must be explicit. The hook sets
only this isolated app's runtime connection and development allowlist; it does
not open a driver, migrate a policy store, grant permissions or backfill graphs.
Do not apply it to operational research configuration.

In trusted local administration, use the existing auth store and named user IDs:

```python
from scidk.services.graph_management_policy import ManagementPolicyStore, connection_key
policy = ManagementPolicyStore(settings_db)
policy.initialize(admin_id=administrator_id)
target = connection_key(uri, user, database, auth_mode)
policy.grant(researcher_id, target, 'graph_management_read', admin_id=administrator_id)
# Only when explicitly authorized for this user and this connection:
policy.grant(researcher_id, target, 'graph_entity_write', admin_id=administrator_id)
policy.grant(researcher_id, target, 'graph_schema_write', admin_id=administrator_id)
# Revocation uses the same method with allow=False.
```

Grants reuse `auth_users`, administrator verification, SQLite transactions and
policy audit events. There is no second identity system or automatic admin grant.
Exact URI spelling, user, database and auth mode determine the connection hash;
a different alias/database does not inherit access. Missing policy/allowlist or
invalid authentication denies access. Named cookie sessions must be unlocked,
enabled and same-origin; no-auth mode, header/session/API tokens and foreign
Origin or cross-site requests fail closed. Checks are registered globally and on
legacy blueprints, and actual Neo4jClient use rechecks connection authority.
Shared destructive requests require `X-SciDK-Confirm: destructive-shared-change`
as well as schema-write permission. The original confirmation UI supplies it.

## Data and provenance limits

All new graph interaction evidence is from a newly created disposable Neo4j
container containing fictional specimens/images, not operational research data.
No operational data/configuration was accessed or changed for this implementation.
Prior Prompt 18 development-source inspection does not establish Resource,
evidence, property, ontology-version or stable source-identity bindings. Those
blockers remain; management records are never relabeled as accepted assertions.
Neo4j element IDs are transient inspector lookup context, never governed identity.
Browser candidates require human review and do not update approved baselines.

Implementation revision: `3b3d9d1d60bf58cbf9a5f0ff84772b478b295489`. Verification counts and browser evidence
are recorded in `docs/design/gui-prompt18-02-report.md`.
