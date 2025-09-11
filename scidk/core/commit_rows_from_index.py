from __future__ import annotations
from typing import Dict, List, Tuple

from . import path_index_sqlite as pix
from .folder_hierarchy import build_complete_folder_hierarchy


def _parent(path: str) -> str:
    try:
        from .path_utils import parse_remote_path, parent_remote_path
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
        from .path_utils import parse_remote_path
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


def build_rows_for_scan_from_index(scan_id: str, scan: Dict, include_hierarchy: bool = True) -> Tuple[List[Dict], List[Dict]]:
    """Shared builder used by endpoints and background tasks.

    Returns rows (files) and folder_rows (folders). If include_hierarchy is True,
    enhances folder_rows with missing ancestors relative to scan['path'].
    """
    conn = pix.connect()
    pix.init_db(conn)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT path, parent_path, name, depth, type, size, modified_time, file_extension, mime_type FROM files WHERE scan_id = ?",
            (scan_id,)
        )
        items = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rows: List[Dict] = []
    folder_rows: List[Dict] = []
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
                'checksum': None,
                'path': p,
                'filename': name or _name(p),
                'extension': ext or '',
                'size_bytes': int(size or 0),
                'created': 0.0,
                'modified': float(mtime or 0.0),
                'mime_type': mime,
                'folder': par,
                'parent': par,
                'parent_in_scan': True,
                'interps': [],
            })

    if include_hierarchy:
        try:
            folder_rows = build_complete_folder_hierarchy(rows, folder_rows, scan)
        except Exception:
            # Best effort; return existing folder_rows on error
            pass

    return rows, folder_rows
