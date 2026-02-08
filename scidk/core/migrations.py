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

        # v3: relationships and sync_queue tables (annotations enhancements)
        if version < 3:
            # create via direct DDL to ensure upgrade path (even if ann.init_db changes)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    type TEXT,
                    properties_json TEXT,
                    created REAL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_to ON relationships(to_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(type);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT,
                    entity_id TEXT,
                    action TEXT,
                    payload TEXT,
                    created REAL,
                    processed REAL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_processed ON sync_queue(processed);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sync_entity ON sync_queue(entity_type, entity_id);")
            conn.commit()
            _set_version(conn, 3)
            version = 3

        # v4: per-scan selection rules (normalized)
        if version < 4:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_selection_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    path TEXT NOT NULL,
                    recursive INTEGER NOT NULL,
                    node_type TEXT,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL DEFAULT (strftime('%s','now')),
                    created_by TEXT
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ssr_scan ON scan_selection_rules(scan_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ssr_scan_order ON scan_selection_rules(scan_id, order_index);")
            conn.commit()
            _set_version(conn, 4)
            version = 4

        # v5: label_definitions for graph schema management
        if version < 5:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS label_definitions (
                    name TEXT PRIMARY KEY,
                    properties TEXT,
                    relationships TEXT,
                    created_at REAL,
                    updated_at REAL
                );
                """
            )
            conn.commit()
            _set_version(conn, 5)
            version = 5

        # v6: link_definitions and link_jobs for relationship creation workflows
        if version < 6:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS link_definitions (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    source_type TEXT,
                    source_config TEXT,
                    target_type TEXT,
                    target_config TEXT,
                    match_strategy TEXT,
                    match_config TEXT,
                    relationship_type TEXT,
                    relationship_props TEXT,
                    created_at REAL,
                    updated_at REAL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS link_jobs (
                    id TEXT PRIMARY KEY,
                    link_def_id TEXT,
                    status TEXT,
                    preview_count INTEGER,
                    executed_count INTEGER,
                    error TEXT,
                    started_at REAL,
                    completed_at REAL,
                    FOREIGN KEY (link_def_id) REFERENCES link_definitions(id)
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_link_jobs_def ON link_jobs(link_def_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_link_jobs_status ON link_jobs(status);")
            conn.commit()
            _set_version(conn, 6)
            version = 6

        # v7: Add source_label and target_label columns to link_definitions for Label→Label refactor
        if version < 7:
            cur.execute("ALTER TABLE link_definitions ADD COLUMN source_label TEXT;")
            cur.execute("ALTER TABLE link_definitions ADD COLUMN target_label TEXT;")
            conn.commit()
            _set_version(conn, 7)
            version = 7

        # v8: Add chat_sessions and chat_messages tables for persistent chat history
        if version < 8:
            # Chat sessions table - stores metadata about conversation sessions
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    metadata TEXT
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated ON chat_sessions(updated_at DESC);")

            # Chat messages table - stores individual messages within sessions
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);")

            conn.commit()
            _set_version(conn, 8)
            version = 8

        # v9: Add saved_queries table for query library
        if version < 9:
            # Saved queries table - stores user's saved Cypher queries
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_queries (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    query TEXT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_used_at REAL,
                    use_count INTEGER DEFAULT 0,
                    metadata TEXT
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_queries_name ON saved_queries(name);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_queries_updated ON saved_queries(updated_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_saved_queries_last_used ON saved_queries(last_used_at DESC);")

            conn.commit()
            _set_version(conn, 9)
            version = 9

        # v10: Add permissions/sharing for chat sessions
        if version < 10:
            # Add owner and visibility columns to chat_sessions
            cur.execute("ALTER TABLE chat_sessions ADD COLUMN owner TEXT DEFAULT 'system'")
            cur.execute("ALTER TABLE chat_sessions ADD COLUMN visibility TEXT DEFAULT 'private'")
            # visibility: 'private' (owner only), 'shared' (specific users), 'public' (all users)

            # Chat session permissions table for shared access
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_session_permissions (
                    session_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    granted_at REAL NOT NULL,
                    granted_by TEXT,
                    PRIMARY KEY (session_id, username),
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                );
                """
            )
            # permission: 'view' (read-only), 'edit' (can add messages), 'admin' (can manage permissions)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_perms_session ON chat_session_permissions(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_perms_user ON chat_session_permissions(username);")

            conn.commit()
            _set_version(conn, 10)
            version = 10

        return version
    finally:
        if own:
            try:
                conn.close()
            except Exception:
                pass
