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
import queue
import sqlite3
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    (b"FCS3.",            "fcs",          None),
    (b"FCS2.",            "fcs",          None),
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
    lower = {c.lower() for c in children}
    for required, label in DIRECTORY_PATTERNS:
        if all(r.lower() in lower for r in required):
            return label
        if any(r.endswith("-") for r in required):
            if all(
                r.lower() in lower or any(c.startswith(r.lower()) for c in lower)
                for r in required
            ):
                return label
    return None


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

    file_row = (fpath, dir_path, fname, fdepth, "file", fsize, fmtime,
                fext, fmime, None, fhash, None, scan_id, None, interp, ij)
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
) -> None:
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

    while True:
        try:
            item = write_q.get(timeout=0.5)
        except queue.Empty:
            flush()
            write_progress()
            print_progress()
            continue

        if item is _STOP:
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
            break

        file_row, item_row = item
        file_buf.append(file_row)
        item_buf.append(item_row)
        if len(file_buf) >= BATCH:
            flush()
        write_progress()
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
        try:
            dmtime = os.stat(dirpath).st_mtime
        except OSError:
            dmtime = None

        write_q.put((
            (dp, dparent, dname, ddepth, "folder", 0, dmtime,
             None, None, None, None, None, scan_id, dextra, None, None),
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

    writer = threading.Thread(
        target=_writer_thread,
        args=(write_q, conn, scan_id, stats, stats_lock, quiet),
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
    write_q.put((
        (root_str, str(root_path.parent), root_path.name or root_str,
         root_depth, "folder", 0, rmtime,
         None, None, None, None, None, scan_id, root_extra, None, None),
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
        SELECT COUNT(*) FILTER (WHERE type='file')   AS n_files,
               COUNT(*) FILTER (WHERE type='folder') AS n_dirs,
               SUM(size) FILTER (WHERE type='file')  AS total_bytes
        FROM files WHERE scan_id=?""", (scan_id,))
    t = cur.fetchone()
    n_files = t["n_files"] or 0
    n_dirs  = t["n_dirs"]  or 0
    tb      = (t["total_bytes"] or 0) / (1024**3)
    print(f"\n  Total   : {n_files:,} files  {n_dirs:,} dirs  {tb:.2f} GB")

    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE interpreted_as IS NOT NULL) AS covered,
               COUNT(*) FILTER (WHERE interpreted_as IS NULL)     AS gaps
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
        print(f"\nSciDK Filesystem Scanner")
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
