from __future__ import annotations
from typing import Dict, List, Tuple, Iterable

from .path_utils import parse_remote_path, parent_remote_path


def _parent_of(path: str) -> str:
    try:
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


def _name_of(path: str) -> str:
    try:
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


def build_complete_folder_hierarchy(rows: List[Dict], folder_rows: List[Dict], scan: Dict) -> List[Dict]:
    """
    Build a complete set of folder rows for a scan, ensuring all intermediate folders exist.
    - rows: file rows (each may have 'folder' field)
    - folder_rows: explicit folder rows captured by scanning or indexing
    - scan: scan metadata dict; uses scan['path'] as the base to stop walking up

    Returns: enhanced list of folder rows where each element has keys:
        - path, name, parent, parent_name
    Ensures uniqueness (no duplicate (path,parent) pairs) and handles both local and remote paths.
    """
    scan_base = (scan or {}).get('path') or ''

    # Track nodes and explicit parent-child relationships
    folder_nodes = set()  # set[str]
    folder_edges = set()  # set[Tuple[str,str]] (parent, child)

    def _walk_to_base(pth: str) -> Iterable[Tuple[str, str]]:
        seenp = set()
        curp = pth
        while curp and (curp not in seenp):
            seenp.add(curp)
            par = _parent_of(curp)
            if not par or par == curp:
                break
            yield (par, curp)
            if scan_base and par == scan_base:
                break
            curp = par

    # Seed from provided folder_rows
    for fr in list(folder_rows or []):
        child = (fr.get('path') or '').strip()
        if not child:
            continue
        parent = (fr.get('parent') or _parent_of(child))
        folder_nodes.add(child)
        if parent:
            folder_nodes.add(parent)
            folder_edges.add((parent, child))
            for (gp, pth) in _walk_to_base(parent):
                folder_nodes.add(gp); folder_nodes.add(pth)
                folder_edges.add((gp, pth))

    # Add ancestors for each file's folder
    for r in rows or []:
        fld = (r.get('folder') or '').strip()
        if not fld:
            continue
        folder_nodes.add(fld)
        par = _parent_of(fld)
        if par:
            folder_nodes.add(par)
            folder_edges.add((par, fld))
            for (gp, pth) in _walk_to_base(par):
                folder_nodes.add(gp); folder_nodes.add(pth)
                folder_edges.add((gp, pth))

    # Build deduplicated folder rows
    new_folder_rows: List[Dict] = []
    for node in sorted(folder_nodes):
        pn = _parent_of(node)
        new_folder_rows.append({
            'path': node,
            'name': _name_of(node),
            'parent': pn,
            'parent_name': _name_of(pn) if pn else ''
        })
    for (par, child) in sorted(folder_edges):
        new_folder_rows.append({
            'path': child,
            'name': _name_of(child),
            'parent': par,
            'parent_name': _name_of(par) if par else ''
        })
    seen_fp = set()
    dedup: List[Dict] = []
    for fr in new_folder_rows:
        key = (fr.get('path'), fr.get('parent'))
        if key in seen_fp:
            continue
        seen_fp.add(key)
        dedup.append(fr)
    return dedup
