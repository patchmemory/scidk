"""Service for building and caching per-scan filesystem indexes for snapshot navigation.

This module extracts the scan index building logic from app.py to keep the application
initialization lean. It builds hierarchical folder structures from scan data.
"""

from pathlib import Path as _P


def get_or_build_scan_index(app, scan_id: str):
    """Build or fetch per-scan filesystem index for snapshot navigation.

    Args:
        app: Flask application instance with extensions['scidk'] configured
        scan_id: Unique identifier for the scan

    Returns:
        dict with keys: folder_info, children_folders, children_files, roots
        Returns None if scan_id not found in scans registry
    """
    cache = app.extensions['scidk'].setdefault('scan_fs', {})
    if scan_id in cache:
        return cache[scan_id]

    scans = app.extensions['scidk'].get('scans', {})
    s = scans.get(scan_id)
    if not s:
        return None

    checksums = s.get('checksums') or []
    ds_map = app.extensions['scidk']['graph'].datasets  # checksum -> dataset

    from ..core.path_utils import parse_remote_path, parent_remote_path

    folder_info = {}
    children_files = {}

    def ensure_complete_parent_chain(path_str: str):
        """Ensure all parent folders exist in folder_info for any given path"""
        if not path_str or path_str in folder_info:
            return

        info = parse_remote_path(path_str)
        if info.get('is_remote'):
            parent = parent_remote_path(path_str)
            name = (info.get('parts')[-1] if info.get('parts') else info.get('remote_name') or path_str)
        else:
            try:
                p = _P(path_str)
                parent = str(p.parent)
                name = p.name or path_str
            except Exception:
                parent = ''
                name = path_str

        folder_info[path_str] = {
            'path': path_str,
            'name': name,
            'parent': parent,
        }

        if parent and parent != path_str:
            ensure_complete_parent_chain(parent)

    # Seed scan base path (stable roots even on empty scans)
    try:
        base_path = s.get('path') or ''
        if base_path:
            ensure_complete_parent_chain(base_path)
    except Exception:
        pass

    # Process files and ensure their parent chains exist
    for ch in checksums:
        d = ds_map.get(ch)
        if not d:
            continue
        file_path = d.get('path')
        if not file_path:
            continue

        info = parse_remote_path(file_path)
        if info.get('is_remote'):
            parent = parent_remote_path(file_path)
            filename = (info.get('parts')[-1] if info.get('parts') else info.get('remote_name') or file_path)
        else:
            try:
                p = _P(file_path)
                parent = str(p.parent)
                filename = p.name or file_path
            except Exception:
                parent = ''
                filename = file_path

        file_entry = {
            'id': d.get('id'),
            'path': file_path,
            'filename': d.get('filename') or filename,
            'extension': d.get('extension'),
            'size_bytes': int(d.get('size_bytes') or 0),
            'modified': float(d.get('modified') or 0),
            'mime_type': d.get('mime_type'),
            'checksum': d.get('checksum'),
        }
        children_files.setdefault(parent, []).append(file_entry)

        if parent:
            ensure_complete_parent_chain(parent)

    # Process explicitly recorded folders
    for f in (s.get('folders') or []):
        path = f.get('path')
        if path:
            ensure_complete_parent_chain(path)

    # Build children_folders map
    children_folders = {}
    for fpath, info in folder_info.items():
        par = info.get('parent')
        if par and par in folder_info:
            children_folders.setdefault(par, []).append(fpath)

    # Find actual roots
    roots = sorted([fp for fp, info in folder_info.items()
                    if not info.get('parent') or info.get('parent') not in folder_info])

    # Prefer scan base as visible root and drop its ancestors
    try:
        base_path = s.get('path') or ''
        if base_path and base_path in folder_info:
            if base_path not in roots:
                roots.append(base_path)
            def _is_ancestor(candidate: str, child: str) -> bool:
                if not candidate or candidate == child:
                    return False
                cinf = parse_remote_path(candidate)
                chinf = parse_remote_path(child)
                if chinf.get('is_remote') and cinf.get('is_remote'):
                    return child.startswith(candidate.rstrip('/') + '/')
                try:
                    return str(_P(child)).startswith(str(_P(candidate)) + '/')
                except Exception:
                    return False
            roots = [r for r in roots if not _is_ancestor(r, base_path) or r == base_path]
            roots = sorted(list(dict.fromkeys(roots)))
    except Exception:
        pass

    # Sort children deterministically
    for k in list(children_folders.keys()):
        children_folders[k].sort(key=lambda p: folder_info.get(p, {}).get('name', '').lower())
    for k in list(children_files.keys()):
        children_files[k].sort(key=lambda f: (f.get('filename') or '').lower())

    idx = {
        'folder_info': folder_info,
        'children_folders': children_folders,
        'children_files': children_files,
        'roots': roots,
    }
    cache[scan_id] = idx
    return idx
