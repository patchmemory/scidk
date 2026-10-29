# Prompt 13 — Knowledge workspace integration

The follow-up `codex_prompt_13_01.txt` approved the conservative boundary below.
The implementation and final validation are documented after the preserved initial
audit. The earlier stop is resolved; no new disclosure policy was introduced.

## Initial activation audit (historical)

Status: preliminary activation verification complete; Knowledge implementation
has not started. Prompt 13 section 13 says: “Stop if a material security or
ontology-policy conflict requires approval.” The decision below is pending.

## Worktree and running service

Verified on ki-ed3g.mit.edu:

- Worktree: `/home/patch/Projects/scidk-knowledge-curation`.
- Branch: `design/knowledge-curation-20261029`.
- HEAD: `f4087df` (Prompt 12).
- Initial changes: only untracked prompts 01–13 and the consolidated vision/demo
  inputs. These were preserved. No runtime code was changed during this audit.
- Port 5001 binds `127.0.0.1`; listener processes were development-server parent
  PID 412685 and serving child PID 412753 at inspection time.
- Both process working directories resolve to this permanent worktree; the
  executable is this worktree's `.venv/bin/scidk-serve` / Python 3.13 environment.
  Import inspection with that interpreter also resolves `scidk.app` here.

There is no evidence that port 5001 uses the wrong checkout. Other SciDK processes
exist on the host; the listening socket identifies the one relevant to this port.
No process was stopped, restarted or reconfigured.

## Why the legacy GUI appears

`scidk/web/routes/ui.py` checks
`current_app.config.get('SCIDK_GUI_V3_ENABLED') is True`. This requires the actual
Python boolean in Flask application configuration. `scidk/app.py:create_app()`
does not read this flag from the environment, and `main()` calls the factory
without applying a GUI override. Setting a same-named shell variable therefore
does not activate the shell.

Read-only checks against the actual service:

| Route | HTTP status |
| --- | --- |
| `/` | 200, legacy Settings interface |
| `/overview`, `/knowledge`, `/review` | 404 |
| `/map`, `/entities`, `/datasets`, `/settings` | 200 |

For a development-only launch, first stop the existing development server using
the terminal or supervisor that owns it, then run the following from the permanent
worktree. Do not run a second listener on the occupied port.

```sh
cd /home/patch/Projects/scidk-knowledge-curation
.venv/bin/python -c 'from scidk.app import create_app; app = create_app(); app.config["SCIDK_GUI_V3_ENABLED"] = True; app.run(host="127.0.0.1", port=5001, debug=False)'
```

Visit `/overview` through the existing tunnel. This changes only the newly created
process's configuration. Overview conversation and dataset sharing retain their
separate default-off flags and authorization prerequisites. No production default,
environment file, service unit or global configuration was changed. The startup
command is provided for the existing development configuration, not executed by
this audit; normal app startup can initialize its configured services/storage.

## Browser verification

Used the existing disconnected Prompt 10 harness, which sets the strict GUI flag
on a disposable app and blocks external requests. Captured activated Overview at
1440×900, 1280×800 and 1024×768. Visually inspected the largest screenshot: all six
destinations are present—Overview, Files & Datasets, Resources, Knowledge, Review,
Settings. Disabled chat is expected because its separate feature flag is off.

Artifacts:

- `/tmp/scidk-prompt13-activation/overview-1440x900.png`
- `/tmp/scidk-prompt13-activation/overview-1280x800.png`
- `/tmp/scidk-prompt13-activation/overview-1024x768.png`

Command:

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui/test_visuals.py -k overview --gui-record-candidates --gui-artifacts /tmp/scidk-prompt13-activation -q -o addopts=''
```

Result: **3 passed, 19 deselected**, 5.58 seconds. This is a capture-only run, not
visual baseline acceptance or a Knowledge implementation test. No baseline was
overwritten. Chrome ran outside the sandbox with approval for local socket access.

## Material boundary requiring clarification

Prompt 13 requires both reuse of the full legacy explorer/Entities/Canvas and
Stage 3 authorization on all new Knowledge retrieval. The current human-facing
interfaces and the Stage 3–6 tool boundary provide different capabilities:

- `map.html` issues arbitrary requests to `/api/graph/query` and reads global
  schema/instances. `api_canvas.py:search_nodes` reads raw graph properties and
  internal Neo4j identifiers; these are not accepted-fact serializers.
- `/entities` uses the existing Labels/Links interfaces, including their existing
  schema configuration/actions. Embedding them does not make their reads scoped.
- `api_canvas.py:commit_canvas` authorizes the legacy admin role and writes
  declarations directly to Neo4j. It does not create ledger evidence, human
  curation decisions or applied receipts. Hiding the button alone does not change
  that backend boundary.
- Stage 6's “GUI backend-readiness inventory” explicitly lists the absence of
  source-scoped Research search, pagination and neighbor-expansion templates.
  It says legacy arbitrary SQL/Cypher cannot supply them. The same report forbids
  repurposing the direct Canvas commit path for Sketch-to-curation.
- Existing Stage 3 policy resolves a destination even for the current chat-based
  human adapter. Using it unchanged for human graph discovery would require an
  approved stored provider endpoint/model despite making no AI request. Defining
  destination-independent human disclosure would change the policy contract.

These are backend authority differences, not merely presentation controls. A
working legacy page is not evidence that its records are currently accepted or
permitted by Stage 3. No new route has exposed these interfaces as scoped knowledge.

Proposed decision for the new workspace: keep legacy routes and saved records
unchanged and explicitly separate, reuse the existing graph/Canvas components,
add bounded ledger-authorized Research discovery/expansion adapters, retain the
existing provider-bound Stage 3 authorization requirement initially, and omit all
direct-commit/schema-mutation operations from the new workspace. Sketch promotion
and unsupported history/enrichment operations would remain explicitly unavailable
until their typed adapters exist. This avoids changing ontology or disclosure
policy, but must be agreed as the interpretation of “preserve existing entity
actions” within the new restricted workspace.

The alternative—making all existing entity/editor operations available under a
new human-specific disclosure policy—requires a separate security-contract design
and exceeds a presentation-only integration. No such policy has been introduced.

No Knowledge feature tests or backend regressions are claimed, and no
implementation commit was created. The only new workspace file from this audit
is this report; the screenshots are disposable local artifacts.

## Implementation after follow-up approval

Built on `f4087df` in the permanent development worktree. The live development
server was checked again: `/overview` returned 200 with all six navigation links.
The server was not restarted or reconfigured by this work.

### Activation

The Knowledge workspace appears at `/knowledge` when the existing strict Flask
configuration `SCIDK_GUI_V3_ENABLED = True` is set. It can optionally be disabled
within that experimental shell with `SCIDK_KNOWLEDGE_WORKSPACE_ENABLED = False`.
With the GUI flag absent/false, the new page and adapters remain unavailable.
No global GUI, security, ontology or production settings were enabled.

Retrieval requires the existing `SCIDK_KNOWLEDGE_CONTEXT_ENABLED = True`, trusted
`knowledge_services` assembly, named unlocked session, Overview tool grants,
Resource classifications/access, evidence metadata grants, sharing policy and
approved actual stored provider endpoint/model. A provider binding remains
necessary for human reads, as explicitly approved; these adapters make no model
requests. The GUI flag alone does not initialize or authorize knowledge services.
Unconfigured development hosts show an explicit refusal/unavailable state.

### Shared views and reuse

Domain and view selectors are independent: Research / Ontology / System × Graph /
Entities / Sketch. The workspace uses the existing `SciDKGraph` rendering/style
utilities and the same Cytoscape 3.27.0 release used by Maps. That release and its
MIT license are vendored for this page so new workflows do not depend on a CDN.
Legacy asset URLs are unchanged; the known Settings CDN issue is not fixed here.

Graph supports permitted entity search, node/edge selection, typed one-hop
Research expansion, System/Ontology traversal, relationship filtering, force /
circle / grid / breadth-first layouts, node coloring, fit, and saving/reopening
positions and node colors. Entities lists the same authorized records with
selection into the shared inspector and bounded Research pagination. Full legacy
Maps, Entities, Labels/Links, Results and named saved records remain accessible
through an explicitly separate legacy-interface section. They are not embedded
as though their raw results were governed accepted knowledge.

Maps Canvas provisional-node creation and selection removal were extracted into
`canvas_editor.js`; both the original Maps template and Knowledge use these
primitives. Existing undo behavior remains available through the helper's optional
undo manager. Knowledge also uses shared provisional edge construction, existing
Cytoscape manipulation, and the original `CanvasService` session storage. There
is no second Canvas database, new graph-write service or canonical editor.

Sketch supports provisional nodes/relationships, current stable knowledge-node
references, freeform notes, selection/removal and manual save/reopen. Reference
metadata is not cached in saved snapshots. Source identifiers/catalog selectors
and current source/version details remain available through reauthorized reference
inspection. User-authored exploratory ontology definitions and workflow ideas
remain drafts; no ontology or code/document/config file is changed.

The four enrichment markers—unresolved, suggested investigation, proposed
assertion, pending human review—are explicitly labeled **planning intent**, not
backend execution states. Investigate, Submit proposal and Commit to graph remain
disabled. No fabricated investigation, assertion submission or review occurs.

### Backend authority and bounds

New POST `/api/knowledge/<domain>/<operation>` adapters accept only fixed
operations. They bind a named authenticated human and server-selected Overview
profile; API tokens, identity/profile/provider overrides and unsupported graph
writes refuse. No raw Neo4j query, property read, internal graph ID or arbitrary
Cypher route was added. Responses use `Cache-Control: no-store` and generic
refusals without hidden record identifiers/counts or raw backend exceptions.

Research discovery is bounded to 500 candidate node facts. Search predicates
operate only on fields already released by `FactDisclosure`, never on candidate
identity claims or hidden properties. Returned pages contain at most 25 permitted
records; offsets describe only that authorized result set. Every selected node,
property, relationship and both endpoints use receipt-backed current support in
one read-only ledger/policy snapshot. Evidence citations require their existing
metadata grants. Proposed/rejected/superseded/unapplied/unclassified records and
disallowed fields do not become search previews. Neighbor discovery is bounded
to 128 candidate incident relationships; property discovery to 128 candidates
per node, with a 2 MiB serialized-support budget. Exceeded bounds refuse the whole
operation. Disallowed candidates are omitted without withholding counts.

System and Ontology call the existing Stage 5 tools over Stage 4 projections.
Workflow references, source paths/hashes/revisions, endpoint/type/property/identity
definitions, registered external catalog selections, freshness warnings and
authorized catalog blockers retain their original contracts. A conflicted catalog
has no authoritative label definitions. No YAML/SQLite winner is invented.

The inspector reauthorizes selection and renders data as text. Research support
is labeled accepted/applied, with epistemic status kept separately. Projections
are labeled generated source-backed context; drafts are labeled user-authored.
Research support omits raw Source Resource IDs and source-record payloads;
projection source bindings appear only where ContextService authorizes them.
Unrestricted review history remains unavailable. Context switching clears old
records, inspector data and drafts; request-version checks discard stale replies.

### Persistence, layouts and context continuity

Private storage is keyed by the server-authenticated user ID and existing
`CanvasService` contexts `knowledge:<domain>:sketch|graph|layout`. Legacy default
and `pipeline_source:*` contexts and named SavedMapsService records are untouched.
There is one current private graph view and draft per domain, rather than a new
named-map library. Draft/session JSON is bounded to 128 KiB and 128 elements.
Graph views save only stable references, positions and simple colors. System and
Ontology references also pin the source projection version and registered catalog;
a changed version refuses reopen rather than silently rebasing the draft.
References are reauthorized on save and reopen; revocation refuses the saved view without
disclosing retained metadata. User-owned text is never treated as accepted facts.

Single, Split and Three panes retain the chosen view; saved layout/view preference
is per user/domain. Narrow screens stack panes. ResizeObserver recalculates
Cytoscape dimensions when panes resize, including vertical canvas resizing.
Positions are restored after graph reauthorization; full docking is deferred.

URLs preserve the selected domain/view and stable entity ID. Dataset inspectors
with a stable curation identity link to the corresponding Research expansion.
Internal Neo4j element IDs and display names are not used as authority. Graph and
Entities share selection; nodes can be referenced in Sketch; Review receives the
selected stable ID. Files and legacy links remain available. Automatic Files
reselection/drive-path restoration across a full page reload is still a missing
adapter; this pass does not silently reinterpret a legacy dataset as curated.

### Remaining limitations

- Provider-bound human authorization and operational service wiring/grants remain
  explicit prerequisites. No production bootstrap or ontology reconciliation runs.
- Research discovery is intentionally bounded and may refuse large candidate sets;
  indexed large-ledger search is future work, not a claim of production scale.
- Sketch-to-curation translation, evidence capture, proposal submission, sharing,
  review history and actual enrichment remain unavailable in the new workspace.
- Existing named legacy maps/drafts remain in the legacy interface. They are not
  automatically imported as accepted facts or rewritten into new contexts.
- Advanced legacy query editing, schema mutation, direct adoption, edgehandles and
  undo/redo UI remain in Maps; the governed draft subset uses shared Canvas
  primitives without exposing their ungoverned routes. No capability is removed
  from the legacy interface.
- Offline draft files/text cannot enforce revocation after disclosure. Reopen and
  new retrieval are reauthorized; previously displayed information cannot be
  recalled from a human browser. Live production Neo4j/model behavior is not tested.
- Human UX approval and approval of all new screenshot candidates remain pending.

### Validation

Focused new backend adapters: 14 passed before adding the source-freshness case.
Focused integrated browser workflows: 4 passed before adding cross-domain Sketch
and responsive coverage. These browser tests use real session authentication,
disclosure policy, ledger/review and CanvasService over a disposable loopback app;
only source data and transactional graph application are synthetic. Outside-origin
requests and unexpected browser errors fail through the existing Prompt 10 harness.

The original Prompt 10/12 visual fixture explicitly leaves the new workspace off,
preserving its frozen references. New Knowledge screenshots are separate
unapproved candidates; no visual reference is overwritten.

Final backend verification:

- Relevant backend/security/compatibility regression: **258 passed** in 150.85s.
  This ran before the final projection-version pin and subsequent UI refinements.
- Focused adapter suite after the projection-version pin: **16 passed** in 19.50s.
  Includes current-support freshness, denied discovery/inspection/expansion,
  private persistence, and refusing references after projection version changes.

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e tests/security tests/agent_integration tests/pipeline/test_canvas_context.py tests/test_saved_maps_service.py tests/test_canvas_export_auth.py tests/test_gui_slice.py tests/test_nih_dms_plan.py -q -o addopts=''
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/knowledge_e2e/test_workspace.py -q -o addopts=''
```

Browser regression: **36 passed, 1 xfailed** in 79.64s, before the final
projection-version pin. The expected failure remains GUI-004 (Settings CDN
dependency). All 21 existing visual baselines passed. Artifacts:
`/tmp/scidk-prompt13-browser-final`.

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui -q -o addopts='' --gui-artifacts /tmp/scidk-prompt13-browser-final
```

JavaScript syntax checks cover `knowledge_workspace.js`, `canvas_editor.js` and
`gui_slice.js`; `git diff --check` verifies whitespace. No baseline acceptance,
live-server restart, production configuration change or Prompt 14 work occurred.

Final focused browser verification after the version-pin implementation and final
UI change: **7 passed** in 47.70s. This includes adding System/Ontology references
to Sketch, reopening saved graphs, and reopening private sketches with preserved
projection versions, alongside Research authorization/revocation workflows.
The first extended run caught a test attempting to click a hidden Sketch control;
the corrected test explicitly switches views before interacting with it.

```sh
/home/patch/PycharmProjects/scidk/.venv/bin/python -m pytest tests/gui/test_knowledge_workspace.py -q -o addopts='' --gui-artifacts /tmp/scidk-prompt13-knowledge-pinned-corrected
```

Final screenshots/traces/request logs are in
`/tmp/scidk-prompt13-knowledge-pinned-corrected`. New screenshot candidates remain
unapproved. The implementation commit contains this report; its hash is reported
in the completion message rather than embedded recursively in its own contents.
