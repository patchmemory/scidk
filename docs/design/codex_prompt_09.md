# Codex Prompt 08 — SciDK GUI v3.1: Audit and First Working Slice

Continue in the isolated SciDK development worktree. Stage 6 was reported complete at `0896c5a` (666 passed, 0 failed, 1 skipped). **The new GUI is in scope for the NCI development build.**

## Inputs

Read the following from the repo (copy the accompanying handoff files into `docs/design/` first):
- `docs/design/scidk-gui-v3-spec.md` — implementation contract, including Stage 6 addendum.
- `docs/design/scidk-gui-v3.html` — visual prototype, **not production code**.
- `docs/vision/scidk-vision-v1.1.md` and its scope addendum.
- `docs/demo/nci-2026-demo-plan.md` and its scope addendum.
- `docs/architecture/knowledge-curation-stage-6.md` and relevant Stage 5 interfaces.

## Stage A: Focused inventory (do not skip)

Inspect existing routes, templates, JS, and services for the current file browser, datasets, annotations, Entities pages, Cytoscape/Maps, Canvas persistence, Resources Source/Schema/Mapping builder, NIH DMS exporter, chat/Parley, and Stage 1–6 curation APIs. Create `docs/design/scidk-gui-migration-map.md` mapping **each existing capability and route** to its new location and noting compatibility/deep-link risks. Avoid broad repository rediscovery; inspect only relevant files.

## Stage B: Implement the first usable GUI slice in this same pass

1. Add the six-destination shell: Overview, Files & Datasets, Resources, Knowledge, Review, Settings. Preserve existing routes via aliases or redirects where needed. Do not remove old pages.
2. Build the **central Overview chat** using the existing provider/session/tool infrastructure and the Stage 5 Overview profile. Enforce Stage 6 accepted-only support filtering on the server; no proposed/rejected/unsupported facts even if the user has Review grants. If live chat cannot be safely wired, show an honest disabled state rather than a fake answer.
3. Create **Files & Datasets** with two tabs. Mount/reuse the existing file browser in Files; expose recognized datasets in Datasets using actual available services. Keep Annotations reachable.
4. Implement a shared **Metadata / Annotations / Provenance** inspector with docked and expanded modes, selection preservation, nested/raw metadata support, and clear file-versus-dataset semantics. Reuse existing metadata and annotation services.
5. Add the **Prepare for Sharing** action from a selected dataset. The Stage 6 report says the legacy NIH DMS exporter summarizes the entire graph. **Do not mislabel it as dataset-scoped.** If a safe scoped adapter cannot be completed in this pass, show an explicit unavailable state and document the next required backend task. Do not expose unrelated or restricted data.

## Constraints

- Work in the isolated worktree; check git status and preserve uncommitted files.
- Reuse existing frontend architecture; do not paste the wireframe HTML into production.
- No production database writes, schema migrations, arbitrary Cypher, or changes to the canonical scan/import/profile pipeline.
- No agent review/accept/materialization. Keep experimental features default-off.
- No new plugin harvesting, docking library, or broad Knowledge/Review rewrites in this pass. Those follow in later GUI slices.
- Keep existing Entities, Cytoscape, Canvas, Resources builder, saved maps, annotations, and DMS exporter functioning.

## Validation and reporting

Add targeted tests for navigation and legacy route continuity, Overview profile isolation, Files/Datasets selection, inspector state, and DMS action safety. Avoid duplicating Stage 1–6 backend unit tests. Run focused tests during development and one relevant regression run at the end.

Deliver: migration map, working first GUI slice, concise implementation report, changed-file list, test counts (pass/fail/skip), screenshots if the local renderer/browser is available, known blockers, and focused commit hash. Stop for approval on material security or ontology conflicts. **Do not begin the next GUI slice until review.**
