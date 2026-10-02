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
    --workers N         Parallel I/O workers (default: 1)
                        Try 8-32 on network mounts with magic bytes on
                        Try 4-8 on local SSD
    --no-hash           Skip content hashing (faster, no integrity data)
    --hash-limit MB     Only hash files smaller than this (default: 100)
    --magic-limit MB    Sample magic bytes for files < this MB (default: 0 = OFF)
                        0  = stat-only, ncdu-speed
                        500 = rich format detection, slower on network mounts
    --depth INT         Max directory depth (default: unlimited)
    --exclude PATTERN   Glob pattern to exclude (repeatable)
    --follow-symlinks   Follow symbolic links (default: off)
    --resume ID         Resume a previous scan by scan_id
    --report            Print gap report for most recent scan and exit
    --report-id ID      Print gap report for a specific scan ID and exit
    --quiet             Suppress progress output

Worker tuning guide:
    Local SSD          : --workers 4-8
    Network NFS/CIFS   : --workers 16-32  (latency-bound, more threads help a lot)
    HPC Lustre/GPFS    : --workers 8-16
    Magic bytes off    : 1 worker is plenty (bottleneck is stat, not I/O wait)
    Magic bytes on     : parallelism makes the biggest difference here

Schema compatibility:
    Writes to: scans, files, scan_items, scan_progress, file_history
    Adds:      interpreted_as, interpretation_json (migration-safe ALTER TABLE)
    Compatible with: SciDK production-mvp branch, path_index_sqlite.py schema
"""

import argparse
import fnmatch
import hashlib
import json
import mimetypes
import os
import shutil
import socket
import queue
import sqlite3
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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
        DIRECTORY_PATTERN_INTERPRETERS, EXTENSION_DIRECTORY_PATTERNS,
        interpreter_for_dir_pattern, detect_directory_pattern,
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
        ".csv":   "csv",
        ".tsv":   "csv",              # over-claim: CsvInterpreter is ['.csv']
        ".xlsx":  "xlsx",
        ".xls":   "xlsx",             # over-claim: XlsxInterpreter is ['.xlsx', '.xlsm']
        ".json":  "json",
        ".jsonl": "json",             # over-claim: JsonInterpreter is ['.json']
        ".yaml":  "yaml",
        ".yml":   "yaml",
        ".ipynb": "ipynb",
        ".dcm":   "dicom_bioformats",
        ".dicom": "dicom_bioformats",
        ".tif":   "ome_tiff",         # over-claim: OMETiffInterpreter is ['.ome.tif', '.ome.tiff']
        ".tiff":  "ome_tiff",         # over-claim: as above
        ".h5":    None,               # hdf5_interpreter: specced, not yet implemented
        ".hdf5":  None,               # hdf5_interpreter: specced, not yet implemented
        ".nc":    None,               # netcdf_interpreter: specced, not yet implemented
        ".nc4":   None,               # netcdf_interpreter: specced, not yet implemented
        ".rdf":   None,               # rdf_interpreter: specced, not yet implemented
        ".ttl":   None,               # rdf_interpreter: specced, not yet implemented
        ".owl":   None,               # owl_interpreter: specced, not yet implemented
        ".py":    "python_code",
        ".fcs":   "fcs_interpreter",  # FCS2.0/3.0/3.1 flow cytometry
        ".svs":   "svs_interpreter",  # Aperio whole-slide image
        ".ndpi":  "svs_interpreter",  # Hamamatsu — same TIFF-derived container
        ".scn":   "svs_interpreter",  # Leica whole-slide
        ".pzfx":  None,               # GraphPad Prism — no interpreter yet
    }

    MAGIC_SIGNATURES: List[Tuple[bytes, str, Optional[str]]] = [
        (b"\x89HDF",          "hdf5",         None),  # hdf5_interpreter not implemented
        (b"CDF\x01",          "netcdf3",      None),  # netcdf_interpreter not implemented
        (b"CDF\x02",          "netcdf3_64",   None),  # netcdf_interpreter not implemented
        (b"\x89PNG",          "png",          None),
        (b"\xff\xd8\xff",     "jpeg",         None),
        (b"GIF8",             "gif",          None),
        (b"II\x2a\x00",       "tiff_le",      "ome_tiff"),
        (b"MM\x00\x2a",       "tiff_be",      "ome_tiff"),
        (b"DICM",             "dicom",        "dicom_bioformats"),   # at offset 128
        (b"PK\x03\x04",       "zip_based",    None),
        (b"%PDF",             "pdf",          None),
        (b"{\n",              "json_likely",  "json"),
        (b"{\"",              "json_likely",  "json"),
        (b"[\n",              "json_likely",  "json"),
        (b"[{",               "json_likely",  "json"),
        (b"@HD\t",            "sam",          None),
        (b"BAM\x01",          "bam",          None),
        (b"##fileformat=VCF", "vcf",          None),
        (b"BZh",              "bz2",          None),
        (b"\x1f\x8b",         "gzip",         None),
        (b"FCS3.",            "fcs",          "fcs_interpreter"),
        (b"FCS2.",            "fcs",          "fcs_interpreter"),
        (b"SIMPLE  =",        "fits",         None),
        (b"#\n# ",            "r_data",       None),
    ]

    DIRECTORY_PATTERNS: List[Tuple[List[str], str]] = [
        (["barcodes.tsv", "features.tsv", "matrix.mtx"],          "10x_genomics_mtx"),
        (["barcodes.tsv.gz", "features.tsv.gz", "matrix.mtx.gz"], "10x_genomics_mtx_gz"),
        (["proteinGroups.txt", "peptides.txt"],                    "maxquant_output"),
        (["summary.txt", "Parameters.txt"],                        "maxquant_run"),
        (["acqp", "method", "fid"],                                "bruker_mri"),
        (["acqp", "method", "ser"],                                "bruker_mri"),
        (["2dseq"],                                                "bruker_processed"),
        (["OME", "metadata.xml"],                                  "ome_tiff_dir"),
        (["DICOMDIR"],                                             "dicom_dir"),
        (["dataset_description.json", "participants.tsv"],         "bids_root"),
        (["Manifest.xml"],                                         "tcga_manifest"),
        (["clinical_data.txt", "mutations.txt"],                   "tcga_export"),
    ]

    DIRECTORY_PATTERN_INTERPRETERS: Dict[str, Optional[str]] = {
        "10x_genomics_mtx":      "mtx_interpreter",        # not yet implemented
        "10x_genomics_mtx_gz":   "mtx_interpreter",        # not yet implemented
        "maxquant_output":       "maxquant_interpreter",   # not yet implemented
        "maxquant_run":          "maxquant_interpreter",   # not yet implemented
        "bruker_mri":            "bruker_mri_interpreter", # not yet implemented
        "bruker_processed":      "bruker_mri_interpreter", # not yet implemented
        "ome_tiff_dir":          "ome_tiff",               # registered
        "dicom_dir":             "dicom_bioformats",       # registered
        "bids_dataset":          "bids_interpreter",       # not yet implemented
        "bids_root":             "bids_interpreter",       # not yet implemented
        "tcga_manifest":         "tcga_interpreter",       # not yet implemented
        "tcga_export":           "tcga_interpreter",       # not yet implemented
        "flow_cytometry_session": "flow_session_interpreter",       # registered
        "histology_session":      "histology_session_interpreter",  # registered
    }

    # Directories recognised by which extensions they hold rather than by exact
    # filenames — a flow run is a folder of .fcs named after the samples.
    # ([extensions_any_of], pattern_name, min_count)
    EXTENSION_DIRECTORY_PATTERNS: List[Tuple[List[str], str, int]] = [
        ([".fcs"],                   "flow_cytometry_session", 1),
        ([".svs", ".ndpi", ".scn"],  "histology_session",      1),
    ]

    def interpreter_for_dir_pattern(pattern):
        if not pattern:
            return None
        return DIRECTORY_PATTERN_INTERPRETERS.get(pattern, pattern)

    def detect_directory_pattern(child_names):
        lower = {str(c).lower() for c in child_names}
        for required, pattern in DIRECTORY_PATTERNS:
            if all(r.lower() in lower for r in required):
                return pattern
            if any(r.endswith("-") for r in required):
                if all(
                    r.lower() in lower or any(c.startswith(r.lower()) for c in lower)
                    for r in required
                ):
                    return pattern
        suffixes = [Path(n).suffix.lower() for n in child_names]
        for extensions, pattern, min_count in EXTENSION_DIRECTORY_PATTERNS:
            wanted = {e.lower() for e in extensions}
            if sum(1 for s in suffixes if s in wanted) >= min_count:
                return pattern
        return None


# Writer queue sentinel
_STOP = object()


# ─────────────────────────────────────────────────────────────────────────────
# SQLite — schema-compatible with SciDK path_index_sqlite + migrations
# ─────────────────────────────────────────────────────────────────────────────

def db_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-80000;")
    conn.row_factory = sqlite3.Row
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id         TEXT PRIMARY KEY,
            root       TEXT,
            started    REAL,
            completed  REAL,
            status     TEXT,
            extra_json TEXT
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path                TEXT NOT NULL,
            parent_path         TEXT,
            name                TEXT NOT NULL,
            depth               INTEGER NOT NULL,
            type                TEXT NOT NULL,
            size                INTEGER NOT NULL,
            modified_time       REAL,
            file_extension      TEXT,
            mime_type           TEXT,
            etag                TEXT,
            hash                TEXT,
            remote              TEXT,
            scan_id             TEXT,
            extra_json          TEXT,
            interpreted_as      TEXT,
            interpretation_json TEXT
        )""")
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_files_scan_ext    ON files(scan_id, file_extension)",
        "CREATE INDEX IF NOT EXISTS idx_files_scan_type   ON files(scan_id, type)",
        "CREATE INDEX IF NOT EXISTS idx_files_scan_parent ON files(scan_id, parent_path, name)",
        "CREATE INDEX IF NOT EXISTS idx_files_interp      ON files(scan_id, interpreted_as)",
    ]:
        cur.execute(idx_sql)
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
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_items_ext  ON scan_items(scan_id, file_extension)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_items_type ON scan_items(scan_id, type)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scan_progress (
            scan_id TEXT NOT NULL,
            metric  TEXT NOT NULL,
            value   REAL,
            updated REAL,
            PRIMARY KEY (scan_id, metric)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS file_history (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            filesystem             TEXT,
            path                   TEXT NOT NULL,
            size                   INTEGER,
            modified_time          REAL,
            hash                   TEXT,
            scan_id                TEXT,
            change_type            TEXT,
            previous_size          INTEGER,
            previous_modified_time REAL,
            previous_path          TEXT,
            logical_key            TEXT
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_path ON file_history(path)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_scan ON file_history(scan_id)")
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers — called freely from any worker thread
# ─────────────────────────────────────────────────────────────────────────────

def _depth(path: str) -> int:
    try:
        return len(Path(path).parts) - 1
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


def _sample_magic(file_path: str, limit_bytes: int
                  ) -> Tuple[Optional[str], Optional[str], str]:
    """Returns (format_label, interpreter_hint, hex_prefix). Reads ≤256 bytes."""
    if limit_bytes == 0:
        return None, None, ""
    try:
        if os.path.getsize(file_path) > limit_bytes:
            return None, None, ""
        with open(file_path, "rb") as f:
            header = f.read(256)
        hex_prefix = header[:16].hex()
        # DICOM preamble lives at offset 128
        if len(header) >= 132 and header[128:132] == b"DICM":
            return "dicom", "dicom_bioformats", hex_prefix
        for sig, label, hint in MAGIC_SIGNATURES:
            if header[: len(sig)] == sig:
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
    """Delegates to the shared table in ``scanner_formats``; see the twin in
    ``scidk_scanner.py``. This copy also silently lacked the ``bids_dataset``
    row its fallback table never carried."""
    return detect_directory_pattern(children)


def _make_file_rows(
    fpath: str, dir_path: str, fname: str,
    scan_id: str,
    do_hash: bool, hash_limit_bytes: int, magic_limit_bytes: int,
    follow_symlinks: bool,
    stats: Dict, stats_lock: threading.Lock,
) -> Optional[Tuple[Tuple, Tuple]]:
    """Stat + magic + hash one file. Returns (file_row, item_row) or None on error."""
    try:
        st = os.stat(fpath, follow_symlinks=follow_symlinks)
    except OSError:
        with stats_lock:
            stats["errors"] += 1
        return None

    fsize  = st.st_size
    fmtime = st.st_mtime
    fext   = Path(fname).suffix.lower()
    fmime, _ = mimetypes.guess_type(fname)
    fdepth = _depth(fpath)

    ml, mh, hx = _sample_magic(fpath, magic_limit_bytes)
    interp = _detect_interpreter(fext, ml, mh)
    ij = json.dumps({"magic_label": ml, "magic_hint": mh,
                     "hex_prefix": hx or None}) if (ml or mh or hx) else None
    fhash = _compute_hash(fpath, hash_limit_bytes) if do_hash else None

    with stats_lock:
        stats["files"] += 1
        stats["bytes"] += fsize
        if interp:
            stats["identified"] += 1
        else:
            stats["gaps"] += 1

    _local_remote = socket.getfqdn()
    file_row = (fpath, dir_path, fname, fdepth, "file", fsize, fmtime,
                fext, fmime, None, fhash, _local_remote, scan_id, None, interp, ij)
    item_row = (scan_id, fpath, "file", fsize, fmtime,
                fext, fmime, None, fhash, None)
    return file_row, item_row


# ─────────────────────────────────────────────────────────────────────────────
# Writer thread — sole owner of the SQLite connection
# ─────────────────────────────────────────────────────────────────────────────

def _writer_thread(
    write_q: "queue.Queue",
    conn: sqlite3.Connection,
    scan_id: str,
    stats: Dict,
    stats_lock: threading.Lock,
    quiet: bool,
    writer_error: Optional[List[BaseException]] = None,
) -> None:
    """Sole owner of the SQLite connection.

    ``writer_error`` is a caller-owned list, mutated in place so walk_path()
    sees the failure across the thread boundary. Every SQLite call here is
    guarded: an unhandled OperationalError (disk full, locked DB) used to kill
    this thread silently, after which the 16000-slot queue filled, all workers
    blocked forever in write_q.put(), and the main thread blocked forever in
    as_completed() — a 0% CPU hang that never exits. See drain_until_stop().
    """
    FILE_SQL = """INSERT INTO files(
        path, parent_path, name, depth, type, size,
        modified_time, file_extension, mime_type,
        etag, hash, remote, scan_id, extra_json,
        interpreted_as, interpretation_json
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    ITEM_SQL = """INSERT OR IGNORE INTO scan_items(
        scan_id, path, type, size, modified_time,
        file_extension, mime_type, etag, hash, extra_json
    ) VALUES (?,?,?,?,?,?,?,?,?,?)"""

    BATCH      = 2000
    PROG_EVERY = 8.0
    PRINT_EVERY = 2.0

    file_buf: List[Tuple] = []
    item_buf: List[Tuple] = []
    last_prog  = time.time()
    last_print = time.time()

    def flush() -> None:
        if not file_buf:
            return
        conn.executemany(FILE_SQL, file_buf)
        conn.executemany(ITEM_SQL, item_buf)
        conn.commit()
        file_buf.clear()
        item_buf.clear()

    def write_progress() -> None:
        nonlocal last_prog
        now = time.time()
        if now - last_prog < PROG_EVERY:
            return
        with stats_lock:
            f, d, b = stats["files"], stats["dirs"], stats["bytes"]
        conn.executemany(
            "INSERT OR REPLACE INTO scan_progress(scan_id,metric,value,updated) VALUES(?,?,?,?)",
            [(scan_id, "files_scanned", f, now),
             (scan_id, "dirs_scanned",  d, now),
             (scan_id, "bytes_scanned", b, now)],
        )
        conn.commit()
        last_prog = now

    def print_progress() -> None:
        nonlocal last_print
        if quiet:
            return
        now = time.time()
        if now - last_print < PRINT_EVERY:
            return
        with stats_lock:
            f, d, b, g = stats["files"], stats["dirs"], stats["bytes"], stats["gaps"]
        print(f"\r  {f:>9,} files  {d:>6,} dirs  "
              f"{b/(1024**3):.2f} GB  {g:>6,} gaps",
              end="", flush=True)
        last_print = now

    def record_failure(e: BaseException) -> None:
        """Publish the failure to the caller and to stderr.

        There is no logger in this module, so stderr is the channel — and it is
        the right one: launch_scanner() redirects the child's stderr to
        <tmp_db>.log, which the monitor reads back with _read_tail() and stores
        as the task's error message.
        """
        if writer_error is not None and not writer_error:
            writer_error.append(e)
        print(f"\n[fatal] writer thread failed: {e}", file=sys.stderr)
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
        sys.stderr.flush()

    def drain_until_stop() -> None:
        """Keep consuming and discarding until _STOP, then let the thread end.

        Draining once is not enough: the workers would unblock, push, keep
        walking, and refill the queue within seconds — restoring the exact
        deadlock this guard exists to prevent. Consuming until _STOP lets the
        walk finish and lets walk_path() reach its writer_error check, which
        exits the process non-zero so the monitor's returncode != 0 branch
        settles the task as 'error'.
        """
        file_buf.clear()
        item_buf.clear()
        while True:
            try:
                if write_q.get(timeout=0.5) is _STOP:
                    return
            except queue.Empty:
                continue

    while True:
        try:
            item = write_q.get(timeout=0.5)
        except queue.Empty:
            try:
                flush()
                write_progress()
            except Exception as e:
                record_failure(e)
                drain_until_stop()
                return
            print_progress()
            continue

        if item is _STOP:
            try:
                flush()
                now = time.time()
                with stats_lock:
                    f, d, b = stats["files"], stats["dirs"], stats["bytes"]
                conn.executemany(
                    "INSERT OR REPLACE INTO scan_progress(scan_id,metric,value,updated) VALUES(?,?,?,?)",
                    [(scan_id, "files_scanned", f, now),
                     (scan_id, "dirs_scanned",  d, now),
                     (scan_id, "bytes_scanned", b, now)],
                )
                conn.commit()
            except Exception as e:
                # _STOP is already consumed, so there is nothing left to drain
                # and no producer left to unblock — just report and exit.
                record_failure(e)
            break

        file_row, item_row = item
        file_buf.append(file_row)
        item_buf.append(item_row)
        try:
            if len(file_buf) >= BATCH:
                flush()
            write_progress()
        except Exception as e:
            record_failure(e)
            drain_until_stop()
            return
        print_progress()


# ─────────────────────────────────────────────────────────────────────────────
# Worker — walks one subtree, pushes rows onto write_q, never touches SQLite
# ─────────────────────────────────────────────────────────────────────────────

def _walk_subtree(
    root_str: str,
    subdir: str,
    scan_id: str,
    write_q: "queue.Queue",
    stats: Dict,
    stats_lock: threading.Lock,
    *,
    do_hash: bool,
    hash_limit_bytes: int,
    magic_limit_bytes: int,
    max_depth: Optional[int],
    root_depth: int,
    excludes: List[str],
    follow_symlinks: bool,
) -> None:
    for dirpath, dirnames, filenames in os.walk(
        subdir, followlinks=follow_symlinks, topdown=True
    ):
        current_depth = _depth(dirpath) - root_depth
        if max_depth is not None and current_depth >= max_depth:
            dirnames.clear()

        dirnames[:] = [
            d for d in dirnames
            if not any(fnmatch.fnmatch(d, p) for p in excludes)
        ]

        # Directory row
        dp      = str(Path(dirpath))
        dparent = str(Path(dirpath).parent)
        dname   = Path(dirpath).name or dp
        ddepth  = _depth(dp)
        pattern = _detect_dir_pattern(dirnames + filenames)
        dextra  = json.dumps({"pattern": pattern}) if pattern else None
        # Route the pattern to interpreted_as as well; extra_json is a dead end.
        dinterp = interpreter_for_dir_pattern(pattern)
        try:
            dmtime = os.stat(dirpath).st_mtime
        except OSError:
            dmtime = None

        write_q.put((
            (dp, dparent, dname, ddepth, "folder", 0, dmtime,
             None, None, None, None, socket.getfqdn(), scan_id, dextra, dinterp, None),
            (scan_id, dp, "folder", 0, dmtime, None, None, None, None, dextra),
        ))
        with stats_lock:
            stats["dirs"] += 1

        # File rows
        for fname in filenames:
            if any(fnmatch.fnmatch(fname, p) for p in excludes):
                continue
            fpath = os.path.join(dirpath, fname)
            rows = _make_file_rows(
                fpath, dp, fname, scan_id,
                do_hash, hash_limit_bytes, magic_limit_bytes,
                follow_symlinks, stats, stats_lock,
            )
            if rows:
                write_q.put(rows)


def _abort_on_writer_error(writer_error: List[BaseException]) -> None:
    """Exit non-zero if the writer thread failed.

    Nothing was written after the failure, so the child's database holds a
    partial tree under a scan whose status is still 'running'. Exiting non-zero
    routes the task to _monitor()'s returncode != 0 branch, which marks it
    'error' and never merges those rows into files.db.
    """
    if writer_error:
        sys.exit(f"Scanner aborted: writer thread failed \u2014 {writer_error[0]}")


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator — splits top-level dirs across workers, single writer thread
# ─────────────────────────────────────────────────────────────────────────────

def walk_path(
    root: str,
    scan_id: str,
    conn: sqlite3.Connection,
    *,
    workers: int = 1,
    do_hash: bool = True,
    hash_limit_bytes: int = 100 * 1024 * 1024,
    magic_limit_bytes: int = 0,
    max_depth: Optional[int] = None,
    excludes: List[str] = [],
    follow_symlinks: bool = False,
    quiet: bool = False,
) -> Dict:
    mimetypes.init()
    root_path  = Path(root).resolve()
    root_str   = str(root_path)
    root_depth = _depth(root_str)

    stats: Dict = {"files": 0, "dirs": 0, "bytes": 0,
                   "gaps": 0, "identified": 0, "errors": 0}
    stats_lock = threading.Lock()

    # Queue sized so workers can stay busy without blowing memory
    write_q: "queue.Queue" = queue.Queue(maxsize=workers * 1000)

    # Shared by reference with the writer thread: the list object is the
    # channel, so an append() there is visible here without any locking (the
    # only write happens before writer.join() returns, which is the barrier).
    writer_error: List[BaseException] = []

    writer = threading.Thread(
        target=_writer_thread,
        args=(write_q, conn, scan_id, stats, stats_lock, quiet, writer_error),
        daemon=True,
        name="scidk-writer",
    )
    writer.start()

    # Enumerate top-level entries
    try:
        top_entries = list(os.scandir(root_str))
    except PermissionError as e:
        print(f"\n[error] Cannot scan root: {e}", file=sys.stderr)
        write_q.put(_STOP)
        writer.join()
        _abort_on_writer_error(writer_error)
        return stats

    top_dirs  = [e.path for e in top_entries
                 if e.is_dir(follow_symlinks=follow_symlinks)
                 and not any(fnmatch.fnmatch(e.name, p) for p in excludes)]
    top_files = [e for e in top_entries
                 if e.is_file(follow_symlinks=follow_symlinks)
                 and not any(fnmatch.fnmatch(e.name, p) for p in excludes)]

    # Emit root directory row
    try:
        rmtime = os.stat(root_str).st_mtime
    except OSError:
        rmtime = None
    root_pattern = _detect_dir_pattern([e.name for e in top_entries])
    root_extra   = json.dumps({"pattern": root_pattern}) if root_pattern else None
    root_interp  = interpreter_for_dir_pattern(root_pattern)
    write_q.put((
        (root_str, str(root_path.parent), root_path.name or root_str,
         root_depth, "folder", 0, rmtime,
         None, None, None, None, socket.getfqdn(), scan_id, root_extra, root_interp, None),
        (scan_id, root_str, "folder", 0, rmtime,
         None, None, None, None, root_extra),
    ))
    with stats_lock:
        stats["dirs"] += 1

    # Emit files directly in root
    for e in top_files:
        rows = _make_file_rows(
            e.path, root_str, e.name, scan_id,
            do_hash, hash_limit_bytes, magic_limit_bytes,
            follow_symlinks, stats, stats_lock,
        )
        if rows:
            write_q.put(rows)

    # Walk subdirs — parallel or serial
    worker_kwargs = dict(
        scan_id=scan_id, write_q=write_q,
        stats=stats, stats_lock=stats_lock,
        do_hash=do_hash, hash_limit_bytes=hash_limit_bytes,
        magic_limit_bytes=magic_limit_bytes,
        max_depth=max_depth, root_depth=root_depth,
        excludes=excludes, follow_symlinks=follow_symlinks,
    )
    n_workers = min(workers, max(1, len(top_dirs)))

    if n_workers <= 1:
        for subdir in top_dirs:
            _walk_subtree(root_str, subdir, **worker_kwargs)
    else:
        with ThreadPoolExecutor(max_workers=n_workers,
                                thread_name_prefix="scidk-worker") as pool:
            futures = {
                pool.submit(_walk_subtree, root_str, subdir, **worker_kwargs): subdir
                for subdir in top_dirs
            }
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc and not quiet:
                    print(f"\n[warn] worker error on {futures[fut]}: {exc}",
                          file=sys.stderr)

    write_q.put(_STOP)
    writer.join()
    # Checked after join(), not inside the pool block: the writer keeps draining
    # after a failure so the walk can finish, and only join() guarantees it has
    # published its error. A non-zero exit is what tells the monitor in
    # scanner_subprocess.py to take its returncode != 0 branch.
    _abort_on_writer_error(writer_error)
    return stats




# ─────────────────────────────────────────────────────────────────────────────
# rclone provider — optional code path, activated by --provider rclone
# rclone is a binary (not a Python package), so there is no import to guard.
# The only stdlib functions used are subprocess, json, shutil, socket, time.
# ─────────────────────────────────────────────────────────────────────────────

def _rc_depth(path: str) -> int:
    """Depth of an rclone path like 'dropbox:Photos/2024' or 'remote:/a/b'."""
    if ':' in path:
        suffix = path.split(':', 1)[1].strip('/')
        return 0 if not suffix else suffix.count('/') + 1
    return _depth(path)


def _rc_parent(path: str) -> str:
    """Parent of an rclone path. Root returns itself."""
    if ':' in path:
        remote_prefix, rest = path.split(':', 1)
        rest = rest.strip('/')
        if not rest or '/' not in rest:
            return remote_prefix + ':'
        return remote_prefix + ':' + rest.rsplit('/', 1)[0]
    p = str(Path(path).parent)
    return p if p != path else path


def _rc_join(base: str, name: str) -> str:
    """Join an rclone base path with a child name."""
    if ':' in base:
        remote_prefix, rest = base.split(':', 1)
        rest = rest.strip('/')
        return remote_prefix + ':' + (rest + '/' + name if rest else name)
    return str(Path(base) / name)


def _rclone_run(args: List[str]) -> str:
    """Run rclone with args, return stdout. Raises RuntimeError on failure."""
    import shutil as _shutil
    import subprocess as _subprocess
    exe = _shutil.which('rclone')
    if not exe:
        raise RuntimeError("rclone not found on PATH — install rclone or use --provider local")
    proc = _subprocess.run(
        [exe] + args,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
        text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"rclone exited {proc.returncode}")
    return proc.stdout


def walk_rclone(
    target: str,
    scan_id: str,
    conn: sqlite3.Connection,
    *,
    max_depth: Optional[int] = None,
    do_hash: bool = False,          # rclone etags replace hashes; hashing disabled by default
    quiet: bool = False,
) -> Dict:
    """Walk an rclone remote (e.g. 'dropbox:' or 'ki-preclinical-data:Images')
    and write file + folder rows into *conn* using the same 16-column schema as
    walk_path().  Returns a stats dict compatible with the local scanner.

    Implementation notes
    ────────────────────
    • rclone lsjson --recursive returns a flat JSON array — no subtree splitting.
      A single writer thread is sufficient; rclone itself handles the concurrency.
    • Folders are emitted in a first pass (sorted by depth so parents precede
      children); files in a second pass.  This avoids a dependency on insertion
      order in downstream queries that walk parent_path.
    • etag is populated from rclone's "ID" field when present (Drive/Dropbox
      object IDs), or from the "Hashes" dict (MD5/SHA1) otherwise.
    • interpreted_as / interpretation_json are populated by the same helpers as
      the local scanner.
    • remote column = the remote name prefix (e.g. 'dropbox', 'ki-preclinical-data').
    """
    import json as _json
    import subprocess as _subprocess
    import shutil as _shutil

    remote_name = target.split(':', 1)[0] if ':' in target else target

    stats: Dict = {"files": 0, "dirs": 0, "bytes": 0,
                   "gaps": 0, "identified": 0, "errors": 0}
    stats_lock = threading.Lock()
    writer_error: List[BaseException] = []
    write_q: "queue.Queue" = queue.Queue(maxsize=16000)

    writer = threading.Thread(
        target=_writer_thread,
        args=(write_q, conn, scan_id, stats, stats_lock, quiet, writer_error),
        daemon=True,
        name="scidk-rclone-writer",
    )
    writer.start()

    mimetypes.init()

    try:
        lsjson_args = ['lsjson', '--recursive', '--no-modtime', target]
        if max_depth is not None:
            lsjson_args += ['--max-depth', str(max_depth)]

        if not quiet:
            print(f"  [rclone] listing {target} …", flush=True)

        raw = _rclone_run(lsjson_args)
        items: List[Dict] = _json.loads(raw) if raw.strip() else []

        if not quiet:
            print(f"  [rclone] {len(items):,} items received, indexing…", flush=True)

        # Separate and sort: folders first (by depth so parents before children)
        folders = sorted(
            [it for it in items if it.get('IsDir', False)],
            key=lambda it: it.get('Path', '').count('/'),
        )
        files = [it for it in items if not it.get('IsDir', False)]

        # Emit root directory row
        rmtime_str = None  # lsjson --no-modtime-dirs omits mtime for dirs
        rmtime = None
        root_pattern = _detect_dir_pattern([it.get('Name', '') for it in items
                                            if '/' not in it.get('Path', '')])
        root_extra  = _json.dumps({"pattern": root_pattern}) if root_pattern else None
        root_interp = interpreter_for_dir_pattern(root_pattern)
        root_depth  = _rc_depth(target)
        root_parent = _rc_parent(target)
        root_name   = target.split(':', 1)[1].strip('/').rsplit('/', 1)[-1] if ':' in target else target
        if not root_name:
            root_name = remote_name

        write_q.put((
            (target, root_parent, root_name, root_depth, "folder",
             0, rmtime, None, None, None, None, remote_name,
             scan_id, root_extra, root_interp, None),
            (scan_id, target, "folder", 0, rmtime,
             None, None, None, None, root_extra),
        ))
        with stats_lock:
            stats["dirs"] += 1

        # Folder rows
        for it in folders:
            rel_path = it.get('Path', '')
            full_path = _rc_join(target, rel_path) if rel_path else target
            parent_path = _rc_parent(full_path)
            name = it.get('Name', rel_path.rsplit('/', 1)[-1])
            depth = _rc_depth(full_path)

            # Detect pattern from children in the same flat listing
            # (only direct children whose path starts with rel_path + '/')
            child_names = []
            prefix = (rel_path + '/') if rel_path else ''
            for child in items:
                cp = child.get('Path', '')
                if cp.startswith(prefix):
                    remainder = cp[len(prefix):]
                    if '/' not in remainder:
                        child_names.append(child.get('Name', remainder))
            pattern = _detect_dir_pattern(child_names)
            extra   = _json.dumps({"pattern": pattern}) if pattern else None
            interp  = interpreter_for_dir_pattern(pattern)

            # mtime: rclone may omit it for dirs even without --no-modtime-dirs
            mtime_str = it.get('ModTime')
            try:
                from datetime import datetime as _dt
                mtime = _dt.fromisoformat(
                    mtime_str.replace('Z', '+00:00')).timestamp() if mtime_str else None
            except Exception:
                mtime = None

            write_q.put((
                (full_path, parent_path, name, depth, "folder",
                 0, mtime, None, None, None, None, remote_name,
                 scan_id, extra, interp, None),
                (scan_id, full_path, "folder", 0, mtime,
                 None, None, None, None, extra),
            ))
            with stats_lock:
                stats["dirs"] += 1

        # File rows
        for it in files:
            rel_path = it.get('Path', '')
            full_path = _rc_join(target, rel_path) if rel_path else target
            parent_path = _rc_parent(full_path)
            name = it.get('Name', rel_path.rsplit('/', 1)[-1])
            depth = _rc_depth(full_path)
            size = it.get('Size', 0) or 0
            fext = Path(name).suffix.lower()
            fmime, _ = mimetypes.guess_type(name)

            mtime_str = it.get('ModTime')
            try:
                from datetime import datetime as _dt
                mtime = _dt.fromisoformat(
                    mtime_str.replace('Z', '+00:00')).timestamp() if mtime_str else None
            except Exception:
                mtime = None

            # etag: prefer object ID (stable across renames in Dropbox/Drive),
            # fall back to hash from Hashes dict
            etag = it.get('ID') or None
            ahash = None
            hashes = it.get('Hashes') or {}
            if not etag:
                # no object ID — use first available hash as etag
                etag = next(iter(hashes.values()), None)
            else:
                # have object ID; pick a hash if present
                ahash = hashes.get('MD5') or hashes.get('SHA-1') or next(iter(hashes.values()), None)

            # interpreter detection (no magic bytes possible for remote files)
            interp = _detect_interpreter(fext, None, None)
            ij = None

            with stats_lock:
                stats["files"] += 1
                stats["bytes"] += size
                if interp:
                    stats["identified"] += 1
                else:
                    stats["gaps"] += 1

            write_q.put((
                (full_path, parent_path, name, depth, "file",
                 size, mtime, fext, fmime, etag, ahash, remote_name,
                 scan_id, None, interp, ij),
                (scan_id, full_path, "file", size, mtime,
                 fext, fmime, etag, ahash, None),
            ))

    except Exception as exc:
        print(f"\n[fatal] rclone walk failed: {exc}", file=sys.stderr)
        writer_error.append(exc)
    finally:
        write_q.put(_STOP)
        writer.join()

    _abort_on_writer_error(writer_error)
    return stats

# ─────────────────────────────────────────────────────────────────────────────
# Gap report
# ─────────────────────────────────────────────────────────────────────────────

def print_gap_report(conn: sqlite3.Connection, scan_id: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT root, started, completed FROM scans WHERE id=?", (scan_id,))
    row  = cur.fetchone()
    root    = row["root"]      if row else "?"
    started = row["started"]   if row else 0
    ended   = row["completed"] if row else time.time()

    W = 64
    print(f"\n{'═'*W}")
    print(f"  SciDK Filesystem Scan Report")
    print(f"  Root   : {root}")
    print(f"  Scan ID: {scan_id}")
    print(f"  Time   : "
          f"{datetime.fromtimestamp(started, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
          f"  ({int(ended - started)}s)")
    print(f"{'═'*W}")

    cur.execute("""
        SELECT SUM(CASE WHEN type='file'   THEN 1 ELSE 0 END) AS n_files,
               SUM(CASE WHEN type='folder' THEN 1 ELSE 0 END) AS n_dirs,
               SUM(CASE WHEN type='file'   THEN size ELSE 0 END) AS total_bytes
        FROM files WHERE scan_id=?""", (scan_id,))
    t = cur.fetchone()
    n_files = t["n_files"] or 0
    n_dirs  = t["n_dirs"]  or 0
    tb      = (t["total_bytes"] or 0) / (1024**3)
    print(f"\n  Total   : {n_files:,} files  {n_dirs:,} dirs  {tb:.2f} GB")

    cur.execute("""
        SELECT SUM(CASE WHEN interpreted_as IS NOT NULL THEN 1 ELSE 0 END) AS covered,
               SUM(CASE WHEN interpreted_as IS NULL     THEN 1 ELSE 0 END) AS gaps
        FROM files WHERE scan_id=? AND type='file'""", (scan_id,))
    c = cur.fetchone()
    covered = c["covered"] or 0
    gaps    = c["gaps"]    or 0
    pct     = 100.0 * covered / n_files if n_files else 0
    print(f"  Coverage: {covered:,} identified  {gaps:,} gaps  ({pct:.1f}% covered)")

    print(f"\n  {'COVERED EXTENSIONS':42s}  {'count':>7}  {'GB':>8}")
    print(f"  {'-'*W}")
    cur.execute("""
        SELECT file_extension, interpreted_as, COUNT(*) AS n, SUM(size) AS b
        FROM files WHERE scan_id=? AND type='file' AND interpreted_as IS NOT NULL
        GROUP BY file_extension ORDER BY n DESC LIMIT 20""", (scan_id,))
    for r in cur.fetchall():
        ext  = r["file_extension"] or "(none)"
        size = (r["b"] or 0) / (1024**3)
        print(f"  {ext:<20}  {r['interpreted_as']:<22}  {r['n']:>7,}  {size:>8.2f}")

    print(f"\n  {'GAP EXTENSIONS (no interpreter)':42s}  {'count':>7}  {'GB':>8}")
    print(f"  {'-'*W}")
    cur.execute("""
        SELECT file_extension, COUNT(*) AS n, SUM(size) AS b
        FROM files WHERE scan_id=? AND type='file' AND interpreted_as IS NULL
          AND file_extension IS NOT NULL AND file_extension != ''
        GROUP BY file_extension ORDER BY n DESC LIMIT 30""", (scan_id,))
    for r in cur.fetchall():
        size = (r["b"] or 0) / (1024**3)
        print(f"  {r['file_extension']:<42}  {r['n']:>7,}  {size:>8.2f}")

    cur.execute("""
        SELECT COUNT(*) AS n, SUM(size) AS b FROM files
        WHERE scan_id=? AND type='file' AND interpreted_as IS NULL
          AND (file_extension IS NULL OR file_extension = '')""", (scan_id,))
    u = cur.fetchone()
    if u["n"]:
        print(f"  {'(no extension)':42}  {u['n']:>7,}  {(u['b'] or 0)/(1024**3):>8.2f}")

    print(f"\n  DETECTED INSTRUMENT / PIPELINE DIRECTORIES")
    print(f"  {'-'*W}")
    cur.execute("""
        SELECT json_extract(extra_json, '$.pattern') AS pattern, COUNT(*) AS n
        FROM files WHERE scan_id=? AND type='folder' AND extra_json IS NOT NULL
        GROUP BY pattern ORDER BY n DESC""", (scan_id,))
    rows = [r for r in cur.fetchall() if r["pattern"]]
    if rows:
        for r in rows:
            print(f"  {r['pattern']:<44}  {r['n']:>4} dir{'s' if r['n']!=1 else ''}")
    else:
        print("  (none detected)")

    print(f"\n  MAGIC BYTE IDs  (gap files where format was detected)")
    print(f"  {'-'*W}")
    cur.execute("""
        SELECT json_extract(interpretation_json, '$.magic_label') AS ml, COUNT(*) AS n
        FROM files WHERE scan_id=? AND type='file'
          AND interpreted_as IS NULL AND interpretation_json IS NOT NULL
          AND json_extract(interpretation_json, '$.magic_label') IS NOT NULL
        GROUP BY ml ORDER BY n DESC LIMIT 15""", (scan_id,))
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r['ml']:<44}  {r['n']:>7,}")
    else:
        print("  (none — use --magic-limit N to enable format sampling)")

    print(f"\n{'═'*W}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SciDK-compatible parallel filesystem scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("root", nargs="?", help="Directory to scan")
    parser.add_argument("--db", default="./scidk_scan.db",
                        help="SQLite output path (default: ./scidk_scan.db)")
    parser.add_argument("--note", default="", help="Human note stored with the scan")
    parser.add_argument("--workers", type=int, default=1, metavar="N",
                        help="Parallel I/O workers (default: 1). "
                             "Try 8-32 on network mounts.")
    parser.add_argument("--no-hash", action="store_true", help="Skip content hashing")
    parser.add_argument("--hash-limit", type=int, default=100, metavar="MB",
                        help="Only hash files < this MB (default: 100)")
    parser.add_argument("--magic-limit", type=int, default=0, metavar="MB",
                        help="Sample magic bytes for files < this MB. "
                             "0 = off (default, ncdu-speed). 500 = rich detection.")
    parser.add_argument("--depth", type=int, default=None,
                        help="Max directory depth (default: unlimited)")
    parser.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                        help="Glob pattern to exclude (repeatable)")
    parser.add_argument("--follow-symlinks", action="store_true")
    parser.add_argument("--resume", metavar="SCAN_ID",
                        help="Resume an existing scan by ID")
    parser.add_argument("--report", action="store_true",
                        help="Print gap report for most recent scan and exit")
    parser.add_argument("--report-id", metavar="SCAN_ID",
                        help="Print gap report for a specific scan ID and exit")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["local", "rclone"],
        default="local",
        help=(
            "Filesystem provider: 'local' (default) walks a local/NFS path; "
            "'rclone' calls 'rclone lsjson --recursive' on an rclone remote "
            "(e.g. 'dropbox:' or 'ki-preclinical-data:Images'). "
            "rclone must be on PATH when using --provider rclone."
        ),
    )
    args = parser.parse_args()

    # Report-only mode
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

    if args.provider == "rclone":
        root = args.root  # rclone target, not a local path
        if not shutil.which("rclone"):
            print("Error: rclone not found on PATH.", file=sys.stderr)
            sys.exit(1)
    else:
        root = str(Path(args.root).resolve())
        if not os.path.isdir(root):
            print(f"Error: '{root}' is not a directory.", file=sys.stderr)
            sys.exit(1)

    conn = db_connect(args.db)
    db_init(conn)

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
        conn.execute(
            "INSERT INTO scans(id, root, started, status, extra_json) VALUES(?,?,?,?,?)",
            (scan_id, root, time.time(), "running", json.dumps({
                "note": args.note, "tool": "scidk_scanner.py",
                "workers": args.workers, "excludes": args.exclude,
            })),
        )
        conn.commit()

    magic_str = "off (stat-only)" if args.magic_limit == 0 \
                else f"files < {args.magic_limit} MB"
    if not args.quiet:
        provider_label = getattr(args, "provider", "local")
        print(f"\nSciDK Filesystem Scanner  [{provider_label}]")
        print(f"  Root    : {root}")
        print(f"  Database: {args.db}")
        print(f"  Scan ID : {scan_id}")
        print(f"  Workers : {args.workers}")
        print(f"  Hashing : {'off' if args.no_hash else f'files < {args.hash_limit} MB'}")
        print(f"  Magic   : {magic_str}")
        if args.exclude:
            print(f"  Excludes: {', '.join(args.exclude)}")
        print()

    t0 = time.time()
    try:
        if getattr(args, "provider", "local") == "rclone":
            # rclone path: args.root is the rclone target (e.g. dropbox:)
            stats = walk_rclone(
                args.root, scan_id, conn,
                max_depth=args.depth,
                do_hash=not args.no_hash,
                quiet=args.quiet,
            )
        else:
            stats = walk_path(
                root, scan_id, conn,
                workers=args.workers,
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
        print(f"\r  {stats['files']:>9,} files  {stats['dirs']:>6,} dirs  "
              f"{gb:.2f} GB  {stats['gaps']:>6,} gaps  ({elapsed:.0f}s)          ")
        print(f"\n  Saved → {args.db}")

    print_gap_report(conn, scan_id)
    conn.close()


if __name__ == "__main__":
    main()
