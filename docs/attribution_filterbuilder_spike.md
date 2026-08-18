# FilterBuilder Spike — Attribution Panel

Throwaway spike, executed and removed. Written against `production-mvp` at `e413927`.

**How it was run.** A temporary `scidk/ui/templates/filter_builder_spike.html` extending `base.html`, plus a
throwaway `GET /_spike/filter-builder` route in `scidk/web/routes/ui.py`. Two `FilterBuilder` instances
(Anchor → `Investigator`, Target → `Folder`), driven in real Chrome via Playwright against the **live
Neo4j graph** on `bolt://localhost:7687` (22 labels, 18 relationship types, ~5.5M `:File` nodes). Both the
template and the route are deleted; `git diff` over tracked files is empty apart from the pre-existing
`dev` submodule pointer.

Everything below is measured, not inferred, except where explicitly marked.

---

## A. Does it render?

**Yes — cleanly, with zero console errors and zero page errors.**

Anchor section rendered: a label `<select>` carrying all 22 live labels with `Investigator` pre-selected, a
`Match: ALL|ANY` select, one condition row (property select → operator select → value input → `×`), and a
`+ Add condition` link. Target section rendered the same, and after `addBlock()` also produced the
`↳ relates via` row — relationship-type select with all 18 live types plus `hops: [1] – [1]` number
spinners.

Property selects were populated from the live schema: Anchor offered `email`, `name`; Target offered
`host`, `host_id`, `host_type`, `name`, `path`, `provider_id`. Operator dropdowns carried the full
nine-operator string set. Both instances laid out side by side at ~520px without overflow.

**One real gotcha.** `base.html` loads `filter_builder.js` at the *end of `<body>`*, after
`{% block content %}`. An inline script in the content block sees `typeof FilterBuilder === 'undefined'`
(measured). Instantiation must be deferred to `DOMContentLoaded` or later. The panel is unaffected in
practice — `openAttributionPanel()` is user-triggered — but a naive `new FilterBuilder(...)` at parse time
in `datasets.html` will throw.

---

## B. Do the schema fetches work?

**Yes. All four call sites work, and the `SCIDK_BASE` fix is confirmed in a real browser.**

| Request | Status | Returned |
|---|---|---|
| `GET /api/schema/labels` | 200 | 22 labels |
| `GET /api/schema/relationship-types` | 200 | 18 types |
| `GET /api/schema/property-types?label=Investigator` | 200 | `email:string`, `name:string` |
| `GET /api/schema/property-types?label=Folder` | 200 | 6 string properties |
| `POST /api/schema/filter-preview` | 200 | see C |

Two cost notes, neither blocking:

- **No cross-instance schema cache.** `labelList`, `relTypeList` and `schemaCache` are per-instance, so
  each `FilterBuilder` fetches `/api/schema/labels` and `/api/schema/relationship-types` for itself.
  Measured: two instances → 4 calls where 2 would do. A two-section panel makes 6 schema requests on open.
- **`/api/schema/*` opens and closes a fresh Neo4j driver per request** (`_get_schema_driver`,
  `api_graph.py:1203`), unlike the attribution routes, which reuse a driver cached on
  `app.extensions['scidk']` precisely to avoid the TCP connect plus Bolt handshake
  (`api_files.py:_attribution_service`). Six schema requests on panel open means six driver lifecycles.

---

## C. What does the output object look like?

`getFilterDef()` is the accessor. It returns a deep copy of `{blocks: [...]}`. Actual output after setting
one condition in each section:

```json
{
  "anchor": {
    "blocks": [
      { "label": "Investigator", "match": "ALL",
        "conditions": [ {"property": "name", "operator": "contains", "value": "Zhang"} ] }
    ]
  },
  "target": {
    "blocks": [
      { "label": "Folder", "match": "ALL",
        "conditions": [ {"property": "host", "operator": "contains", "value": "vevo"} ] },
      { "label": "", "match": "ALL", "conditions": [],
        "via": {"type": "CONTAINS", "min_hops": 1, "max_hops": 1} }
    ]
  }
}
```

**It matches `filter_builder.py`'s expected input exactly.** POSTing the Anchor def to
`/api/schema/filter-preview` returned 200 with:

```
MATCH (n0:Investigator)
WHERE n0.name CONTAINS $v0
RETURN DISTINCT n0        params {"v0": "Zhang"}   total 2
```

Three operator classes verified end-to-end against the live graph:

| Condition built in the UI | Generated Cypher | Result |
|---|---|---|
| `name contains "Zhang"` (string) | `n0.name CONTAINS $v0` | 200, total 2 |
| `size_bytes between 1000–50000` (number, `File`) | `n0.size_bytes >= $v0 AND n0.size_bytes <= $v1`, params `1000`/`50000` as **numbers** | 200, total 72694 |
| `host_id is present` (value-less) | `n0.host_id IS NOT NULL`, params `{}` | 200, total 48729 |

The `between` case confirms the `typed()` coercion in `refreshValue` works: values arrive as JSON numbers,
not `"1000"`, which matters because Cypher never matches `"5"` against `5`. The `is_not_null` case
confirms a stale value is correctly nulled out rather than sent.

**One failure mode found.** A block whose label is empty produces a def the backend rejects:

```json
{"blocks": [{"label": "", "match": "ALL",
             "conditions": [{"property": "", "operator": "contains", "value": ""}]}]}
→ 400 {"error": "identifier is missing"}
```

This is the **default state after clicking `+ Add block`** (new blocks start `label: ''`) and after
`+ Add condition` on an unlabeled block. There is no client-side validation; the only surfacing is the
string `Error: identifier is missing` in the small `fb-preview-count` span.

---

## D. Does the shell fit the panel?

**There is no `headless` or `embed` mode.** The complete options surface is
`{onPreview, onUse, onSave, defaultLabel, showSave}` — verified by reading
`Object.keys(instance.options)` at runtime.

What `_renderShell` renders beyond the blocks: an `.fb-actions` row containing `+ Add block`, `Preview`, a
preview-count span, plus `Save as dataset` if `showSave` and `Use` if `onUse` is passed.

**It renders no heading at all** — which is a plus, not a problem. The panel supplies its own `<strong>`
in the wrapper (that is what "Anchor"/"Target" were in the spike).

**CSS suppression works and is cleanly scopable.** Two rules on a wrapper class were enough:

```css
.fb-anchor-scope .fb-actions { display: none; }        /* computed display: none, verified */
.fb-anchor-scope .fb-block   { border: none; padding: 0; background: none; }
```

The element stays in the DOM but is unreachable. The second rule matters because `.fb-block` carries its
own border, padding and background, which double-frames inside the panel's own bordered section.

Two things fall out of this that make the fit better than expected:

- **`+ Add condition` lives inside the block, not in `.fb-actions`** — so hiding the actions row leaves
  condition editing fully intact while removing the only user path to a second block.
- **`_makeViaRow` only renders for block index > 0.** So *"property conditions but no `via` row"* is
  exactly "one block, actions row hidden" — achievable with the two CSS rules above and **no JS change**.
  That is the Anchor mode the task asked for, and it works today.

---

## E. Tom Select integration

**Tom Select does not auto-enhance anything.** Measured: after both instances rendered, `.ts-wrapper`
count inside the containers was **0** while the `<select>` count was as expected. Tom Select requires an
explicit `new TomSelect(el)`; `FilterBuilder` never calls it and has no knowledge of it. `base.html` loads
`tom-select.complete.min.js` *after* `filter_builder.js`, but both execute before `DOMContentLoaded`, so
either file may reference the other's global from deferred code.

**Attaching externally works in both directions, and does not conflict with FilterBuilder's own change
handling.** Measured: `new TomSelect(labelSel)` then `ts.setValue('Lab')` → Tom Select dispatched the
native `change`, FilterBuilder's `labelSel.onchange` ran, `blocks[0].label` became `'Lab'`, conditions
cleared, and `/api/schema/property-types?label=Lab` was fetched. Nothing broke.

**The conflict is destruction, not change.** Three FilterBuilder code paths wipe DOM that Tom Select has
taken ownership of:

- `refreshOps()` — `opSel.innerHTML = ''`, then rebuilds `<option>`s. A TS-attached operator select stops
  updating visibly. (Same bug class as §7 of the prior evaluation, for the panel's own selects.)
- `_refreshConditions(i)` — `container.innerHTML = ''`, re-renders every condition row.
- `_removeBlock()` → `_renderAll()` — `this._blocksEl.innerHTML = ''`, destroying **every** select in the
  instance, label selects included.

Measured on the second of those: 4 TS instances attached → 4 `.ts-wrapper`s. After one
`_refreshConditions(0)`, wrappers dropped to **2** (the surviving header selects) and the two condition-row
selects reappeared as **plain, unstyled `<select>`s**. Half-styled UI, no error thrown. The two orphaned
`TomSelect` objects were never `.destroy()`d — leaked, with their document-level listeners still attached.

Consequence: Tom Select on the **label / match** selects is drop-in. Tom Select on the **condition rows**
is not wiring — it needs a render hook in `filter_builder.js` (re-attach after render, destroy before
wipe). This confirms the prior evaluation's decision to sequence Tom Select last and separately.

---

## F. What would wiring cost?

### Anchor → `/api/files/attribution/anchors` — this is the expensive mismatch

`list_anchors` (`folder_attribution.py:172`) accepts exactly **one** `filter_property` and **one**
`filter_value`, matched case-insensitively with `CONTAINS`. `FilterBuilder` emits N conditions × 9 string
operators × `ALL`/`ANY`.

Mapping its output onto that endpoint means reading `blocks[0].conditions[0].property` and `.value` and
**silently discarding everything else**. A user who builds `email is present AND name starts with "Zh"`
would get a list filtered by `email CONTAINS ""`. That is not wiring — it is a control that lies about what
it did. So the Anchor section needs one of:

- **(a)** the structured anchor-search endpoint from step 4(d) of the prior sequencing, delegating to
  `generate_cypher` — which this spike has now proven works end-to-end from browser to Cypher; or
- **(b)** keep the existing single property/value pair and do **not** use `FilterBuilder` there.

### Target → `/api/files/attribution/candidates` — blocked, then trivial

The POST body has **no place for property conditions at all** today (`anchor_name`, `anchor_label`,
`target_label`, `modality_keywords`, `include_labmates`, `sources`). The Target section is fully blocked on
step 4(b). Once that lands the mapping is direct: `blocks[0].conditions` is already the
`{property, operator, value}` shape `_operator_to_clause` consumes, and it accepts the property reference as
a string, so `f.<prop>` reuses it verbatim.

### Events / callbacks

**There is no component-level change event.** Options are only `onPreview` / `onUse` / `onSave`; the
prototype exposes no subscribe method (verified by enumerating
`Object.getOwnPropertyNames(Object.getPrototypeOf(fb))`).

The panel should therefore read `getFilterDef()` at submit time. That is the right pattern anyway — it is
the same discipline as the stale-anchor fix: derive from the control, never cache.

If a dirty signal is wanted, note that `FilterBuilder`'s controls are real `<select>`/`<input>` elements,
so a bubbled `change` listener on the container should serve. **Not verified in this spike** — my probe
invoked `.onchange()` directly, which dispatches no event, so it correctly saw nothing. Worth a one-line
check before relying on it, and note Tom Select wrapping would change the picture.

No polling is needed either way.

---

## G. What would NOT fit

1. **The Anchor section needs a *selection*, not a filter.** The panel's job is: narrow the list → pick
   **one** anchor by name → write edges from it. `FilterBuilder` produces a filter definition and has no
   concept of choosing one matched node. `attr-anchor-sel` and `_attrCurrentAnchor()` must still exist
   alongside it. FilterBuilder can replace the *narrowing* half of the Anchor section, not the section.

2. **It loses the value picker — a UX regression on the panel's most-used control.** Today
   `attr-filter-val-sel` is populated from `/api/files/attribution/anchor-property-values`, so the user
   picks from values that actually exist on those nodes. `FilterBuilder`'s value control is a bare
   free-text `<input>` with no hook to inject a value source. Users would go from choosing a real lab name
   to guessing a substring.

3. **`defaultLabel` diverges silently when the label is not in the graph.** Measured:
   `new FilterBuilder(el, {defaultLabel: 'NoSuchLabel'})` leaves `blocks[0].label === 'NoSuchLabel'` while
   the visible select reads `"Select label…"`, and `getFilterDef()` returns the invisible label —
   generating `MATCH (n0:NoSuchLabel)`, 200, total 0. The current panel deliberately does the opposite:
   `_loadSchemaLabels` prepends the current value so `Investigator`/`Folder` stay selectable even when
   absent. On a deployment with no `:Investigator` nodes the Anchor section would look unset and silently
   query a label the user cannot see. This is a genuine bug in `filter_builder.js:305`, which discards a
   value it does not offer instead of offering it.

4. **Date operators are unreachable for this graph's timestamps.** `File.created` and `File.modified` are
   stored as epoch numbers, so `_classify` types them `"number"` and only the numeric operators are
   offered — measured for `modified`: `equals/gt/gte/lt/lte/between`, **no `after`/`before`**. "Modified
   since 2024-01-01" requires typing `1704067200` into a number spinner. The format-awareness is real, but
   the `date` branch never fires on the properties users would most want it for.

5. **The `via` row is the wrong instrument for the Target section.** Its semantics are "the previous block
   connects to this one by this relationship type" — a filter on edges that *already exist*. In this panel
   the relationship is the thing being **written**, and `_fetch_folders` does not traverse an anchor→target
   edge at all. A `via` row in the Target section reproduces exactly the misreading §2 of the prior
   evaluation rejected under Interpretation A: it would look like it constrains candidates while either
   doing nothing or restricting to already-attributed targets. Hop counts (1–9, variable-length) have no
   meaning here either.

6. **`Preview` counts the wrong thing in the Target section.** `/api/schema/filter-preview` runs
   `generate_count_cypher` over the filter def alone. For the Anchor that is coherent ("2 investigators
   match"). For the Target it would report "48729 Folders match" while the real candidate search
   additionally requires a name-variant path match and returns a scored, ranked list — two numbers labelled
   the same thing, differing by orders of magnitude. Preview must be hidden there. Conveniently it lives in
   `.fb-actions`, so the same CSS rule that removes `+ Add block` removes it.

7. **`+ Add block` / multi-block is meaningless in both sections**, and produces backend-invalid defs by
   default (400 until a label is picked — see C). Must be suppressed; CSS does it.

8. **No validation surface.** Errors surface as a string in the small `fb-preview-count` span. The panel has
   `attr-status`. Wiring `onPreview` yields `(count, cypher)` but **not** the error text — `preview()`
   writes `d.error` to the span and still calls `onPreview(d.total, d.cypher)` with `total` undefined.

---

## Recommendation

**Wire `FilterBuilder` with modifications — Target section first. Do not use it for the Anchor section's
narrowing until the structured anchor-search endpoint exists. Do not write a purpose-built builder.**

The component works. It renders without error, follows the live schema, and produces exactly the object the
already-tested backend generator consumes — verified across string, numeric-`between` and value-less
operators, browser to Cypher, against a real 5.5M-node graph. The shell fits inside the panel with **three
scoped CSS rules and no JS change**, and the Anchor's "conditions but no `via` row" mode falls out of the
existing design for free. A purpose-built builder would re-derive the operator matrix, the type-aware
inputs, the numeric coercion, and the schema plumbing — all of which demonstrably work — to avoid deltas
that are mostly subtractive.

**The blocker is not the component. It is that neither attribution endpoint can accept its output today.**
The Anchor endpoint takes one `CONTAINS` pair; `/candidates` takes no property conditions at all. So
"wire FilterBuilder" cannot precede backend step 4 — and the prior sequencing already has that order right.

### Sequencing amendment

Step 3 (this spike) is done. Read step 6 as **"wire `FilterBuilder` into the Target section after 4(b);
leave the Anchor picker as-is until 4(d)"**, rather than "rewrite the panel with plain selects".

### Changes needed in `filter_builder.js`

All five are additive and option-gated with defaults that reproduce today's behavior. `FilterBuilder` is
loaded on every page but — verified by grep — still **instantiated nowhere**, so the blast radius today is
literally zero. Write them option-gated anyway, so that stays true when a second consumer appears.

| # | Change | Needed for | Safe globally? |
|---|---|---|---|
| 1 | **Fix the `defaultLabel` divergence** at `:305`: if `block.label` is truthy but not in `labelList`, prepend it as an option instead of showing the placeholder while silently keeping the value. | G3 — correctness | **Yes.** Strictly reduces divergence; no other consumer exists. Worth doing regardless of this panel. |
| 2 | **`options.valueOptionsFor(label, property) → Promise<string[] \| null>`**, rendering a `<select>` when it resolves to a list and falling back to today's `<input>` on `null`. | G2 — restores the value picker | **Yes.** No-op when unset. The one substantive addition. |
| 3 | **`options.onRender(container)`** at the end of `_renderBlock` / `_refreshConditions` / `_renderAll`, plus a `beforeWipe` destroy path. | E — makes Tom Select on condition rows implementable at all | **Yes.** No-op when unset. Only needed when step 7 lands. |
| 4 | **Client-side validation**: skip label-less blocks in `getFilterDef()`, or expose `validate()`. | C, G7 — stop emitting 400-generating defs | **Yes**, if `getFilterDef()` keeps returning raw state and validation is a separate method — changing what `getFilterDef()` returns is the one thing that could surprise a future consumer. |
| 5 | **Pass `d.error` through to `onPreview`** so the panel can route it to `attr-status`. | G8 | **Yes.** Additive third argument. |

**Do with CSS, not JS** — suppressing `.fb-actions` (which removes `+ Add block`, `Preview`, `Save`) and
flattening `.fb-block`. Scoped to a panel wrapper class, this touches no shared file and is the whole of
the "shell doesn't fit" problem.

**Do not** add a `mode: 'anchor' | 'target'` option. The two modes differ only by CSS and by whether a
second block is reachable; encoding panel-specific vocabulary into a generic component buys nothing.

### One thing to settle before writing the implementation prompt

Whether the Anchor section gets the structured search endpoint (4(d)) at all. If it does, `FilterBuilder`
serves both sections and change #2 is what makes it not a regression. If it does not, the Anchor section
keeps its current two dropdowns, `FilterBuilder` appears only in the Target section, and change #2 becomes
optional. That decision sets the size of the panel work more than anything else in this report.
