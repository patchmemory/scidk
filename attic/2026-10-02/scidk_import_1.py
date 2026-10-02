#!/usr/bin/env python3
"""
scidk_import.py — Import external scan DBs into the central SciDK files.db
===========================================================================
Merges one or more scan databases produced by scidk_scanner_opt.py (or
scidk_scanner.py) into the central SciDK files.db. Safe to run on remote
scan DBs scp'd back to the SciDK host after server-side scanning.

Usage:
    python3 scidk_import.py ~/.scidk/scans/atwai_scan.db
    python3 scidk_import.py ~/.scidk/scans/*.db
    python3 scidk_import.py scan1.db scan2.db --db /custom/files.db

Options:
    --db PATH           Target files.db (default: ~/.scidk/db/files.db)
    --on-conflict MODE  skip | replace (default: skip)
                        skip:    existing scan_ids are left untouched
                        replace: existing scan_ids are deleted and re-imported
    --dry-run           Show what would be imported without writing anything
    --quiet             Suppress progress output
    --remote HOSTNAME   Hostname to stamp on imported rows where remote is NULL.
                        Defaults to socket.getfqdn() (the local FQDN).

Exit codes:
    0  All DBs imported or skipped successfully
    1  One or more DBs failed (schema mismatch, corrupt file, etc.)

Notes:
    - Idempotent by default: re-running with the same DB is safe
    - Validates schema before importing — will not corrupt files.db
    - Does not trigger profiling or interpretation
    - stdlib only — no SciDK installation required
"""

import argparse
import os
import socket
import sqlite3
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Schema validation
# ─────────────────────────────────────────────────────────────────────────────

# Tables that must exist in the source DB
REQUIRED_SOURCE_TABLES = {"scans", "files", "scan_progress"}

# Columns that must exist in source files table
REQUIRED_FILE_COLUMNS = {
    "path", "parent_path", "name", "depth", "type", "size",
    "modified_time", "file_extension", "mime_type", "etag", "hash",
    "remote", "scan_id", "extra_json",
}

# Optional columns — added to target if missing, skipped in INSERT if absent
OPTIONAL_FILE_COLUMNS = {"interpreted_as", "interpretation_json"}

# All columns in target files table (superset)
TARGET_FILE_COLUMNS = REQUIRED_FILE_COLUMNS | OPTIONAL_FILE_COLUMNS


def _get_tables(conn: sqlite3.Connection) -> set:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cur.fetchall()}


def _get_columns(conn: sqlite3.Connection, table: str) -> set:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _validate_source(src_path: str) -> Tuple[bool, str, set]:
    """
    Validate source DB schema. Returns (ok, error_message, present_columns).
    """
    if not os.path.exists(src_path):
        return False, f"File not found: {src_path}", set()

    if os.path.getsize(src_path) == 0:
        return False, f"File is empty (possibly a deleted-inode stub): {src_path}", set()

    try:
        conn = sqlite3.connect(src_path)
        conn.execute("SELECT 1")  # lightweight connection check only
    except sqlite3.DatabaseError as e:
        return False, f"Cannot open DB: {e}", set()

    try:
        tables = _get_tables(conn)
        missing = REQUIRED_SOURCE_TABLES - tables
        if missing:
            conn.close()
            return False, f"Missing required tables: {missing}", set()

        cols = _get_columns(conn, "files")
        missing_cols = REQUIRED_FILE_COLUMNS - cols
        if missing_cols:
            conn.close()
            return False, f"Missing required columns in files table: {missing_cols}", set()

        conn.close()
        return True, "", cols

    except Exception as e:
        conn.close()
        return False, f"Schema validation error: {e}", set()


# ─────────────────────────────────────────────────────────────────────────────
# Target DB initialisation
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_target(target_path: str) -> sqlite3.Connection:
    """Open (or create) the target files.db and ensure schema is present."""
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-80000")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id         TEXT PRIMARY KEY,
            root       TEXT,
            started    REAL,
            completed  REAL,
            status     TEXT,
            extra_json TEXT
        );

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
        );

        CREATE INDEX IF NOT EXISTS idx_files_scan_ext
            ON files(scan_id, file_extension);
        CREATE INDEX IF NOT EXISTS idx_files_scan_type
            ON files(scan_id, type);
        CREATE INDEX IF NOT EXISTS idx_files_scan_parent
            ON files(scan_id, parent_path, name);
        CREATE INDEX IF NOT EXISTS idx_files_interp
            ON files(scan_id, interpreted_as);
        CREATE INDEX IF NOT EXISTS idx_files_path
            ON files(path);
        CREATE INDEX IF NOT EXISTS idx_files_depth
            ON files(scan_id, depth, parent_path);
        CREATE INDEX IF NOT EXISTS idx_files_path_prefix
            ON files(scan_id, type, path);

        CREATE TABLE IF NOT EXISTS scan_progress (
            scan_id TEXT NOT NULL,
            metric  TEXT NOT NULL,
            value   REAL,
            updated REAL,
            PRIMARY KEY (scan_id, metric)
        );
    """)
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Index management
# ─────────────────────────────────────────────────────────────────────────────

# All indexes SciDK expects on files.db — idempotent, safe to re-run
REQUIRED_INDEXES = [
    ("idx_files_scan_ext",    "ON files(scan_id, file_extension)"),
    ("idx_files_scan_type",   "ON files(scan_id, type)"),
    ("idx_files_scan_parent", "ON files(scan_id, parent_path, name)"),
    ("idx_files_interp",      "ON files(scan_id, interpreted_as)"),
    ("idx_files_path",        "ON files(path)"),
    ("idx_files_depth",       "ON files(scan_id, depth, parent_path)"),
    ("idx_files_path_prefix", "ON files(scan_id, type, path)"),
]


def ensure_indexes(
    db_path: str,
    quiet: bool = False,
) -> bool:
    """
    Create any missing indexes on an existing files.db.
    Safe to run on a live DB — uses CREATE INDEX IF NOT EXISTS.
    Returns True on success.

    On a 120M row DB this may take 10-30 minutes. Progress is printed
    per index. Run with nohup for large DBs.
    """
    if not os.path.exists(db_path):
        print(f"  ERROR: DB not found: {db_path}", file=sys.stderr)
        return False

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-200000")  # 200MB cache for index build

    # Check which indexes already exist
    existing = {
        row[0] for row in
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }

    to_create = [
        (name, defn) for name, defn in REQUIRED_INDEXES
        if name not in existing
    ]

    if not to_create:
        if not quiet:
            print(f"  All indexes present — nothing to do.")
        conn.close()
        return True

    if not quiet:
        print(f"  Creating {len(to_create)} missing index(es) on {db_path}")
        print(f"  (this may take several minutes on large DBs)\n")

    for name, defn in to_create:
        if not quiet:
            print(f"  Building {name}...", end="", flush=True)
        t0 = time.time()
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} {defn}")
        conn.commit()
        elapsed = time.time() - t0
        if not quiet:
            print(f"  done ({elapsed:.1f}s)")

    conn.close()
    if not quiet:
        print(f"\n  All indexes ready.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Merge
# ─────────────────────────────────────────────────────────────────────────────

def _get_scan_ids(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT id FROM scans ORDER BY started")
    return [row[0] for row in cur.fetchall()]


def _get_file_count(conn: sqlite3.Connection, scan_id: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) FROM files WHERE scan_id=?", (scan_id,)
    )
    return cur.fetchone()[0]


def _scan_exists_in_target(target: sqlite3.Connection, scan_id: str) -> bool:
    cur = target.execute(
        "SELECT 1 FROM scans WHERE id=?", (scan_id,)
    )
    return cur.fetchone() is not None


def _delete_scan(target: sqlite3.Connection, scan_id: str) -> None:
    target.execute("DELETE FROM files WHERE scan_id=?", (scan_id,))
    target.execute("DELETE FROM scans WHERE id=?", (scan_id,))
    target.execute("DELETE FROM scan_progress WHERE scan_id=?", (scan_id,))
    target.commit()


def _merge_scan(
    src_path: str,
    target: sqlite3.Connection,
    scan_id: str,
    src_cols: set,
    quiet: bool,
) -> int:
    """
    Merge one scan_id from src_path into target using SQLite ATTACH.
    Returns number of rows inserted.
    """
    # Columns present in source that we'll copy
    # Always use intersection so we never reference a column that doesn't exist
    copy_cols = list(TARGET_FILE_COLUMNS & src_cols)
    # Ensure required columns are all present (validated earlier, but be safe)
    col_list = ", ".join(copy_cols)

    target.execute(f"ATTACH DATABASE ? AS src", (src_path,))
    try:
        # Copy scan record
        target.execute("""
            INSERT OR IGNORE INTO scans (id, root, started, completed, status, extra_json)
            SELECT id, root, started, completed, status, extra_json
            FROM src.scans WHERE id=?
        """, (scan_id,))

        # Copy files
        target.execute(f"""
            INSERT INTO files ({col_list})
            SELECT {col_list} FROM src.files WHERE scan_id=?
        """, (scan_id,))

        rows = target.execute(
            "SELECT changes()"
        ).fetchone()[0]

        # Copy scan_progress metrics
        target.execute("""
            INSERT OR REPLACE INTO scan_progress (scan_id, metric, value, updated)
            SELECT scan_id, metric, value, updated
            FROM src.scan_progress WHERE scan_id=?
        """, (scan_id,))

        target.commit()
        return rows

    finally:
        target.execute("DETACH DATABASE src")


# ─────────────────────────────────────────────────────────────────────────────
# Import one DB file
# ─────────────────────────────────────────────────────────────────────────────

def import_db(
    src_path: str,
    target: sqlite3.Connection,
    on_conflict: str = "skip",
    dry_run: bool = False,
    quiet: bool = False,
    remote: Optional[str] = None,
) -> bool:
    """
    Import all scan_ids from src_path into target.
    Returns True on success, False on failure.

    If remote is provided (or auto-detected via socket.getfqdn()), rows
    imported with remote=NULL will be stamped with that hostname.
    """
    label = os.path.basename(src_path)

    # Validate source
    ok, err, src_cols = _validate_source(src_path)
    if not ok:
        print(f"  FAIL  {label}: {err}", file=sys.stderr)
        return False

    # Open source to enumerate scan_ids
    src_conn = sqlite3.connect(src_path)
    scan_ids = _get_scan_ids(src_conn)
    src_conn.close()

    if not scan_ids:
        if not quiet:
            print(f"  SKIP  {label}: no scans found in DB")
        return True

    all_ok = True
    for scan_id in scan_ids:
        short_id = scan_id[:12]

        # Check conflict
        if _scan_exists_in_target(target, scan_id):
            if on_conflict == "skip":
                if not quiet:
                    print(f"  SKIP  {label}  [{short_id}]  already imported")
                continue
            elif on_conflict == "replace":
                if not quiet:
                    print(f"  REPL  {label}  [{short_id}]  replacing existing")
                if not dry_run:
                    _delete_scan(target, scan_id)
            else:
                print(f"  FAIL  {label}  [{short_id}]  unknown conflict mode: {on_conflict}",
                      file=sys.stderr)
                all_ok = False
                continue

        if dry_run:
            src_conn = sqlite3.connect(src_path)
            n = _get_file_count(src_conn, scan_id)
            src_conn.close()
            print(f"  DRY   {label}  [{short_id}]  {n:,} files (not written)")
            continue

        try:
            t0 = time.time()
            n = _merge_scan(src_path, target, scan_id, src_cols, quiet)

            # Stamp remote hostname on rows imported with remote=NULL
            if remote:
                target.execute(
                    "UPDATE files SET remote=? WHERE scan_id=? AND (remote IS NULL OR remote='')",
                    (remote, scan_id),
                )
                target.commit()

            elapsed = time.time() - t0
            if not quiet:
                print(f"  OK    {label}  [{short_id}]  {n:,} files  ({elapsed:.1f}s)")
        except Exception as e:
            print(f"  FAIL  {label}  [{short_id}]  {e}", file=sys.stderr)
            all_ok = False

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import external scan DBs into the central SciDK files.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "sources", nargs="*", metavar="scan.db",
        help="One or more scan DB files to import",
    )
    parser.add_argument(
        "--reindex", action="store_true",
        help="Create any missing indexes on the target DB and exit. "
             "Safe to run on existing DB. May take 10-30 min on large DBs.",
    )
    parser.add_argument(
        "--db",
        default=str(Path.home() / ".scidk" / "db" / "files.db"),
        help="Target files.db (default: ~/.scidk/db/files.db)",
    )
    parser.add_argument(
        "--on-conflict", choices=["skip", "replace"], default="skip",
        help="What to do if scan_id already exists (default: skip)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be imported without writing anything",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--remote",
        default=None,
        help=(
            "Hostname to stamp on imported rows where remote is NULL. "
            "Defaults to socket.getfqdn() (e.g. ki-ed3g.mit.edu). "
            "Pass --remote '' to skip stamping entirely."
        ),
    )
    args = parser.parse_args()

    # Resolve remote hostname: explicit flag > auto-detect > skip
    # Empty string explicitly passed means skip stamping
    if args.remote is None:
        remote_val: Optional[str] = socket.getfqdn()
    elif args.remote == '':
        remote_val = None
    else:
        remote_val = args.remote

    if not args.quiet:
        if args.reindex:
            print(f"\nSciDK Import — Reindex mode")
        else:
            mode = " [DRY RUN]" if args.dry_run else ""
            print(f"\nSciDK Import{mode}")
        print(f"  Target : {args.db}")
        if not args.reindex:
            print(f"  Sources: {len(args.sources)} file(s)")
            print(f"  Conflict: {args.on_conflict}")
            if not args.dry_run:
                print(f"  Remote : {remote_val or '(not stamping)'}")
        print()

    # Reindex mode — build missing indexes and exit
    if args.reindex:
        ok = ensure_indexes(args.db, quiet=args.quiet)
        sys.exit(0 if ok else 1)

    # Dry run — only read sources, never open target
    if args.dry_run:
        t_total = time.time()
        failed = 0
        for src_path in args.sources:
            label = os.path.basename(src_path)
            ok, err, src_cols = _validate_source(src_path)
            if not ok:
                print(f"  FAIL  {label}: {err}", file=sys.stderr)
                failed += 1
                continue
            src_conn = sqlite3.connect(src_path)
            for scan_id in _get_scan_ids(src_conn):
                n = _get_file_count(src_conn, scan_id)
                print(f"  DRY   {label}  [{scan_id[:12]}]  {n:,} files (not written)")
            src_conn.close()
        elapsed = time.time() - t_total
        print(f"\n  Done ({elapsed:.1f}s) — nothing written\n")
        sys.exit(1 if failed else 0)

    # Open target
    if not args.sources and not args.reindex:
        parser.error("Provide at least one scan.db source, or use --reindex")

    try:
        target = _ensure_target(args.db)
    except Exception as e:
        print(f"Cannot open target DB {args.db}: {e}", file=sys.stderr)
        sys.exit(1)

    # Import each source
    t_total = time.time()
    failed = 0
    for src_path in args.sources:
        ok = import_db(
            src_path,
            target,
            on_conflict=args.on_conflict,
            dry_run=False,
            quiet=args.quiet,
            remote=remote_val,
        )
        if not ok:
            failed += 1

    target.close()

    if not args.quiet:
        elapsed = time.time() - t_total
        print()
        if failed:
            print(f"  {failed} DB(s) failed — see errors above")
        else:
            print(f"  Done ({elapsed:.1f}s)")
        print()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
