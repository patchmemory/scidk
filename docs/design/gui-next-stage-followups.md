# Agreed GUI and security follow-ups

Preserved from `scidk_prompt14_handoff/ux-and-security-followups.md` during
Prompt 14. These are next-stage requirements, not capabilities implemented by
the Review workspace. Prompt 14 does not begin Prompt 15.

## Prompt 15: Resources, Annotations and legacy dataset reconciliation

- Preserve the existing Source -> Schema -> Mapping builder and Annotations workflows.
- Inspect admin-only environment credential import and shared-provider use. Add negative non-admin API tests, no secret disclosure, and approved-model restrictions. Do not leak keys to browsers/logs.
- Design safe onboarding/reconciliation of legacy recognized datasets into curated Dataset/File/CONTAINS identities without fabricated human acceptance or ontology changes.
- Keep dataset-scoped NIH DMS export and guided/advanced sharing packages working with authorized curated fixtures; report real-data blockers.

Prompt 14 narrowly fixes environment import authorization and error disclosure
and adds negative tests for that route. Prompt 15 still owns the broader settings
and shared-provider audit, server-only shared credential resolution, negative
authorization tests across provider APIs, and discovered-versus-approved model
restrictions. Do not infer approval from model discovery.

## Prompt 16: UX consolidation

- Knowledge Graph: group advanced layout/filter/style controls behind a Tools affordance; improve status messaging and search discoverability.
- Entities: distinguish empty results from authorization failure and uncurated legacy data; offer safe next steps.
- Sketch: move from text-field-first node/edge creation to canvas-first visual interaction, retaining advanced fields in inspector; reuse existing Cytoscape/Canvas primitives.
- Improve cross-page context trail, shared inspector, responsive layout and accessible keyboard flow.
- Preserve strict authorization; never populate blank graph via raw legacy APIs.

Tracked findings from Prompt 13 screenshots: crowded Knowledge toolbars, a
form-heavy Sketch editor, unclear disclosure refusal wording, and empty
Entities/Graph states without actionable explanation. These remain open for
Prompt 16. Review-specific presentation changes do not resolve these issues.

## Prompt 17: Demo rehearsal

- Run Overview -> Files/Datasets -> Metadata -> Knowledge -> Review -> NIH DMS draft / dataset package.
- Verify approved synthetic or authorized curated data, real Parley smoke test if permitted, live Neo4j integration only in disposable target, and PowerShell package script on Windows.
- Review screenshot baselines with a human, capture defects, freeze a known-good demo build.

## Later: Controlled Burn

- Follow `docs/roadmap/scidk-controlled-burn-fast-follow.md` after internal demo feedback.
