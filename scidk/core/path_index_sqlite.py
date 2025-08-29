from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

DEFAULT_DB = os.path.expanduser("~/.scidk/db/files.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    parent_path TEXT,
    name TEXT,
    depth INTEGER,
    type TEXT,                 -- 'file' | 'folder'
    size INTEGER,
    modified_time REAL,
    file_extension TEXT,
    mime_type TEXT,
    etag TEXT,
    hash TEXT,
    remote TEXT,
    scan_id TEXT,
    extra_json TEXT
);
-- Composite-friendly indexes to speed common queries
CREATE INDEX IF NOT EXISTS idx_files_scan_parent_name ON files(scan_id, parent_path, name);
CREATE INDEX IF NOT EXISTS idx_files_scan_ext ON files(scan_id, file_extension);
CREATE INDEX IF NOT EXISTS idx_files_scan_type ON files(scan_id, type);
"""


def _db_path() -> str:
    return os.environ.get("SCIDK_DB_PATH", DEFAULT_DB)


def connect() -> sqlite3.Connection:
    """Create a connection to the configured SQLite DB and enable WAL."""
    path = _db_path()
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(path)
    # Force WAL; tests expect exact 'wal'
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _ensure_db() -> sqlite3.Connection:
    conn = connect()
    init_db(conn)
    return conn


def map_rclone_item_to_row(item: Dict, root_path: str, scan_id: str) -> Dict:
    """Map a single rclone lsjson item to the path-index row dict.
    Expected item fields include: Name, Path, Size, IsDir, MimeType...
    root_path is the scan root target (e.g., "remote:bucket" or "remote:")
    """
    name = (item.get("Name") or item.get("Path") or "").strip()
    is_dir = bool(item.get("IsDir"))
    size = int(item.get("Size") or 0)
    # Build full path by joining root and Name (or Path) with '/' unless root endswith ':'
    base = root_path if root_path else ""
    if base.endswith(":"):
        full_path = f"{base}{name}" if name else base
    else:
        if name:
            full_path = f"{base.rstrip('/')}/{name}"
        else:
            full_path = base.rstrip('/')
    p = Path(full_path)
    parent = str(p.parent) if str(p) else ""
    depth = len([x for x in p.parts if x not in ("", "/")])
    ext = "" if is_dir else p.suffix.lower()
    row = {
        "path": str(p),
        "parent_path": parent,
        "name": p.name or str(p),
        "depth": depth,
        "type": "folder" if is_dir else "file",
        "size": 0 if is_dir else size,
        "modified": 0.0,
        "ext": ext,
        "scan_id": scan_id,
        # provider/host metadata can be filled by caller in future; keep None for now
        "provider_id": "rclone",
        "host_type": "rclone",
        "host_id": None,
        "root_id": None,
        "root_label": None,
    }
    return row




def list_roots(scan_id: str) -> List[str]:
    """Return root folder paths for a scan (folders whose parent_path is NULL or empty within this scan)."""
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "SELECT path FROM files WHERE scan_id=? AND type='folder' AND (parent_path IS NULL OR parent_path='') ORDER BY name COLLATE NOCASE",
            (scan_id,)
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        try:
            conn.close()
        except Exception:
            pass


def list_children(scan_id: str, parent_path: str) -> Dict[str, List[Dict]]:
    """List child folders and files for a given parent_path within a scan.
    Returns dict with keys folders, files. Each entry has name, path, and size for files.
    """
    conn = _ensure_db()
    try:
        folders = []
        files = []
        for row in conn.execute(
            "SELECT name, path FROM files WHERE scan_id=? AND parent_path=? AND type='folder' ORDER BY name COLLATE NOCASE",
            (scan_id, parent_path)
        ).fetchall():
            folders.append({'name': row[0], 'path': row[1]})
        for row in conn.execute(
            "SELECT name, path, size, file_extension, mime_type FROM files WHERE scan_id=? AND parent_path=? AND type='file' ORDER BY name COLLATE NOCASE",
            (scan_id, parent_path)
        ).fetchall():
            files.append({'name': row[0], 'path': row[1], 'size_bytes': int(row[2] or 0), 'extension': row[3] or '', 'mime_type': row[4]})
        return {'folders': folders, 'files': files}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def batch_insert_files(rows: List[Tuple], batch_size: int = 10000) -> int:
    """Insert rows into SQLite in batches. Returns inserted row count.
    Creates the DB and schema on first use.
    The row tuple order must match the schema fields used by tests:
    (path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, etag, hash, remote, scan_id, extra_json)
    """
    if not rows:
        return 0
    conn = _ensure_db()
    inserted = 0
    cols = (
        "path,parent_path,name,depth,type,size,modified_time,file_extension,mime_type,etag,hash,remote,scan_id,extra_json"
    )
    sql = f"INSERT INTO files ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    try:
        with conn:
            batch: List[Tuple] = []
            for r in rows:
                if not isinstance(r, tuple):
                    # tolerate dict style rows minimally by mapping known keys
                    try:
                        r = (
                            r.get('path'), r.get('parent_path'), r.get('name'), r.get('depth'), r.get('type'), r.get('size'),
                            r.get('modified_time') or r.get('modified') or 0.0, r.get('file_extension') or r.get('ext'),
                            r.get('mime_type'), r.get('etag'), r.get('hash'), r.get('remote'), r.get('scan_id'), r.get('extra_json')
                        )
                    except Exception:
                        continue
                batch.append(r)
                if len(batch) >= batch_size:
                    conn.executemany(sql, batch)
                    inserted += len(batch)
                    batch = []
            if batch:
                conn.executemany(sql, batch)
                inserted += len(batch)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return inserted
