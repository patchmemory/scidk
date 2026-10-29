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

## Prompt 15 implementation checkpoint

Prompt 15 adds named-admin boolean readiness, an isolated authenticated development
launcher and tiny synthetic System hook, deterministic HTTP-provider verification,
server-only shared usage grants, approved global credential/configuration gates,
and a trusted first-admin bootstrap transition. See
`gui-development-startup.md`, `gui-prompt15-reconciliation.md` and
`gui-prompt15-report.md` for exact scope and validation.

Resources Source → Schema → Mapping and the native Annotate drawer are retained;
`/annotations` is a route adapter. JSON builder round-trip and new capability-based
source operations remain unavailable/unverified. Live Dataset onboarding requires
operational ontology reconciliation, source-scoped evidence, named human review
and applied support; no automatic acceptance or bulk migration was performed.

Port 5001 was observed with named auth and Overview/Review flags off. A separate
port-5002 startup is documented; the existing listener was not restarted. The
System-only development hook does not supply research assertions or ReviewService.
Operational Knowledge/Review assembly, exact model approvals, real Resource/evidence
grants and live provider connectivity remain configuration/integration work.
User-reported Parley checkpoint remains $13.44 cumulative and unverified; Prompt 15
made no paid requests. Browser artifacts are unapproved candidates; no baseline
was accepted automatically. Prompt 16 and 17 requirements above remain open.

## Prompt 16 implementation checkpoint

Shared opt-in sidebar/design tokens, no-ID bounded Ask SciDK discovery and linked
sources, progressive Knowledge tools, visual private Sketch placement/connection,
and stable Files/Knowledge-to-Ask links are implemented. Settings now uses the
bundled Cytoscape asset. See `gui-prompt16-report.md` for limits and wireframe gaps;
its human acceptance checklist remains pending. Existing tools and security gates
are retained. Semantic/freeform retrieval, fictional dashboard metrics, complete
field-level trust rendering, drag-to-dock, unified Resources builder composition
and full cross-page history are not claimed as implemented. No paid calls or
existing service restart occurred. User-reported spend is now $15.91, unverified.
Prompt 17 remains unstarted and retains the operational/demo blockers above.
