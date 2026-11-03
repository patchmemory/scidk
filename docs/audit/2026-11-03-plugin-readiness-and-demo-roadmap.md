# Plugin Readiness and Demo Roadmap

**Scope:** `design/knowledge-curation-20261029` at `28701f8`, reviewed 2026-11-03.

## Contract that exists today

`scidk.pipeline.plugin_base.DataSourcePlugin` is the canonical source-plugin interface:

- `find(config)`: bounded discovery, columns and preview
- `access(config)`: verifies the read that a run will need
- `fetch(config)`: lazy raw-row stream
- `transform_library()`: pure, documented source-specific transforms

The Pipeline owns mapping, graph writes, FAIR/preflight reporting, scheduling and run history. Source plugins must not write to Neo4j directly.

## Readiness inventory

| Capability | Evidence | Readiness | Recommended role |
| --- | --- | --- | --- |
| Built-in table/file import | `scidk/pipeline/file_source.py`; resolves CSV, TSV, Excel, upload and Table Loader aliases | Runnable | Always-available Source path |
| SharePoint Intake | `plugins/sharepoint_intake/`; DataSourcePlugin methods, rclone/local export support, reference AIPT mapping, contract/transform tests | Runnable after real profile/path configuration | First external-plugin demo |
| iLab Data Importer | `plugins/ilab_table_loader/`; Equipment, Services and PI Directory presets, column hints and old SQLite importer tests | Template-only, not a DataSourcePlugin | Adapt into built-in-table Source adapter |
| EDA | `scidk/interpreters/eda_interpreter.py`; parser/label conversion and tests; direct label-import route | Interpreter/legacy direct import, not a Source plugin | Future EDA Source or Ecosystem interpreter |
| PubMed / MeSH | Documentation examples only | Not implemented | Future API-backed Source plugin |
| PubChem | No runnable plugin found | Not implemented | Future API-backed Source plugin |

The old `dev/code-imports/nc3rsEDA` material is referenced by the EDA interpreter but has been described in repository audit material as an archival import, not an operational dependency.

## Minimum compelling demo

1. Present **Import a table or file** in Sources independently of external plugin availability.
2. Create a Source from a safe local CSV/Excel file and demonstrate preview, schema/mapping, FAIR/dry check, and run history.
3. Load/register SharePoint Intake and demonstrate the same flow using a local SharePoint export.
4. Configure a real rclone-backed SharePoint path only after the export flow is clean and verified.
5. Surface health truthfully: template installed, profile configured, Source accessible, mapping ready, latest run outcome.

## iLab implementation direction

Do not direct new work through the legacy `TableImporter → SQLite table` route as a separate ingestion model.

Instead, implement an iLab adapter over the existing `TabularFilePlugin`:

- Source types remain CSV/Excel table files.
- iLab presets supply default friendly name, expected/header hints, suggested labels and mapping starters.
- The adapter implements the four DataSourcePlugin methods by delegating file reading to TabularFilePlugin.
- Mapping, FAIR check, dry run and graph writes stay entirely in Pipeline.
- Keep the old importer only for backward compatibility until migration is deliberate.

This makes iLab the first domain-specialized tabular Source, rather than an exception.

## Estimated delivery bands

- **4–6 focused hours:** Sources UI activation plus built-in file demo and SharePoint local-export source demo.
- **7–10 focused hours:** add iLab adapter/presets to the shared Source contract, mapping starter and test coverage.
- **1–2 focused days after that:** reusable plugin authoring harness with manifest validation, contract fixtures, negative/error tests, preview/FAIR/run integration suite and documentation template.
- **Per new API integration:** generally 1–2 days for a careful PubMed/PubChem-like plugin; longer when an unfamiliar external data model needs ontology/mapping decisions.

## Plugin acceptance suite to build next

A source-capable plugin should prove:

1. manifest/capability declaration is valid;
2. source configuration validation gives actionable, redacted errors;
3. find/access/fetch/transform contract succeeds with fixtures;
4. timeout, malformed input, missing profile and invalid credentials fail safely;
5. preview and mapping work against representative data;
6. FAIR/preflight/dry run make no graph writes;
7. a permitted run records structured provenance and history;
8. schedule/retry controls only appear when infrastructure and plugin capability support them;
9. existing Resources pages report installed/configured/ready/degraded states accurately.

No plugin should receive a Run control merely because it has a UI template.
