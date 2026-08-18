# SciDK Platform Roadmap
*August 2026 — NCI Symposium November 5–6, 2026 and beyond*

---

## Vision

**SciDK is where data acquires meaning, and that meaning is portable.**

A file enters as a TIFF. It leaves with a sidecar that says what animal, what protocol, what treatment group, what timepoint — validated against the facility ontology. That annotation file can go anywhere: to a collaborator, to a public repository, into a LIMS. The knowledge graph is the source of truth, but it is not the only destination.

The platform solves a structural problem that gets worse every year: scientists optimize for results, not for making their data findable five years later by someone they've never met. SciDK meets researchers where they already work — SharePoint, shared drives, instrument software — and builds the connective tissue underneath without asking them to change behavior.

---

## What's Built (August 2026)

### Core infrastructure
- **Knowledge graph** (Neo4j) with 5.18M nodes, 14.95M relationships on the AIPT instance
- **Schema Intelligence layer** — property rankings, label profiles, always/never include, usage tracking, contamination-free attribution
- **APScheduler** with single-instance guarantee under gunicorn `--preload`, persistent SQLAlchemy jobstore for dynamic schedule changes
- **MCP server** — 5 tools over stdio, usable from Claude Desktop, security-hardened (keyword filter, label injection fixed)
- **Auth and RBAC** — `@require_role('admin', 'user')`, session management, audit log

### Data ingestion (Resources)
- **Pipeline ETL substrate** — `DataSourcePlugin` contract (find/access/fetch/transform_library mapped to FAIR)
- **SharePoint plugin** — rclone-backed, lazy streaming, 6 SharePoint-specific transforms
- **Mapping engine** — config-driven, JSON Schema validated, property sanitization, no hardcoded column names
- **FAIR check** — F→A→I→R in sequence, sampled dry run with merge/create lookup against live Neo4j, zero writes
- **Source management UI** at `/pipeline/sources` with stepped wizard (connection → schema canvas → column mapping → FAIR check → run/schedule)
- **Schema canvas** — Arrows.app round-trip, derive from live graph, build from scratch; scoped to each source via `context_id`
- **Column mapping UI** — two-panel, role-based multi-node rows, format layer tested under Node against real engine

### Maps canvas
- **Four modes**: Explore, Curate, Schema view toggle, Design (schema-space elements with `_space: "schema"` flag)
- **Cytoscape.js** engine shared with schema canvas; `cytoscape-edgehandles` for provisional edge drawing
- **Commit flow** — writes to Neo4j via `write_declared_nodes`; schema elements blocked from instance writes
- **Canvas exports** — Cypher, Python, RO-Crate (all auth-gated)
- **Saved maps** with query library

### Publication
- **RO-Crate bridge** (`scidk/rocrate_bridge.py`) — `build_from_selection()`, `build_from_map()` (hand-rolled pure), `ingest_crate()` (uses `rocrate` library); golden-mastered before refactor
- **Files page** — "Build RO-Crate" button on selection, "Generate DMS Plan Draft" in header
- **NIH DMS generator** (`plugins/nih_dms/`) — four DMS sections from real graph data, PHI detection across 12 property-name variants, exact file format aggregation over 5.1M nodes, 8.4s generation

### Chat and AI
- **ReAct loop** with streaming and step visualization
- **Concept Graph** — intent routing, tool nodes (`:Concept_Tool`), weight decay (nightly, 90-day half-life), export/import, CLI (`python -m scidk.concept_graph seed`)
- **Schema context enrichment** — ranked properties, label descriptions, always/never include applied to MCP responses
- **Canonical tool registry** — single `TOOL_DEFINITIONS` consumed by MCP server, Concept Graph seeding, and `GET /api/platform/tools`

### Settings and connections
- **Connections overview** — Research Graph, Chat History, Concept Graph as peer cards with real connectivity probes, on-demand node/edge counts, last verified timestamp
- **Concept Graph card** — export/import controls added

---

## Navigation Architecture

```
SciDK ▾  |  Results  |  Chats  |  Maps  |  Entities  |  Files  |  Resources
```

| Nav item | Content | URL |
|---|---|---|
| **Results** | Search, browse, query results | `/results` |
| **Chats** | Chat sessions with ReAct loop and graph context | `/chat` |
| **Maps** | Canvas (Explore/Curate/Design), saved maps, query library | `/map` |
| **Entities** | Two tabs: Entities (Labels) and Relationships (Links) | `/entities` |
| **Files** | File browser, annotations, RO-Crate, DMS plan | `/files` |
| **Resources** | Bidirectional connectors (was Pipeline/Sources) | `/pipeline/sources` |

**Settings sidebar**: Connections, Backup, Security, Advanced (Scripts, Plugins)

**SciDK ▾ dropdown**: Settings, Admin, About

---

## Near-Term Roadmap

### What Phase 2 Cycles Cover (Cycles 10–16, ~16–22 Junie sessions)

Phase 2 is specified in `SciDK_Phase2_Cycles.md`. The seven cycles cover:

| Cycle | Sessions | Delivers |
|---|---|---|
| 10 — Chat session ownership + sidebar + sharing | 2–3 | Session ownership fix, saved session sidebar, Cypher panel, **sharing UI** |
| 11 — AI document artifacts + MCP chat tools | 2–3 | Artifact data model, AI DMS as chat artifact, **MCP chat history tools** |
| 12 — Query library + named datasets + scope wiring | 3–4 | Universal query library, named datasets, filter GUI, **scope selector in all panels** |
| 13 — Annotation export from Files | 1–2 | Annotation export service, CSV/JSON-LD export route, Files page panel |
| 14 — Write-direction Resources contract | 3–4 | `DataResourcePlugin` contract, local file writer, runner write path, direction badges |
| 15 — SharePoint write connector | 1–2 | rclone-backed SharePoint write plugin (requires AIPT deployment) |
| 16 — Bidirectional (⇄ Both) connector | 1–2 | `SharePointBidirectionalPlugin`, FAIR check both directions |

### Phase 2 now covers all four original gaps

The four gaps identified in the initial Phase 2 review have been incorporated into `SciDK_Phase2_Cycles.md`:

- **Gap 1 — Session sharing UI** → Cycle 10, Task D (sharing panel, invite/revoke, visibility toggle)
- **Gap 2 — Scope selector wiring** → Cycle 12, Task D (unified scope component in DMS, RO-Crate, annotation export panels; Maps canvas "Use as scope" action)
- **Gap 3 — MCP tools for chat history** → Cycle 11, Task C (`list_sessions`, `get_conversation_history`, `get_artifact` as MCP tools)
- **Gap 4 — ⇄ Both bidirectional connector** → Cycle 16 (`SharePointBidirectionalPlugin`, both directions, FAIR check for each)

Phase 2 is now Cycles 10–16 (~16–22 Junie sessions) and covers the complete near-term feature vision.

---

### Track 1 — Resources: Bidirectional Connectors

**Current state:** Resources page is read-only ingest (Extract → Transform → Load into graph). Every configured source has direction → In (into the graph).

**Vision:** Resources are bidirectional connectors. Each resource has a direction badge:
- **→ In** — data flows from the resource into the graph (current SharePoint, CSV sources)
- **← Out** — graph-derived data flows out to the resource (annotation export targets, API sinks)
- **⇄ Both** — read and write (a LIMS you query and update, an API with GET and PUT)

The FAIR check applies equally to write targets: can SciDK find what the resource accepts (Findable), authenticate to it (Accessible), translate graph data into the resource's format (Interoperable), and reproduce a write reliably (Reproducible)?

**Confirmed by Junie research (2026-08-04):**
- `DataSourcePlugin` is strictly read-only — `find()`, `access()`, `fetch()`, `transform_library()` only
- `runner.py` has no write path; it is entirely graph-inward
- rclone already supports `copy` and `sync` operations — the plugin never uses them
- A write-direction SharePoint connector would use `rclone copy` to push files to a library, or the Microsoft Graph API (via rclone's SharePoint backend) to update list items
- `write_declared_nodes` is graph-inward only; no pattern exists for reading from graph and formatting output for an external system

**Plugin contract extension for write direction:**

```python
class DataResourcePlugin(DataSourcePlugin):
    # Existing read methods: find(), access(), fetch(), transform_library()
    # These four cover FAIR for the read direction.
    
    def accepts(self, config: dict) -> AcceptsResult:
        """FAIR: Findable (write side). What schema does this target accept?
        For SharePoint: what columns does the target list have?
        For CSV: what columns should the output file contain?"""
    
    def authorize_write(self, config: dict) -> AuthResult:
        """FAIR: Accessible (write side). Can SciDK write to this resource?
        For SharePoint: verify rclone write permissions via a test put."""
    
    def push(self, records: Iterator[dict], config: dict) -> PushResult:
        """FAIR: Interoperable (write side). Write records to the resource.
        For SharePoint: rclone copy to a library or Graph API list item update.
        For CSV: write to a local or rclone-accessible path."""
    
    def push_transform_library(self) -> dict[str, Callable]:
        """FAIR: Reproducible (write side). Format transforms for output.
        Inverse of the read transform_library where applicable."""
```

**Write path for the Resources UI:**
- Direction badge on each resource card (→ In / ← Out / ⇄ Both)
- Write-direction resources show a "Push" button alongside Run
- Schema mapping for write direction: graph properties → target columns
- Write FAIR check before any push

**Immediate value:** annotation export files. A researcher curates a set of files on the Maps canvas → pushes enriched metadata to a CSV resource → the annotation file travels with the data. Graph is the source of truth; the annotation file is the portable output.

---

### Track 2 — Files: Annotation Export

**Current state (confirmed by Junie research 2026-08-04):**
- Annotation data exists in `files.db`: `id`, `file_path`, `label`, `value`, `confidence`, `source`, `created_at`, `updated_at`
- Endpoints `GET/POST /api/annotations` and `DELETE /api/annotations/<id>` are CRUD only — no export route
- A typical `File` node in Neo4j carries: `path`, `name`, `extension`, `size`, `checksum`, `mime_type`, `last_modified`, `record_source` plus relationships: `CONTAINS`, `SCANNED_IN`, `DERIVED_FROM`, `OF_TYPE`, `ATTACHED_TO`, `LOCATED_AT`, `CLASSIFIED_AS`
- No "export selection" or "download metadata" feature exists anywhere in `api_files.py`

**What's needed is closer than expected.** The annotation data already exists in SQLite. The gap is an export route that combines SQLite annotations with Neo4j File node properties and relationships into a portable format.

**Export formats:**
- **CSV sidecar** — flat, instrument-compatible: one row per file with `path`, `label`, `value`, `confidence`, `source` plus graph-derived columns (entity type, protocol, treatment, PI, session)
- **JSON-LD** — semantically typed, links to ontology terms where available
- **RO-Crate** — already exists via `build_from_selection()`; annotation export is a complement (richer per-file metadata), not a replacement

**Implementation path:**
1. `scidk/services/annotation_export.py` — for a given set of file paths or node IDs: query SQLite for annotations, query Neo4j for File node properties + relationships up to N hops, merge into enriched records, format to requested output
2. Route: `POST /api/files/export/annotations` (admin or user) — accepts `{node_ids, format, depth}` where depth is the relationship hop distance to include
3. Files page export panel — alongside "Build RO-Crate" on selection; format selector (CSV / JSON-LD / both); depth control (1–3 hops)

**Connection to Resources write path:** once write-direction Resources exist, annotation export becomes "push to CSV resource" or "push to JSON-LD resource" — same content, different delivery. The Files export panel and Resources push are two entry points into the same data.

---

### Track 3 — Chat: Sessions, Artifacts, and AI Document Generation

**Current state:** Chat has a ReAct loop, streaming, step visualization, Concept Graph routing, and schema context enrichment. Chat sessions exist in the database but `chat_sessions.owner` defaults to `'system'` and `create_session()` never sets it — session sharing endpoints exist but return 403 to everyone.

#### 3A — Fix session ownership (prerequisite for everything else)

One-line fix in `chat_service.create_session()`:
```python
# Set owner from the authenticated user, not 'system'
session.owner = g.scidk_user or 'system'
```

This unblocks sharing endpoints which already exist and gate correctly once owner is set.

**Also needed:** update existing `chat_sessions` rows to set `owner` from `auth_audit_log` where recoverable; add `created_by` index for sharing queries.

#### 3B — Saved session sidebar (Claude Desktop-style)

After 3A, the sidebar becomes buildable:

```
Chats
├── [Today]
│     ├── AIPT imaging cohort query
│     └── DMS plan — Q3 2026
├── [Yesterday]
│     └── SharePoint mapping discussion
└── [+ New chat]
```

Each session shows: name (auto-generated from first user message or editable), timestamp, artifact count. Clicking opens the session and restores the full conversation including artifacts.

Sessions can be shared with other users — the sharing endpoints are already built.

**Session artifacts:** each conversation accumulates artifacts (documents, queries, crate exports, annotation files). Artifacts appear as cards in a sidebar panel alongside the conversation.

#### 3C — Document artifacts in chat

The DMS plan generator currently produces a static markdown output in the Files page. The better architecture: **document artifacts in chat**.

A researcher asks the chat "generate a DMS plan for the Q3 imaging cohort" → the AI uses the graph facts + a DMS-aware prompt → produces a draft that appears as an artifact card in the conversation. The researcher can then ask follow-up questions:
- "Make the Access section more specific to our IRB constraints"
- "Add a note about the NIfTI files in the microCT section"
- "Rewrite Standards to include BIDS"

Each turn revises the document in place. The artifact shows the current version with a diff from the previous turn on hover.

This pattern generalizes: any structured output the AI produces (DMS plan, RO-Crate manifest summary, annotation template, data harmonization plan) can be an artifact. The chat becomes a document editor with AI drafting support.

**Implementation:** SSE events already carry ReAct steps. Adding an `artifact` event type that the frontend renders as a card is the extension. The document is stored as a `chat_artifact` table row linked to the session.

#### 3D — AI-enhanced DMS generation

**Current state:** `plugins/nih_dms/generator.py` is purely rule-based. It produces accurate but template-sounding prose.

**Enhancement:** pass the graph facts to the chat ReAct loop with a DMS-aware system prompt instead of templating prose directly.

```python
# Instead of:
prose = f"This dataset contains {label_counts['Project']} Project records..."

# Pass to chat:
graph_summary = {
    "label_counts": label_counts,
    "file_formats": format_distribution,
    "phi_status": phi_check,
    "total_size_tib": total_size,
    ...
}
dms_prompt = build_dms_system_prompt(graph_summary)
response = chat_react_loop(dms_prompt, section="data_types")
```

The AI writes natural prose grounded in real facts. The researcher can then iterate via chat turns (Track 3C). The facts are immutable (from the graph); the language is flexible.

**Scope:** opt-in via a "Use AI drafting" toggle on the DMS plan generation panel. The rule-based generator remains the default for reproducibility and speed; the AI draft is for submission-quality prose.

#### 3E — Cypher panel and external models

**Cypher panel:** the right frame in the chat UI has a Cypher query panel. Verify whether it's receiving ReAct loop SSE events (the loop should emit Cypher steps). If the SSE plumbing is there but the panel isn't rendering it, this is a one-session fix.

**External models:** multi-provider LLM support shipped in February 2026. If the model selector is visible but greyed out, check whether it's a missing API key config vs a feature flag. If it's config, document the env vars clearly. If it's a feature flag, decide whether to enable it.

#### 3F — MCP tools for chat history

Adds three new MCP tools that a Claude Desktop session can use to access SciDK conversation history alongside the graph:

- `get_conversation_history(session_id, limit)` — retrieve messages from a saved chat session
- `get_artifact(artifact_id)` — retrieve a document artifact (DMS draft, annotation template)
- `list_sessions(user, limit)` — list recent sessions with metadata

Enables: a researcher in Claude Desktop queries the graph, pulls up a DMS draft from last week, and continues refining it — all through MCP without opening the SciDK UI.

---

### Track 4 — Dataset Scoping and Named Datasets

**The problem:** every feature that operates on "a subset of the graph" (DMS plan, RO-Crate export, annotation export, chat context) currently operates on the whole graph. A facility with multiple PIs and dozens of projects needs to scope: "generate this plan for Project X and everything associated with it."

**Three scoping mechanisms, all producing the same scope definition:**

#### Option A — Saved query from Maps query library (power tool)
The query library in Maps already exists. Making it universal means the DMS generator, RO-Crate export, annotation export, and chat context scope selector can all consume a saved query. A data manager defines the scope once in Maps and reuses it everywhere.

**Action:** promote the query library from a Maps-specific feature to a universal library at `/api/queries/` accessible from all features.

#### Option B — Label + property filter GUI (accessible tool)
For users who don't know Cypher: a GUI filter that says "include Project nodes where `pi_email` = `smith@mit.edu`" with checkboxes for which related entity types to include.

This generates Cypher under the hood from the schema layer:
```cypher
MATCH (p:Project {pi_email: 'smith@mit.edu'})
OPTIONAL MATCH (p)-[:CONTAINS*1..2]-(related)
RETURN p, related
```

**UI:** a filter panel that appears as a scope selector in the DMS generator, RO-Crate build panel, and annotation export panel. The schema canvas already knows all labels and their properties — the filter UI is a simplified query builder on top of it.

**Relationship distance boundary:** "include everything within N hops of these anchor nodes" is the natural extension. A PI selects their Project node, sets distance to 2, and gets all directly connected Sessions and Samples but not unrelated projects. This maps directly to Cypher's variable-length path pattern (`*1..N`).

#### Option C — Current Maps canvas selection (contextual tool)
Whatever nodes are on the Maps canvas is the scope. The RO-Crate bridge already supports `build_from_selection(node_ids, ...)` — the canvas selection is a natural scope input for any feature.

**UI:** on the canvas, a "Use as scope" action that opens a scope menu: "Export annotations for this selection", "Generate DMS plan for this selection", "Build RO-Crate for this selection".

#### Named datasets
A saved scope definition — a query, a filter, or a canvas snapshot — that can be named and referenced across features.

```
Named datasets
├── AIPT Q3 2026 Imaging Cohort    [Saved query]   last used: 2026-08-01
├── Smith Lab microCT Archive      [Canvas snapshot]  last used: 2026-07-28
└── Active Projects (all PIs)      [Label filter]    last used: 2026-08-04
```

"Run the DMS generator on the AIPT Q3 imaging cohort" becomes a one-click operation. The named dataset is the reusable unit; the features (DMS, RO-Crate, annotation export, chat) are operations on it.

**Maps is already close to this.** A saved map is a query with a result set. What's missing is treating maps as dataset definitions that other features can consume, not just visualizations. The rename from "saved maps" to "datasets" (or treating datasets as a superset of saved maps) is mostly a UI framing change.

---

## Architecture Decisions

### Resources replace the Pipeline/Sources vocabulary

- **Resources** — the things SciDK connects to: SharePoint lists, CSV files, APIs, databases, annotation export targets
- **Pipeline** — the mechanism SciDK uses to connect a Resource to/from the knowledge graph; internal architecture term, not user-facing
- **FAIR check** — validates that SciDK can interact with a Resource reliably, in either direction

URLs stay at `/pipeline/sources` internally. The display name "Resources" is the user-facing label. This avoids doc churn while giving the right vocabulary in the UI.

### Universal query library

The query library currently lives inside Maps. Every feature that needs dataset scoping needs access to it. The library should live at `/api/queries/` and be accessible from:
- Maps (current home — query editor, run, save)
- DMS generator scope selector
- RO-Crate build scope selector  
- Annotation export scope selector
- Chat context scope selector
- Named datasets

The Maps query editor is still the primary authoring interface for Cypher queries. The library is just elevated from a Maps-internal store to a platform-level resource.

### Named datasets as a cross-cutting concept

A named dataset is a scope definition with an identity. It appears wherever scope is needed:

```
Dataset: "AIPT Q3 2026 Imaging Cohort"
  Type: Saved query
  Query: MATCH (p:Project {quarter: 'Q3-2026'})-[:CONTAINS*1..3]-(n) RETURN n
  Node count (last computed): 14,892
  Last used: DMS plan 2026-08-01
  Used by: [DMS Plan draft] [RO-Crate export] [Chat session: Q3 data review]
```

This is the concept that makes SciDK more than a visualization tool. A dataset defined once flows through DMS compliance, data sharing, annotation, and AI-assisted analysis without re-specifying the scope at each step.

---

## Longer-Term Tracks

These tracks are post-Phase 2. Each has an effort estimate and its hard dependencies stated. Imaging Tier 1 is the most independent — it can start any time.

### Layer model (~3–4 sessions · after Cycle 6 Task B portable state envelope)

Retrofit existing scans, interpreters, plugins, and canvas commits as typed Layers (sourced/computed/authored). A Layer has: inputs, outputs, a run history, and a `depends_on` structure. The Layer model is what makes the Pipeline Canvas DAG meaningful — right now the canvas can show sources, but a DAG needs layers as typed objects with dependency edges.

This is the largest single architectural effort in the longer-term roadmap. It's a retrofit of four existing systems (scanner, interpreter, plugin runner, canvas commit) under a common interface — similar in scope to what Cycles 3–3B were for the plugin architecture.

### Full Pipeline Canvas DAG (~3–4 sessions · after Layer model)

The visual DAG designed in the Pipeline Canvas Design Vision section of cycles.md. Adds:
- Layer nodes with run history drill-down
- Dependency edges (data flow between layers)
- Live run feedback (pulsing border → green/amber/red on completion)
- Source/target focus widget (lineage view for any label or relationship type)
- DAG derivation from layer creation history

Cannot start until Layer model lands — the DAG needs layers as typed objects with `depends_on` edges to derive from. The Resources page infrastructure (Cycle 3B) is already in place; this page adds the visual DAG on top.

### Cycle 9 — Data Sovereignty and Sharing Modes (~2–3 sessions · deferred from Phase 1)

Per-property sharing modes in the Labels UI (`raw` / `hidden` / `pseudonymized` / `simulated` / `randomized`) and a sovereignty filter applied to MCP responses. The first federation-enabling cycle. Fully specced in cycles.md §Cycle 9 — pick it up when federation becomes a priority.

### Bidirectional Federation (~2–3 sessions · after Cycle 9)

Connect two SciDK instances via MCP. Sovereignty filter applied at each instance boundary. Cross-instance queries with mixed sharing modes. The named dataset concept becomes a federated dataset — a scope definition that spans multiple instances.

### Reference Brain integration (~4–5 sessions · after federation)

BioCypher integration for UBERON (anatomy), MGI (mouse genetics), and other reference ontologies. Three-layer model: Reference Brains → Instance Graph → Brain Profiles. The facility's data is enriched with ontology terms; queries can traverse both instance data and reference knowledge. The largest scope item in the full roadmap — BioCypher integration itself is non-trivial and the three-layer model requires care to keep queries performant.

### Imaging visualization Tier 1 (~2–3 sessions · independent, can start any time)

Inline DICOM preview using Cornerstone2D or Papaya, thumbnail + metadata panel for non-DICOM, "Open in 3D Slicer" button. Independent of all other longer-term tracks — does not need Layer model or federation. The reason it's deferred is not dependency but priority: the knowledge graph navigation features deliver more value first, and images are most useful once you can navigate to them via meaningful queries.

### Imaging visualization Tier 2 (~3–4 sessions · after Tier 1)

3D Slicer via noVNC, file paths passed via the Slicer WebServer REST API (port 2016). Requires Tier 1 to be working and tested.

---

## Key Deferred Items (tracked, not forgotten)

Grouped by effort. The "quick wins" column are all fixable in a single short session combined.

### Quick wins (combine into one session, ~1 hour total)
| Item | Fix |
|---|---|
| `test_semantic_retrieval.py::test_query` rename | One-line rename — collection error every test run |
| `POST /chat/concept-graph/reseed` tools_seeded bug | One-word fix: reads wrong key, reports 0 always |
| `datetime.utcnow()` deprecation sweep | Repo-wide mechanical sweep — warns on Python 3.12 |

### Short sessions (~30–60 min each)
| Item | Effort | When |
|---|---|---|
| Links page relationship description write path | ~45 min | Any time — improves chat quality for relationship types immediately |
| Concept Graph route family auth sweep | ~1 session | Decision needed: which `/chat/concept-graph/*` write routes need gating |
| `get_label_profile` slow on large labels (12.6s for File at 5.1M nodes) | ~1 session | Sampled or `db.schema.nodeTypeProperties()`-based key list |
| `get_enriched_schema_context` truncates `'all'` mode | ~1 session | SI bug — `'all'` behaves as `'top_n'`; fixing changes what every chat prompt contains |
| `Two t.embedding` formats in Concept Graph | ~30 min | Latent; nothing reads it yet — fix when embedding reads are added |
| Portable state envelope (Cycle 6 Task B) | ~1 session | Stubs only; nothing depends on it — after demo |

### Deferred cycles (fully specced, waiting for priority)
| Cycle | Effort | Dependency |
|---|---|---|
| Cycle 9 — Sharing modes UI in Labels | 1–2 sessions | After demo; prerequisite for federation |
| Cycle 9 — Sovereignty filter on MCP responses | 1–2 sessions | After Cycle 9 sharing modes; prerequisite for federation |

---

## Full Roadmap Effort Summary

A complete accounting of all work in the roadmap — Phase 2, gaps, deferrals, and longer-term tracks.

| Category | Sessions | Notes |
|---|---|---|
| **Phase 2 cycles 10–16** | 16–22 | All four original gaps now incorporated; see `SciDK_Phase2_Cycles.md` |
| **Phase 1 deferred cycles** (Cycle 9 sovereignty) | 3–4 | Fully specced; prerequisite for federation |
| **Quick wins + short sessions** | 3–5 | Bug fixes, deprecation sweep, Links descriptions |
| **Layer model** | 3–4 | Multi-system retrofit; prerequisite for Pipeline Canvas DAG |
| **Full Pipeline Canvas DAG** | 3–4 | After Layer model |
| **Bidirectional federation** | 2–3 | After Cycle 9 + Layer model |
| **Reference Brain integration** | 4–5 | After federation; largest single scope item |
| **Imaging Tier 1** | 2–3 | Independent — can start any time |
| **Imaging Tier 2** | 3–4 | After Tier 1 |
| **Total** | **~40–55 sessions** | |

**Context:** Cycles 1–8 (roughly 18–22 sessions of work) were completed in a single afternoon on 2026-08-04. At that pace, Phase 2 complete is 2–3 more afternoons. The full roadmap including longer-term tracks represents several weeks of focused afternoon sessions.

**Critical path to November demo:** Cycle 10A (session ownership) → Cycle 11B (AI DMS artifact) → Cycle 13 (annotation export). These three make the demo story significantly richer. Everything else can follow after November.

**Most independent longer-term item:** Imaging Tier 1. It has no dependency on Layer model, federation, or sovereignty. It can start any time and will have the highest visible impact for researchers who spend time in the Files page.

---

## NCI Demo Plan (November 5–6, 2026)

**Story arc:** Past → Present → Future

| Dataset | Story | Features to demo |
|---|---|---|
| Longitudinal Lab Archive (microCT, ultrasound, field notes) | "What happens when a scientist leaves" | SharePoint intake → graph → Chat (what datasets did this PI create?) → DMS plan |
| Multimodal Protocol Project (MRI, IVIS, ultrasound, active) | "DSMI mandate: assembling disparate data" | FAIR check → pipeline run → Maps schema view → annotation export |
| Federated Cloud Monitoring | "Data stays where it lives" | Resources page → MCP in Claude Desktop → cross-source query |

**Features to demo:** SharePoint intake → FAIR check → knowledge graph → Chat (GraphRAG) → Maps/canvas → RO-Crate export → NIH DMS plan generator → Resources management

**Features to mention, not demo:** Federation, imaging visualization, Layer model, Pipeline Canvas DAG, AI document artifacts (roadmap)

---

*Based on: cycles.md (August 2026) · conversations on bidirectional resources, chat improvements, dataset scoping, and annotation export*