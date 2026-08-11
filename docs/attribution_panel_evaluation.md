# Attribution Panel UX Redesign — Evaluation Pass

Evaluation only. No implementation code. Written against `production-mvp` at `84b0e27`.

Files read: `scidk/services/folder_attribution.py` (all 609 lines), `scidk/web/routes/api_files.py:2055-2404`,
`scidk/ui/templates/datasets.html:560-719` + `:3665-4067`, `scidk/services/filter_builder.py` (all),
`scidk/web/routes/api_graph.py:1035-1364`, `scidk/ui/static/js/filter_builder.js`,
`scidk/ui/templates/base.html`, `tests/test_attribution_service.py`.

There is no `scidk/web/routes/api_schema.py` and no schema introspection in `scidk/core/graph.py`.
The schema API lives in `api_graph.py` under `/api/schema/*`, and the introspection logic lives in
`scidk/services/filter_builder.py`. That relocation matters to all three questions.

---

## 1. Current state

The attribution feature is three clean layers. `FolderAttributionService` is a heuristic **path-string
matcher**, not a graph traversal engine: it expands an anchor's `name` into ~10 spellings
(`_name_variants`), asks the database for every target node whose `path` contains any of them
(`_fetch_folders`), then scores each hit **in Python** by depth below its scan root, modality keyword
presence, and whether the matched spelling was the anchor's own or a labmate's (`_score`). Seven routes
in `api_files.py` wrap it — five GETs that populate pickers (`anchors`, the deprecated `persons` alias,
`anchor-properties`, `anchor-property-values`, `relationship-suggestions`) and two POSTs that do the work
(`candidates`, `confirm`). Every query is a single round trip, values always travel as bound parameters,
and the three identifiers that *must* be interpolated (anchor label, target label, relationship type) are
whitelisted through `filter_builder._validate_identifier` / `_validate_rel_type` first. The UI is a flat
vertical stack of fixed controls (`datasets.html:560-719`) driven by ~400 lines of module-scope functions
and four module-scope `let` variables, with shadow selection state in `_attrSelectedAnchor`. The service
is well-factored and the boundaries are already in the right places; the panel is the weak layer.

**The single most important finding for scoping:** `scidk/ui/static/js/filter_builder.js` already
implements the proposed three-section structured query builder — blocks of `{label, match, conditions[],
via}`, format-aware operators per inferred type, property pickers fed from `/api/schema/property-types`,
relationship picker fed from `/api/schema/relationship-types` — and `filter_builder.py` already turns that
exact object into parameterized Cypher, with tests (`tests/test_filter_builder.py`). It is loaded globally
in `base.html:369` and **instantiated nowhere**. The redesign is largely describing a component that
already exists and is unused.

---

## 2. Question 1 — Relationship section property filters

### Does the candidate query traverse relationships? No.

`_fetch_folders` (`folder_attribution.py:584-608`) is the entire candidate query:

```
MATCH (f:{target_label})-[:SCANNED_IN]->(s:Scan)
WHERE ($sources IS NULL OR s.host_id IN $sources)
  AND any(v IN $needles WHERE toLower(f.path) CONTAINS v)
```

The one relationship it traverses, `SCANNED_IN`, is not an anchor→target relationship — it exists only to
fetch `s.host_id` and `s.path` for source scoping and depth computation. **The anchor node is never
matched in the candidate query at all.** The anchor contributes nothing but strings: `get_candidates`
turns `anchor_name` into `$needles` via `_name_variants`, and `$needles` is the only trace of it that
reaches the database. Matching is purely `CONTAINS` on `f.path`.

So yes — interpretation A requires a fundamentally different query strategy. It would have to match the
anchor and an existing edge, something like `MATCH (a:Anchor {name:$name})-[r:REL]->(t:Target) WHERE <r
property conditions>`, which is a different query *shape* (relationship-anchored rather than
string-anchored) and a different result set.

### Interpretation A is close to self-defeating

Beyond the query cost, A contradicts the panel's purpose. Attribution exists to surface targets that are
**not yet** connected to the anchor so a staff member can create that edge. Pre-filtering candidates by
properties on an existing anchor→target relationship restricts the result set to targets that are
*already attributed* — the panel would only ever return edges it had previously written. That is a useful
feature ("review my past confirmations, filtered by who confirmed them"), but it is a **review/audit
view, not a candidate search**, and putting it in the Relationship section of a find-candidates form
would mislead the user about what the form does.

### Adding write-time edge properties is nearly free

`confirm` (`:448-501`) currently writes three properties in its `ON CREATE SET`:

- `rel.confirmed_by = $by` (from `g.scidk_user`, defaulting to `'system'`, set at `api_files.py:2392`)
- `rel.confirmed_at = $ts` (UTC ISO-8601)
- `rel.method = 'attribution_panel'` (a literal)

Passing additional caller-supplied pairs through is easy, and there is a mechanism that avoids the usual
property-key problem entirely. Property keys normally cannot be bound as parameters, so they would each
need `_validate_identifier` and interpolation — but Cypher's map-merge form, `SET rel += $props`, is valid
on relationships and accepts the whole dict as **one bound parameter**. Placing the map merge *before* the
three fixed assignments means the reserved provenance keys always win, so a caller cannot spoof
`confirmed_by`. That is a handful of lines in one method, plus reading one key in the route.

Two caveats worth stating in the implementation prompt, neither structural:
- Neo4j properties must be scalars or homogeneous arrays of scalars; nested maps/objects raise at write
  time. The value side needs a shallow type check, and the route should return 400 rather than 502.
- `ON CREATE SET` means properties land only on newly created edges. Re-confirming an existing edge with
  a new `project` value writes nothing and reports as `skipped`. That is the current semantics for
  `confirmed_by` too, so it is consistent, but the UI should not imply an update.

### Recommendation: **Interpretation B — edge metadata written at confirm time**

Four reasons:

1. **Architecture.** B is a contained change to one method. A is a new query strategy in the one method
   whose current strategy (string matching, anchor absent) is the feature's whole design.
2. **Coherence.** A "Relationship" section sitting between Anchor and Target reads naturally as *"this is
   the edge you are about to write."* B makes the section describe its own subject. Under A the section
   would silently be a filter on edges that already exist — the opposite of what the panel writes.
3. **The design intent is already B.** `confirmed_by` / `confirmed_at` / `method` are exactly
   "metadata written onto the edge at confirm time." B generalizes an existing pattern rather than
   introducing one.
4. **Researcher value, grounded in this repo.** The task's own example, `project = CAC-2024-0042`, matches
   a real property in this codebase: `cleanup_usage_event_contamination.py:7` queries
   `(:Project)-[:PI_OF]-(:Person)` with `p.cac_protocol`. Tagging an attribution edge with the CAC
   protocol it was performed under is precisely the provenance a core facility needs to defend an
   allocation later — and it is per-edge, so it cannot be reconstructed from anything else afterwards.

If the review-past-confirmations capability is wanted, it is a separate read-only view over
`(:Anchor)-[r:REL]->(:Target)` filtered on `r.*`, and it should not be folded into this panel.

---

## 3. Question 2 — Generalizing labmates

### How the traversal is expressed

`_get_labmates` (`:569-582`):

```
MATCH (p:{label} {name: $name})-[:MEMBER_OF]->(lab:Lab)<-[:MEMBER_OF]-(lm:{label})
WHERE lm.name <> $name
RETURN DISTINCT lm.name AS name
```

`MEMBER_OF` is **hardcoded**, and so is nearly everything else that matters: the intermediate label
`:Lab`, the direction (outbound then inbound), and the hop count (exactly two). Only `label` is
parameterized — and it is reused for *both* ends, so a labmate must carry the same label as the anchor.
The one thing that comes back is a list of **names as plain strings**.

That last detail is the important one, and it cuts strongly in favor of generalizing.

### `labmate_variants` is loosely coupled — the seam is already clean

In `get_candidates` (`:383-441`) the flow is: labmate names → `_name_variants` per name → concatenated
into the single `$needles` list handed to `_fetch_folders` → in the Python scoring loop, own variants are
tested first and related variants second, with a hit on the latter setting `is_labmate_folder=True` →
`_score` maps that flag to MED (with a modality hit) or LOW.

So the entire coupling between labmate discovery and candidate scoring is **"a list of related names."**
Any traversal that returns names plugs in with **no changes to the scoring logic whatsoever**. What is
labmate-specific is only naming and copy: the `labmate_variants` local, the
`AttributionCandidate.is_labmate_folder` field, and two reason strings in `_score` (`"labmate folder ·
…"`). Generalizing means renaming those to something like `related_names` / `is_related_match` and making
the reason string carry the pattern's label instead of the word "labmate". The dedup step that keeps own
variants out of the related list (`own_lower`, `:390-391`) and the first-hit-wins specificity ordering both
stay correct unchanged.

This is the cheapest of the three changes evaluated here, and it is cheap because the existing code
already put the seam in the right place.

### What the schema API exposes today

| Endpoint | Returns | Useful for a rel picker? |
|---|---|---|
| `GET /api/schema/labels` (`api_graph.py:1227`) | flat label list via `db.labels()` | labels only |
| `GET /api/schema/relationship-types` (`:1251`) | flat rel-type list via `db.relationshipTypes()` | **yes, but unscoped** |
| `GET /api/schema/property-types?label=` (`:1278`) | properties + inferred type + sample for one label | yes, for property rows |
| `GET /api/schema/map` (`:1035`) | Cytoscape nodes/edges **with source/target labels per rel type** | yes, but APOC-dependent |

A freeform relationship picker is therefore feasible **with zero backend work** — `/api/schema/relationship-types`
already exists and `filter_builder.js` already consumes it (`_loadRelTypes`). What is missing is *scoping*:
the flat list would offer `SCANNED_IN`, `INTERPRETED_AS`, `PREVIEW_ROWS`, `MAX_REPORTED_PROBLEMS` and
similar for an `Investigator` anchor, nearly all of which yield nothing. `/api/schema/map` has the
label-pair information but calls `apoc.cypher.run` (with a non-APOC fallback that loses the edge data),
opens and closes its own driver per request, and is built for graph rendering.

If scoping is wanted without APOC, `get_relationship_suggestions` (`:293-346`) is the template: it already
discovers types between a label *pair* from the live graph, merges them with seeds, drops non-uppercase
types, and dedupes. A sibling method returning types incident on a single anchor label is a small
addition in the same shape.

### The decisive point against pure Option A

**A naive freeform picker cannot express labmates at all.** "Labmates" is not "traverse `MEMBER_OF`" — it
is "traverse `MEMBER_OF` outbound to a `:Lab`, then inbound from a *sibling* of the same label." A picker
offering one relationship type and doing `(anchor)-[:REL]-(other)` would, given `MEMBER_OF`, return the
*Lab itself*, whose `name` is then expanded into name variants and matched against folder paths — quiet
nonsense rather than an error. Making Option A cover the current behavior means also exposing direction,
hop count, and intermediate label. That is a schema-query UI, and the users are facility staff doing
attribution, not graph modelers.

Grounding the other half: relationships that actually appear in this repo are `SCANNED_IN`, `CONTAINS`,
`INTERPRETED_AS`, `MEMBER_OF`, `PI_OF`, `INVOLVES`, `RETRIEVES`, `REFERENCED_NODE`, `CONNECTED_VIA`,
`ABOUT`, `HAS_FILE`, plus `SUBMITTED` / `COLLABORATES_ON` / `HAS_ATTACHMENT` in mapping fixtures. Of
these, only two connect people to people through an intermediate, which is the shape attribution needs.
A curated list is short because the useful patterns are genuinely few.

### Recommendation: **Option B — curated patterns, made declarative and data-driven**

Not hardcoded Cypher scattered through the service, but a module-level registry beside
`RELATIONSHIP_SUGGESTIONS`, each entry a friendly label plus the structural parts (`via` type,
intermediate label, direction, whether the far end shares the anchor's label), exposed over a new
`GET /api/files/attribution/traversal-patterns` so the UI stays a renderer of whatever the registry holds.
Maintenance is then one dict entry per pattern, matching the convention the module already established for
relationship suggestions — including its best property, that unlisted cases still work.

Keep the escape hatch, because the panel already has this exact idiom: the Relationship control pairs a
suggestions dropdown with an "or type custom" field (`datasets.html:641-650`, `toggleCustomRel`). A
"custom traversal" option following the same pattern gives Option A's generality to the rare user who
needs it without imposing schema knowledge on everyone else.

**Initial curated set.** Only the first is fully grounded in implemented code; the honest answer is that
the rest need one look at the live graph before shipping, and the prompt should say so rather than inviting
invention:

| Pattern | Traversal | Grounding |
|---|---|---|
| **Lab members** | `(a)-[:MEMBER_OF]->(:Lab)<-[:MEMBER_OF]-(other)` | Implemented today (`_get_labmates`). Certain. |
| **Project co-investigators** | `(a)-[:PI_OF]-(:Project)-[:PI_OF]-(other)` | `PI_OF` + `:Project` + `:Person` appear in a real maintenance script (`cleanup_usage_event_contamination.py:7`) and in `schema_intelligence.py:170`. Note both use `PI_OF` **undirected** — direction is evidently not consistent in the real graph, so this pattern should be undirected too. |
| **Collaborators** | `(a)-[:COLLABORATES_ON]-(…)-[…]-(other)` | Speculative. `COLLABORATES_ON` appears only in a mapping-UI test fixture (`tests/pipeline/test_mapping_ui.py:139`), never in service code. Confirm against the deployment graph before including. |

Two further notes. `ensure_person_label` (`:152-167`) backfills a shared `:Person` label across
`Investigator` and `User`, so patterns spanning both should anchor on `:Person` rather than reusing the
anchor's own label as `_get_labmates` does — that is a latent limitation of the current query worth fixing
while generalizing. And `:Lab` appears nowhere in this repo except `_get_labmates` itself and one plugin
field mapping (`plugins/ilab_table_loader/__init__.py:104`), meaning no ingest code in-tree creates
`MEMBER_OF` or `:Lab`; the current checkbox depends on data loaded from outside the repo. Worth verifying
it returns anything at all on the target deployment before building a UI around generalizing it.

---

## 4. Question 3 — Scope of the rebuild

### Multi-property anchor filtering does not belong in `/candidates`

`get_candidates` takes `anchor_name` — a **single exact name** — and `confirm` matches on
`{name: $name}`. Anchor property filters are not search parameters; they are a **picker-narrowing
device**, which is exactly what `list_anchors(filter_property, filter_value)` already is. Filtering by
`email` AND `lab` selects *which anchor*, and once one is selected the filters have done their job and are
irrelevant to the candidate query. So this belongs on the anchor-listing endpoint, and the `/candidates`
signature does not need to grow for it at all.

`list_anchors` currently accepts one property/value pair and one operator (case-insensitive `CONTAINS`,
`:215`). Extending that:

- **Repeated query params** on the GET (`filter_property=a&filter_value=1&…`) is order-coupled and
  fragile, and cannot express operators or `ANY` semantics.
- **Sequential frontend calls** technically work for the AND case — issue one filtered call per property
  and intersect by `name` client-side — but it is N round trips for one user action, cannot express `OR`,
  and cannot express anything but `CONTAINS`, so `size > X` or a date range is simply unavailable. It is
  not a viable strategy for the proposed format-aware controls.
- **A structured POST** delegating to `filter_builder.generate_cypher` is the clean answer, and this is the
  key point: **the backend already exists.** `filter_builder.py` accepts
  `{blocks: [{label, match, conditions: [{property, operator, value}]}]}`, whitelists all structural parts,
  binds every value, has a documented operator matrix per inferred type, and is already exposed at
  `POST /api/schema/filter-preview` with tests. The redesign's `{property, format, value, options}` rows
  are a near-exact restatement of it — "format" is `PropertyInfo.type`, "options" are
  `FilterBuilder.OPERATORS[type]`. No new Cypher generation has to be written for the anchor side.

### Target-side property filters are additional `WHERE` clauses — no new query shape

`_fetch_folders`'s `WHERE` is a conjunction already. `size > X`, `server IN [...]`, `date BETWEEN …` are
predicates on `f` and append as further `AND` terms on the same `MATCH`. No structural change, no second
`MATCH`, no `WITH`, no change to the `SCANNED_IN` join. Specifics:

- Property **keys** must be interpolated → one `_validate_identifier` per key, the rule already applied in
  `list_anchors` and `list_anchor_property_values`.
- `filter_builder._operator_to_clause(ref, op, value, params, param_idx)` produces exactly these fragments
  and takes the property reference as a string, so passing `"f.size"` reuses it verbatim. Its `$v0`, `$v1`
  parameter names do not collide with `$sources` / `$needles`. `between` on an ISO date already works via
  `_coerce_scalar`, which keeps strings as strings.
- `server IN [...]` is worth a look before building: source/host filtering already exists as the `sources`
  parameter (`s.host_id IN $sources`), so a target-side "server" row may be a duplicate control.
- Everything after the fetch is Python over returned rows, so target filters that prune heavily are a pure
  win — fewer rows on the wire — and **no scoring logic changes**.

### Reuse if the frontend sends structured filters

| Unchanged | Changed | New |
|---|---|---|
| `_name_variants`, `_relative_depth`, `_score`, `_resolve_keywords`, `confirm`*, `list_anchors`, `list_anchor_properties`, `list_anchor_property_values`, `get_relationship_suggestions`, `ensure_person_label`, `_session` | `_fetch_folders` (+ target conditions), `get_candidates` (+ target filters, + related names in place of `include_labmates`) | structured anchor search; traversal-pattern registry + route |

\* `confirm` changes only for Question 1's edge properties, which is independent.

That is **two methods touched**. The heuristic core — the part that encodes the actual domain knowledge
and would be expensive to get wrong — is untouched.

### Risk of Option B: low and contained

Five reasons it does not cascade:

1. The Cypher generator exists and is tested. The largest piece of new backend work is already written.
2. The validation boundary is already factored into two named guards used consistently.
3. Every method is single-purpose and single-round-trip; there is no shared query-building state to
   destabilize.
4. Nothing outside the attribution surface imports the service — verified: only `api_files.py`,
   `app.py:410-418` (for `ensure_person_label` at startup), and the tests.
5. `tests/test_attribution_service.py` uses a fake driver asserting on query text and bound params, so
   extending coverage is mechanical.

The one genuine risk is signature churn on `get_candidates`, which the route, the panel, and the tests all
call positionally-by-keyword. Mitigation: **add optional keyword params whose defaults reproduce today's
behavior**, and keep `include_labmates` accepted as a deprecated alias mapping onto the `lab_members`
pattern — the module already does exactly this for `person_name` / `folder_paths` / the `/persons` route,
so it is the established convention here. That lets the entire backend land while the current panel keeps
working unchanged.

There is one real gap to name: the existing tests cannot execute Cypher, and the module's docstring says
so plainly. Every new generated clause is therefore **unverified until run against a live graph**. That
deserves an explicit verification step, not an assumption.

### Recommendation: **Option B, minimally scoped — plus reuse `FilterBuilder` rather than writing a new builder**

Option A's coordination strategy is genuinely bad here (N calls per action, no `OR`, no operators beyond
`CONTAINS`), and Option B's backend mostly already exists. But "B" should be read narrowly:

**Do:**
- Add optional params to `_fetch_folders` / `get_candidates`; reuse `_operator_to_clause` for the clauses.
- Add one structured anchor-search endpoint delegating to `generate_cypher`.
- Add `relationship_properties` to `confirm` via `SET rel += $props`.
- Add the traversal-pattern registry and its route.

**Do not:**
- Replace the `/candidates` request contract with a single opaque structured object. `anchor_name`,
  `anchor_label`, `target_label`, and `sources` are fine as they are; the deprecated aliases and the
  existing tests depend on them, and restructuring buys nothing.
- Hand-write a new query-builder UI in `datasets.html`. **Spike instantiating `FilterBuilder` for the
  Anchor and Target sections first** — it is loaded globally, instantiated nowhere, and already does
  label pickers, per-type operator sets, dynamic condition rows, and a `via` relationship row with hop
  counts. If it fits, a large share of the "significant HTML/JS rewrite" becomes wiring.

Three caveats on that reuse, which the spike exists to settle: it has never run in production, so it is
unproven in the browser; it renders its own shell with Preview/Use/Save buttons that may not suit the
panel; and it fetches bare `/api/schema/labels` with **no `window.SCIDK_BASE` prefix** (zero occurrences
in the file, versus consistent use throughout `datasets.html`) — a real bug that breaks it under a
subpath mount and must be fixed before it can be relied on.

---

## 5. Stale anchor bug

**Confirmed, and worse than a stale search.**

`_attrSelectedAnchor` (`datasets.html:3675`) is written in exactly one place: `selectAttrAnchor(name)`
(`:3965`), wired to the listbox's `onchange` (`:619`). The property and value dropdowns call
`_loadAnchorPropertyValues()` and `applyAnchorFilter()`, which re-render the listbox by assigning
`innerHTML` inside `_renderAnchors()` (`:3941`). **Assigning `innerHTML` does not fire a `change`
event**, so `_attrSelectedAnchor` survives every filter and search operation, while the `attr-anchor-label`
span keeps displaying `→ OldName`. The user sees a listbox with nothing selected and a label naming
someone who is no longer in it.

Three paths strand the state — `applyAnchorFilter()` (`:3857`), `clearAnchorFilter()` (`:3885`), and
`filterAttrAnchors()` (`:3954`). `onAnchorLabelChange()` (`:3744`) is the one that gets it right, clearing
both the variable and the span.

The consequential half is not `runAttribution()` (`:3971`) returning candidates for the wrong anchor —
that is visible and recoverable. It is `runConfirm()` (`:4049`), which posts the same stale
`_attrSelectedAnchor` to `/confirm` and **writes edges from the wrong anchor into the graph**, reporting
success. Silent bad provenance in a system whose purpose is provenance.

**Fix, at the level of the bug class rather than the three call sites:** delete the shadow variable and
derive selection from the control — a `_attrCurrentAnchor()` getter reading `attr-anchor-sel.value`, which
is empty whenever the listbox has no selection, including immediately after a re-render. That makes the
stale state unrepresentable instead of patching each render path and hoping the next one remembers. Keep
the `→ Name` span as a pure render of the getter.

For the redesign: if the anchor picker becomes a Tom Select combobox, the same rule applies — read
`ts.getValue()` at submit time rather than caching the selection on change. `runConfirm()` should also
validate the anchor independently rather than trusting that `runAttribution()` ran with the same one, and
both should surface failure in `attr-status` rather than `alert()`.

---

## 6. Modality keywords removal

`MODALITY_KEYWORDS` (`:86-92`) is exported in `__all__` but read in exactly one place: `_resolve_keywords`
(`:558-567`), inside the same module. Verified by grep across `*.py`, `*.html`, and `*.js`: no other
module, template, or script references it. The only other mention of the shorthands anywhere is the five
checkbox `value` attributes (`datasets.html:657-669`), which are the dict's keys — so the dict is
effectively the UI's contract, and any renaming has to move together.

**Removing the checkboxes is safe server-side.** The route reads `body.get('modality_keywords')`
(`api_files.py:2326`) with no validation; the service parameter defaults to `None`; `_resolve_keywords(None)`
returns `[]`; `any(kw in path_lower for kw in [])` is `False`. No 4xx, no exception, no changed response
shape. Nothing needs to be removed server-side, and the parameter is worth keeping — it costs nothing and
the API stays capable.

**One consequence must be decided, not absorbed silently.** `has_modality` becomes `False` for every
candidate, and `_score` (`:544-556`) uses it in two places: it appends `"+ modality"` to reason strings
(cosmetic), and it is the **only** path by which a labmate/related match reaches `MED` — without it,
`is_labmate` always returns `LOW`. Combined with Question 2's generalization, every related-anchor match
would be permanently LOW, which flattens the confidence signal the panel exists to provide. Options:

1. Express modality through the new target property filters (`path contains "vevo"`), which is strictly
   more general — but then explicitly revisit `_score`'s modality branch, since nothing will set the flag.
2. Keep a small modality convenience control that translates to `modality_keywords`, preserving the tier.

Either is defensible. What is not defensible is removing the checkboxes without touching `_score`, which
silently downgrades every related match. Recommend sequencing this **last**, after target filters work, so
the decision is made with the replacement in hand.

---

## 7. Tom Select compatibility

**Not present.** Grep for `tomselect` / `tom-select` / `select2` / `choices.js` / `selectize` across
`scidk/ui/` returns zero hits. Not loaded, not vendored, not referenced.

**No CDN precedent anywhere.** `base.html` loads exactly three scripts, all local: `notifications.js`,
`graph_utils.js`, `filter_builder.js` (`:363-369`). The only `<link>` in the file is the favicon; all CSS
is inline in a `<style>` block. `scidk/ui/static/` contains only `favicon.ico` and `js/` — **there is no
CSS file in the project at all.** A CDN-loaded Tom Select would be the app's first third-party runtime
dependency and its first external network fetch at page load. No CSP header is set anywhere (grep found
none), so it would not be *blocked* — but for facility deployments on internal or air-gapped networks the
panel would silently degrade to unstyled selects. **Recommend vendoring** to
`scidk/ui/static/js/vendor/` and serving through `url_for('static', …)` like everything else.

**"Bootstrap-compatible" is a non-benefit here: there is no Bootstrap.** The panel's
`btn btn-sm btn-outline-primary` / `btn-outline-secondary` classes have **no matching CSS anywhere** —
`base.html` defines no `.btn` rules, there is no stylesheet, and the `button.btn` rules that do exist are
page-scoped `<style>` blocks in `pipeline_*.html` and `results.html`, none of which `datasets.html`
includes. Those buttons render as unstyled browser defaults today. Consequence: ship
`tom-select.default.css`, not the Bootstrap 5 theme, and expect to write panel CSS regardless — which is
also an opportunity, since the panel is currently ~40 inline `style=` attributes.

**The real hazard is DOM ownership, and it overlaps the stale-anchor fix.** Tom Select hides the original
`<select>` and builds its own wrapper. The panel manipulates its selects directly by id — `_renderAnchors`
(`:3941`), `_loadAnchorProperties` (`:3802`), `_loadAnchorPropertyValues` (`:3844`),
`_attrResetValuePicker` (`:3817`), `_loadRelSuggestions` (`:3911`), and `_loadSchemaLabels` (`:3729`) all
assign `.innerHTML`, and several assign `.value`. Once Tom Select is attached, **`sel.innerHTML = …`
silently stops updating the visible control** — options have to go through
`clearOptions()` / `addOptions()` / `setValue()` / `sync()`. All six functions must be converted or the
panel will appear frozen with stale options. Note these are the same functions implicated in §5, so the
two changes touch identical code and should not be interleaved.

Lesser notes: no jQuery and no other select-enhancement library, so no wrapper conflicts. The
`data-testid` attributes on the current selects (`attr-anchor-sel`, `attr-filter-prop-sel`,
`attr-rel-select`, …) will end up on hidden elements — currently harmless, since grep finds **no test in
`tests/` referencing any attribution `data-testid`**, but the redesign should put testids on the visible
Tom Select wrappers so the panel remains testable.

---

## 8. Recommended sequencing

Ordered so each step is independently verifiable and nothing user-visible breaks mid-flight. The pivot is
that steps 1-5 all land while the **current panel keeps working unchanged**, via optional params and
deprecated aliases.

| # | Step | Why here |
|---|---|---|
| 1 | **Fix the stale anchor bug** (getter-based, §5). | Smallest change, real correctness win (wrong-anchor writes), ships alone. Must precede the picker rewrite, which multiplies the render paths that can strand state. |
| 2 | **Fix `filter_builder.js` to use `window.SCIDK_BASE`.** | Prerequisite for any `FilterBuilder` reuse; harmless and correct standalone. |
| 3 | **Spike `FilterBuilder` in the panel.** Throwaway — does the component fit, or is a new builder needed? | The answer changes the size of step 6 substantially. Cheapest possible way to learn it, and knowing it before writing the implementation prompt is the point of this evaluation. |
| 4 | **Backend, additive, defaults preserving current behavior**, in order: (a) `confirm(relationship_properties=…)` via `SET rel += $props`; (b) `_fetch_folders`/`get_candidates` target conditions reusing `_operator_to_clause`; (c) related-names generalization + pattern registry + route, with `include_labmates` kept as a deprecated alias; (d) structured anchor search — **only if** step 6 needs it. | Each is a separate testable unit against the fake driver. Independent of each other and invisible to the running panel. (a) first because it is the smallest and touches no query shape. |
| 5 | **Verify step 4 against a live graph.** | The fake-driver tests cannot execute Cypher — the module docstring says so. Every new generated clause is unverified until this runs. Do not skip; do not fold into step 6, where a Cypher error and a UI error look alike. |
| 6 | **Rewrite the panel into three sections using plain `<select>`s** against the new endpoints. | Correctness of the new query semantics gets proven with zero new dependencies in play. |
| 7 | **Layer Tom Select onto the pickers** (vendored, default theme, all six render functions converted). | Kept separate from step 6 so a library problem cannot be mistaken for a query-semantics problem. Reversible on its own. |
| 8 | **Remove the modality checkboxes** and make the `_score` decision explicitly (§6). | Last, once target property filters can express modality. Removing earlier silently downgrades every related match to LOW. |

Two standing notes for the implementation prompt: keep `include_labmates`, `person_name`, and
`folder_paths` accepted throughout — the module's existing deprecation convention is what decouples steps
4 and 6. And extend `tests/test_attribution_service.py` in step 4 rather than after step 6, while the
subject is still one method at a time.
