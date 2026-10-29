# SciDK GUI v3 — Implementation Design Specification

**Status:** GUI implementation contract, updated after Stage 6 (`0896c5a`); backend status is Codex-reported, not production-verified.  
**Companion:** `scidk-gui-v3.html` (interactive, synthetic-data wireframe).  
**Product authority:** `docs/vision/scidk-vision-v1.1.md`.

## Product goal

Make SciDK's existing strengths—filesystem discovery, dataset recognition, annotations, Resources mapping, Entities, Cytoscape/Canvas, NIH DMS export, and secure AI-assisted curation—feel like one continuous workflow.

**Primary navigation:** Overview → Files & Datasets → Resources → Knowledge → Review → Settings.

## Page contracts

| Page | Core interactions | Reuse and preservation |
|---|---|---|
| Overview | Executive metrics; central Ask SciDK with citations and currently supported facts | Existing dashboard, Parley/API, Stage 5 Overview profile |
| Files & Datasets | Files and Datasets tabs; + Drive; dataset inspector; Prepare for Sharing | Existing file browser, annotations, dataset recognition, NIH DMS exporter |
| Resources | Sources, Builder, Runs; Source → Schema → Mapping | Existing CSV plugin builder, mapping roles, FAIR checks, configuration and run history |
| Knowledge | Research / Ontology / System domains × Graph / Entities / Sketch views | Existing Entities pages, Cytoscape explorer, Maps Canvas, saved sessions |
| Review | Queues, evidence inspector, human decisions, contextual assistant | Stage 1–5 curation services, existing interpretation review, Review profile |
| Settings | Plugins, AI providers, security and operations | Existing configuration, permissions, provider and plugin registries |

## Files & Datasets

- Files tab preserves the existing drive/folder/file browser, search, selection and annotations.
- Datasets tab presents recognized datasets with filtering, membership, scientific metadata, interpretation, and study links.
- Shared inspector must support **docked**, **expanded**, and optionally **detached** modes. Retain selection, drive path and tab state across resizing and navigation.
- Inspector tabs: **Metadata**, **Annotations**, **Provenance**.
- Metadata must support filesystem properties, scientific metadata, nested raw JSON/XML, field-level provenance, dataset aggregation and distinctions among observed, inferred and confirmed values.
- Reuse the existing Annotations page functionality rather than reimplementing annotation storage.
- **Prepare for Sharing** remains a prominent dataset action, invoking the actual NIH DMS Plan exporter; label the output as a draft requiring investigator review.
- **+ Drive** is an admin-only action. Discover rclone remotes using the effective SciDK service-account configuration, not the browser. Validate access read-only; never expose credentials or allow arbitrary path registration.

## Knowledge workspace

The two independent axes are **domain** (Research, Ontology, System) and **view** (Graph, Entities, Sketch).

- **Graph:** Existing Cytoscape exploration, expansion, filtering, styling, saved layouts.
- **Entities:** Existing powerful entity browsing, properties, relationships, schema editing where authorized.
- **Sketch:** Existing persistent Maps Canvas, domain-aware draft creation, grounding, and curation proposals.
- **Research Sketch:** Proposed scientific nodes, properties and relationships.
- **Ontology Sketch:** Proposed SciDK schema extensions, external ontology selections and mappings; never mutate authoritative external vocabularies directly.
- **System Sketch:** Proposed workflow, documentation and tool relationships; canonical code/docs remain authoritative.
- Sketches are private by default and can be shared explicitly. Sketch content is not automatically accepted knowledge.
- Layouts: Single, Split, Three panes; eventually drag-to-dock, resizable panes, per-user persistence and reset. Verify Cytoscape resize and session restoration.

## Minimal reasoning and enrichment

A Sketch may mark unresolved nodes or edges. **Detect gaps** creates suggestions based on bounded checks. **Investigate** creates an authorized, source-restricted enrichment task. Agents/plugins return evidence and proposed CurationAssertions. Reviewers alone accept or reject; only approved materialization changes accepted knowledge. Implement one end-to-end task before generalizing.

## Chat contexts

One shared chat infrastructure with two declarative profiles:

- **Overview:** accepted/permitted knowledge discovery, explanations and citations; no proposals by default.
- **Review:** permitted assertion/evidence context, uncertainty investigation, comparisons and proposal drafting; no agent acceptance/materialization.

Authorization is enforced by the backend, never by prompt alone.

## Resources and plugins

Keep the existing Source → Schema → Mapping builder. Add text/JSON import-export, validation, diff and preview without losing advanced configuration. Plugins are **direct sources with declared capabilities** (discover, query, import, resolve, interpret, enrich, validate, export, Sketch import). MeSH/PubMed, NExtSEEK, TCGA/GDC, pathways and NC3Rs EDA are optional source plugins, not SciDK Core dependencies.

## Cross-page continuity — recommended enhancement

Preserve the selected dataset/entity, filters, drive path and provenance references as the user moves Files → Knowledge → Review → Files. Offer a visible breadcrumb or 'return to source' link.

## Additional product improvements

1. **Dataset readiness summary:** Show missing metadata, unreviewed interpretations and sharing prerequisites without claiming NIH compliance.
2. **Field-level trust indicators:** Make provenance, citation and knowledge status inspectable beside important metadata values.
3. **Saved workspaces:** Preserve Knowledge layouts, graph filters and Sketch sessions per user; default Sketch to private.
4. **Contextual actions:** 'View source files', 'Open graph', 'Investigate gap', 'Propose correction', 'Prepare for sharing' should follow the selected object.
5. **Clear source freshness:** Display last scan/import and ontology/source versions, and distinguish stale evidence from accepted but older knowledge.
6. **Progressive disclosure:** Keep Overview uncluttered, while Review exposes the full audit trail.


## Stage 6 integration findings — mandatory corrections

- **Dataset-scoped NIH DMS export:** The existing exporter reportedly summarizes the *whole graph*. The redesigned dataset action must accept a stable dataset identifier, use only authorized dataset-specific metadata and relationships, identify unknown/investigator-supplied fields, and produce a clearly labeled draft. Do not expose the old global exporter under a dataset-specific label. Preserve the legacy export route for compatibility if needed. Test two distinct datasets to prove no cross-dataset leakage.
- **Overview isolation:** Stage 6 fixed a cross-profile leak. Overview must show only currently supported accepted facts even if its user also holds Review grants. Enforce this server-side; add a regression test at the GUI-to-API boundary.
- **Review integration:** Build an actual authorized review queue, evidence inspector, and human-only decision controls using Stage 1–6 contracts. An assistant may inspect and propose but cannot accept, reject, supersede, or materialize.
- **Sketch integration:** Reuse persistent Maps Canvas. Keep draft sketches separate from accepted research facts; implement a minimal, manually triggered Sketch-to-proposal adapter and bounded enrichment task only after the security contracts are verified.
- **Graph-write gate:** Live disposable Neo4j materialization/recovery integration remains unverified. Keep new write flows default-off for production and never use a production connection for destructive tests.
- **Preservation:** Existing Entities, Cytoscape, Annotations, Resources wizard, saved maps/canvas sessions, file browser, and scanner/import/profile paths are required compatibility surfaces.

## Required implementation slices and test ownership

| Slice | Deliverable | Key acceptance check |
|---|---|---|
| GUI 1 | Component/route inventory and migration map | Every legacy capability mapped; no rewrites without rationale |
| GUI 2 | Six-destination shell and central Overview chat | Deep links preserved; accepted-only query enforcement |
| GUI 3 | Files/Datasets and metadata inspector | Drive tree, dataset selection, raw metadata, annotations, provenance, expand/restore state |
| GUI 4 | Selected-dataset DMS adapter | Two datasets produce different scoped drafts; no unrelated/restricted facts |
| GUI 5 | Knowledge domains x Graph/Entities/Sketch | Existing Cytoscape, Entities, Canvas, saved state reused |
| GUI 6 | Review and contextual assistant | Human-only decisions; review context and citations visible |
| GUI 7 | Resources/plugins and optional docking | Existing mapping JSON round-trip; capability registry; Cytoscape resizes |
| GUI 8 | NCI rehearsal and regression | Discover → Structure → Connect → Curate → Prepare to Share in redesigned GUI |

Run focused UI/service tests for each slice, and one broad regression suite at the end. Do not duplicate Stage 1–6 backend tests in browser fixtures.

## Implementation sequence

1. Audit existing routes/templates/JS and map every target view to reusable components.
2. Implement shell/navigation and Overview; preserve legacy deep links.
3. Implement Files/Datasets tabs and shared metadata inspector; test annotations and DMS export.
4. Consolidate Knowledge around existing Entities, Cytoscape and Canvas; add domain/view controls.
5. Implement Review queue and assistant integration using existing secure APIs.
6. Extend Resources mapping and capability-based plugin configuration.
7. Add docking/persistence and minimal enrichment task flow, if stable.
8. Run browser smoke tests, permission checks, saved-state regression, and the full NCI demonstration narrative.

## Acceptance gate

The redesigned interface must support: browse drive → select/recognize dataset → inspect rich metadata → annotate → view graph → sketch missing context → submit a cited proposal → human review → retrieve supported knowledge → export NIH DMS Plan draft. Existing scanner, importer, annotation, mapping, saved map and export workflows must remain functional. Never claim a simulated wireframe control is a production implementation.
