from __future__ import annotations
from typing import Dict, List, Tuple


class CommitService:
    """
    Commit pipeline helpers. Centralizes logic for preparing rows for commit
    from either the file index (preferred) or legacy in-memory dataset maps.
    """

    # --- Index-based builder ---
    def build_rows_from_index(self, scan_id: str, scan: Dict, include_hierarchy: bool = True) -> Tuple[List[Dict], List[Dict]]:
        """Build file and folder rows for a scan from the SQLite path index.

        Delegates to core.commit_rows_from_index.build_rows_for_scan_from_index.
        """
        from ..core.commit_rows_from_index import build_rows_for_scan_from_index
        return build_rows_for_scan_from_index(scan_id, scan, include_hierarchy)

    # --- Legacy builder (from in-memory dataset map) ---
    def build_rows_legacy_from_datasets(self, scan: Dict, ds_map: Dict[str, Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Legacy builder used by endpoints when committing from datasets in memory.

        This is a refactor of the function previously defined inside app.create_app().
        Returns (rows, folder_rows).
        """
        from ..core.path_utils import parse_remote_path, parent_remote_path

        checksums = scan.get('checksums') or []

        def _parent_of(p: str) -> str:
            try:
                info = parse_remote_path(p)
                if info.get('is_remote'):
                    return parent_remote_path(p)
            except Exception:
                pass
            from pathlib import Path as __P
            try:
                return str(__P(p).parent)
            except Exception:
                return ''

        def _name_of(p: str) -> str:
            try:
                info = parse_remote_path(p)
                if info.get('is_remote'):
                    parts = info.get('parts') or []
                    if not parts:
                        return info.get('remote_name') or ''
                    return parts[-1]
            except Exception:
                pass
            from pathlib import Path as __P
            try:
                return __P(p).name
            except Exception:
                return p

        def _parent_name_of(p: str) -> str:
            try:
                par = _parent_of(p)
                info = parse_remote_path(par)
                if info.get('is_remote'):
                    parts = info.get('parts') or []
                    if not parts:
                        return info.get('remote_name') or ''
                    return parts[-1]
            except Exception:
                pass
            from pathlib import Path as __P
            try:
                return __P(par).name
            except Exception:
                return par

        # Precompute folders observed in this scan (parents of files)
        folder_set = set()
        for ch in checksums:
            dtmp = ds_map.get(ch)
            if not dtmp:
                continue
            folder_set.add(_parent_of(dtmp.get('path') or ''))

        rows: List[Dict] = []
        for ch in checksums:
            d = ds_map.get(ch)
            if not d:
                continue
            parent = _parent_of(d.get('path') or '')
            interps = list((d.get('interpretations') or {}).keys())
            folder_path = parent
            folder_name = _name_of(folder_path) if folder_path else ''
            folder_parent = _parent_of(folder_path) if folder_path else ''
            folder_parent_name = _parent_name_of(folder_path) if folder_parent else ''
            rows.append({
                'checksum': d.get('checksum'),
                'path': d.get('path'),
                'filename': d.get('filename'),
                'extension': d.get('extension'),
                'size_bytes': int(d.get('size_bytes') or 0),
                'created': float(d.get('created') or 0),
                'modified': float(d.get('modified') or 0),
                'mime_type': d.get('mime_type'),
                'folder': folder_path,
                'folder_name': folder_name,
                'folder_parent': folder_parent,
                'folder_parent_name': folder_parent_name,
                'parent_in_scan': bool(folder_parent and (folder_parent in folder_set)),
                'interps': interps,
            })

        folder_rows: List[Dict] = []
        for f in (scan.get('folders') or []):
            folder_rows.append({
                'path': f.get('path'),
                'name': f.get('name'),
                'parent': f.get('parent'),
                'parent_name': f.get('parent_name'),
            })

        # Enhance with complete hierarchy
        try:
            from ..core.folder_hierarchy import build_complete_folder_hierarchy
            folder_rows = build_complete_folder_hierarchy(rows, folder_rows, scan)
        except Exception:
            pass

        return rows, folder_rows
