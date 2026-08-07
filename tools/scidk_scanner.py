#!/usr/bin/env python3
"""
scidk_scanner.py — Standalone filesystem scanner for SciDK
============================================================
Walks a target directory and writes file metadata into a SQLite database
that is schema-compatible with SciDK's path_index_sqlite / migrations schema.

The same .db file can be:
  - Opened directly by SciDK if run on the same host (SCIDK_DB_PATH)
  - Copied (scp) to the SciDK host and read without any conversion
  - Queried standalone with any SQLite client

Usage:
    python3 scidk_scanner.py /path/to/scan [options]

Options:
    --db PATH           SQLite output path (default: ./scidk_scan.db)
    --note TEXT         Human note stored in scans.extra_json
    --no-hash           Skip content hashing (faster, no integrity data)
    --hash-limit MB     Only hash files smaller than this (default: 100)
    --magic-limit MB    Only sample magic bytes for files smaller than this (default: 500)
    --depth INT         Max directory depth (default: unlimited)
    --exclude PATTERN   Glob pattern to exclude (can repeat, e.g. --exclude '*.tmp')
    --follow-symlinks   Follow symbolic links (default: off)
    --resume ID         Resume a previous scan by scan_id
    --report            Print gap report after scan and exit
    --quiet             Suppress progress output

Schema compatibility:
    Writes to: scans, files, file_history, scan_items
    Adds:       interpreted_as, interpretation_json columns (migration-safe)
    Compatible with: SciDK production-mvp branch, path_index_sqlite.py schema
"""

import argparse
import fnmatch
import hashlib
import json
import mimetypes
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
# ─────────────────────────────────────────────
# Format-recognition tables
# ─────────────────────────────────────────────
# Single source of truth is scidk/core/scanner_formats.py. The fallback below
# keeps this script runnable on a host that has the file but not the installed
# package — running standalone and copying the .db over is the whole point of
# this scanner. Keep the two in step when editing.
try:
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from scidk.core.scanner_formats import (  # type: ignore
        KNOWN_INTERPRETERS, MAGIC_SIGNATURES, DIRECTORY_PATTERNS,
    )
except Exception:  # pragma: no cover - standalone fallback

    # ─────────────────────────────────────────────
    # Known interpreter coverage (SciDK built-ins)
    # Update this list as new interpreters are added
    # ─────────────────────────────────────────────
    # Values must match the `id` class attribute of an interpreter in
    # scidk/interpreters/, as listed in scidk/interpreters/__init__.py:INTERPRETERS.
    # Print the current ids and the extensions they really claim with:
    #     python -c "from scidk.interpreters import INTERPRETERS; \
    #                [print(i.id, i.extensions) for i in INTERPRETERS]"
    # A value that matches no registry id is written into files.interpreted_as and
    # then resolves to nothing downstream — a silent no-op, not an error.
    #
    # None means "no interpreter reads this": the extension is recognised, so magic
    # sniffing is skipped, but the file is counted as a gap rather than as covered.
    KNOWN_INTERPRETERS: Dict[str, Optional[str]] = {
        # extension (lowercase, with dot) → interpreter id
        ".csv":      "csv",
        ".tsv":      "csv",              # over-claim: CsvInterpreter.extensions is ['.csv']
        ".xlsx":     "xlsx",
        ".xls":      "xlsx",             # over-claim: XlsxInterpreter is ['.xlsx', '.xlsm']
        ".json":     "json",
        ".jsonl":    "json",             # over-claim: JsonInterpreter is ['.json']
        ".yaml":     "yaml",
        ".yml":      "yaml",
        ".ipynb":    "ipynb",
        ".dcm":      "dicom_bioformats",
        ".dicom":    "dicom_bioformats",
        ".tif":      "ome_tiff",         # over-claim: OMETiffInterpreter is ['.ome.tif', '.ome.tiff']
        ".tiff":     "ome_tiff",         # over-claim: as above
        ".h5":       None,               # hdf5_interpreter: specced, not yet implemented
        ".hdf5":     None,               # hdf5_interpreter: specced, not yet implemented
        ".nc":       None,               # netcdf_interpreter: specced, not yet implemented
        ".nc4":      None,               # netcdf_interpreter: specced, not yet implemented
        ".rdf":      None,               # rdf_interpreter: specced, not yet implemented
        ".ttl":      None,               # rdf_interpreter: specced, not yet implemented
        ".owl":      None,               # owl_interpreter: specced, not yet implemented
        ".py":       "python_code",
        # Add entries here as new interpreters land in scidk/interpreters/
        # Registered but unlisted here: txt (.txt), bruker_skyscan_log (.log).
    }

    # ─────────────────────────────────────────────
    # Magic byte signatures for format identification
    # Used when extension is ambiguous or missing
    # ─────────────────────────────────────────────
    MAGIC_SIGNATURES: List[Tuple[bytes, str, Optional[str]]] = [
        # (prefix_bytes, format_label, interpreter_hint)
        # A None hint means the format is identifiable but no interpreter reads it.
        (b"\x89HDF",           "hdf5",        None),  # hdf5_interpreter not implemented
        (b"CDF\x01",           "netcdf3",     None),  # netcdf_interpreter not implemented
        (b"CDF\x02",           "netcdf3_64",  None),  # netcdf_interpreter not implemented
        (b"\x89PNG",           "png",         None),
        (b"\xff\xd8\xff",      "jpeg",        None),
        (b"GIF8",              "gif",         None),
        (b"II\x2a\x00",        "tiff_le",     "ome_tiff"),
        (b"MM\x00\x2a",        "tiff_be",     "ome_tiff"),
        (b"DICM",              "dicom",       "dicom_bioformats"),        # offset 128
        (b"PK\x03\x04",        "zip_based",   None),                      # xlsx, docx, jar…
        (b"%PDF",              "pdf",         None),
        (b"{\n",               "json_likely", "json"),
        (b"{\"",               "json_likely", "json"),
        (b"[\n",               "json_likely", "json"),
        (b"[{",                "json_likely", "json"),
        (b"@HD\t",             "sam",         None),
        (b"BAM\x01",           "bam",         None),
        (b"##fileformat=VCF",  "vcf",         None),
        (b"@SQUAWK",           "fastq_likely",None),
        (b"BZh",               "bz2",         None),
        (b"\x1f\x8b",          "gzip",        None),
        (b"FCS3.",             "fcs",         None),                       # flow cytometry
        (b"FCS2.",             "fcs",         None),
        (b"\x89\x48\x44\x46",  "hdf5",        None),  # hdf5_interpreter not implemented
        (b"SIMPLE  =",         "fits",        None),                       # FITS astronomy/bio
        (b"#\n# ",             "r_data",      None),
    ]

    # Directory structure patterns → instrument/pipeline recognition
    DIRECTORY_PATTERNS: List[Tuple[List[str], str]] = [
        # (required_filenames_in_dir, pattern_label)
        (["barcodes.tsv", "features.tsv", "matrix.mtx"],  "10x_genomics_mtx"),
        (["barcodes.tsv.gz", "features.tsv.gz", "matrix.mtx.gz"], "10x_genomics_mtx_gz"),
        (["proteinGroups.txt", "peptides.txt"],            "maxquant_output"),
        (["summary.txt", "Parameters.txt"],                "maxquant_run"),
        (["acqp", "method", "fid"],                        "bruker_mri"),
        (["acqp", "method", "ser"],                        "bruker_mri"),
        (["2dseq"],                                        "bruker_processed"),
        (["OME", "metadata.xml"],                          "ome_tiff_dir"),
        (["DICOMDIR"],                                     "dicom_dir"),
        (["subject", "ses-", "anat"],                      "bids_dataset"),   # partial match
        (["dataset_description.json", "participants.tsv"], "bids_root"),
        (["Manifest.xml"],                                 "tcga_manifest"),
        (["clinical_data.txt", "mutations.txt"],           "tcga_export"),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SQLite setup — schema-compatible with SciDK path_index_sqlite + migrations
# ─────────────────────────────────────────────────────────────────────────────

def db_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-80000;")
    conn.row_factory = sqlite3.Row
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # scans — matches SciDK migrations.py v2
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id       TEXT PRIMARY KEY,
            root     TEXT,
            started  REAL,
            completed REAL,
            status   TEXT,
            extra_json TEXT
        );
    """)

    # files — matches SciDK path_index_sqlite.py (+ interpretation columns)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path             TEXT NOT NULL,
            parent_path      TEXT,
            name             TEXT NOT NULL,
            depth            INTEGER NOT NULL,
            type             TEXT NOT NULL,
            size             INTEGER NOT NULL,
            modified_time    REAL,
            file_extension   TEXT,
            mime_type        TEXT,
            etag             TEXT,
            hash             TEXT,
            remote           TEXT,
            scan_id          TEXT,
            extra_json       TEXT,
            interpreted_as   TEXT,
            interpretation_json TEXT
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_ext    ON files(scan_id, file_extension);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_type   ON files(scan_id, type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_parent ON files(scan_id, parent_path, name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_files_interp      ON files(scan_id, interpreted_as);")

    # scan_items — per-scan snapshot, matches migrations.py v2
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scan_items (
            scan_id        TEXT NOT NULL,
            path           TEXT NOT NULL,
            type           TEXT,
            size           INTEGER,
            modified_time  REAL,
            file_extension TEXT,
            mime_type      TEXT,
            etag           TEXT,
            hash           TEXT,
            extra_json     TEXT,
            PRIMARY KEY (scan_id, path)
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_items_ext  ON scan_items(scan_id, file_extension);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_items_type ON scan_items(scan_id, type);")

    # scan_progress — matches migrations.py v2
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scan_progress (
            scan_id TEXT NOT NULL,
            metric  TEXT NOT NULL,
            value   REAL,
            updated REAL,
            PRIMARY KEY (scan_id, metric)
        );
    """)

    # file_history — matches SciDK path_index_sqlite.py
    cur.execute("""
        CREATE TABLE IF NOT EXISTS file_history (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            filesystem            TEXT,
            path                  TEXT NOT NULL,
            size                  INTEGER,
            modified_time         REAL,
            hash                  TEXT,
            scan_id               TEXT,
            change_type           TEXT,
            previous_size         INTEGER,
            previous_modified_time REAL,
            previous_path         TEXT,
            logical_key           TEXT
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_path ON file_history(path);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_scan ON file_history(scan_id);")

    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _depth(path: str) -> int:
    p = Path(path)
    try:
        return len(p.parts) - 1
    except Exception:
        return 0


def _compute_hash(file_path: str, limit_bytes: int) -> Optional[str]:
    try:
        if os.path.getsize(file_path) > limit_bytes:
            return None
        try:
            import blake3  # type: ignore
            h = blake3.blake3()
        except ImportError:
            h = hashlib.blake2b()
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _sample_magic(file_path: str, limit_bytes: int) -> Tuple[Optional[str], Optional[str], str]:
    """
    Returns (format_label, interpreter_hint, hex_prefix).
    Reads first 256 bytes (and checks offset 128 for DICOM).
    """
    try:
        size = os.path.getsize(file_path)
        if size > limit_bytes:
            return None, None, ""
        with open(file_path, "rb") as f:
            header = f.read(256)
        hex_prefix = header[:16].hex()

        # DICOM: magic at offset 128
        if len(header) >= 132 and header[128:132] == b"DICM":
            return "dicom", "dicom_bioformats", hex_prefix

        for sig, label, hint in MAGIC_SIGNATURES:
            if header[:len(sig)] == sig:
                return label, hint, hex_prefix

    except Exception:
        pass
    return None, None, ""


def _detect_interpreter(ext: str, magic_label: Optional[str],
                         magic_hint: Optional[str]) -> Optional[str]:
    """Return interpreter id or None (gap).

    A known extension is authoritative even when its value is None: None means
    the format is recognised and nothing reads it, so falling through to a magic
    hint would relabel the very files the None was there to report as gaps.
    """
    if ext and ext in KNOWN_INTERPRETERS:
        return KNOWN_INTERPRETERS[ext]
    if magic_hint:
        return magic_hint
    return None


def _detect_dir_pattern(children: List[str]) -> Optional[str]:
    """Check if a directory's child names match any known instrument pattern."""
    child_set = set(children)
    for required, label in DIRECTORY_PATTERNS:
        # All required names must be present (case-insensitive)
        lower_children = {c.lower() for c in child_set}
        if all(r.lower() in lower_children for r in required):
            return label
        # Partial BIDS: check for prefix matches
        if any(r.endswith("-") for r in required):
            matches = all(
                r.lower() in lower_children or
                any(c.startswith(r.lower()) for c in lower_children)
                for r in required
            )
            if matches:
                return label
    return None


def _update_progress(conn: sqlite3.Connection, scan_id: str,
                     files: int, dirs: int, bytes_: int) -> None:
    now = time.time()
    conn.executemany(
        "INSERT OR REPLACE INTO scan_progress(scan_id, metric, value, updated) VALUES(?,?,?,?)",
        [
            (scan_id, "files_scanned", files, now),
            (scan_id, "dirs_scanned",  dirs,  now),
            (scan_id, "bytes_scanned", bytes_, now),
        ],
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Core scanner
# ─────────────────────────────────────────────────────────────────────────────

def walk_path(
    root: str,
    scan_id: str,
    conn: sqlite3.Connection,
    *,
    do_hash: bool = True,
    hash_limit_bytes: int = 100 * 1024 * 1024,
    magic_limit_bytes: int = 500 * 1024 * 1024,
    max_depth: Optional[int] = None,
    excludes: List[str] = [],
    follow_symlinks: bool = False,
    quiet: bool = False,
) -> Dict:
    """Walk root, insert rows, return stats dict."""

    mimetypes.init()
    root_path = Path(root).resolve()
    root_str  = str(root_path)

    file_buf: List[Tuple] = []
    item_buf: List[Tuple] = []
    BATCH = 5000

    stats = {"files": 0, "dirs": 0, "bytes": 0,
             "gaps": 0, "identified": 0, "errors": 0}
    last_print = time.time()

    def flush(force: bool = False) -> None:
        if len(file_buf) >= BATCH or (force and file_buf):
            conn.executemany(
                """INSERT INTO files(
                       path, parent_path, name, depth, type, size,
                       modified_time, file_extension, mime_type,
                       etag, hash, remote, scan_id, extra_json,
                       interpreted_as, interpretation_json
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                file_buf,
            )
            conn.executemany(
                """INSERT OR IGNORE INTO scan_items(
                       scan_id, path, type, size, modified_time,
                       file_extension, mime_type, etag, hash, extra_json
                   ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                item_buf,
            )
            conn.commit()
            file_buf.clear()
            item_buf.clear()

    def print_progress() -> None:
        nonlocal last_print
        if quiet:
            return
        now = time.time()
        if now - last_print >= 2.0:
            print(
                f"\r  {stats['files']:>8,} files  "
                f"{stats['dirs']:>6,} dirs  "
                f"{stats['bytes'] / (1024**3):.2f} GB  "
                f"{stats['gaps']:>5} gaps",
                end="", flush=True,
            )
            last_print = now

    for dirpath, dirnames, filenames in os.walk(
        root_str, followlinks=follow_symlinks, topdown=True
    ):
        current_depth = _depth(dirpath) - _depth(root_str)

        # Depth pruning
        if max_depth is not None and current_depth >= max_depth:
            dirnames.clear()

        # Exclusion pruning on directories
        dirnames[:] = [
            d for d in dirnames
            if not any(fnmatch.fnmatch(d, pat) for pat in excludes)
        ]

        # Directory row
        dir_path_str  = str(Path(dirpath))
        dir_parent    = str(Path(dirpath).parent)
        dir_name      = Path(dirpath).name or dir_path_str
        dir_depth     = _depth(dir_path_str)

        # Detect instrument directory patterns
        all_children  = dirnames + filenames
        dir_pattern   = _detect_dir_pattern(all_children)
        dir_extra     = json.dumps({"pattern": dir_pattern}) if dir_pattern else None

        try:
            st = os.stat(dirpath)
            dir_size  = 0
            dir_mtime = st.st_mtime
        except OSError:
            dir_size  = 0
            dir_mtime = None

        file_buf.append((
            dir_path_str, dir_parent, dir_name, dir_depth,
            "folder", dir_size, dir_mtime,
            None, None, None, None, None, scan_id, dir_extra,
            None, None,
        ))
        item_buf.append((
            scan_id, dir_path_str, "folder", dir_size,
            dir_mtime, None, None, None, None, dir_extra,
        ))
        stats["dirs"] += 1
        flush()
        print_progress()

        # File rows
        for fname in filenames:
            # Exclusion check
            if any(fnmatch.fnmatch(fname, pat) for pat in excludes):
                continue

            fpath = os.path.join(dirpath, fname)
            fpath_str = str(fpath)

            try:
                st = os.stat(fpath, follow_symlinks=follow_symlinks)
            except OSError as e:
                stats["errors"] += 1
                if not quiet:
                    print(f"\n  [warn] cannot stat {fpath}: {e}", file=sys.stderr)
                continue

            fsize  = st.st_size
            fmtime = st.st_mtime
            fext   = Path(fname).suffix.lower()
            fmime, _ = mimetypes.guess_type(fname)
            fdepth = _depth(fpath_str)
            fparent = dir_path_str

            # Magic byte sampling
            magic_label, magic_hint, hex_prefix = _sample_magic(
                fpath_str, magic_limit_bytes
            )

            # Interpreter matching
            interp = _detect_interpreter(fext, magic_label, magic_hint)
            if interp:
                stats["identified"] += 1
            else:
                stats["gaps"] += 1

            # Interpretation metadata
            interp_json = None
            if magic_label or magic_hint or hex_prefix:
                interp_json = json.dumps({
                    "magic_label":  magic_label,
                    "magic_hint":   magic_hint,
                    "hex_prefix":   hex_prefix or None,
                })

            # Content hash
            fhash = None
            if do_hash:
                fhash = _compute_hash(fpath_str, hash_limit_bytes)

            file_buf.append((
                fpath_str, fparent, fname, fdepth,
                "file", fsize, fmtime,
                fext, fmime, None, fhash, None, scan_id,
                None,        # extra_json (file)
                interp, interp_json,
            ))
            item_buf.append((
                scan_id, fpath_str, "file", fsize, fmtime,
                fext, fmime, None, fhash, None,
            ))

            stats["files"] += 1
            stats["bytes"] += fsize
            flush()
            print_progress()

    flush(force=True)
    _update_progress(conn, scan_id,
                     stats["files"], stats["dirs"], stats["bytes"])
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Gap report
# ─────────────────────────────────────────────────────────────────────────────

def print_gap_report(conn: sqlite3.Connection, scan_id: str) -> None:
    cur = conn.cursor()

    # Pull scan root for context
    cur.execute("SELECT root, started, completed FROM scans WHERE id=?", (scan_id,))
    row = cur.fetchone()
    root    = row["root"]    if row else "?"
    started = row["started"] if row else 0
    ended   = row["completed"] if row else time.time()

    print(f"\n{'═'*62}")
    print(f"  SciDK Filesystem Scan Report")
    print(f"  Root   : {root}")
    print(f"  Scan ID: {scan_id}")
    print(f"  Time   : {datetime.fromtimestamp(started, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
          f"  ({int(ended - started)}s)")
    print(f"{'═'*62}")

    # Totals
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE type='file')   as n_files,
            COUNT(*) FILTER (WHERE type='folder') as n_dirs,
            SUM(size) FILTER (WHERE type='file')  as total_bytes
        FROM files WHERE scan_id=?
    """, (scan_id,))
    t = cur.fetchone()
    n_files  = t["n_files"]  or 0
    n_dirs   = t["n_dirs"]   or 0
    tb       = (t["total_bytes"] or 0) / (1024**3)
    print(f"\n  Total  : {n_files:,} files  {n_dirs:,} dirs  {tb:.2f} GB")

    # Coverage summary
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE interpreted_as IS NOT NULL) as covered,
            COUNT(*) FILTER (WHERE interpreted_as IS NULL)     as gaps
        FROM files WHERE scan_id=? AND type='file'
    """, (scan_id,))
    c = cur.fetchone()
    covered = c["covered"] or 0
    gaps    = c["gaps"]    or 0
    pct     = 100.0 * covered / n_files if n_files else 0
    print(f"  Coverage: {covered:,} identified  {gaps:,} gaps  ({pct:.1f}% covered)")

    # ── Top covered extensions ──────────────────────────────────────────────
    print(f"\n  {'COVERED EXTENSIONS':42s}  {'count':>7}  {'size GB':>8}")
    print(f"  {'-'*62}")
    cur.execute("""
        SELECT file_extension, interpreted_as,
               COUNT(*) as n, SUM(size) as b
        FROM files
        WHERE scan_id=? AND type='file' AND interpreted_as IS NOT NULL
        GROUP BY file_extension
        ORDER BY n DESC LIMIT 20
    """, (scan_id,))
    for r in cur.fetchall():
        ext  = r["file_extension"] or "(none)"
        size = (r["b"] or 0) / (1024**3)
        print(f"  {ext:<20}  {r['interpreted_as']:<22}  {r['n']:>7,}  {size:>8.2f}")

    # ── Gap extensions ──────────────────────────────────────────────────────
    print(f"\n  {'GAP EXTENSIONS (no interpreter)':42s}  {'count':>7}  {'size GB':>8}")
    print(f"  {'-'*62}")
    cur.execute("""
        SELECT file_extension,
               COUNT(*) as n, SUM(size) as b
        FROM files
        WHERE scan_id=? AND type='file' AND interpreted_as IS NULL
          AND file_extension IS NOT NULL AND file_extension != ''
        GROUP BY file_extension
        ORDER BY n DESC LIMIT 30
    """, (scan_id,))
    for r in cur.fetchall():
        size = (r["b"] or 0) / (1024**3)
        print(f"  {r['file_extension']:<42}  {r['n']:>7,}  {size:>8.2f}")

    # ── Extension-less / unknown ────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) as n, SUM(size) as b
        FROM files
        WHERE scan_id=? AND type='file' AND interpreted_as IS NULL
          AND (file_extension IS NULL OR file_extension = '')
    """, (scan_id,))
    u = cur.fetchone()
    if u["n"]:
        size = (u["b"] or 0) / (1024**3)
        print(f"  {'(no extension)':42}  {u['n']:>7,}  {size:>8.2f}")

    # ── Detected directory patterns ─────────────────────────────────────────
    print(f"\n  DETECTED INSTRUMENT / PIPELINE DIRECTORIES")
    print(f"  {'-'*62}")
    cur.execute("""
        SELECT json_extract(extra_json, '$.pattern') as pattern,
               COUNT(*) as n, name
        FROM files
        WHERE scan_id=? AND type='folder'
          AND extra_json IS NOT NULL
        GROUP BY pattern ORDER BY n DESC
    """, (scan_id,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            if r["pattern"]:
                print(f"  {r['pattern']:<40}  {r['n']:>4} director{'y' if r['n']==1 else 'ies'}")
    else:
        print("  (none detected)")

    # ── Magic byte findings for gaps ────────────────────────────────────────
    print(f"\n  MAGIC BYTE IDENTIFICATIONS (unmatched extension)")
    print(f"  {'-'*62}")
    cur.execute("""
        SELECT json_extract(interpretation_json, '$.magic_label') as ml,
               COUNT(*) as n
        FROM files
        WHERE scan_id=? AND type='file'
          AND interpreted_as IS NULL
          AND interpretation_json IS NOT NULL
          AND json_extract(interpretation_json, '$.magic_label') IS NOT NULL
        GROUP BY ml ORDER BY n DESC LIMIT 15
    """, (scan_id,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r['ml']:<42}  {r['n']:>7,}")
    else:
        print("  (none — increase --magic-limit to sample more files)")

    print(f"\n{'═'*62}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SciDK-compatible standalone filesystem scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("root", nargs="?",
                        help="Directory to scan")
    parser.add_argument("--db", default="./scidk_scan.db",
                        help="SQLite output path (default: ./scidk_scan.db)")
    parser.add_argument("--note", default="",
                        help="Human note stored with the scan")
    parser.add_argument("--no-hash", action="store_true",
                        help="Skip content hashing")
    parser.add_argument("--hash-limit", type=int, default=100,
                        metavar="MB",
                        help="Only hash files smaller than this MB (default 100)")
    parser.add_argument("--magic-limit", type=int, default=500,
                        metavar="MB",
                        help="Only sample magic bytes for files < this MB (default 500)")
    parser.add_argument("--depth", type=int, default=None,
                        help="Max directory depth (default: unlimited)")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="PATTERN",
                        help="Glob pattern to exclude (repeatable)")
    parser.add_argument("--follow-symlinks", action="store_true")
    parser.add_argument("--resume",
                        metavar="SCAN_ID",
                        help="Resume an existing scan by ID (skips re-walking)")
    parser.add_argument("--report", action="store_true",
                        help="Print gap report for most recent scan and exit")
    parser.add_argument("--report-id",
                        metavar="SCAN_ID",
                        help="Print gap report for a specific scan ID and exit")
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    # ── Report-only mode ────────────────────────────────────────────────────
    if args.report or args.report_id:
        conn = db_connect(args.db)
        db_init(conn)
        if args.report_id:
            scan_id = args.report_id
        else:
            cur = conn.cursor()
            cur.execute("SELECT id FROM scans ORDER BY started DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                print("No scans found in database.", file=sys.stderr)
                sys.exit(1)
            scan_id = row["id"]
        print_gap_report(conn, scan_id)
        conn.close()
        return

    if not args.root:
        parser.print_help()
        sys.exit(1)

    root = str(Path(args.root).resolve())
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    # ── Open / init DB ──────────────────────────────────────────────────────
    conn = db_connect(args.db)
    db_init(conn)

    # ── Create or resume scan ───────────────────────────────────────────────
    if args.resume:
        scan_id = args.resume
        cur = conn.cursor()
        cur.execute("SELECT id FROM scans WHERE id=?", (scan_id,))
        if not cur.fetchone():
            print(f"Scan ID '{scan_id}' not found in {args.db}", file=sys.stderr)
            sys.exit(1)
        if not args.quiet:
            print(f"Resuming scan: {scan_id}")
    else:
        scan_id = str(uuid.uuid4())
        extra = json.dumps({
            "note":     args.note,
            "tool":     "scidk_scanner.py",
            "excludes": args.exclude,
        })
        conn.execute(
            "INSERT INTO scans(id, root, started, status, extra_json) VALUES(?,?,?,?,?)",
            (scan_id, root, time.time(), "running", extra),
        )
        conn.commit()

    if not args.quiet:
        print(f"\nSciDK Filesystem Scanner")
        print(f"  Root    : {root}")
        print(f"  Database: {args.db}")
        print(f"  Scan ID : {scan_id}")
        print(f"  Hashing : {'off' if args.no_hash else f'files < {args.hash_limit} MB'}")
        print(f"  Magic   : files < {args.magic_limit} MB")
        if args.exclude:
            print(f"  Excludes: {', '.join(args.exclude)}")
        print()

    # ── Walk ────────────────────────────────────────────────────────────────
    t0 = time.time()
    try:
        stats = walk_path(
            root, scan_id, conn,
            do_hash=not args.no_hash,
            hash_limit_bytes=args.hash_limit * 1024 * 1024,
            magic_limit_bytes=args.magic_limit * 1024 * 1024,
            max_depth=args.depth,
            excludes=args.exclude,
            follow_symlinks=args.follow_symlinks,
            quiet=args.quiet,
        )
    except KeyboardInterrupt:
        if not args.quiet:
            print("\n\n  [interrupted — partial results saved]")
        conn.execute(
            "UPDATE scans SET status=?, completed=? WHERE id=?",
            ("interrupted", time.time(), scan_id),
        )
        conn.commit()
        conn.close()
        return

    elapsed = time.time() - t0
    conn.execute(
        "UPDATE scans SET status=?, completed=? WHERE id=?",
        ("complete", time.time(), scan_id),
    )
    conn.commit()

    if not args.quiet:
        gb = stats["bytes"] / (1024**3)
        print(f"\r  {stats['files']:>8,} files  "
              f"{stats['dirs']:>6,} dirs  "
              f"{gb:.2f} GB  "
              f"{stats['gaps']:>5} gaps  "
              f"({elapsed:.0f}s)          ")
        print(f"\n  Saved → {args.db}")

    print_gap_report(conn, scan_id)
    conn.close()


if __name__ == "__main__":
    main()
