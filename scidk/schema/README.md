# SciDK Schema Layer

The schema layer provides type-safe access to Label-defined node classes with
tab-completion, inline sanitization documentation, and a thin write adapter
that enforces sanitization policy before any Neo4j write.

## Architecture

```
scidk/labels/builtin/       ← Label YAML definitions (source of truth)
scidk/schema/
  base.py                   ← SciDKNode base class (the "ORM")
  sanitization.py           ← Sanitization pipeline
  registry.py               ← LabelRegistry (loads YAML definitions)
  generate_stubs.py         ← Generates Python classes from YAML
  generated/                ← Auto-generated stub classes (do not edit)
    sample.py
    imaging_dataset.py
    ...
    __init__.py
  __init__.py               ← Re-exports all generated classes
```

## Why a custom ORM instead of neomodel?

SciDK's Label definitions are user-defined and change at runtime. Existing
graph ORMs like neomodel assume static schemas defined at build time. The
mismatch causes friction in three places:

1. **Dynamic schema** — neomodel works best with statically defined classes.
   Dynamic class generation from YAML at runtime requires metaclass tricks
   that lose most of the IDE benefits.

2. **Sanitization** — the sanitization pipeline must intercept writes before
   they reach Neo4j. Hooking into neomodel's write path requires subclassing
   its property types or using pre-save signals — fighting the library rather
   than using it.

3. **Multi-format links** — Cypher links, GUI links, and spreadsheet links all
   bypass an ORM entirely. Two parallel paths to the graph is more complex than
   one consistent write path.

The custom ORM is intentionally thin (~100 lines in base.py). It provides:
- Schema metadata for tab-complete and type checking
- Sanitization at write time via `to_cypher_props()`
- MERGE Cypher generation via `merge_cypher()`

It does NOT abstract Cypher, manage connections, or implement relationship
traversal. Cypher remains the first-class interface for Links and Analyses.

## Setup

```bash
# Generate stub classes from Label YAML definitions
python -m scidk.schema.generate_stubs

# Or via CLI (if configured)
scidk labels generate-stubs
```

## Usage

```python
from scidk.schema import Sample, ImagingDataset, Study

# In an interpreter — create a node declaration
dataset = ImagingDataset(
    path=str(file_path.parent),
    modality="microCT",
    voxel_size_um=5.0,
    instrument="Bruker SkyScan 1272"
)
result.node_created(dataset)
# Sanitization runs automatically when the commit pipeline calls
# dataset.to_declaration() → write_declared_nodes()

# In a link script — use Label classes for type-safe property access
from scidk.schema import Sample
# Tab-complete shows: Sample.sample_id, Sample.species, Sample.donor_age, ...
# Inline docs show: donor_age is binned, donor_name is redacted, etc.

# Validate a node before declaring it
errors = dataset.validate()
if errors:
    logger.warning(f"Validation issues: {errors}")
```

## Adding a new Label

1. Create a YAML file in `scidk/labels/` (or `scidk/labels/builtin/` for
   built-in labels that ship with SciDK)

2. Follow the format in `scidk/labels/builtin/sample.yaml`

3. Regenerate stubs:
   ```bash
   python -m scidk.schema.generate_stubs
   ```

4. Push constraints to Neo4j via the Labels page in the SciDK UI
   (or `scidk labels push` from the CLI)

5. The new class is immediately importable:
   ```python
   from scidk.schema import MyNewLabel
   ```

## Sanitization rules

Sanitization is defined per-property in the Label YAML and enforced at write
time — no module can bypass it. Rules:

| Rule | Behavior | Use for |
|---|---|---|
| `none` | Pass through unchanged | Non-sensitive scientific metadata |
| `redact` | Drop entirely, never written | Names, emails, PII |
| `hash` | Deterministic SHA-256 | Institution names, cohort IDs |
| `bin` | Numeric range e.g. 45→"40-50 years" | Age, weight |
| `encode` | Map to controlled vocabulary | Diagnoses, phenotypes |
| `truncate` | Round to reduce precision | GPS coordinates |

If a sanitization rule fails, the property passes through unchanged and a
warning is logged. Failed sanitization never prevents a write.

## Running tests

```bash
pytest tests/test_schema.py -v
```
