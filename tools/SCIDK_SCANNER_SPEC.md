# SciDK Filesystem Scanner — Integration Spec
**File:** `scidk_scanner.py`
**Branch target:** `production-mvp`
**Status:** Standalone tool, ready for repo integration

---

## Purpose

`scidk_scanner.py` is a standalone Python script that walks a filesystem volume,
classifies every file it finds, and writes results into a SQLite database that is
schema-identical to SciDK's internal `files.db`.

It is designed as a field tool for exploring unknown research volumes before or
independent of a full SciDK deployment. Because it writes the same schema,
any scan database can be read directly by SciDK without conversion.

---

## What It Does

1. **Walks** a target directory tree using `os.walk`
2. **Classifies** each file by extension against SciDK's known interpreter registry
3. **Samples magic bytes** (first 256 bytes) to identify files with missing or
   misleading extensions — covers HDF5, NetCDF, DICOM, TIFF, BAM, VCF, FCS,
   FASTQ, FITS, PDF, ZIP-based, and ~20 other formats
4. **Detects directory patterns** for instrument/pipeline output structures:
   10x Genomics MTX triplets, MaxQuant output, Bruker MRI, OME-TIFF, DICOM dirs,
   BIDS datasets, TCGA exports
5. **Hashes files** (blake3 if available, blake2b otherwise) up to a configurable
   size limit
6. **Persists everything** to SQLite with SciDK-compatible schema
7. **Prints a gap report** on completion — ranked by extension frequency,
   with coverage percentage and magic-byte identifications for unknown files

---

## Schema Compatibility

The tool writes to these tables, using the **exact column names and types**
defined in `scidk/core/path_index_sqlite.py` and `scidk/core/migrations.py`:

| Table | Source | Notes |
|---|---|---|
| `scans` | `migrations.py v2` | One row per scan run |
| `files` | `path_index_sqlite.py` | Per-file index, primary output |
| `scan_items` | `migrations.py v2` | Per-scan snapshot (parallel to files) |
| `scan_progress` | `migrations.py v2` | Progress metrics per scan |
| `file_history` | `path_index_sqlite.py` | Change tracking between scans |

Two interpretation columns (`interpreted_as`, `interpretation_json`) are added
to `files` via the same migration-safe `ALTER TABLE` pattern already used in
`path_index_sqlite.py`. They will not break an existing SciDK database.

---

## Integration Points

### Option A — Zero-change import (recommended for MVP)

The scanner writes to `scidk_scan.db` by default. To import into a running
SciDK instance:

```bash
# On the research server
python3 scidk_scanner.py /data/lab --db scan_$(date +%Y%m%d).db

# Copy to SciDK host
scp scan_20260310.db ki-ed3g:~/.scidk/db/

# SciDK reads it by setting SCIDK_DB_PATH or via the import endpoint
```

No code changes needed. SciDK already knows how to open a `files.db` at any path.

### Option B — Add scanner as a SciDK route (suggested)

**Suggested location:** `scidk/core/filesystem_scanner.py`

Extract the core `walk_path()` function and expose it through:

```
POST /api/scanner/scan
  body: { path, options }
  → triggers walk_path() as background task
  → writes to SciDK's primary files.db
  → streams progress via scan_progress table

GET /api/scanner/report/<scan_id>
  → returns gap report as JSON

GET /api/scanner/scans
  → lists all scan_runs with status, root, file count

POST /api/scanner/import
  → accepts an external scidk_scan.db file
  → merges into primary files.db (scan_id namespacing prevents collisions)
```

The background task pattern is already established in SciDK via
`background_tasks` table in `migrations.py`. The scanner should register a
task row and update it as the walk progresses.

### Option C — Wire into existing FilesystemScanner class

The existing `FilesystemScanner` class (in `scidk/core/filesystem_scanner.py`)
currently delegates to `ncdu`. The `walk_path()` function in this script can
replace or augment that — same output schema, with richer metadata.

Suggested refactor:
```python
class FilesystemScanner:
    def scan_directory(self, path, options):
        # existing ncdu path remains as fallback
        if self._ncdu_available():
            return self._scan_ncdu(path, options)
        # new Python-native path
        return walk_path(path, scan_id, self.conn, **options)
```

---

## Known Interpreter Registry

The `KNOWN_INTERPRETERS` dict at the top of the script is the canonical
source of truth for coverage. It must be kept in sync with
`scidk/interpreters/` as new interpreters are registered.

**Suggested integration:** Import from a shared location rather than
duplicating. Options:

```python
# In scidk_scanner.py (standalone mode)
try:
    from scidk.core.registry import get_extension_map
    KNOWN_INTERPRETERS = get_extension_map()
except ImportError:
    KNOWN_INTERPRETERS = _BUILTIN_FALLBACK  # hardcoded dict for standalone use
```

This keeps the tool standalone-capable while staying in sync when running
inside SciDK.

---

## Gap Report Query

The gap report is also directly queryable from any SQLite client or
SciDK's chat interface:

```sql
-- Ranked gap extensions for a scan
SELECT file_extension,
       COUNT(*)       AS file_count,
       SUM(size)/1e9  AS size_gb
FROM files
WHERE scan_id = '<scan_id>'
  AND type = 'file'
  AND interpreted_as IS NULL
  AND file_extension IS NOT NULL
GROUP BY file_extension
ORDER BY file_count DESC;

-- Coverage summary
SELECT
  COUNT(*) FILTER (WHERE interpreted_as IS NOT NULL) * 100.0 / COUNT(*) AS pct_covered,
  COUNT(*) FILTER (WHERE interpreted_as IS NULL) AS gaps
FROM files
WHERE scan_id = '<scan_id>' AND type = 'file';

-- Files identified by magic bytes but not extension
SELECT json_extract(interpretation_json, '$.magic_label') AS detected_format,
       COUNT(*) AS n
FROM files
WHERE scan_id = '<scan_id>'
  AND interpreted_as IS NULL
  AND interpretation_json IS NOT NULL
GROUP BY detected_format ORDER BY n DESC;
```

---

## Suggested File Layout in Repo

```
scidk/
  core/
    filesystem_scanner.py     ← existing (modify to call walk_path)
    scanner_formats.py        ← NEW: extract KNOWN_INTERPRETERS + MAGIC_SIGNATURES
                                      shared between scanner and interpreter registry
  tools/
    scidk_scanner.py          ← this file, standalone entry point
tests/
  test_scanner.py             ← NEW (see test plan below)
```

---

## Test Plan

```python
# tests/test_scanner.py

def test_schema_compatibility():
    """Scanner DB opens cleanly in SciDK's path_index_sqlite.connect()"""

def test_gap_report_structure():
    """Gap report runs without error on a real scan result"""

def test_magic_byte_detection():
    """Known-format files are identified by magic bytes regardless of extension"""
    # rename sample.h5 → sample.dat, verify hdf5 is detected

def test_directory_pattern_detection():
    """10x MTX triplet directory is flagged as 10x_genomics_mtx"""

def test_scan_resume():
    """--resume flag continues an existing scan_id without creating a new one"""

def test_known_interpreters_sync():
    """Every interpreter in scidk/interpreters/ has an entry in KNOWN_INTERPRETERS"""
```

---

## Dependencies

**Stdlib only** for core functionality:
`os`, `sqlite3`, `pathlib`, `hashlib`, `mimetypes`, `json`, `uuid`, `time`,
`argparse`, `fnmatch`

**Optional:**
- `blake3` — faster hashing (falls back to `blake2b` if absent)

**No** pandas, numpy, or any scientific library required for the scanner itself.

---

## Usage Examples

```bash
# Basic scan
python3 scidk_scanner.py /data/lab1

# Fast scan (no hashing, no magic sampling on large files)
python3 scidk_scanner.py /data/lab1 --no-hash --magic-limit 50

# Scan with note, custom db location
python3 scidk_scanner.py /data/lab1 \
    --db ~/scans/lab1_2026-03-10.db \
    --note "Initial survey for Data Science Core onboarding"

# Exclude scratch and temp dirs
python3 scidk_scanner.py /data/lab1 \
    --exclude '__pycache__' \
    --exclude '*.tmp' \
    --exclude '.git'

# Re-open existing db and view gap report without rescanning
python3 scidk_scanner.py --db ~/scans/lab1.db --report

# Report for a specific scan
python3 scidk_scanner.py --db ~/scans/lab1.db --report-id <scan_id>
```

---

## Output Example (terminal)

```
SciDK Filesystem Scanner
  Root    : /data/lab1
  Database: ./scidk_scan.db
  Scan ID : a3f2b1c0-...
  Hashing : files < 100 MB

    142,831 files    4,219 dirs  2.31 GB  1,204 gaps  (47s)

  Saved → ./scidk_scan.db

══════════════════════════════════════════════════════════════
  SciDK Filesystem Scan Report
  Root   : /data/lab1
  Scan ID: a3f2b1c0-...
══════════════════════════════════════════════════════════════

  Total   : 142,831 files  4,219 dirs  2.31 GB
  Coverage: 141,627 identified  1,204 gaps  (99.2% covered)

  COVERED EXTENSIONS                          count     size GB
  ──────────────────────────────────────────────────────────────
  .fastq.gz            fastq_interpreter      42,310      1.21
  .bam                 bam_interpreter         8,104      0.88
  ...

  GAP EXTENSIONS (no interpreter)             count     size GB
  ──────────────────────────────────────────────────────────────
  .fcs                                          892      0.14
  .raw                                          201      0.06
  ...

  DETECTED INSTRUMENT / PIPELINE DIRECTORIES
  ──────────────────────────────────────────────────────────────
  10x_genomics_mtx                               14 directories
  maxquant_output                                 3 directories
  bids_root                                       1 directory
══════════════════════════════════════════════════════════════
```
