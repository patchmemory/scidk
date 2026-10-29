# GUI v3.1 first slice — codex_prompt_09.txt

Implemented on `design/knowledge-curation-20261029` from Stage 6 `0896c5a`.
The accompanying Markdown handoff and static HTML reference are copied into
this isolated worktree; the original checkout and user inputs are untouched.

## Behavior and activation

Set Flask configuration `SCIDK_GUI_V3_ENABLED = True` in the development host.
The default remains off; this is a strict boolean config, not an environment
variable parser. No database setup or migrations occur on shell reads.

The six header destinations are Overview, Files & Datasets, Resources, Knowledge,
Review and Settings. With the flag enabled `/` opens Overview and `/settings`
renders the existing Settings page, including section fragments. Legacy routes
remain available. Knowledge links to existing Maps/Canvas, Entities,
Relationships and Results. Review explains its unavailable state; no human or
agent decisions are performed by this slice.

Overview has a central disabled Ask SciDK composer. The existing chat session
and provider pages remain linked. The current provider adapter sends approved
fixed-tool results, not an authorized natural-language conversation. Consequently
Overview never calls the generic chat endpoints, never executes Review tools,
and never transmits questions/history. Even `?profile=review` cannot enable it.
Stage 6 server-side accepted/current-support filtering is unchanged. Enabling
chat requires a separate approved transport with a server-bound Overview profile.

Files mounts the current browser unchanged except for selection events. Dataset
search reuses the bounded existing Canvas node search with `label=Dataset`;
no arbitrary Cypher or new graph endpoint is introduced. Recognition and Collect
continue to use their existing services. The older file interpretation index is
separately labeled: it must not be confused with recognized Dataset nodes, and
its Neo4j adapter currently returns an empty list. Search requires a name/path
term and returns at most 100 matches; this is not an exhaustive dataset catalog.

The shared inspector retains per-tab selected records and the inspector tab and
expanded state when switching between Files and Datasets. Closing it preserves
selection, and selecting a record reopens it. Docked mode reserves browser space;
expanded mode uses the viewport. Metadata includes expandable raw JSON and safely
renders raw XML/string content as text. Annotations reads the existing filtered
API, capped at 100, with stale-request protection. Existing Annotate, Share,
Collect and interpretation drawers remain intact. Stored provenance is shown
without inventing acceptance/evidence status. The inspector does not provide a
new annotation editing form: existing annotation/attribution workflows remain
in the preserved legacy interfaces. Graph element IDs, index IDs and file paths
are intentionally distinct annotation keys; preexisting alternate-key annotations
are not automatically reconciled.

Selected recognized datasets show disabled Prepare for Sharing with the backend
reason. No NIH exporter request is made. The preserved legacy DMS drawer is now
explicitly labeled whole graph. It retains its existing human access behavior;
this pass adds no new disclosure guarantees to that exporter or legacy graph
browsing. Before dataset sharing, implement authorized dataset membership and
current-support/evidence projection and reconcile the export configuration stores.

## Validation

Focused GUI suite: **3 passed, 0 failed, 0 skipped** (4.80 seconds). Final
relevant regression: **430 passed, 0 failed, 1 skipped** (162.29 seconds).
The skip is the optional disposable Neo4j test; no explicit safe instance was
configured. JavaScript syntax and Git whitespace checks passed.

Local system Chrome is available; Playwright's
bundled Chromium is not installed. Browser tests use Flask route interception and
synthetic service responses, not a live Neo4j/provider. They exercise real shipped
HTML/CSS/JS. Node additionally exercises shipped inspector event handlers and
asynchronous annotation response protection. Stage 6 end-to-end tests retain
accepted-only Overview checks. No production data or real provider was used.

## Files and remaining work

Runtime: `scidk/web/routes/ui.py`, `scidk/ui/templates/base.html`,
`scidk/ui/templates/files/{datasets.html,_dms_panel.html}`,
`scidk/ui/templates/gui/{workspace.html,files_inspector.html}`,
`scidk/ui/static/{css/gui_slice.css,js/gui_slice.js}`.
Tests: `tests/test_gui_slice.py`, `tests/gui/inspector_state.cjs`.
Documentation: copied `docs/design/*.md` and visual HTML handoff, migration map,
this report, cost checkpoint and synthetic browser screenshots.

Live free-text chat, authorized dataset-scoped DMS, full Knowledge/Review UI,
production scientific dataset recognition and live disposable Neo4j verification
remain outside this slice. Stop here for review; do not begin the following slice.

## Browser artifacts

Synthetic intercepted service responses in system Chrome:

- [Overview disabled composer](screenshots/gui-overview.png)
- [Docked dataset inspector](screenshots/gui-dataset-docked.png)
- [Expanded dataset inspector](screenshots/gui-dataset-inspector.png)

The screenshots demonstrate layout and controls, not live provider, graph or
production authorization validation. Existing root Settings fragment bookmarks
must use `/settings#...` when the new Overview landing page is enabled.

Final regression command (the project virtualenv Python):

```sh
python -m pytest tests/test_gui_slice.py tests/knowledge_e2e tests/agent_integration tests/security tests/curation tests/knowledge tests/pipeline/test_mapping_ui.py tests/pipeline/test_api_mapping.py tests/pipeline/test_canvas_context.py tests/test_annotations_rest_endpoints.py tests/test_annotations_relationships_syncqueue.py tests/test_annotations_and_selections.py tests/test_canvas_export_auth.py tests/test_nih_dms_plan.py tests/test_chat_api.py tests/test_api_tokens.py -q -o addopts=''
```

The commit containing this report is the focused first-slice checkpoint; its exact
hash is recorded in the completion response. The primary checkout's existing
modified `dev` and untracked prompt/design/demo/vision files were preserved.
