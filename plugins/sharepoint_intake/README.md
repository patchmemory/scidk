# SharePoint Intake Plugin

Connects a SharePoint list or document library to SciDK as a **data source**.

This plugin implements the `DataSourcePlugin` contract and nothing more: it
discovers a list, verifies access, streams rows, and supplies SharePoint-specific
field transforms. It does **not** ingest. Mapping the rows into the graph, writing
to Neo4j, checking FAIR compliance, scheduling, and recording run history all
belong to the Pipeline (`scidk/pipeline/`).

The SharePoint list is exported to CSV or Excel (a Power Automate mirror flow
keeps it current and writes back attachment metadata) and made reachable via an
[rclone](https://rclone.org) remote. A local path to the same export also works,
which is what the tests use.

## The plugin contract

Defined in [`scidk/pipeline/plugin_base.py`](../../scidk/pipeline/plugin_base.py).
Four methods, one per FAIR principle:

| Method | FAIR | Returns | Notes |
|---|---|---|---|
| `find(config)` | **F**indable | `{ok, columns, row_count, sample, metadata, error}` | One lazy pass; keeps only the sample, so memory is flat. Targets <10s. |
| `access(config)` | **A**ccessible | `{ok, auth_method, error}` | Reads one byte of real content. `auth_method` is `rclone_oauth`, `rclone_basic`, `local`, or `None`. |
| `fetch(config)` | **I**nteroperable | `Iterator[dict]` | Raw `{column: value}` rows, streamed. No transforms applied. |
| `transform_library()` | **R**eproducible | `{name: callable}` | The six SharePoint-specific transforms. |

Neither `find()` nor `access()` raises for an unreachable source or a rejected
credential — those are results, reported in `ok`/`error`. `fetch()` raises
`ValueError` eagerly when no source is configured, so a misconfiguration surfaces
at the call rather than on first iteration.

### `find()` vs `access()`

They look redundant and are not. `find()` needs only enough of the source to
describe its schema, and can succeed with a credential scoped to listing and
metadata. `access()` asserts that the authenticated read of row content the
Pipeline will actually perform is permitted, and reports which credential did it.
A token that can enumerate a library but not download from it passes `find()` and
fails `access()`.

### `fetch()` laziness

Delimited sources stream off an `rclone cat` pipe one row at a time — the Pipeline
relies on this to ingest lists larger than memory. Two documented exceptions
buffer the whole source first:

- a provider with no `open()` (falls back to `cat()`, logged at debug);
- an Excel workbook, because an xlsx is a zip container and needs random access.

## Usage

```python
from plugins.sharepoint_intake import get_plugin

plugin = get_plugin()
config = {"source_path": "aipt:intake/merged_list.csv"}

print(plugin.find(config)["columns"])    # what is in the list
print(plugin.access(config))             # can we read it, and as whom
for row in plugin.fetch(config):         # raw rows, lazily
    ...
```

Instance config keys:

| Key | Default | Meaning |
|---|---|---|
| `source_path` | — | rclone remote path (`remote:Site/Lists/Name.csv`) or local path. `source` / `file_path` are accepted as aliases. |
| `sheet` | first sheet | Worksheet name, for an Excel export. |
| `sample_rows` | `3` | Preview rows returned by `find()`. |
| `max_scan_rows` | `100000` | Rows `find()` counts before reporting `row_count: None`. Lower it for a list too large to count inside the budget. |
| `timeout_sec` | `120` | Timeout for a buffered remote read. |

Omit `source_path` to fall back to the configured source, resolved with the
standard SciDK precedence (**persisted setting → environment variable**):

| Purpose | Setting key | Env var |
|---|---|---|
| SharePoint list export | `sharepoint_intake_sync_remote` | `SCIDK_SHAREPOINT_INTAKE_SYNC_REMOTE` |
| Controlled-vocabulary list | `sharepoint_intake_vocab_path` | `SCIDK_SHAREPOINT_INTAKE_VOCAB_PATH` |

The vocabulary path is read by the Pipeline's vocabulary check, not by the plugin
— the plugin does not validate values.

## Transform library

Pure functions in [`transforms.py`](transforms.py). Empty input returns the
type's empty value and never raises; malformed input raises `TransformError`,
which the Pipeline attributes to the row and column before continuing.

| Transform | Input | Output |
|---|---|---|
| `parse_rfc5322` | `"Jane Smith <j@mit.edu>"` | `{name, email}` |
| `parse_rfc5322_list` | `"A <a@x>; B <b@x>"` | `[{name, email}, ...]` |
| `sp_multiselect` | `"A;B;C"`, `"A;#B;#C"`, `"A,B,C"` | `["A", "B", "C"]` |
| `sp_date` | SharePoint date string | ISO-8601 string or `None` |
| `sp_yesno` | `"Yes"` / `"No"` | `True` / `False` (`None` when blank) |
| `sp_colresolution` | `(prefer_col, fallback_col, row)` | First non-empty value, else `None` |

Source-agnostic transforms (`lowercase_strip`, `integer_coerce`,
`boolean_coerce`, `date_parse`, `split_delimiter`) are **not** here. They live in
[`scidk/pipeline/transforms.py`](../../scidk/pipeline/transforms.py) and the
Pipeline always makes them available to a mapping config.

A few behaviours are decisions rather than accidents:

- `sp_yesno("")` is `None`, not `False` — "not stated" is not "No".
- `sp_date` keeps a date-only value a date instead of promoting it to midnight.
- `parse_rfc5322_list` treats a comma as a separator only when more than one
  address is present, so `"Smith, Jane <j@mit.edu>"` stays one person.
- A malformed entry in a person list raises rather than being skipped: silently
  dropping a collaborator is worse than failing the row.

## Mapping (Pipeline, not plugin)

`configs/aipt_intake_mapping.json` is the reference mapping for the AIPT
deployment. It declares — as configuration, not code — the node labels, merge
keys, property/column bindings, relationship types, `_sp`/`_orig` resolution
rules, the project-id fallback, the attachment condition, and the controlled
vocabularies. Its `conventions` block documents the format.

| Concern | Owner |
|---|---|
| Column→node/relationship mapping | `scidk/pipeline/mapping_engine.py` |
| `write_declared_nodes` call | `scidk/pipeline/runner.py` |
| FAIR check / dry run | `scidk/pipeline/runner.py` |
| Job scheduling | `scidk/pipeline/scheduler.py` |
| Run history | `scidk/pipeline/run_history.py` |

The mapping engine and runner are built in **Cycle 3B**; the mapping config
format is the stable interface between them and this plugin.

> **Identifier safety:** `write_declared_nodes` interpolates labels, relationship
> types, and property *names* raw into Cypher (only values are parameterized). The
> Pipeline mapping engine must sanitize every identifier that comes out of a
> mapping config before writing. See the `_LABEL_RE` / `_REL_RE` guards in
> `canvas_service.py`.

## Files

| File | Responsibility |
|---|---|
| `plugin.py` | `SharePointPlugin` — the four contract methods. |
| `ingest.py` | Streaming a source's rows lazily. |
| `source.py` | Locating, describing, and authorizing access to a source. |
| `readers.py` | Format parsing (delimited and Excel). |
| `transforms.py` | The six SharePoint-specific transforms. |
| `config.py` | Settings keys and the mapping-config path. Knows no columns. |
| `configs/aipt_intake_mapping.json` | Reference mapping for the AIPT deployment. |
| `__init__.py` | Template registration and `get_plugin()`. |

## Tests

- `tests/plugins/test_sharepoint_intake.py` — the four contract methods.
- `tests/plugins/test_sharepoint_transforms.py` — every transform.
- `tests/plugins/test_sharepoint_registration.py` — template registration.

All three run offline against a local CSV fixture and a fake rclone provider. Two
things still need a live list to confirm in the deployment: `find()` completing in
under 10s at production scale, and `access()` against genuinely valid vs. expired
rclone credentials.
