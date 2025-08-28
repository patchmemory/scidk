from __future__ import annotations
from typing import Dict, Tuple


def parse_remote_path(s: str) -> Dict:
    """Parse an rclone-style remote path "remote:folder/sub".
    Returns a dict with keys:
      - is_remote: bool
      - remote_id: 'remote:' or None
      - remote_name: 'remote' or None
      - rel: relative path under remote (no leading slash)
      - parts: list of segments of rel
      - is_root: True when rel is empty
      - base_folder: first segment or remote_name if at root
      - base_path: remote_id if at root else remote_id+first-segment
    For non-remote inputs, returns { is_remote: False, path: s }.
    """
    try:
        if not s:
            return {"is_remote": False, "path": s}
        if ':' in s:
            i = s.index(':')
            # rclone remote is the token before the first ':' if colon comes before any slash
            j = s.find('/')
            if j == -1 or i < j:
                remote_id = s[:i+1]
                remote_name = remote_id.rstrip(':')
                rel = s[i+1:].lstrip('/')
                parts = [p for p in rel.split('/') if p]
                is_root = len(parts) == 0
                base_folder = parts[0] if parts else remote_name
                base_path = remote_id if is_root else f"{remote_id}{parts[0]}"
                return {
                    "is_remote": True,
                    "remote_id": remote_id,
                    "remote_name": remote_name,
                    "rel": rel,
                    "parts": parts,
                    "is_root": is_root,
                    "base_folder": base_folder,
                    "base_path": base_path,
                }
    except Exception:
        pass
    return {"is_remote": False, "path": s}


def join_remote_path(remote_id: str, rel: str) -> str:
    rel = (rel or '').lstrip('/')
    return remote_id if not rel else (remote_id + rel if remote_id.endswith(':') else remote_id.rstrip('/') + '/' + rel)


def parent_remote_path(s: str) -> str:
    info = parse_remote_path(s)
    if info.get('is_remote'):
        parts = info.get('parts') or []
        remote_id = info.get('remote_id') or ''
        if not parts:
            return remote_id
        if len(parts) == 1:
            return remote_id
        return remote_id + '/'.join(parts[:-1])
    try:
        # local or mounted path
        from pathlib import Path
        return str(Path(s).parent)
    except Exception:
        return ''
