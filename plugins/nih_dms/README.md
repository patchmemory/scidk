# NIH DMS Plan Generator

Generates draft prose for an NIH Data Management and Sharing plan out of whatever
is actually in this instance's knowledge graph.

```
GET /api/plugins/nih_dms/draft_plan          → markdown
GET /api/plugins/nih_dms/draft_plan?format=json  → {markdown, summary}
GET /api/plugins/nih_dms/config              → what the generator looks for
```

UI entry point: **Generate DMS Plan Draft**, in the Files page header. It opens a
panel with the markdown ready to copy into DMPTool or a grant application, plus a
`.md` download. Both roles (`admin`, `user`) may generate a plan.

## Why generate rather than template

Every figure in the draft is read from the graph: entity counts, file formats and
volumes, the assays the records name. A researcher's first read is therefore a
review of their own data rather than a fill-in-the-blanks exercise, and a wrong
number is visible immediately.

Two rules follow from that, and both are enforced by tests:

- **No fiction.** If Neo4j is not configured or not reachable, the route returns
  503 with a message saying so. It never falls back to a static plan — a
  plan-shaped document that nobody generated is the one output that could reach a
  funder unchecked.
- **Every human decision is a bracketed placeholder.** `[REPOSITORY_NAME]`,
  `[RETENTION_PERIOD]` and the rest are upper-case in brackets, so a reviewer can
  find them by eye and by search. The draft ends by telling the reader to search
  for `[`.

## Sections

Four sections, titled with the NIH element numbers so the draft can be pasted
into DMPTool field by field:

| Section | Source |
| --- | --- |
| Element 1 — Data Type | Label inventory (count store), exact file format and volume distribution, relationship inventory |
| Element 3 — Standards | Formats mapped to community standards, media types, modality/assay properties found in the graph, RO-Crate as the metadata standard |
| Element 4 — Preservation | Static prose plus `[REPOSITORY_NAME]` / `[RETENTION_PERIOD]`; names RO-Crate as the packaging format |
| Element 5 — Access | Per-property `sharing_modes` where present, else the configured sharing mode, else a prompt listing the choices |

Elements 2 (tools/code) and 6 (oversight) are deliberately **not** generated —
nothing in the graph knows who signs off on a plan or which code produced a
result. They appear in a closing section as explicit prompts, so their absence
cannot be mistaken for completeness.

## PHI detection

Property names are matched against `PHI_PROPERTY_NAMES` in `config.py`
(`patient_id`, `subject_name`, `patient_name`, `mrn`, `date_of_birth`, `dob`) on a
canonical form — lower-cased with separators removed — so `patient_id`,
`patientID` and `Patient Id` all match one entry. Both sources are scanned:
current node and relationship properties, and property names curated in
`label_profile`.

A match adds a warning to Element 1 naming the properties and what has to be
resolved (de-identification standard, consent terms, controlled access), and makes
the privacy subsection of Element 5 non-optional.

Evidence is graded, because the grades mean different things:

| Evidence | Meaning |
| --- | --- |
| `graph` | On current nodes or relationships |
| `label_profile` | Curated in the schema layer — somebody wrote it down |
| `property_key_store` | The key exists but no current node carries it — usually deleted data. Surfaced, but **not** as live PHI |

When nothing matches, the draft says so *and* says it is not a finding that the
data are de-identified: the check compares property names and cannot see an
identifier inside a free-text note, a filename or an image header.

## Configuration

Optional settings, read from `scidk_settings.db`. Unset ones become visible
placeholders rather than silent defaults.

| Setting | Effect |
| --- | --- |
| `publication.dms.repository` | Fills `[REPOSITORY_NAME]` |
| `publication.dms.retention_years` | Fills `[RETENTION_PERIOD]` |
| `publication.dms.sharing_mode` | `open` / `registered_access` / `controlled_access` / `metadata_only` / `not_shared` — drives Element 5 |
| `publication.dms.access_contact` | Fills `[DATA_ACCESS_CONTACT]` where the chosen mode names one |

`config.py` holds every table the generator would otherwise hardcode: PHI names,
modality property names, the extension → format → standard map, and the sharing
mode prose. Adding an instrument or a format is a change to a table there, not to
the code that walks the graph.

## Cost

On the AIPT graph (5.1M `:File` nodes, 8 TB indexed) a draft takes ~8s.

| Read | Cost | Why |
| --- | --- | --- |
| Label and relationship counts | ~0.06s | Count store — a counter, not a scan |
| File format distribution | ~7s | One pass grouped by `(extension, mime_type)`, folded in Python. Replaced three separate scans (~11s) |
| Per-label property schema | ~9s | **Skipped** unless it can add something — see below |
| Modality values | ~0.02s | Only properties the schema says exist are queried |

Two deliberate choices:

**The format scan is exact, not sampled.** A `LIMIT 200000` prefix of the AIPT
graph reports `.dcm` as the second-commonest format and misses `.bmp` (897k files)
and `.nii` (800 GB of NIfTI) entirely, because store order is not sample order. A
plan may not be wrong about what data the lab holds. `?sample_limit=N` is
available as an escape hatch for a deployment where the exact scan is too slow,
and the generated draft then says in its own text that it was sampled and why that
is a weaker claim.

**`db.schema.nodeTypeProperties` is skipped when it cannot help.** It is the
expensive read, so it runs only when the cheap key store shows there is something
to find *and* the relationship schema has not already accounted for it. Two
exceptions: any PHI-shaped key forces the full read (a missed identifier is the
expensive mistake), and `?deep=1` forces it unconditionally. When the shortcut
applies, the draft records it in its generation notes — the cost is a modality
listing being less complete, never a PHI warning being missed.

## Layout

```
plugins/nih_dms/
├── config.py       # every table the generator would otherwise hardcode
├── graph_facts.py  # all Neo4j + SQLite reads → GraphFacts
├── generator.py    # GraphFacts → markdown (pure; no database, no clock)
├── routes.py       # the blueprint, and the three ways this can fail
└── __init__.py     # register_plugin(app)
```

`generator.py` being a pure function of `GraphFacts` is what makes the prose
testable without a database. Tests: `tests/test_nih_dms_plan.py` — the fake graph
answers the module's real Cypher over a small node list rather than returning
canned rows, so a mistake in a query fails there.
