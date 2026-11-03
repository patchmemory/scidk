# Source Intake Architecture Review

**Scope:** Current branch `design/knowledge-curation-20261029` at `28701f8`, reviewed 2026-11-03.

## Finding

SciDK already has a built-in, runnable table-import path for CSV, TSV and Excel. It is not an optional external plugin and must not disappear merely because no deployment-installed source plugins are registered.

The current Resources experience makes this capability difficult to reach because the Sources empty state directs people to Plugins. In a profile with no installed plugin templates, that creates an apparent dead end despite the built-in importer being present.

## Evidence

- `scidk/pipeline/file_source.py` implements `TabularFilePlugin`, a local CSV/TSV/Excel `DataSourcePlugin`.
- `scidk/pipeline/plugin_registry.py` resolves `tabular_file`, `file_upload`, `csv`, `tsv`, `excel`, and `table_loader` as built-ins. Its module documentation explicitly states that Table Loader with CSV/Excel/TSV presets must work even when every package in `plugins/` is disabled.
- `scidk/web/routes/api_pipeline.py` documents and exposes source CRUD, upload/test-connection, schema, mapping, FAIR/preflight, and runs. Its source-creation contract supports a template `preset`.
- `scidk/ui/templates/pipeline_sources.html` describes the existing pipeline source flow, including an Add Source picker populated from plugin templates.

## Recommended product model

```
Built-in table/file import ──> Source instance ──> schema/mapping ──> run history
External connector template ──> connection/profile ─> Source instance ──> schema/mapping ──> run history
```

The first lane is a core SciDK capability; the second is extensibility. They should be presented together under **Sources**, but never conflated.

### Sources page

1. Keep the configured-source list as the primary content.
2. Always offer **Import a table or file** when no external plugins are installed:
   - CSV
   - TSV
   - Excel
3. Route that action into the existing source flow with a built-in `tabular_file`/Table Loader preset, then preserve the established upload, preview, schema, mapping, FAIR-check, and run steps.
4. Show external connectors separately as **Additional source connectors**, using the real installed/available state only.
5. If none are installed, say so without blocking table/file import; link to Plugins for deployment extension instructions.

### Plugins page

Describe code capabilities by category and status:

- Built-in: local table/file import (always available)
- Installed connector templates: only what the active registry actually exposes
- Planned/unavailable: never presented as selectable source types

### Profiles and interpreters

- **Connection profiles** are reusable configuration/access details for external connectors. Keep secrets and editing under Settings; show only a read-only summary in Resources.
- **Interpreters/profilers** operate on inventory/files and recognised datasets. They are neither a connector template nor a Source instance.
- Keep the inventory chain distinct:

```
Inventory/files.db ──> interpreters/profilers ──> recognised datasets
```

## Implementation guardrails

- Do not turn the built-in table importer into a fake optional plugin.
- Do not fabricate CSV/SQL/Neo4j/RDF source templates unless their executable contract is actually registered.
- Preserve the legacy `/pipeline/sources` flow and its deep links.
- Retain existing upload-directory/path guards; a source upload should not become an arbitrary server-side file reader.
- Expose source mapping and run configuration on the configured Source instance, not the template.

## Follow-up tests

- With zero installed external plugin templates, Resources -> Sources still offers and successfully launches built-in CSV/TSV/Excel intake.
- Built-in intake reaches column preview, schema, mapping, and a dry/Fair check using existing infrastructure.
- External-plugin empty state does not claim that no Sources can be created.
- Source list accurately distinguishes built-in table/file sources from connector-backed sources.
- Profile and interpreter summaries report only existing configuration/capability.
