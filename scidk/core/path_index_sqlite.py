import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import hashlib

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
    # Performance/safety PRAGMAs
    try:
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        # Negative cache_size means KB pages; -80000 ≈ ~80MB if 1KB page, engines vary — acceptable default
        conn.execute("PRAGMA cache_size=-80000;")
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
        # Indexes for files
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_parent_name ON files(scan_id, parent_path, name);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_ext ON files(scan_id, file_extension);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_files_scan_type ON files(scan_id, type);")
        
        # Minimal history table for future change tracking
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS file_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filesystem TEXT,
                path TEXT NOT NULL,
                size INTEGER,
                modified_time REAL,
                hash TEXT,
                scan_id TEXT,
                change_type TEXT,
                previous_size INTEGER,
                previous_modified_time REAL,
                previous_path TEXT,
                logical_key TEXT
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_path ON file_history(path);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_hist_scan ON file_history(scan_id);")
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


from .path_utils import join_remote_path, parent_remote_path, parse_remote_path

def map_rclone_item_to_row(item: Dict, target_root: str, scan_id: str) -> Tuple:
    # rclone lsjson fields: Name, Path, Size, MimeType, ModTime, IsDir
    rel = str(item.get('Path') or item.get('Name') or '')
    # Normalize rel to be relative to target_root to avoid base/base duplication
    try:
        info_base = parse_remote_path(target_root)
        parts = info_base.get('parts') or []
        base_suffix = '/'.join(parts) if parts else ''
        if base_suffix:
            if rel == base_suffix:
                rel = ''
            elif isinstance(rel, str) and rel.startswith(base_suffix + '/'):
                rel = rel[len(base_suffix) + 1:]
    except Exception:
        # Best-effort; ignore on errors
        pass
    leaf = item.get('Name') or (rel.rsplit('/', 1)[-1] if rel else '')
    is_dir = bool(item.get('IsDir'))
    size = int(item.get('Size') or 0)
    mime = item.get('MimeType')
    # Full path under target root using central utils; empty rel keeps base
    full = join_remote_path(target_root, rel)
    parent = parent_remote_path(full)
    depth = _depth_of(full)
    ext = '' if is_dir else Path(leaf).suffix.lower()
    mtime = None
    # Best-effort ModTime parsing
    mod = item.get('ModTime')
    if mod:
        try:
            m = str(mod).replace('Z', '+00:00')
            from datetime import datetime
            mtime = datetime.fromisoformat(m).timestamp()
        except Exception:
            try:
                from dateutil import parser as dtp  # type: ignore
                mtime = dtp.parse(str(mod)).timestamp()
            except Exception:
                mtime = None
    # ETag/Hash not available from lsjson by default
    etag = None
    ahash = None
    remote = target_root.split(':', 1)[0] if ':' in target_root else None
    type_val = 'folder' if is_dir else 'file'
    extra = None
    return (
        full,            # path
        parent,          # parent_path
        leaf,            # name (leaf)
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


def get_latest_file_meta(path: str) -> Optional[Tuple[Optional[int], Optional[float], Optional[str]]]:
    """Return (size, modified_time, hash) for the latest indexed row for this path, or None."""
    conn = connect()
    init_db(conn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT size, modified_time, hash FROM files WHERE path=? ORDER BY rowid DESC LIMIT 1;", (path,))
        row = cur.fetchone()
        if not row:
            return None
        return (row[0], row[1], row[2])
    finally:
        conn.close()


def compute_content_hash(file_path: str, policy: str = 'auto', chunk_size: int = 1024 * 1024) -> Optional[str]:
    """Compute content hash with policy: 'auto' → blake3 if available else blake2b; 'blake3', 'blake2b', or 'none'.
    Returns hex digest string or None if policy is 'none' or file unreadable.
    """
    policy = (policy or 'auto').lower()
    if policy == 'none':
        return None
    try:
        if policy in ('blake3', 'auto'):
            try:
                import blake3  # type: ignore
                h = blake3.blake3()
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        h.update(chunk)
                return h.hexdigest()
            except Exception:
                if policy == 'blake3':
                    return None
                # fall through to blake2b
        # blake2b fallback
        h2 = hashlib.blake2b()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h2.update(chunk)
        return h2.hexdigest()
    except Exception:
        return None


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


def apply_basic_change_history(scan_id: str, target_root: str) -> dict:
    """
    Compute created/modified/deleted vs the most recent previous scan that indexed the same target_root prefix,
    and append rows into file_history. This is a minimal, size-based change detector for MVP.
    Returns counts dict.
    """
    conn = connect()
    init_db(conn)
    try:
        cur = conn.cursor()
        # Normalize prefix for LIKE match
        prefix = target_root if target_root.endswith(':') else target_root.rstrip('/') + '/'
        # Find previous scan for the same prefix (heuristic)
        cur.execute(
            """
            SELECT scan_id FROM files
            WHERE scan_id <> ? AND path LIKE ?
            ORDER BY rowid DESC LIMIT 1
            """,
            (scan_id, f"{prefix}%"),
        )
        row = cur.fetchone()
        prev_scan = row[0] if row else None
        if not prev_scan:
            return {"created": 0, "modified": 0, "deleted": 0}
        # Create temp tables
        cur.execute("DROP TABLE IF EXISTS _curr;")
        cur.execute("DROP TABLE IF EXISTS _prev;")
        cur.execute("CREATE TEMP TABLE _curr AS SELECT path, size FROM files WHERE scan_id=? AND path LIKE ?;", (scan_id, f"{prefix}%"))
        cur.execute("CREATE TEMP TABLE _prev AS SELECT path, size FROM files WHERE scan_id=? AND path LIKE ?;", (prev_scan, f"{prefix}%"))
        # New (created)
        cur.execute(
            """
            INSERT INTO file_history(filesystem, path, size, modified_time, hash, scan_id, change_type, previous_size, previous_modified_time, previous_path, logical_key)
            SELECT NULL as filesystem, c.path, c.size, NULL, NULL, ?, 'created', NULL, NULL, NULL, NULL
            FROM _curr c LEFT JOIN _prev p ON p.path = c.path
            WHERE p.path IS NULL;
            """,
            (scan_id,),
        )
        created = cur.rowcount if hasattr(cur, 'rowcount') else 0
        # Deleted
        cur.execute(
            """
            INSERT INTO file_history(filesystem, path, size, modified_time, hash, scan_id, change_type, previous_size, previous_modified_time, previous_path, logical_key)
            SELECT NULL, p.path, NULL, NULL, NULL, ?, 'deleted', p.size, NULL, p.path, NULL
            FROM _prev p LEFT JOIN _curr c ON c.path = p.path
            WHERE c.path IS NULL;
            """,
            (scan_id,),
        )
        deleted = cur.rowcount if hasattr(cur, 'rowcount') else 0
        # Modified (size change)
        cur.execute(
            """
            INSERT INTO file_history(filesystem, path, size, modified_time, hash, scan_id, change_type, previous_size, previous_modified_time, previous_path, logical_key)
            SELECT NULL, c.path, c.size, NULL, NULL, ?, 'modified', p.size, NULL, c.path, NULL
            FROM _curr c JOIN _prev p ON p.path = c.path
            WHERE COALESCE(c.size,-1) <> COALESCE(p.size,-1);
            """,
            (scan_id,),
        )
        modified = cur.rowcount if hasattr(cur, 'rowcount') else 0
        conn.commit()
        return {"created": int(created), "modified": int(modified), "deleted": int(deleted)}
    finally:
        conn.close()


def record_scan_items(scan_id: str, rows: Iterable[Tuple], batch_size: int = 10000) -> int:
    """
    Record scan items into scan_items table for caching.
    Rows: (path, type, size, modified_time, file_extension, mime_type, etag, hash, extra_json)
    Returns total inserted.
    """
    from .migrations import migrate
    conn = connect()
    migrate(conn)
    total = 0
    try:
        cur = conn.cursor()
        buf: List[Tuple] = []
        for r in rows:
            # Expand row to match scan_items schema
            buf.append((scan_id,) + r)
            if len(buf) >= batch_size:
                cur.executemany(
                    """INSERT INTO scan_items(scan_id, path, type, size, modified_time, file_extension, mime_type, etag, hash, extra_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    buf,
                )
                conn.commit()
                total += len(buf)
                buf.clear()
        if buf:
            cur.executemany(
                """INSERT INTO scan_items(scan_id, path, type, size, modified_time, file_extension, mime_type, etag, hash, extra_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                buf,
            )
            conn.commit()
            total += len(buf)
        return total
    finally:
        conn.close()


def cache_directory_listing(scan_id: str, dir_path: str, children: List[str]) -> None:
    """
    Cache directory listing in directory_cache table.
    children: list of child file/folder names (not full paths)
    """
    import json
    import time
    from .migrations import migrate
    conn = connect()
    migrate(conn)
    try:
        children_json = json.dumps(children)
        created = time.time()
        conn.execute(
            """INSERT OR REPLACE INTO directory_cache(scan_id, path, children_json, created)
               VALUES (?,?,?,?)""",
            (scan_id, dir_path, children_json, created)
        )
        conn.commit()
    finally:
        conn.close()


def get_cached_directory(scan_id: str, dir_path: str) -> Optional[List[str]]:
    """
    Retrieve cached directory listing from directory_cache.
    Returns list of child names or None if not cached.
    """
    import json
    from .migrations import migrate
    conn = connect()
    migrate(conn)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT children_json FROM directory_cache WHERE scan_id=? AND path=?",
            (scan_id, dir_path)
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0] or "[]")
        except Exception:
            return None
    finally:
        conn.close()


def get_previous_scan_for_path(path: str) -> Optional[str]:
    """
    Find the most recent scan_id that includes this path.
    Returns scan_id or None.
    """
    conn = connect()
    init_db(conn)
    try:
        cur = conn.cursor()
        # Try scan_items first (more structured)
        cur.execute(
            "SELECT scan_id FROM scan_items WHERE path=? ORDER BY rowid DESC LIMIT 1",
            (path,)
        )
        row = cur.fetchone()
        if row:
            return row[0]
        # Fallback to files table
        cur.execute(
            "SELECT scan_id FROM files WHERE path=? ORDER BY rowid DESC LIMIT 1",
            (path,)
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_scan_item(scan_id: str, path: str) -> Optional[Dict]:
    """
    Retrieve scan item metadata from scan_items table.
    Returns dict with path, type, size, modified_time, hash, etc. or None.
    """
    from .migrations import migrate
    conn = connect()
    migrate(conn)
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT path, type, size, modified_time, file_extension, mime_type, etag, hash
               FROM scan_items WHERE scan_id=? AND path=?""",
            (scan_id, path)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            'path': row[0],
            'type': row[1],
            'size': row[2],
            'modified_time': row[3],
            'file_extension': row[4],
            'mime_type': row[5],
            'etag': row[6],
            'hash': row[7],
        }
    finally:
        conn.close()
