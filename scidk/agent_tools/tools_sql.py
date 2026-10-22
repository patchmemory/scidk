"""Read-only tools over the file index (files.db).

files.db can be very large (the demo deployment's is 212 GB), so every query
here is indexed or bounded: counts come from ``scans.extra_json`` rather than
from scanning ``files``, and per-scan breakdowns read
``idx_files_scan_ext(scan_id, file_extension)``.

Profile (Pass 3) writes ``data_objects`` / ``object_members``
(docs/pipeline_scripts_spec.md) and Adam is adding ``collections``. Until a
files.db has those tables, the tools that need them say so plainly instead of
returning an empty list that reads as "there is no data".
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .tools_graph import MAX_ROWS

#: Above this many files, a per-scan byte breakdown would read every row; skip it.
_BYTES_BREAKDOWN_MAX_FILES = 200_000


def _connect(ctx) -> Optional[sqlite3.Connection]:
    if not ctx.files_db:
        return None
    try:
        conn = sqlite3.connect(f"file:{ctx.files_db}?mode=ro", uri=True, timeout=10)
        conn.execute("PRAGMA query_only = 1")
        return conn
    except sqlite3.Error:
        return None


def _tables(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}


def _columns(conn, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


_NO_INDEX = {"status": "error", "error": "No file index (files.db) is available on this SciDK instance."}


def _not_profiled(what: str) -> Dict[str, Any]:
    return {"status": "not_profiled",
            "error": f"{what} come from Profile (Pass 3), which hasn't been run on this file index yet. "
                     "Scans are available through scan_summary."}


def scan_summary(ctx, scan_id: Optional[str] = None) -> Dict[str, Any]:
    """Scans in the index, newest first; with ``scan_id``, that scan's top extensions."""
    conn = _connect(ctx)
    if conn is None:
        return dict(_NO_INDEX)
    try:
        if 'scans' not in _tables(conn):
            return {"status": "success", "scans": [], "total": 0, "note": "No scans have been imported yet."}
        total = conn.execute("SELECT count(*) FROM scans").fetchone()[0]
        where, args = ("WHERE id = ?", (scan_id,)) if scan_id else ("", ())
        rows = conn.execute(
            f"SELECT id, root, started, completed, status, extra_json FROM scans {where} "
            f"ORDER BY started DESC LIMIT {MAX_ROWS}", args).fetchall()
        scans = []
        for sid, root, started, completed, status, extra in rows:
            try:
                x = json.loads(extra or '{}')
            except ValueError:
                x = {}
            scans.append({'_labels': ['Scan'], 'scan_id': sid, 'root': root, 'status': status,
                          'started': started, 'completed': completed,
                          'file_count': x.get('file_count'), 'folder_count': x.get('folder_count'),
                          'provider_id': x.get('provider_id'), 'committed': bool(x.get('committed'))})
        out: Dict[str, Any] = {"status": "success", "scans": scans, "total": total}
        if scan_id:
            if not scans:
                return {"status": "error", "error": f"No scan with id {scan_id!r}."}
            exts = conn.execute(
                "SELECT file_extension, count(*) FROM files WHERE scan_id = ? AND file_extension != '' "
                "GROUP BY file_extension ORDER BY 2 DESC LIMIT 15", (scan_id,)).fetchall()
            out['top_extensions'] = [{'extension': e, 'files': n} for e, n in exts]
            if (scans[0]['file_count'] or 0) <= _BYTES_BREAKDOWN_MAX_FILES:
                out['total_bytes'] = conn.execute(
                    "SELECT coalesce(sum(size),0) FROM files WHERE scan_id = ? AND type = 'file'",
                    (scan_id,)).fetchone()[0]
            hosts = conn.execute(
                "SELECT DISTINCT remote FROM files WHERE scan_id = ? LIMIT 3", (scan_id,)).fetchall()
            out['hosts'] = [h for (h,) in hosts if h]
        return out
    finally:
        conn.close()


def _filtered_rows(conn, table: str, label: str, filters: Dict[str, Any],
                   text: Optional[str] = None, text_columns=(), order: Optional[str] = None):
    cols = _columns(conn, table)
    unknown = [k for k in filters if k not in cols]
    clauses, args = [], []
    for k, v in filters.items():
        if k in cols and v not in (None, ''):
            clauses.append(f'"{k}" = ?')
            args.append(v)
    if text:
        likes = [f'"{c}" LIKE ?' for c in text_columns if c in cols]
        if likes:
            clauses.append('(' + ' OR '.join(likes) + ')')
            args += [f'%{text}%'] * len(likes)
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    total = conn.execute(f'SELECT count(*) FROM "{table}" {where}', args).fetchone()[0]
    order_by = f'ORDER BY "{order}" DESC' if order in cols else ''
    rows = conn.execute(f'SELECT * FROM "{table}" {where} {order_by} LIMIT {MAX_ROWS}', args).fetchall()
    records = [{'_labels': [label], **dict(zip(cols, r))} for r in rows]
    return records, total, unknown


def list_collections(ctx, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    conn = _connect(ctx)
    if conn is None:
        return dict(_NO_INDEX)
    try:
        if 'collections' not in _tables(conn):
            return _not_profiled("Collections")
        records, total, unknown = _filtered_rows(conn, 'collections', 'Collection', filters or {},
                                                 order='updated_at')
        out = {"status": "success", "collections": records, "total": total}
        if unknown:
            out['note'] = f"Ignored filters this index doesn't have: {', '.join(unknown)}."
        return out
    finally:
        conn.close()


def get_collection(ctx, id: str) -> Dict[str, Any]:  # noqa: A002 - the tool's parameter name
    conn = _connect(ctx)
    if conn is None:
        return dict(_NO_INDEX)
    try:
        if 'collections' not in _tables(conn):
            return _not_profiled("Collections")
        records, _, _ = _filtered_rows(conn, 'collections', 'Collection', {'id': id})
        if not records:
            return {"status": "error", "error": f"No collection with id {id!r}."}
        return {"status": "success", "collection": records[0]}
    finally:
        conn.close()


def search_datasets(ctx, query: Optional[str] = None, profile: Optional[str] = None,
                    owner: Optional[str] = None, project: Optional[str] = None,
                    date_from: Optional[float] = None, date_to: Optional[float] = None) -> Dict[str, Any]:
    """Candidate and confirmed datasets (Profile's data_objects)."""
    conn = _connect(ctx)
    if conn is None:
        return dict(_NO_INDEX)
    try:
        if 'data_objects' not in _tables(conn):
            return _not_profiled("Datasets")
        filters = {'pattern_name': profile, 'owner': owner, 'project': project}
        records, total, unknown = _filtered_rows(
            conn, 'data_objects', 'DataObject', {k: v for k, v in filters.items() if v},
            text=query, text_columns=('root_path', 'pattern_name', 'id'), order='updated_at')
        if date_from is not None or date_to is not None:
            lo, hi = float(date_from or 0), float(date_to or 1e12)
            records = [r for r in records if lo <= float(r.get('created_at') or 0) <= hi]
        out = {"status": "success", "datasets": records, "total": total}
        if unknown:
            out['note'] = (f"This index has no {', '.join(unknown)} facet yet "
                           "(owner/project come with the collections table); those filters were ignored.")
        return out
    finally:
        conn.close()


def unclaimed_summary(ctx, scan_id: Optional[str] = None) -> Dict[str, Any]:
    """Files no dataset claims, by extension: what a new profile should cover."""
    conn = _connect(ctx)
    if conn is None:
        return dict(_NO_INDEX)
    try:
        if 'object_members' not in _tables(conn):
            return _not_profiled("Claimed / unclaimed counts")
        if not scan_id:
            row = conn.execute("SELECT id FROM scans ORDER BY started DESC LIMIT 1").fetchone()
            if not row:
                return {"status": "success", "extensions": [], "note": "No scans yet."}
            scan_id = row[0]
        rows = conn.execute(
            "SELECT f.file_extension, count(*), coalesce(sum(f.size),0) FROM files f "
            "LEFT JOIN object_members m ON m.file_path = f.path "
            "WHERE f.scan_id = ? AND f.type = 'file' AND m.file_path IS NULL "
            "GROUP BY f.file_extension ORDER BY 2 DESC LIMIT 25", (scan_id,)).fetchall()
        return {"status": "success", "scan_id": scan_id,
                "extensions": [{'extension': e or '(none)', 'files': n, 'bytes': b} for e, n, b in rows]}
    finally:
        conn.close()
