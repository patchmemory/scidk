#!/usr/bin/env python3
"""
End-to-end trace to prove no truncation from SQLite index -> commit rows -> Neo4j Cypher params.

This script:
- Connects to the default SQLite index used by scidk.core.path_index_sqlite
- Loads rows for a given scan_id (or auto-detects a recent one) where path LIKE 'dropbox:%'
- Builds rows (files) and folder_rows exactly like api_scan_commit does in index mode
- Monkeypatches neo4j.GraphDatabase with a fake driver that records all executed Cypher and parameters
- Calls scidk.app.commit_to_neo4j_batched and prints a detailed step-by-step report

Usage examples:
  python dev/rclone_commit_trace.py --scan <scan_id> --limit 50
  python dev/rclone_commit_trace.py --remote dropbox: --limit 50
  python dev/rclone_commit_trace.py --all   # prints all mapped rows and all cypher params (can be verbose)

This does NOT write to a real Neo4j database.
"""
import argparse
import os
import sys
from typing import Dict, Any, List

# Ensure project root on sys.path
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scidk.core import path_index_sqlite as pix
from scidk.app import commit_to_neo4j_batched

# --- Neo4j recorder fakes ---
class _FakeResult:
    def __init__(self, data=None):
        self._data = data or {}
    def single(self):
        return self._data
    def __iter__(self):
        return iter([self._data])
    def consume(self):
        return None

class Recorder:
    calls: List[Dict[str, Any]] = []  # { cypher: str, params: dict }

class _FakeSession:
    def run(self, cypher, **params):
        Recorder.calls.append({"cypher": cypher, "params": dict(params)})
        c = (cypher or '').strip()
        if c.startswith("OPTIONAL MATCH (s:Scan"):
            return _FakeResult({'scan_exists': True, 'files_cnt': 0, 'folders_cnt': 0})
        return _FakeResult({})
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        self.close()

class _FakeDriver:
    def __init__(self, uri=None, auth=None):
        self.uri = uri
        self.auth = auth
    def session(self, database=None):
        return _FakeSession()
    def close(self):
        pass

class _FakeGraphDatabase:
    @staticmethod
    def driver(uri, auth=None):
        return _FakeDriver(uri=uri, auth=auth)


def _parent(path: str) -> str:
    try:
        from scidk.core.path_utils import parse_remote_path, parent_remote_path
        info = parse_remote_path(path)
        if info.get('is_remote'):
            return parent_remote_path(path)
    except Exception:
        pass
    try:
        from pathlib import Path as _P
        return str(_P(path).parent)
    except Exception:
        return ''

def _name(path: str) -> str:
    try:
        from scidk.core.path_utils import parse_remote_path
        info = parse_remote_path(path)
        if info.get('is_remote'):
            parts = info.get('parts') or []
            return (info.get('remote_name') or '') if not parts else parts[-1]
    except Exception:
        pass
    try:
        from pathlib import Path as _P
        return _P(path).name
    except Exception:
        return path


def build_rows_from_sqlite(scan_id: str, limit: int = 200, remote_prefix: str = 'dropbox:'):
    conn = pix.connect()
    pix.init_db(conn)
    try:
        cur = conn.cursor()
        if scan_id:
            cur.execute(
                "SELECT path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type "
                "FROM files WHERE scan_id = ? AND path LIKE ? ORDER BY depth, path LIMIT ?",
                (scan_id, f"{remote_prefix}%", limit)
            )
        else:
            # auto-detect most recent scan containing remote_prefix
            cur.execute(
                "SELECT scan_id FROM files WHERE path LIKE ? ORDER BY rowid DESC LIMIT 1",
                (f"{remote_prefix}%",)
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"No rows found in SQLite for paths like {remote_prefix}%.")
            scan_id = row[0]
            cur.execute(
                "SELECT path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type "
                "FROM files WHERE scan_id = ? AND path LIKE ? ORDER BY depth, path LIMIT ?",
                (scan_id, f"{remote_prefix}%", limit)
            )
        items = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rows: List[Dict[str, Any]] = []
    folder_rows: List[Dict[str, Any]] = []
    folders_seen = set()
    for (p, parent, name, depth, typ, size, mtime, ext, mime) in items:
        if typ == 'folder':
            if p in folders_seen:
                continue
            folders_seen.add(p)
            par = (parent or '').strip() or _parent(p)
            folder_rows.append({
                'path': p,
                'name': name or _name(p),
                'parent': par,
                'parent_name': _name(par),
            })
        else:
            par = (parent or '').strip() or _parent(p)
            rows.append({
                'path': p,
                'filename': name or _name(p),
                'extension': ext or '',
                'size_bytes': int(size or 0),
                'created': 0.0,
                'modified': float(mtime or 0.0),
                'mime_type': mime,
                'folder': par,
            })
    return scan_id, rows, folder_rows


def print_samples(header: str, sample: List[Dict[str, Any]], fields: List[str], limit: int = 10):
    print(f"\n=== {header} (showing up to {limit}) ===")
    for i, r in enumerate(sample[:limit]):
        out = {k: r.get(k) for k in fields}
        print(f"{i+1:>3}: {out}")


def main():
    ap = argparse.ArgumentParser(description="Trace rclone commit rows to Neo4j Cypher params; optional real commit.")
    ap.add_argument('--scan', dest='scan_id', help='Specific scan_id to trace', default=None)
    ap.add_argument('--remote', dest='remote', default='dropbox:', help='Remote id prefix (default: dropbox:)')
    ap.add_argument('--limit', dest='limit', type=int, default=200, help='Max rows to load from SQLite (default 200)')
    ap.add_argument('--all', dest='show_all', action='store_true', help='Print all rows and all Cypher params (verbose)')
    ap.add_argument('--execute', '-x', dest='execute', action='store_true', help='Perform a real commit to Neo4j (no monkeypatch)')
    ap.add_argument('--batch-files', type=int, default=None, help='Files batch size override (default auto)')
    ap.add_argument('--batch-folders', type=int, default=None, help='Folders batch size override (default auto)')
    ap.add_argument('--check-path', dest='check_path', default=None, help='Optional exact File.path to verify after commit')
    args = ap.parse_args()

    # Step 1: load from SQLite
    scan_id, rows, folder_rows = build_rows_from_sqlite(args.scan_id, args.limit, args.remote)

    print(f"Scan: {scan_id}")
    print(f"Loaded from SQLite: files={len(rows)}, folders={len(folder_rows)} (prefix={args.remote})")

    # Step 2: show SQLite-derived mappings
    print_samples("SQLite -> commit rows (files)", rows, ["path", "folder"]) 
    print_samples("SQLite -> commit folder_rows", folder_rows, ["path", "parent"]) 

    # Step 3: prepare a minimal scan dict (matches app commit input)
    scan = {
        'id': scan_id,
        'path': '',
        'provider_id': 'rclone',
        'host_type': 'rclone',
        'host_id': 'rclone:dropbox',
        'root_id': None,
        'root_label': None,
        'scan_source': 'index',
    }

    # Step 4: Choose dry-run vs real execution
    if not args.execute:
        # Monkeypatch neo4j with a module-like object exposing GraphDatabase
        import types as _types
        sys.modules['neo4j'] = _types.SimpleNamespace(GraphDatabase=_FakeGraphDatabase)
        # Sanity check
        try:
            from neo4j import GraphDatabase as _GD
            assert _GD is _FakeGraphDatabase
            print("[trace] Using fake neo4j.GraphDatabase (dry-run mode)")
        except Exception as _e:
            print(f"[trace] Warning: failed to patch neo4j properly: {_e}")
        neo4j_params = ("bolt://localhost:7687", None, None, None, "none")
    else:
        # Real commit mode uses your environment for Neo4j connection
        print("[trace] Using REAL Neo4j connection (execute mode)")
        uri = os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')
        auth_env = (os.environ.get('NEO4J_AUTH') or '').strip().lower()
        user = os.environ.get('NEO4J_USER') or os.environ.get('NEO4J_USERNAME')
        pwd = os.environ.get('NEO4J_PASSWORD')
        database = os.environ.get('SCIDK_NEO4J_DATABASE') or None
        if not uri:
            print('[trace] ERROR: NEO4J_URI is not set. Export NEO4J_URI (and NEO4J_AUTH=none or NEO4J_USER/NEO4J_PASSWORD).')
            sys.exit(2)
        if auth_env == 'none':
            neo4j_params = (uri, None, None, database, 'none')
        else:
            neo4j_params = (uri, user, pwd, database, 'basic')

    # Step 5: call commit_to_neo4j_batched, capture details
    Recorder.calls.clear()
    file_bs = args.batch_files if args.batch_files is not None else (min(2000, max(1, len(rows))) or 1)
    folder_bs = args.batch_folders if args.batch_folders is not None else (min(2000, max(1, len(folder_rows))) or 1)
    res = commit_to_neo4j_batched(
        rows=rows,
        folder_rows=folder_rows,
        scan=scan,
        neo4j_params=neo4j_params,
        file_batch_size=file_bs,
        folder_batch_size=folder_bs,
        max_retries=0,
        on_progress=lambda e, p: print(f"[progress:{e}] {p}")
    )

    # Step 6: analyze recorded cypher params (only in dry-run)
    if not args.execute:
        file_calls = [c for c in Recorder.calls if isinstance(c.get('cypher'), str) and 'UNWIND $rows AS r' in c['cypher']]
        folder_upsert_calls = [c for c in Recorder.calls if 'UNWIND $folders AS folder' in (c.get('cypher') or '') and 'MERGE (fo:Folder' in c['cypher']]
        folder_link_calls = [c for c in Recorder.calls if 'UNWIND $folders AS folder' in (c.get('cypher') or '') and 'MERGE (child:Folder' in c['cypher']]

        print(f"\nResult: {res}")

        # Print sample params from file stage
        if file_calls:
            rows_params = file_calls[-1]['params'].get('rows') or []
            print_samples("Cypher params -> files rows", rows_params, ["path", "folder"], limit=(len(rows_params) if args.show_all else 10))
        else:
            print("No files stage calls recorded.")

        # Print sample params from folder stages
        if folder_upsert_calls:
            folders_params = folder_upsert_calls[-1]['params'].get('folders') or []
            print_samples("Cypher params -> folders upsert", folders_params, ["path", "parent"], limit=(len(folders_params) if args.show_all else 10))
        else:
            print("No folder upsert stage calls recorded.")

        if folder_link_calls:
            link_params = folder_link_calls[-1]['params'].get('folders') or []
            print_samples("Cypher params -> folders link", link_params, ["path", "parent"], limit=(len(link_params) if args.show_all else 10))
        else:
            print("No folder link stage calls recorded.")

        # Cross-check truncation only in dry-run
        def detect_truncation(sql_rows: List[Dict[str, Any]], cypher_rows: List[Dict[str, Any]]):
            import collections
            sql_by_file = collections.defaultdict(set)
            cyp_by_file = collections.defaultdict(set)
            for r in sql_rows:
                sql_by_file[(r.get('filename') or r.get('path') or '').split('/')[-1]].add(r.get('path'))
            for r in cypher_rows:
                cyp_by_file[(r.get('filename') or r.get('path') or '').split('/')[-1]].add(r.get('path'))
            trunc = []
            for k in sql_by_file.keys() | cyp_by_file.keys():
                spaths = sql_by_file.get(k) or set()
                cpaths = cyp_by_file.get(k) or set()
                if spaths and cpaths and not cpaths.issuperset(spaths):
                    trunc.append((k, spaths, cpaths))
            return trunc

        cy_rows = file_calls[-1]['params'].get('rows') if file_calls else []
        truncation = detect_truncation(rows, cy_rows)
        print("\n=== Truncation check ===")
        if not truncation:
            print("No truncation detected: all Cypher file paths are consistent with SQLite-derived rows.")
        else:
            print("Potential truncation mismatches detected:")
            for (fname, spaths, cpaths) in truncation[:10]:
                print(f"- {fname}:\n  SQLite paths: {sorted(spaths)}\n  Cypher paths: {sorted(cpaths)}")

    # In execute mode, run a post-commit probe against the DB
    if args.execute:
        from neo4j import GraphDatabase as _GD
        uri, user, pwd, database, mode = neo4j_params
        auth = None if mode == 'none' else (user, pwd)
        print("\n[verify] Connecting to Neo4j for post-commit checks…")
        drv = _GD.driver(uri, auth=auth)
        try:
            with drv.session(database=database) as sess:
                q = (
                    "OPTIONAL MATCH (s:Scan {id: $scan_id}) "
                    "WITH s "
                    "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(f:File) "
                    "WITH s, count(DISTINCT f) AS files_cnt "
                    "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(fo:Folder) "
                    "RETURN coalesce(s IS NOT NULL, false) AS scan_exists, files_cnt AS files_cnt, count(DISTINCT fo) AS folders_cnt"
                )
                rec = sess.run(q, scan_id=scan_id).single()
                print(f"[verify] scan_exists={rec.get('scan_exists')}, files={rec.get('files_cnt')}, folders={rec.get('folders_cnt')}")
                deep = args.check_path
                if not deep:
                    deep_rows = sorted([r for r in rows if r.get('path')], key=lambda r: len(r['path']), reverse=True)
                    deep = deep_rows[0]['path'] if deep_rows else None
                if deep:
                    print(f"[verify] Checking exact File.path exists: {deep}")
                    f1 = sess.run("MATCH (f:File {path:$p}) RETURN f", p=deep).single()
                    print("[verify] File exists:", bool(f1))
                    print(f"[verify] Checking folder containing file:")
                    fo = sess.run("MATCH (f:File {path:$p})<-[:CONTAINS]-(fo:Folder) RETURN fo.path AS fo", p=deep).single()
                    print("[verify] Parent folder:", fo.get('fo') if fo else None)
        finally:
            drv.close()

if __name__ == '__main__':
    main()
