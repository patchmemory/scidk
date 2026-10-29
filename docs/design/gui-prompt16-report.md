# Prompt 16 — Product UX consolidation and Ask SciDK

Worktree: `/home/patch/Projects/scidk-knowledge-curation`.
Branch: `design/knowledge-curation-20261029`.
Starting HEAD: `aedc16637ce180a4bcab1b242567d7ad17f00759`.
Implementation commit: `ea4ab107a410d873ac5516fadaa4895ba92c9de1`.
This report is committed separately so it can name that exact revision.
The complete 56-file implementation/candidate manifest is available with
`git show --stat ea4ab107a410d873ac5516fadaa4895ba92c9de1`.
The saved `scidk_prompt_16_01.txt` authorizes this implementation of
`codex_prompt_16.txt`. All pre-existing untracked prompts, handoffs, ZIPs,
vision/demo/roadmap documents and secret-key file remain untouched and uncommitted.
Prompt 17 was not begun.

## Design-to-component mapping

The pre-edit mapping used the actual `scidk-gui-v3.html` visual target and bundled
human UX checklist, not only its routes:

| Wireframe intent | Reused component / implementation |
|---|---|
| Dark sidebar, pale workspace, rounded surfaces, blue primary actions | `base.html` plus opt-in `gui_design.css` tokens and reusable selectors across all six destinations |
| Central Ask SciDK, suggested questions, scoped sources | Existing Overview template, JavaScript and fixed-profile transport; bounded released-record discovery adapter |
| Canvas-focused Knowledge with optional advanced tools | Existing Knowledge template, SciDKGraph/Cytoscape and Canvas primitives; collapsed layout/filter/style controls |
| Visual private Sketch | Existing provisional nodes/edges and CanvasService persistence; click-to-place, node-to-node connection, drag and inspector name editing |
| Dataset metadata and provenance inspector | Existing Files browser, GUI inspector and Annotate drawer; docked/expanded behavior and sharing controls retained |
| Resources Source → Schema → Mapping | Existing source pages, templates, schema/mapping engine, FAIR and run/history paths, with shared shell styling |
| Evidence-first Review | Existing real queue, evidence, human confirmation and assistant contract, styled through shared components |
| Consistent workflow trail | Shared workspace trail, stable Knowledge/Files-to-Ask links and existing Review return links |

## Implemented researcher experience

Overview now presents a question box, optional “My accessible knowledge”, “System
documentation” or inherited “Current selection” scope, suggested questions and an
explicit disclosure checkbox. It requires no manual node ID, model selector or
context tool. Ask is a deliberate action; suggestions never send requests or check
consent. Scope changes clear the answer, sources and consent. Late replies are
ignored after question/context changes. Retrieved facts and authorized citations
appear separately from the AI interpretation, with same-origin Knowledge links.
Advanced explicit-ID API requests remain compatible.

The shared opt-in GUI stylesheet implements the wireframe sidebar, typography,
spacing, cards, inputs, buttons, focus states, badges and responsive surfaces.
Legacy installations with GUI v3 off retain their existing shell. The actual
Files browser, Annotations drawer, Resources builder and Review remain in use.
No fictional metrics or populated scientific results are added to empty services.
Settings uses the existing vendored Cytoscape asset, resolving its known offline
CDN dependency without replacing its scientific schema-map functionality.

Knowledge keeps Research/Ontology/System and Graph/Entities/Sketch. Primary actions
remain visible; layout, relationship filters and styling are collapsed in Graph
tools. Wide displays place the inspector alongside the canvas; narrower layouts
stack it. Source JSON/provenance is inspectable on demand. Service-disconnected
and authorization-refused states are distinct from an authorized empty result.

Sketch has Place a node and Connect drafts modes: click the canvas, drag nodes,
select two nodes to connect, and rename a selected draft in the inspector. Typed
IDs remain available under advanced draft tools for compatibility but are not
needed for routine connections. Save/load continues through the existing private
CanvasService. No assertion submission, review decision or authoritative graph
write is added. Stable source references remain subject to reauthorization.

## Bounded discovery contract

`scidk/services/overview_discovery.py` implements a deterministic first slice,
reusing the Stage 3 current-support serializer, authorized ResearchReader,
System/Ontology fixed tools and existing Overview transport:

- Research lookup searches released type/properties after current support,
  applied receipt, source/evidence and property checks. Raw candidate identity
  claims and legacy graph data are never searched. Existing Research discovery
  scans at most 500 ledger candidates and a 2 MiB serialization budget; the first
  slice refuses if the authorized result set would require a second 25-item page.
- System lookup considers at most 64 configured projection entries and searches
  only successfully disclosed nodes, at depth zero/limit one. Raw names, hidden
  metadata and inaccessible identifiers are not used as previews or matches.
- At most 16 meaningful lexical terms, three matches and 48,000 serialized context
  bytes. Name/property matching uses normalized words, simple plural handling and
  at least two matching terms when the question has multiple terms. It is not an
  embedding engine or general natural-language query planner. Broad results are
  refused rather than silently truncated. Each lookup has a three-second deadline;
  Research SQLite uses a deadline progress handler. Discovery transport uses the
  existing one-call provider client with a 30-second timeout and 1,200-token cap.
- Current selection accepts a stable Research/System/canonical Ontology identity,
  reauthorized at every use; selection is not an authorization grant. No default
  external ontology catalog is inferred from a browser label.
- The fixed Overview tool/profile and exact approved provider are rechecked before
  transport. Lookup/context and credential/support/grants are rechecked after
  transport; changed or revoked context refuses the reply. No model-selected
  tools, arbitrary Cypher, autonomous agent, new history replay, or proposal path.
- Same-origin unlocked named-cookie session and explicit consent are required for
  the new discovery path. Tokens, header sessions, anonymous/no-auth, locked and
  cross-origin requests are denied. Existing credential/bootstrap/backup gates,
  shared credential ownership and exact model approval remain intact.

No matches returns a neutral authorized-empty message without hidden-record counts.
Missing configured services is reported as unavailable. Policy refusal exposes no
record existence. Exceeded limits ask the user to narrow the question. No provider
call occurs in these cases. A successful match alone never approves a model or
confers Resource/evidence permissions. The explicit-ID endpoint remains available
for advanced/API use with its previous fixed tool contract.

Supported first slice: named dataset/entity lookup, System documentation topic
lookup, and questions about a selected authorized record. Unsupported: general
aggregation, multi-hop arbitrary research questions, unconstrained comparisons,
semantic retrieval, inferred relationships, unknown external catalog selection,
and unrestricted freeform/history chat. No unsupported question is translated to
raw queries or given fabricated facts.

## Validation and visual evidence

Before candidates: `/tmp/scidk-prompt16-before` (22 visual/geometry checks passed).
After candidates: `/tmp/scidk-prompt16-final`; final targeted visual refresh:
`/tmp/scidk-prompt16-visual-final`. Selected before/after and real workflow images
are committed in [gui-prompt16-candidates](gui-prompt16-candidates/README.md).

| Check | Result |
|---|---|
| Focused Prompt 15/16 policy, source lookup, context, shared-provider and security checks | **22 passed**, 28.71 s |
| Clean backend regression: `PYTHON_DOTENV_DISABLED=1 python -m pytest tests/security tests/knowledge_e2e tests/pipeline tests/test_dev_gui.py tests/test_llm_provider_settings.py tests/test_auth.py -q -o addopts=''` | **632 passed**, 180.14 s; no skips/xfails |
| Full browser regression/candidate capture: `PYTHON_DOTENV_DISABLED=1 python -m pytest tests/gui -q -o addopts='' --gui-record-candidates --gui-artifacts /tmp/scidk-prompt16-final` | **57 passed**, 133.99 s; no skips/xfails |
| Final targeted visual/Knowledge/Ask checks after selected-tab contrast and canvas zoom corrections | **36 passed**, 94.13 s; no skips/xfails |
| `git diff --check` | Passed |

Use `/home/patch/PycharmProjects/scidk/.venv/bin/python`. Initial regressions found
narrow inspector overflow and the Settings fixture's newly reachable schema-map
request. Both were corrected; Settings' old strict expected failure was removed
when its bundled graph library made offline loading work. Clean final results
above supersede early mixed-revision runs. The original visual references are not
auto-updated or approved.
Frozen `tests/gui/baselines` remain unchanged. The browser capture flag deliberately
skips old pixel-baseline acceptance while retaining workflow, geometry, responsive,
keyboard, focus, outside-request blocking and console-error assertions. Capturing
new design candidates is not a claim that the old pixels still match or that a
human has approved the new design.

Backend fixtures use real isolated policy, ledger, Review and fake graph writers.
Ask browser tests use actual governed services and loopback deterministic HTTP
transport. Legacy file/annotation/Settings display fixtures and sharing presentation
responses are explicitly synthetic/mocked. No live institutional content, live
provider, production database or operational ontology was used. Tests cover
no-ID lookup, accepted/applied support, hidden-property and cross-user isolation,
consent, model approval, selected context, citations, revoked grants, bounded
lookup, profile injection, token/header/cross-origin/locked denial, visual private
Sketch persistence, Graph/Entities navigation, Review controls and legacy routes.

## Wireframe gap assessment and Prompt 17 blockers

| Target | Assessment / remaining gap |
|---|---|
| Shared polished shell | Implemented sidebar/tokens/cards/control hierarchy. Mature embedded scientific tools retain their own detailed layouts; this is not a pixel-identical rewrite of every legacy panel. |
| Ask without IDs | Implemented bounded lexical discovery, grounded source links and interpretation separation. General semantic/analytical chat is unavailable. |
| Executive metrics | Not invented: no governed summary contract wired for those wireframe metric cards. Workflow cards provide real navigation instead. |
| Files inspector | Native metadata/annotation/provenance and expansion preserved. Rich nested metadata still exposes raw JSON/XML details; complete field-level trust visualization remains future work. Narrow layouts stack the docked inspector with bounded scrolling. |
| Knowledge graph | Primary canvas and collapsed tools implemented. Complete drag-to-dock multi-pane composition is unavailable; existing saved single/split/three layout preferences remain. |
| Visual Sketch | Placement, drag, connection and name editing work with private persistence. Investigation, automatic enrichment, Sketch-to-assertion translation and direct commit remain explicitly unavailable. |
| Resources | Real builder/validation/runs retained. One unified in-page Sources/Builder/Runs composition, arbitrary JSON round-trip and capability-source expansion remain unimplemented/unverified. Some preserved advanced legacy graph pages still use external scripts. |
| Review | Existing real queue/evidence/human confirmation retained and restyled. Live Review backend, grants, model and operational context still need trusted assembly. |
| Continuity | Stable Files/Knowledge-to-Ask and Review return links plus workspace trail. Comprehensive cross-page filter/drive-path history and detachable inspectors are not implemented. |
| Human acceptance | Candidates at 1440×900, 1280×800 and 1024×768 require human review; checklist is not auto-approved. |

The running port-5001 service was not restarted or reconfigured. Prompt 15's live
named-auth/flag/service/model/grant blockers therefore remain unverified until an
operator activates the separate authenticated development setup. See the updated
`gui-development-startup.md`: its local fake-provider System example now uses a
question rather than a context-ID field. No paid provider calls were made;
user-reported cumulative Parley spend **$15.91** is unverified.

Operational Dataset identity/evidence/ontology reconciliation, accepted/applied
membership, service assembly, exact destination approval and a consented live
provider smoke test remain demo blockers. Live disposable Neo4j/Windows package
validation and human screenshot approval belong to the later rehearsal; none was
started here. No material security or ontology policy change was required.
