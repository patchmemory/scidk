from __future__ import annotations
from typing import Any, Dict, Optional


class FSIndexService:
    """
    SQLite-backed filesystem index browsing service.

    Provides a stable, index-backed listing of direct children under a parent path
    for a given scan, with server-side pagination and simple filters.

    Contract:
      - Ordering: type DESC, name ASC
      - Pagination token: opaque offset string (stable for MVP)
      - Filters: type (file|folder), extension (normalized lowercase, includes leading dot if provided)
    """

    def __init__(self, app):
        self.app = app

    def browse_children(
        self,
        scan_id: str,
        parent_path: Optional[str],
        page_size: int = 100,
        next_page_token: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from flask import jsonify  # lazy import to avoid hard dependency at import time
        from ..core import path_index_sqlite as pix

        # Ensure scan exists (reconstruct from SQLite if missing in memory)
        scan = self.app.extensions['scidk'].get('scans', {}).get(scan_id)
        if not scan:
            try:
                from ..core import path_index_sqlite as pix
                from ..core import migrations as _migs
                import json as _json
                conn = pix.connect()
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    cur.execute("SELECT id, root, started, completed, status, extra_json FROM scans WHERE id = ?", (scan_id,))
                    row = cur.fetchone()
                    if row:
                        sid, root, started, completed, status, extra = row
                        extra_obj = {}
                        try:
                            if extra:
                                extra_obj = _json.loads(extra)
                        except Exception:
                            extra_obj = {}
                        scan = {
                            'id': sid,
                            'path': root,
                            'started': started,
                            'ended': completed,
                            'provider_id': (extra_obj or {}).get('provider_id') or 'local_fs',
                            'host_type': (extra_obj or {}).get('host_type'),
                            'host_id': (extra_obj or {}).get('host_id'),
                            'root_id': (extra_obj or {}).get('root_id') or '/',
                            'root_label': (extra_obj or {}).get('root_label'),
                        }
                        self.app.extensions['scidk'].setdefault('scans', {})[scan_id] = scan
                    else:
                        return jsonify({'error': 'scan not found'}), 404
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                return jsonify({'error': 'scan not found'}), 404

        # Resolve parent path default to scan base path
        req_path = (parent_path or '').strip()
        if req_path == '':
            req_path = str(scan.get('path') or '')

        # Normalize pagination
        try:
            limit = int(page_size)
        except Exception:
            limit = 100
        limit = max(1, min(limit, 1000))

        token_raw = (next_page_token or '').strip()
        try:
            offset = int(token_raw) if token_raw else 0
        except Exception:
            offset = 0

        # Normalize filters
        filters = filters or {}
        ext = (filters.get('extension') or filters.get('ext') or '').strip().lower()
        typ = (filters.get('type') or '').strip().lower()

        where = ["scan_id = ?", "parent_path = ?"]
        params: list[Any] = [scan_id, req_path]
        if ext:
            where.append("file_extension = ?")
            params.append(ext)
        if typ:
            where.append("type = ?")
            params.append(typ)
        where_sql = " AND ".join(where)
        sql = (
            "SELECT path, name, type, size, modified_time, file_extension, mime_type, interpreted_as, interpretation_json "
            f"FROM files WHERE {where_sql} "
            "ORDER BY type DESC, name ASC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([limit + 1, offset])

        try:
            conn = pix.connect(); pix.init_db(conn)
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            try:
                conn.close()  # type: ignore[name-defined]
            except Exception:
                pass

        entries = []
        for r in rows[:limit]:
            path_val, name_val, type_val, size_val, mtime_val, ext_val, mime_val, interp_as, interp_json = r
            entries.append({
                'path': path_val,
                'name': name_val,
                'type': type_val,
                'size': int(size_val or 0),
                'modified': float(mtime_val or 0.0),
                'extension': ext_val or '',
                'mime_type': mime_val,
                'interpreted_as': interp_as,
                'interpretation_json': interp_json,
            })
        next_token = str(offset + limit) if len(rows) > limit else None

        out = {
            'scan_id': scan_id,
            'path': req_path,
            'page_size': limit,
            'entries': entries,
        }
        if next_token is not None:
            out['next_page_token'] = next_token
        return jsonify(out), 200
