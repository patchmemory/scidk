# LwM demo fixture

One fixture for tests and "done when" checks, built from `demo_data/lwm2026/`
(the multimodal lung-tumor imaging study). Also the demo sample folder.

| Part | What it is |
|---|---|
| `tree/` | Stub folder tree: the real relative paths from `source_results/listings/` |
| `manifest.csv` | One row per file in `tree/`: source, kind, real size and date from the listing |
| `folders.csv` | Every folder, with the real file count and bytes the listing reported |
| `graph/` | Copy of `demo_data/lwm2026/data/`, loaded by `demo_data/lwm2026/load_demo_graph.py` |
| `files.db` | Not committed: built by the real scanner (`tools/scidk_scanner_opt.py`) when needed |

`tree/dropbox/MultiModal/LungTumor/` is the Dropbox study folder; `tree/atwai/` holds
the atwai folders (microCT copies and analysis under `Anderson_Scott`, `Milton_CornwallBrady`
and `archive`, MRI under `huangw/2024`).

**Kinds of file** (`manifest.csv`):
- `placeholder`: empty file at a real path (Dropbox listing).
- `metadata`: real content rebuilt from the listings: SkyScan `*_rec.log`, IVIS `ClickInfo.txt`,
  ParaVision `method` / `acqp`. Only the lines the original `grep` captured are present.
- `inferred`: atwai lists counts per folder, not names. Slices are named from each
  reconstruction log (`Filename Prefix`, `First Section`, `Last Section`), and each
  ParaVision acquisition gets a `fid`.

**What's reduced:** numbered image series longer than 8 keep their first 5 and last file
(about 48k microCT slices become ~500), and atwai folders whose file names aren't in any
listing are empty. Real counts and bytes stay in `folders.csv` (Dropbox root: 49,758 files,
154 GB). Sizes on disk are not real.

## Use

In pytest (`tests/fixtures/demo/pytest_plugin.py`, registered in `tests/conftest.py`):

```python
def test_something(demo_tree, demo_files_db):
    db_path, scan_id = demo_files_db          # session-scoped, built once (~1 s)
```

From code (`demo_fixture.py`): `materialize(dest)` copies the tree and restores empty folders
and dates (git keeps neither, so scan the materialized copy, not `tree/`),
`build_files_db(db, root)` runs the scanner CLI, `graph_statements()` / `node_counts()` give
the study graph without a database, and `load_into(session)` loads it into a Neo4j session.

As a demo sample folder:

```bash
.venv/bin/python -c "from tests.fixtures.demo.demo_fixture import materialize; materialize('/tmp/LungTumorDemo')"
.venv/bin/python tools/scidk_scanner_opt.py /tmp/LungTumorDemo --db /tmp/LungTumorDemo.db --no-hash
```

Test: `.venv/bin/python -m pytest tests/test_demo_fixture.py -q`. The live-Neo4j load test is
skipped unless `SCIDK_DEMO_NEO4J_URI` (plus `_USER` / `_PASSWORD`) points at a throwaway
database; it wipes and reloads the `LWM-DEMO-2026` nodes there.

Regenerate after the listings change: `.venv/bin/python tests/fixtures/demo/build_tree.py`.
