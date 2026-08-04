# SharePoint Intake Plugin

Ingests the AIPT SharePoint intake list into the SciDK knowledge graph.

The SharePoint list is exported to CSV (a Power Automate mirror flow keeps it
current and writes back attachment metadata) and made reachable to SciDK via an
[rclone](../../docs) remote. This plugin fetches that CSV, resolves each row into
graph entities, and MERGEs them into Neo4j.

## Graph model

| Node | Key property | Notes |
|---|---|---|
| `Project` | `project_id` | `CACProtocol`, else a deterministic fallback (`ShortDescription\|RecordSource\|index`) |
| `Person` | `email`, else `name` | submitter, PI, and collaborators |
| `Attachment` | `path`, else `filename` | only created when `AttachmentStatus == "available"` |

| Relationship | From → To |
|---|---|
| `SUBMITTED` | `Person` → `Project` |
| `PI_OF` | `Person` → `Project` |
| `COLLABORATES_ON` | `Person` → `Project` |
| `HAS_ATTACHMENT` | `Project` → `Attachment` |

## Configuration

All column mappings and vocabularies live in `config.py` — nothing is hardcoded
in the ingest logic. Runtime location of the data source is resolved with the
standard SciDK precedence (**persisted setting → environment variable → default**):

| Purpose | Setting key | Env var |
|---|---|---|
| SharePoint list CSV | `sharepoint_intake_sync_remote` | `SCIDK_SHAREPOINT_INTAKE_SYNC_REMOTE` |
| Controlled-vocabulary CSV | `sharepoint_intake_vocab_path` | `SCIDK_SHAREPOINT_INTAKE_VOCAB_PATH` |

If no vocabulary source is configured, the built-in `DEFAULT_VOCABULARY` is used.
The vocabulary check is a **soft consistency check**: mismatches are reported as
warnings and never block ingest.

### Field resolution highlights

- **`_sp` / `_orig` variants** (`StudyType`, `CellToxicity`, `Measurements`) prefer
  the current SharePoint value and fall back to the legacy Drupal value.
- **People** are parsed from RFC 5322 archived columns (`"Jane Smith <j@mit.edu>"`),
  falling back to the raw People-picker display name when no archived column exists.

## Usage

Registered as a multi-instance plugin template (`id: sharepoint_intake`). Instance
config keys:

- `source` / `file_path` — rclone remote path (`remote:path`) or a local CSV path.
  Omit to use the configured sync-remote setting.
- `dry_run` — build and count declarations without writing (default `false`).
- `timeout_sec` — rclone fetch timeout (default `120`).

Presets: **Preview (dry run)** and **Ingest to graph**.

Programmatic use:

```python
from plugins.sharepoint_intake.ingest import run_ingest

summary = run_ingest({"source": "aipt:intake/merged_list.csv", "dry_run": True})
print(summary["message"])
```

## Error isolation

Each row is processed independently. A row lacking both `CACProtocol` and
`ShortDescription` (no usable identity) is recorded in `errors` and skipped; the
run continues. Source/parse failures and an unconfigured Neo4j connection are the
only fatal conditions, and they are returned as `{"status": "error", ...}` rather
than raised.

## Files

- `config.py` — field map, attachment columns, vocabularies, settings keys.
- `parser.py` — pure resolvers (no Flask/Neo4j imports); unit-testable in isolation.
- `ingest.py` — orchestration: rclone fetch → pandas → declarations → Neo4j write.
- `__init__.py` — plugin registration and handler.
