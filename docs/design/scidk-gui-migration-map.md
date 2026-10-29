# GUI v3.1 migration map — prompt codex_prompt_09.txt

Inventory before implementation, 2026-10-29. Preserve all legacy routes and storage.
The static prototype is a visual reference; synthetic data is not runtime data.

| Existing capability / routes | Implementation inspected | Destination and compatibility |
| --- | --- | --- |
| `/` and `/settings`, settings sections/fragments | routes/ui.py, templates/index.html, base.html | Settings; default shell unchanged unless SCIDK_GUI_V3_ENABLED is explicitly True. With flag on, `/` is Overview and `/settings` renders existing settings with fragments intact. |
| `/datasets`, `/api/servers`, browse/scan/task routes, snapshots, selections, Add Drive | api_files.py, files/datasets.html, scan_panel/add_drive/collection JS | Files & Datasets / Files; mount current browser without iframe; preserve cursor, drawers and scans. `/datasets` remains valid. |
| `/api/datasets`, `/api/datasets/{id}`, `/datasets/{id}`, `/workbook/{id}` | api_files.py, core/graph.py and neo4j_graph.py | Datasets tab uses existing index; index records are interpreted files, not necessarily scientific collections. Neo4j index implementation returns empty. Existing detail/workbook links remain. |
| Recognized/collection Dataset nodes, `/api/datasets/collections`, `/api/collections/sweep` | dataset_node_service.py, api_annotation.py, annotate.js | Datasets searches actual Dataset nodes with existing `/api/canvas/nodes/search?label=Dataset`; bounded search, no automatic global harvest. Existing recognition and Collect unchanged. |
| `/api/annotations` CRUD, `/api/relationships`, `/api/sync` queue | api_files.py, api_annotations.py, annotate.js | Shared inspector reads selected-object annotations; existing Annotate drawer remains for attribution/collection/interpretation. Identity keys must match annotation file_id; graph element IDs and paths are distinct. |
| `/entities?tab=entities|relationships`, `/labels`, `/links`, `/integrate` | ui.py, _entities_tabs.html, labels/links templates | Knowledge entry links to existing pages; preserve tab query and compatibility redirects. No merged scripts. |
| `/map`, `/api/maps/saved` CRUD and filtering | map.html, api_maps.py, saved_maps_service | Knowledge / Maps; all saved-map IDs and storage retained. |
| `/api/canvas` config, nodes/search, relationship-types, session, queries, layers, commit, exports/verify/expand | api_canvas.py, canvas_service.py | Existing Canvas stays reachable via Maps/Resources; user/context session keys retained. Commit is legacy direct write, not accepted curation; no agent exposure. |
| `/pipeline/sources`, source `schema` and `mapping`; `/api/pipeline` sources/schema/mapping/columns/upload/test-connection/run/preflight/fair-check, pipeline CRUD/history/schedules | ui.py, api_pipeline.py, pipeline templates, pipeline_mapping.js | Resources; preserve source IDs and pipeline_source context. No mapping/scanner/runner changes. |
| `/plugins`, `/interpreters`, `/extensions`, plugin templates/instances/settings/dependencies | ui.py, api_plugins.py, plugin_template_registry.py | Settings with legacy links; source picker remains Resources. No plugin harvesting. |
| `/api/plugins/nih_dms/draft_plan` and `/config`, DMS/Share drawers | plugins/nih_dms routes/graph_facts/generator/config, dms.js, _dms_panel.html | Existing whole-graph human export preserved and labeled. Selected-dataset Prepare for Sharing disabled until scoped authorized exporter exists. dataset_id is currently ignored. |
| `/chat`, chat session CRUD/messages/import/export/permissions, provider settings; old GraphRAG routes | api_chat.py, chat.html, agent_tools/provider_settings.py | Overview central disabled free-text chat: no authorized conversational transport yet. Preserve legacy sessions/page; never connect Overview to unscoped GraphRAG. |
| `/api/chat/functions.json`, `/api/chat/tools/{name}`, `/api/agent/*`, MCP | agent_tools registry/profiles/security/knowledge, architecture/knowledge-curation-agent-api.md | Overview must bind overview server-side before any future execution. Existing Review selector must never become Overview authority. Disabled GUI executes no tools. Stage 6 accepted-only filtering remains. |
| `/api/curation/assertions` preview/review and ledger/materialization services | api_curation.py, Stage 6 report | Review placeholder; human-only review grants, default-off flags retained. No acceptance/materialization controls added. |
| `/results`, `/scripts`, `/rocrate_view`, `/login` | ui.py and corresponding templates | Knowledge/Settings legacy links; routes unchanged. |

## Next backend work

Build dataset-scoped DMS authorization, bounded membership/evidence/current-support
projection and scoped configuration before enabling sharing. The legacy settings
getter uses SCIDK_DB_PATH whereas schema settings use SCIDK_SETTINGS_DB; reconcile
explicitly in that adapter. Never pass dataset_id to the global exporter and claim
scope. Build approved conversational transport with server-bound Overview profile
and per-turn disclosure before enabling Ask SciDK. Full Knowledge and Review
workspaces, docking libraries and new drive discovery are later slices.

### Remaining deep-link limits

With the new shell enabled, historical Settings bookmarks beginning `/#...`
need `/settings#...` instead; URL fragments are unavailable to Flask routing.
Provider links in the new shell use the existing `#ai-chat/llm-provider` fragment.
Recognized Dataset node element IDs are not legacy `/datasets/{id}` index IDs;
the new inspector does not construct incompatible detail links from them.
