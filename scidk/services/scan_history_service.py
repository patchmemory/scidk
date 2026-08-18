"""Per-path scan timeline (Task H2).

The Scan drawer's History tab wants a git-style log for one path: when it was
first indexed, every scan that saw it since, every time its size or mtime moved,
and when an interpreter last ran over it.

Nothing recorded that directly. What exists is:

* ``files`` — one row per ``(path, scan_id)``, carrying size, mtime and (since
  H1) ``interpreted_at``. Joined to ``scans`` for the wall-clock time of each
  scan, consecutive rows for one path *are* the timeline.
* ``file_history`` — a size-diff log written by ``apply_basic_change_history``,
  and only from the rclone arm of ``POST /api/scan``. Its ``created``/
  ``modified`` rows duplicate what the ``files`` rows already say, so they are
  not re-emitted; its ``deleted`` rows are the one thing ``files`` cannot
  express — a row that is gone leaves nothing behind — so those are kept.

Every timestamp is epoch seconds, matching ``scans.completed``,
``files.modified_time`` and ``files.interpreted_at``.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

__all__ = ["build_history", "MAX_EVENTS"]

#: A path scanned nightly for a year has ~365 rows. The drawer shows a scroll
#: list, not a full audit, so the response is bounded and says when it truncated.
MAX_EVENTS = 200

#: Folder mode fans out over children; without a cap, asking for the history of
#: a 200k-file directory would build 200k timelines.
MAX_FOLDER_FILES = 50


def _humanize_bytes(n: Optional[float]) -> str:
    size = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}' if unit != 'B' else f'{int(size)} B'
        size /= 1024
    return f'{size} B'


def _scan_detail(extra_json: Optional[str]) -> str:
    """A one-line summary of a scan, from whatever its extra_json recorded."""
    try:
        extra = json.loads(extra_json) if extra_json else {}
    except Exception:
        extra = {}
    bits: List[str] = []
    if extra.get('file_count'):
        bits.append(f"{int(extra['file_count']):,} files")
    if extra.get('provider_id'):
        bits.append(f"provider: {extra['provider_id']}")
    return ' · '.join(bits)


def _rows_for_path(conn, path: str) -> List[tuple]:
    """Every index row for one path, oldest scan first.

    Ordered by when the scan finished rather than by rowid: a rescan of an old
    root can be inserted after a newer scan, and a timeline ordered by insertion
    would show it in the wrong place.
    """
    return conn.execute(
        "SELECT f.scan_id, f.size, f.modified_time, f.interpreted_as, f.interpreted_at,"
        "       f.interpreter_version, s.completed, s.started, s.extra_json "
        "FROM files f LEFT JOIN scans s ON s.id = f.scan_id "
        "WHERE f.path = ? "
        "ORDER BY COALESCE(s.completed, s.started, 0) ASC, f.rowid ASC",
        (path,),
    ).fetchall()


def _events_for_rows(rows: List[tuple], path: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    prev_size = None
    prev_mtime = None

    for idx, (scan_id, size, mtime, interpreted_as, interpreted_at,
              interpreter_version, completed, started, extra_json) in enumerate(rows):
        when = completed or started or 0

        if idx == 0:
            events.append({
                'type': 'first_seen',
                'timestamp': when,
                'scan_id': scan_id,
                'path': path,
                'detail': 'first indexed',
            })
        else:
            events.append({
                'type': 'scanned',
                'timestamp': when,
                'scan_id': scan_id,
                'path': path,
                'detail': _scan_detail(extra_json),
            })
            changes = []
            if prev_size is not None and size is not None and int(prev_size) != int(size):
                changes.append(f'size {_humanize_bytes(prev_size)} → {_humanize_bytes(size)}')
            if prev_mtime and mtime and float(prev_mtime) != float(mtime):
                changes.append('mtime updated')
            if changes:
                events.append({
                    'type': 'changed',
                    'timestamp': when,
                    'scan_id': scan_id,
                    'path': path,
                    'detail': ' · '.join(changes),
                })

        if interpreted_at:
            events.append({
                'type': 'interpreted',
                'timestamp': float(interpreted_at),
                'scan_id': scan_id,
                'path': path,
                'interpreter': interpreted_as,
                'version': interpreter_version,
                'detail': interpreted_as or 'interpreted',
            })

        prev_size = size
        prev_mtime = mtime

    return events


def _deletion_events(conn, paths: List[str]) -> List[Dict[str, Any]]:
    """Deletions, which only ``file_history`` records.

    The other change types there restate what the ``files`` rows already carry,
    so re-emitting them would double every entry in the timeline.
    """
    if not paths:
        return []
    placeholders = ','.join('?' for _ in paths)
    rows = conn.execute(
        "SELECT h.path, h.scan_id, h.previous_size, s.completed, s.started "
        "FROM file_history h LEFT JOIN scans s ON s.id = h.scan_id "
        f"WHERE h.change_type = 'deleted' AND h.path IN ({placeholders})",
        paths,
    ).fetchall()
    return [{
        'type': 'deleted',
        'timestamp': (completed or started or 0),
        'scan_id': scan_id,
        'path': path,
        'detail': f'no longer present ({_humanize_bytes(prev_size)})' if prev_size else 'no longer present',
    } for (path, scan_id, prev_size, completed, started) in rows]


def _child_paths(conn, folder: str, limit: int) -> List[str]:
    rows = conn.execute(
        "SELECT DISTINCT path FROM files WHERE parent_path = ? AND type = 'file' ORDER BY path LIMIT ?",
        (folder, limit),
    ).fetchall()
    return [r[0] for r in rows]


def build_history(conn, path: str, limit: int = MAX_EVENTS) -> Dict[str, Any]:
    """The timeline for ``path``, newest event first.

    When ``path`` names a file, the events are that file's. When it names a
    folder — no row has that exact path, but rows have it as ``parent_path`` —
    the events are those of the files directly inside it, each tagged with its
    own ``path`` so the caller can group them.
    """
    path = (path or '').strip()
    if not path:
        return {'path': path, 'events': [], 'scope': 'none'}

    paths = [path]
    scope = 'file'
    if not conn.execute("SELECT 1 FROM files WHERE path = ? LIMIT 1", (path,)).fetchone():
        children = _child_paths(conn, path, MAX_FOLDER_FILES)
        if not children:
            return {'path': path, 'events': [], 'scope': 'unknown'}
        paths = children
        scope = 'folder'

    events: List[Dict[str, Any]] = []
    for p in paths:
        events.extend(_events_for_rows(_rows_for_path(conn, p), p))
    events.extend(_deletion_events(conn, paths))

    # Newest first. The secondary key keeps a scan and the change it detected —
    # both stamped with the scan's completion time — in a readable order rather
    # than whichever the sort happened to visit first.
    order = {'interpreted': 0, 'changed': 1, 'deleted': 1, 'scanned': 2, 'first_seen': 3}
    events.sort(key=lambda e: (-(e.get('timestamp') or 0), order.get(e['type'], 9)))

    out: Dict[str, Any] = {'path': path, 'scope': scope, 'events': events[:limit]}
    if len(events) > limit:
        out['truncated'] = True
        out['total_events'] = len(events)
    if scope == 'folder':
        out['files'] = paths
    return out
