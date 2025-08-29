import os
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List

# SQLite storage for selections and annotations
# Tables:
# - selections(id TEXT PRIMARY KEY, name TEXT, created REAL)
# - selection_items(selection_id TEXT, file_id TEXT, created REAL, PRIMARY KEY(selection_id, file_id))
# - annotations(id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, kind TEXT, label TEXT, note TEXT, data_json TEXT, created REAL)
# Indexes for fast lookups


def _db_path() -> Path:
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
            CREATE TABLE IF NOT EXISTS selections (
                id TEXT PRIMARY KEY,
                name TEXT,
                created REAL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS selection_items (
                selection_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                created REAL,
                PRIMARY KEY (selection_id, file_id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                kind TEXT,
                label TEXT,
                note TEXT,
                data_json TEXT,
                created REAL
            );
            """
        )
        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_selection_items_sel ON selection_items(selection_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_annotations_file ON annotations(file_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_annotations_kind ON annotations(kind);")
        conn.commit()
    finally:
        if own:
            conn.close()


def create_selection(sel_id: str, name: Optional[str], created_ts: float) -> Dict[str, Any]:
    conn = connect()
    init_db(conn)
    try:
        conn.execute("INSERT OR IGNORE INTO selections(id, name, created) VALUES (?,?,?)", (sel_id, name, created_ts))
        conn.commit()
        return {"id": sel_id, "name": name, "created": created_ts}
    finally:
        conn.close()


def add_selection_items(sel_id: str, file_ids: List[str], created_ts: float) -> int:
    conn = connect()
    init_db(conn)
    try:
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO selection_items(selection_id, file_id, created) VALUES (?,?,?)",
            [(sel_id, fid, created_ts) for fid in file_ids],
        )
        conn.commit()
        return cur.rowcount if cur.rowcount is not None else len(file_ids)
    finally:
        conn.close()


def create_annotation(file_id: str, kind: Optional[str], label: Optional[str], note: Optional[str], data_json: Optional[str], created_ts: float) -> Dict[str, Any]:
    conn = connect()
    init_db(conn)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO annotations(file_id, kind, label, note, data_json, created) VALUES (?,?,?,?,?,?)",
            (file_id, kind, label, note, data_json, created_ts),
        )
        conn.commit()
        aid = cur.lastrowid
        return {"id": aid, "file_id": file_id, "kind": kind, "label": label, "note": note, "data_json": data_json, "created": created_ts}
    finally:
        conn.close()


essential_fields = ["file_id", "kind", "label", "note", "data_json", "created"]


def list_annotations_by_file(file_id: str) -> List[Dict[str, Any]]:
    conn = connect()
    init_db(conn)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, file_id, kind, label, note, data_json, created FROM annotations WHERE file_id = ? ORDER BY id DESC", (file_id,))
        rows = cur.fetchall()
        res = []
        for r in rows:
            res.append({
                "id": r[0],
                "file_id": r[1],
                "kind": r[2],
                "label": r[3],
                "note": r[4],
                "data_json": r[5],
                "created": r[6],
            })
        return res
    finally:
        conn.close()
