import sqlite3
from typing import Optional

from . import path_index_sqlite as pix
from . import annotations_sqlite as ann


def _ensure_schema_migrations(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER NOT NULL
        );
        """
    )
    # Ensure at least one row
    row = cur.execute("SELECT version FROM schema_migrations LIMIT 1").fetchone()
    if row is None:
        cur.execute("INSERT INTO schema_migrations(version) VALUES (0)")
    conn.commit()


def _get_version(conn: sqlite3.Connection) -> int:
    _ensure_schema_migrations(conn)
    row = conn.execute("SELECT version FROM schema_migrations LIMIT 1").fetchone()
    try:
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _set_version(conn: sqlite3.Connection, v: int):
    conn.execute("UPDATE schema_migrations SET version = ?", (int(v),))
    conn.commit()


def migrate(conn: Optional[sqlite3.Connection] = None) -> int:
    """Apply minimal schema migrations.
    Returns the final schema version after migrations.
    v1: Ensure selections/selection_items/annotations base exist (register existing annotations schema)
    v2: Add tables:
        scans, scan_items, scan_progress, settings, metrics, logs, background_tasks, directory_cache, provider_mounts
    """
    own = False
    if conn is None:
        conn = pix.connect()
        own = True
    try:
        cur = conn.cursor()
        # Make sure migrations registry exists
        _ensure_schema_migrations(conn)
        version = _get_version(conn)

        # v1: ensure annotations-related tables exist (delegates to annotations_sqlite.init_db)
        if version < 1:
            ann.init_db(conn)
            _set_version(conn, 1)
            version = 1

        # v2: create new tables if not exist
        if version < 2:
            # scans: basic info about a scan operation
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY,
                    root TEXT,
                    started REAL,
                    completed REAL,
                    status TEXT,
                    extra_json TEXT
                );
                """
            )
            # scan_items: file entries observed in a scan (duplicate of files table but scoped per scan for traceability)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_items (
                    scan_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT,
                    size INTEGER,
                    modified_time REAL,
                    file_extension TEXT,
                    mime_type TEXT,
                    etag TEXT,
                    hash TEXT,
                    extra_json TEXT,
                    PRIMARY KEY (scan_id, path)
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_items_ext ON scan_items(scan_id, file_extension);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_scan_items_type ON scan_items(scan_id, type);")

            # scan_progress: progress metrics per scan
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_progress (
                    scan_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL,
                    updated REAL,
                    PRIMARY KEY (scan_id, metric)
                );
                """
            )

            # settings: generic key/value storage (stringly-typed)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

            # metrics: time-series-ish metrics
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    ts REAL,
                    scope TEXT,
                    name TEXT,
                    value REAL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_scope_name ON metrics(scope, name);")

            # logs: basic append-only log lines
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    ts REAL,
                    level TEXT,
                    message TEXT,
                    context TEXT
                );
                """
            )

            # background_tasks: for minimal queueing/state
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS background_tasks (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    status TEXT,
                    created REAL,
                    updated REAL,
                    payload TEXT
                );
                """
            )

            # directory_cache: cache of directory listings for selective scanning
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS directory_cache (
                    scan_id TEXT,
                    path TEXT,
                    children_json TEXT,
                    created REAL,
                    PRIMARY KEY (scan_id, path)
                );
                """
            )

            # provider_mounts: basic info about configured mounts/providers
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_mounts (
                    id TEXT PRIMARY KEY,
                    provider TEXT,
                    root TEXT,
                    created REAL,
                    status TEXT,
                    extra_json TEXT
                );
                """
            )

            conn.commit()
            _set_version(conn, 2)
            version = 2

        return version
    finally:
        if own:
            try:
                conn.close()
            except Exception:
                pass
