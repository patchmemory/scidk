# Junie Diagnostic — Drives, Scan History, and Collection Backend

Read-only audit of `production-mvp` @ 57c3f33. No code was changed.

Summary of the nine questions:

| Q | Area | Status |
|---|---|---|
| Q1 | Drive/server API | **partial** — GET only, no POST/DELETE |
| Q2 | Local FS browsing | **partial** — no host-root enumeration; bad error semantics |
| Q3 | Rclone config management | **missing** — read-only rclone usage, no `config create`, no OAuth |
| Q4 | Scan history per path | **partial** — `file_history` table exists, no route, rclone-only writer |
| Q5 | Collection sweep | **partial** — Dataset/CONTAINS exist; no sweep route; proposed query uses wrong property names |
| Q6 | Dataset creation | **missing** — `POST /api/datasets` does not exist; `GET /api/datasets` is an unrelated legacy concept |
| Q7 | Interpreter status per file | **partial** — state stored, no per-path status route, no timestamps |
| Q8 | Attribution wiring | **exists** — all six routes present, 113 tests pass; file-level paths work with caveats |
| Q9 | `/api/scans/<id>/browse` | **exists** — works, but response shape differs from `/api/browse`, and the page also calls a route that does not exist |

---

## Q1 — Current drive/server API

**Status: partial (read-only).**

**Evidence** — `scidk/web/routes/api_files.py:859-1004`, `api_servers()`.

Response is a bare JSON **array** (not an object envelope), one entry per
provider×root:

```json
[{"id": "local_fs",            // provider id, not a server id
  "display_name": "Local Filesystem",
  "root_id": "/home/patch",
  "root_path": "/home/patch",
  "connected": true,           // hardcoded true (line 940) — never a real probe
  "scanned": false,
  "last_scanned": null,        // epoch float or null
  "file_count": 0,
  "error": "..."}]             // only present on the per-provider failure path
```

- **Source:** two places joined in Python. Providers come from the in-memory
  `ProviderRegistry` (`ext['providers']`, `scidk/core/providers.py:247`); scan
  metadata comes from `files.db` → `scans.extra_json`, aggregated by
  `f"{provider_id}:{root_id}"` (lines 891-928).
- **Local roots included?** Yes. `local_fs` and `mounted_fs` are ordinary
  providers. `LocalFSProvider.list_roots()` (`providers.py:102`) returns exactly
  **one** root — `SCIDK_LOCAL_FILES_BASE` or `$HOME`.
  `MountedFSProvider.list_roots()` (`providers.py:168`) returns the immediate
  children of `/mnt` and `/media`. `RcloneProvider.list_roots()`
  (`providers.py:353`) shells out to `rclone listremotes`.
- **POST /api/servers or /api/drives?** No. Grepped all blueprints — nothing.
- **DELETE?** No.

The nearest write surface is the rclone **mount manager**, which is a different
thing (it starts an `rclone mount` process for an already-configured remote):
`POST /api/rclone/mounts` (`api_providers.py:122`), `DELETE
/api/rclone/mounts/<mid>` (`:213`), plus `/logs` and `/health`.

**Gap**
1. No create/delete of drives at all. Adding a server today means editing the
   rclone config by hand outside SciDK, or setting `SCIDK_LOCAL_FILES_BASE`.
2. `connected` is a literal `True` for any loaded provider — the Files page
   cannot distinguish a reachable remote from a dead one.
3. The scan-history join key is `provider_id:root_id`. `POST /api/scan` defaults
   `root_id` to `'/'` (`api_files.py:159`) while `local_fs`'s root id is
   `str(base_dir)`. Any scan submitted without an explicit `root_id` records a
   key that no server entry will ever match, so `scanned` stays false and
   `file_count` stays 0. Worth confirming against live data before building on
   these fields.

---

## Q2 — Local filesystem browsing

**Status: partial.**

**Evidence** — `scidk/web/routes/api_files.py:1007-1051`, `api_browse()`.

The route is a thin dispatcher: it resolves `provider_id` → provider and calls
`prov.list(root_id=..., path=...)`. Rclone-only options (`recursive`,
`fast_list`, `max_depth`) are parsed only when `provider_id == 'rclone'`.

- **Abstraction or direct?** There *is* an abstraction (the
  `FilesystemProvider` interface), but both local implementations call
  `pathlib` directly: `LocalFSProvider.list` uses `base.iterdir()`
  (`providers.py:118-136`), `MountedFSProvider.list` likewise
  (`providers.py:201-219`). Both sort folders-first then name-ascending and
  return `{"entries": [{id, name, type, size, mtime}]}`.
- **Top-level host path enumeration?** **No such route.** The closest is
  `GET /api/provider_roots?provider_id=` (`api_providers.py:33-45`), which
  returns `[{id, name, path}]` from `list_roots()`. For `local_fs` that is a
  single entry (home dir); for `mounted_fs` it is `/mnt` + `/media` children.
  Nothing enumerates `/`, arbitrary host roots, or `/proc/mounts`.
- **Nonexistent path:** `LocalFSProvider.list` returns `{"entries": []}` when
  `not base.exists()` (`providers.py:120`) → **HTTP 200 with an empty list**.
  Indistinguishable from an empty directory.
- **Inaccessible path:** `base.iterdir()` raises `PermissionError` at the `for`
  statement, which is *outside* the per-child `try` (`providers.py:123-135`).
  It propagates to `api_browse`'s outer handler → **HTTP 500**,
  `{"error": "<str(e)>", "code": "browse_exception"}`.

**Gap**
1. No `GET /api/drives/browse-local` or equivalent. To offer "pick a path on
   this machine", something must enumerate real mount points — `mounted_fs` only
   covers `/mnt` and `/media`, both hardcoded (`providers.py:174`).
2. Missing path returns 200/empty rather than 404 — the drawer cannot show
   "this path is gone" vs "this folder is empty".
3. Permission denied returns a bare 500 with no machine-readable code.

---

## Q3 — Rclone config management

**Status: missing (all rclone usage is read-only, except mounting).**

**Evidence** — `RcloneProvider`, `scidk/core/providers.py:267-490`. All
invocation funnels through `_run()` (`:298`):
`subprocess.run([shutil.which('rclone')] + args, ..., check=False)`.

- **Does SciDK create/modify remotes?** **No.** No `rclone config create`, no
  `rclone config update`, and nothing writes `rclone.conf`. Grepped
  `scidk/`, `plugins/`, `tools/`, `scripts/`.
- **`rclone config` wrapper?** Only one call anywhere, and it is a read:
  `rclone config dump` in `plugins/sharepoint_intake/source.py:100`
  (`detect_auth_method`) — parses the JSON to classify a remote as
  `rclone_oauth` / `rclone_basic`.
- **OAuth flow?** **None.** No route returns an auth URL, opens a browser, or
  handles a callback.
- **Config file path:** never specified. No `--config` flag is passed and
  `RCLONE_CONFIG` is never set, so rclone falls back to its own default
  (`~/.config/rclone/rclone.conf`) under the **server process's** `HOME`. Not
  hardcoded, but also **not configurable from SciDK** — and under gunicorn the
  effective `HOME` may not be the operator's.
- **`rclone lsjson`:** yes, two call sites.
  - `RcloneProvider.list_files` (`:309-343`): `lsjson <target>`, then either
    `--recursive` or `--max-depth <n>` (default 1), plus optional `--fast-list`
    which is retried without the flag if it fails.
  - `RcloneProvider.list` (`:366-457`): two calls —
    `lsjson <target> --max-depth 1 --dirs-only` and
    `lsjson <target> --max-depth 1 --files-only` — falling back to a single
    `lsjson <target> --max-depth 1` if both come back empty.

Other rclone subprocesses: `cat` (`:271`, used for byte-range reads),
`listremotes` (`:355`), `version` (`:346`), and `rclone mount` spawned by
`POST /api/rclone/mounts` (`api_providers.py:122+`).

**Gap** — Everything for "add a drive" is absent: no `config create` wrapper,
no OAuth handshake, no config-path setting, no remote-name validation on write.
Note the mount manager already models the safe pattern (validate the remote
against `_listremotes()`, sanitize the name with `_sanitize_name`,
`api_providers.py:55-70`) — a config-create route should reuse it.

---

## Q4 — Scan history per path

**Status: partial — the table exists, nothing reads it over HTTP.**

**`file_history` exists.** `scidk/core/path_index_sqlite.py:109-128`:

```sql
CREATE TABLE IF NOT EXISTS file_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filesystem TEXT,
    path TEXT NOT NULL,
    size INTEGER,
    modified_time REAL,
    hash TEXT,
    scan_id TEXT,
    change_type TEXT,              -- 'created' | 'modified' | 'deleted'
    previous_size INTEGER,
    previous_modified_time REAL,
    previous_path TEXT,
    logical_key TEXT
);
-- idx_hist_path(path), idx_hist_scan(scan_id)
```

Populated by exactly one writer: `apply_basic_change_history(scan_id,
target_root)` (`path_index_sqlite.py:312-378`), called from **one place** —
`api_files.py:577`, inside the **rclone branch only** of `POST /api/scan`.

Three caveats that matter for a timeline UI:
- It is **size-based only**. Every inserted row leaves `modified_time`, `hash`,
  `filesystem`, and `logical_key` NULL (see the three INSERTs at `:345`, `:356`,
  `:367`). So "mtime changed" is not recorded.
- The previous scan is picked by a heuristic: `SELECT scan_id FROM files WHERE
  scan_id <> ? AND path LIKE ? ORDER BY rowid DESC LIMIT 1` (`:326`). It is not
  ordered by time and can select the wrong baseline.
- `local_fs` and `mounted_fs` scans never call it, so **no history exists for
  local scans at all**.

**No `scan_events` / `scan_log` table.** The scan-side tables are:
- `scans` (`migrations.py:66`): `id, root, started, completed, status, extra_json`
- `scan_items` (`:79`): `scan_id, path, type, size, modified_time,
  file_extension, mime_type, etag, hash, extra_json`, PK `(scan_id, path)`
- `scan_progress` (`:100`), `background_tasks` (`:148`), `logs` (`:136`)
- `files` (`path_index_sqlite.py:47`): the main index —
  `path, parent_path, name, depth, type, size, modified_time, file_extension,
  mime_type, etag, hash, remote, scan_id, extra_json, interpreted_as,
  interpretation_json`

**No route returns per-path history.** Grepped every blueprint: `file_history`
appears in zero route files. There is no endpoint for "when did this file first
appear / change / get interpreted".

**Closest reconstruction.** Yes, it is reconstructible, but only partly:

```sql
-- appearance + size/mtime timeline for one path
SELECT f.scan_id, s.completed, f.size, f.modified_time, f.interpreted_as
FROM files f JOIN scans s ON s.id = f.scan_id
WHERE f.path = ?            -- idx_files_path covers this
ORDER BY s.completed;
```

plus `SELECT * FROM file_history WHERE path = ? ORDER BY id` for rclone-scanned
paths.

**Gap**
1. No read route. A `GET /api/files/history?path=` is entirely new work.
2. **"Interpreted at" is not recorded anywhere.** `files.interpreted_as` /
   `interpretation_json` have no timestamp column, and the Neo4j
   `(:File)-[:INTERPRETED_AS]->(:Interpreter)` edge carries no property either
   (`neo4j_client.py:174-175`). The git-style timeline's "interpreted" event
   cannot be dated without a schema addition.
3. `apply_basic_change_history` needs to run for local scans too, and needs an
   mtime/hash arm, before the timeline shows "file changed" for anything
   non-rclone.
4. Any schema change to `files.db` goes in `path_index_sqlite.init_db()`, **not**
   `migrations.py` — see the session-context warning and the v25 retirement note.

---

## Q5 — Collection sweep (Dataset completeness check)

**Status: partial — the graph shape is right, the proposed query is not.**

**`Dataset` nodes exist.** Written by
`scidk/services/dataset_node_service.py:write_dataset_nodes` (`:168-278`),
called post-commit from `api_neo4j.py:174` and `api_tasks.py:604`.

```cypher
MERGE (d:Dataset {path: $dir_path, host: $host})
ON CREATE SET d.created_at = timestamp()
SET d.name = $name, d.type = $type, d.profile = $profile_id,
    d.scan_id = $scan_id, d.updated_at = timestamp()
```

Properties: `path`, `host` (composite key), `name`, `type`, `profile`,
`scan_id`, `created_at`, `updated_at`.

**`CONTAINS` edges exist.** `dataset_node_service.py:252-259`:

```cypher
MATCH (d:Dataset {path: $dir_path, host: $host})
UNWIND $file_paths AS fp
MATCH (f:File {path: fp, host: $host})
MERGE (d)-[:CONTAINS]->(f)
```

Only files **directly under** the matched directory are linked (`:222-224`),
and only directories that match a non-abstract, enabled dataset profile get a
node at all (`:210`). Coverage is partial by design.

**`File` node shape** — `scidk/services/neo4j_client.py:164-171` (`write_scan`):

```
(:File {path, host})                      // composite key
  .filename, .extension, .size_bytes, .created, .modified, .mime_type,
  .provider_id, .host_type, .host_id, .interpreted_as
```

**`Folder` also has `CONTAINS`** → `(:Folder)-[:CONTAINS]->(:File)` and
`(:Folder)-[:CONTAINS]->(:Folder)` (`neo4j_client.py:159-161`, `:179-180`).

**No sweep route.** No `/api/collections/*` exists anywhere.

**The proposed query will return nothing as written.** Two property names are
wrong and one match is unlabelled:

- `f.name` — File nodes have **`filename`**, not `name`. (`name` is on `Folder`
  and `Dataset`.)
- `f.size` — File nodes have **`size_bytes`**.
- `MATCH (d)-[:CONTAINS]->(all)` is unlabelled; harmless for `Dataset` today
  since only Files hang off it, but it should be `(all:File)`.

Corrected:

```cypher
MATCH (d:Dataset)-[:CONTAINS]->(f:File)
WHERE f.filename IN $file_names
WITH d, count(DISTINCT f) AS present
MATCH (d)-[:CONTAINS]->(all:File)
WITH d, present, count(DISTINCT all) AS total
WHERE present < total
RETURN d.name AS name, d.path AS path, d.host AS host, present, total
ORDER BY (1.0 * present / total) DESC
```

**Gap**
1. Build the sweep route; it is new.
2. Matching by **filename** is ambiguous across a 5.5M-node graph — the same
   basename recurs constantly. If the Collection panel can supply full paths,
   match on `f.path IN $paths` (and ideally `{path, host}` pairs) instead;
   that also uses the composite index rather than scanning.
3. There is no index on `File.filename`, so `f.filename IN $names` is a label
   scan over every File node. Either add the index or switch to path matching.

---

## Q6 — Dataset creation

**Status: missing.**

- **`POST /api/datasets`?** No. Only `GET /api/datasets` (`api_files.py:794`)
  and `GET /api/datasets/<dataset_id>` (`:800`).
- **Naming collision, important.** Those two GETs return
  `ext['graph'].list_datasets()` — the **legacy in-memory per-file "dataset"**
  from the original scanner model, keyed by checksum. They have nothing to do
  with the Neo4j `:Dataset` nodes from Q5. A `POST /api/datasets` bolted onto
  this blueprint would sit next to two GETs that describe a different entity.
  Consider `/api/collections` or `/api/graph/datasets` instead.
- **Similar route elsewhere?** No. The attribution routes write *edges* between
  existing nodes; `api_annotations.py` writes SQLite `relationships` rows, not
  typed graph nodes. The only code that creates a `:Dataset` with `CONTAINS`
  edges is `dataset_node_service.write_dataset_nodes`, and it is a post-commit
  service function, not reachable over HTTP.

**Neo4j write pattern to copy.** Two established shapes:

1. *Typed node + edges* — `dataset_node_service.py:229-259` (quoted in Q5):
   `MERGE` keyed on `{path, host}`, `ON CREATE SET created_at`, then a separate
   `UNWIND $file_paths ... MERGE (d)-[:CONTAINS]->(f)`. Uses
   `neo4j_client.execute_write`.
2. *Edge with provenance* — `folder_attribution.py:487-501` (the confirm route's
   service), one round trip for the whole batch:

```cypher
MATCH (p:Investigator {name: $name})
UNWIND $paths AS target
MATCH (f:Folder {path: target})
MERGE (p)-[rel:OWNS]->(f)
ON CREATE SET rel.confirmed_by = $by, rel.confirmed_at = $ts,
              rel.method = 'attribution_panel'
RETURN DISTINCT target AS path
```

Both are single-round-trip and batched, per the operating constraints. Do not
use `write_declared_nodes` for this — it autocommits per statement and cannot
express the `UNWIND`-batched edge write.

**File node addressing: composite `(path, host)`.** Not hash, not UUID.
`host` is `scan['host_id']`, derived at scan time (`api_files.py:635-650`):
`local:<nodename>` for `local_fs`, `mounted:<root_id>` for `mounted_fs`,
`rclone:<remote>` for rclone; it lands in SQLite as `files.remote`, COALESCEd
to `''`.

**Gap** — `POST /api/datasets {name, file_paths}` cannot resolve File nodes from
`file_paths` alone. Either the body must carry `host`, or the route must look up
`files.remote` per path in SQLite first (one batched `SELECT path, remote FROM
files WHERE path IN (...)`, then group by host). Matching `(:File {path})`
without `host` is the pathological form the session context warns about — it
cannot use the composite index and scans all File nodes.

---

## Q7 — Interpreter status per file

**Status: partial.**

- **`GET /api/interpreters/status?paths[]=`?** Does not exist.
  `GET /api/interpreters` (`api_interpreters.py:15-53`) returns **registry
  metadata only** — global, not per path: `{id, name, version, globs,
  extensions, enabled, default_enabled, cost, runtime, last_used,
  success_rate}`. `?view=effective` overlays the env/CLI enable set.
  `GET /api/enrichment/interpreters` (`api_enrichment.py:72`) is a second,
  similar listing.

- **Where run state lives — two places, neither timestamped:**
  - **SQLite** `files.interpreted_as` (TEXT, interpreter id) and
    `files.interpretation_json` — per `(path, scan_id)`
    (`path_index_sqlite.py:66-72`, index `idx_files_interpreted_as` at `:100`).
  - **Neo4j** `f.interpreted_as` plus `(:File)-[:INTERPRETED_AS]->(:Interpreter
    {id})` (`neo4j_client.py:169-175`, also `web/helpers.py:486-515`).
  - The legacy in-memory graph also holds `add_interpretation(checksum, id,
    {status, data, interpreter_version})` (`api_files.py:850`), used by the old
    `POST /api/interpret` path.

- **Interpreters present** (`scidk/interpreters/`, id → extensions):

  | id | name | handles |
  |---|---|---|
  | `csv` | CSV Interpreter | `.csv` |
  | `txt` | Text File Interpreter | `.txt` |
  | `json` | JSON Interpreter | `.json` |
  | `yaml` | YAML Interpreter | `.yml`, `.yaml` |
  | `xlsx` | Excel Workbook Interpreter | `.xlsx`, `.xlsm` |
  | `python_code` | Python Code Analyzer | `.py` |
  | `ipynb` | Jupyter Notebook Interpreter | `.ipynb` |
  | `fcs_interpreter` | FCS Flow Cytometry Interpreter | `.fcs` |
  | `svs_interpreter` | Whole-Slide Image Interpreter | `.svs`, `.ndpi`, `.scn` |
  | `ome_tiff` | OME-TIFF Interpreter | `.ome.tif`, `.ome.tiff` |
  | `dicom_bioformats` | DICOM Bio-Formats Interpreter | `.dcm`, `.dicom` |
  | `bruker_skyscan_log` | Bruker SkyScan Log | `.log` |
  | `bruker_microct_dataset` | Bruker MicroCT Dataset | directory dispatch |
  | `flow_session_interpreter` | Flow Cytometry Session | directory dispatch |
  | `histology_session_interpreter` | Histology Session | directory dispatch |
  | `bioformats_base` | Bio-Formats Base | abstract — subclasses override |
  | `eda_interpreter` | (see `eda_interpreter.py`) | — |

  `TEMPLATE_imaging.py` is a scaffold, not a live interpreter. Registration is
  by extension in `scidk/interpreters/__init__.py:73`
  (`registry.register_extension`); directory-dispatch interpreters override
  `can_handle` and declare `extensions = []`.

- **Trigger a run on specific paths?** Three routes, none of them is
  "run interpreter X over this list of paths":
  - `POST /api/files/interpret` (`api_files.py:1845`) — **preview only**, one
    `file_path`, and `interpreter_id` resolves against **`ScriptsManager`
    user scripts**, not the built-in registry. Runs in `run_sandboxed` with a
    10s timeout, returns a `preview_hash`. `POST /api/files/interpret/commit`
    (`:1938`) commits that preview.
  - `POST /api/interpret` (`api_files.py:808`) — registry interpreters, but
    takes a single legacy `dataset_id`, not a path.
  - `POST /api/enrichment/run` (`api_enrichment.py:30`) — the real batch
    dispatcher, body `{interpreter, limit, scan_id, force}`. Selects its own
    work from SQLite; **cannot be aimed at a caller-supplied path list**.

**Gap**
1. New route needed: `GET /api/interpreters/status` over a path list. It should
   be one batched SQLite query (`SELECT path, interpreted_as FROM files WHERE
   path IN (...)`, covered by `idx_files_path`) joined against the registry's
   extension map to compute "which interpreters *should* have run".
2. No run timestamps anywhere — "when was it interpreted" needs a schema change
   (see Q4 gap 2).
3. No path-scoped run trigger. `POST /api/enrichment/run` would need a `paths`
   parameter, or a new route.
4. Two competing interpreter concepts (registry classes vs. `ScriptsManager`
   user scripts) are reachable through similarly named routes. The Interpret tab
   must pick one; the registry is the one that populates `interpreted_as`.

---

## Q8 — Annotation / Attribution wiring

**Status: exists. All six routes present; the suite is green.**

| Route | Location | Notes |
|---|---|---|
| `GET /api/schema/labels` | `api_graph.py:1227` | `CALL db.labels()`; `{"labels": [...]}`; 501 if Neo4j unconfigured, 502 on failure |
| `GET /api/files/attribution/anchors` | `api_files.py:2109` | `anchor_label` (default `Investigator`), plus `filter_property`/`filter_value` |
| `GET .../anchor-properties` | `api_files.py:2170` | |
| `GET .../anchor-property-values` | `api_files.py:2203` | |
| `POST .../candidates` | `api_files.py:2294` | |
| `POST .../confirm` | `api_files.py:2361` | |

Also present and possibly useful to the drawer: `GET .../persons` (`:2152`,
legacy alias) and `GET .../relationship-suggestions` (`:2250`).

All are `@require_role('admin', 'user')`. All share a cached driver keyed on
connection params (`_attribution_service`, `api_files.py:2071-2106`) — the
driver lives on `app.extensions['scidk']` and is not closed per request.

**Tested and working.** `tests/test_attribution_service.py` (798 lines),
`tests/test_user_attribution.py`, `tests/test_filter_builder.py`,
`tests/test_dataset_node_service.py`, `tests/test_scan_browse_indexed.py` —
**113 passed in 5.36s** on this working tree.

**Does `confirm` accept individual file paths?** Yes — with three caveats.

`FolderAttributionService.confirm` (`folder_attribution.py:459-511`) takes
`target_paths` and `target_label` and builds
`MATCH (f:{target} {path: target})`. Passing `target_label='File'` with
file-level paths is a supported call; nothing is folder-specific in the write.

1. **The match is path-only — no `host`.** On the production graph this is
   exactly the form the operating constraints call out (composite index on
   `(path, host)`; the path-only form scans all File nodes). It is one query for
   the whole batch, not one per path, so the cost is a single scan rather than
   N — but it is still a scan. Either add `host` to the match or accept the hit
   and measure it.
2. **`target_paths` must match `File.path` byte-for-byte.** The candidates
   endpoint returns `f.path` straight from the graph, so a selection round-tripped
   through the panel is safe; a path assembled in the browser from a `/api/browse`
   listing is not necessarily the same string.
3. **Candidates require `SCANNED_IN`.** `_fetch_folders`
   (`folder_attribution.py:610-668`) matches
   `(f:{target_label})-[:SCANNED_IN]->(s:Scan)`. File nodes do carry
   `SCANNED_IN` (`neo4j_client.py:171`), so `target_label='File'` works — but
   only for files committed to Neo4j through a scan commit. Uncommitted paths
   will not appear as candidates even though `confirm` would accept them.

Also note `MIN_VARIANT_LEN` filtering in `_fetch_folders` — name variants
shorter than the threshold are dropped, so short anchor names yield no
candidates.

**Gap** — Functionally none for the Attribute tab. Two things to decide:
whether to pass `host` through `confirm` for index use, and whether the drawer
sends paths it obtained from `/api/browse` (risky) or from `candidates` (safe).

---

## Q9 — `/api/scans/<id>/browse` for Index mode

**Status: exists and works.**

**Evidence** — `api_files.py:1778-1802`, delegating to
`FSIndexService.browse_children` (`scidk/services/fs_index_service.py:20-151`).
Covered by `tests/test_scan_browse_indexed.py` (all pass).

- **`path` parameter:** yes. Empty defaults to the scan's base path
  (`fs_index_service.py:73-76`). Matching is exact string equality on
  `files.parent_path`.
- **Response shape — *not* the same as `/api/browse`:**

```json
{"scan_id": "...", "path": "...", "page_size": 100,
 "entries": [{"path": "...", "name": "...", "type": "file|folder",
              "size": 0, "modified": 0.0, "extension": ".csv",
              "mime_type": "...", "interpreted_as": null,
              "interpretation_json": null}],
 "next_page_token": "200"}
```

  vs `/api/browse` → `{"entries": [{"id", "name", "type", "size", "mtime",
  "provider_id"}]}`. Differences the page must reconcile: **`path` vs `id`**,
  **`modified` vs `mtime`**, no `provider_id` in Index mode, and two extra
  interpretation fields. `/api/browse` also returns a bare `{entries}` with no
  envelope, no `page_size`, and no pagination at all.

- **Pagination:** offset-based, but **not** via `page`/`page_size` as the
  question assumes. It is `page_size` (default 100, clamped 1–1000) +
  `next_page_token`, where the token is the stringified integer offset
  (`fs_index_service.py:78-89`, `:143`). No `page` parameter. Also supports
  `extension`/`ext` and `type` filters.

**Known issues**
1. `LIMIT ? OFFSET ?` over a 27M-row `files` table is O(offset). Deep paging
   into a large directory degrades linearly. `idx_files_scan_parent_name`
   (`path_index_sqlite.py:76`) covers the `WHERE` and `ORDER BY`, so shallow
   pages are fine.
2. `interpretation_json` is returned **raw and unbounded** for every row
   (`fs_index_service.py:130`). `datasets.html` calls this route with
   `page_size=1000`; if those rows carry real interpretation payloads the
   response can be very large. Nothing truncates it.
3. Exact `parent_path` equality means a trailing-slash or normalization
   mismatch silently returns zero entries rather than an error.
4. The `extension` filter requires the stored form (lowercase, leading dot);
   `.CSV` or `csv` matches nothing.
5. Unknown scan id → 404 `{"error": "scan not found"}` (`:64`, `:71`); the
   service reconstructs a missing in-memory scan from the `scans` table first.

**Separate finding — a route the page calls that does not exist.**
`datasets.html` fetches `/api/scans/${scanId}/entries` in two places. Grepped
every blueprint: **there is no `/entries` route on `/api/scans`.** Those calls
404. Either the template should use `/browse`, or the route needs building.

---

## Cross-cutting notes for the task doc

1. **Property-name mismatches are the highest-value thing to fix in the spec
   before Junie starts.** `File` nodes have `filename`/`size_bytes`, not
   `name`/`size`. Any Cypher in the task doc written against `f.name` will
   silently return empty rather than error.
2. **`(path, host)` is the File node key.** Every new Cypher touching File must
   match both, and `host` must be resolved from `files.remote` (COALESCE `''`)
   or carried in the request body. This is both a correctness and a performance
   requirement.
3. **`files.db` schema changes go in `path_index_sqlite.init_db()`**, never
   `migrations.py` — the latter runs against every test database and none of
   them has a `files` table.
4. **Timestamps are the missing primitive.** Q4 (scan timeline) and Q7
   (interpret history) both need an "interpreted at" that no store currently
   records. Decide once — a column on `files`, a property on the
   `INTERPRETED_AS` edge, or rows in `file_history` — and use it for both.
5. **Response-shape divergence between `/api/browse` and
   `/api/scans/<id>/browse`** (`id`/`mtime` vs `path`/`modified`) is an existing
   trap for any code that switches between Server and Index mode.
