import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Minimal SQLite DAO for path index
# Schema from task-sqlite-path-index:
# files(path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, etag, hash, remote, scan_id, extra_json)


def _db_path() -> Path:
    # Allow override via env; default to ~/.scidk/db/files.db
    base = os.environ.get('SCIDK_DB_PATH')
    if base:
        p = Path(base)
    else:
        p = Path.home() / '.scidk' / 'db' / 'files.db'
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect() -> sqlite3.Connection:
    p = _db_path()
    conn = sqlite3.connect(str(p))
    # WAL mode as per acceptance
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
    except Exception:
        pass
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None):
    own = False
    if conn is None:
        conn = connect()
        own = True
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT NOT NULL,
                parent_path TEXT,
                name TEXT NOT NULL,
                depth INTEGER NOT NULL,
                type TEXT NOT NULL,
                size INTEGER NOT NULL,
                modified_time REAL,
                file_extension TEXT,
                mime_type TEXT,
                etag TEXT,
                hash TEXT,
                remote TEXT,
                scan_id TEXT,
                extra_json TEXT
            );
            """
        )
        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_parent_name ON files(scan_id, parent_path, name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_ext ON files(scan_id, file_extension);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_type ON files(scan_id, type);")
        conn.commit()
    finally:
        if own:
            conn.close()


def _parent_of(path: str) -> str:
    try:
        p = Path(path)
        return str(p.parent)
    except Exception:
        return ''


def _name_of(path: str) -> str:
    try:
        p = Path(path)
        return p.name or str(p)
    except Exception:
        return path


def _depth_of(path: str) -> int:
    try:
        # Count separators; for rclone remotes like "remote:folder/sub", keep colon as root and split on '/'
        # e.g., "remote:folder/sub" -> depth 2 (folder, sub)
        if ':' in path:
            suffix = path.split(':', 1)[1]
            if suffix.startswith('/'):
                suffix = suffix[1:]
            return 0 if not suffix else suffix.count('/') + 1
        # local style
        return 0 if path in ('', '/', None) else str(Path(path)).strip('/').count('/') + 1
    except Exception:
        return 0


def map_rclone_item_to_row(item: Dict, target_root: str, scan_id: str) -> Tuple:
    # rclone lsjson fields: Name, Path, Size, MimeType, ModTime, IsDir
    name = (item.get('Name') or item.get('Path') or '')
    is_dir = bool(item.get('IsDir'))
    size = int(item.get('Size') or 0)
    mime = item.get('MimeType')
    # Full path under target root
    base = target_root if target_root.endswith(':') else target_root.rstrip('/')
    full = f"{base}/{name}" if not base.endswith(':') else f"{base}{name}"
    parent = _parent_of(full)
    depth = _depth_of(full)
    ext = '' if is_dir else Path(name).suffix.lower()
    mtime = None
    # ModTime may be ISO8601; we can store as text in extra_json or leave None for MVP
    # ETag/Hash not available from lsjson by default
    etag = None
    ahash = None
    remote = target_root.split(':', 1)[0] if ':' in target_root else None
    type_val = 'folder' if is_dir else 'file'
    extra = None
    return (
        full,            # path
        parent,          # parent_path
        name,            # name
        depth,           # depth
        type_val,        # type
        size,            # size
        mtime,           # modified_time
        ext,             # file_extension
        mime,            # mime_type
        etag,            # etag
        ahash,           # hash
        remote,          # remote
        scan_id,         # scan_id
        extra,           # extra_json
    )


def batch_insert_files(rows: Iterable[Tuple], batch_size: int = 10000) -> int:
    """Insert rows in batches. Returns total inserted."""
    conn = connect()
    init_db(conn)
    total = 0
    try:
        cur = conn.cursor()
        buf: List[Tuple] = []
        for r in rows:
            buf.append(r)
            if len(buf) >= batch_size:
                cur.executemany(
                    "INSERT INTO files(path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, etag, hash, remote, scan_id, extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    buf,
                )
                conn.commit()
                total += len(buf)
                buf.clear()
        if buf:
            cur.executemany(
                "INSERT INTO files(path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type, etag, hash, remote, scan_id, extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                buf,
            )
            conn.commit()
            total += len(buf)
        return total
    finally:
        conn.close()
