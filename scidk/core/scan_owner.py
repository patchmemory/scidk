"""Who started a scan, so a non-admin can delete their own scans and only those.

Its own small table rather than a key in each writer's ``extra_json``: five
places create scans, each building its own dict, and several rebuild scans
from SQLite without carrying unknown keys. One call per creation site is less
to keep in step. Lives in files.db next to ``scans``; owns its DDL
(``migrations.py`` doesn't, see the files-table note there).
"""
from __future__ import annotations

import time
from typing import Optional


def current_username() -> Optional[str]:
    """The logged-in user for this request, or None (auth off, or no request)."""
    try:
        from flask import g, has_request_context
        if has_request_context():
            return getattr(g, 'scidk_user', None) or None
    except Exception:
        pass
    return None


def _connect():
    from . import path_index_sqlite as pix
    conn = pix.connect()
    conn.execute("CREATE TABLE IF NOT EXISTS scan_owners ("
                 " scan_id TEXT PRIMARY KEY, username TEXT NOT NULL, created REAL)")
    return conn


def record(scan_id: Optional[str], username: Optional[str]) -> None:
    """Best-effort: a scan must never fail because its owner couldn't be noted."""
    if not scan_id or not username:
        return
    try:
        conn = _connect()
        try:
            conn.execute("INSERT OR REPLACE INTO scan_owners(scan_id, username, created) VALUES (?,?,?)",
                         (scan_id, username, time.time()))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def owner_of(scan_id: str) -> Optional[str]:
    try:
        conn = _connect()
        try:
            row = conn.execute("SELECT username FROM scan_owners WHERE scan_id=?", (scan_id,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    return row[0] if row else None


def forget(scan_id: str) -> None:
    try:
        conn = _connect()
        try:
            conn.execute("DELETE FROM scan_owners WHERE scan_id=?", (scan_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
