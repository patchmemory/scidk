"""Rclone mounts metadata loader.

This module rehydrates rclone mount metadata from SQLite on startup.
Note: Process handles are not restored (set to None).
"""

import json
from typing import Dict, List, Any


def rehydrate_rclone_mounts() -> Dict[str, Dict[str, Any]]:
    """Load rclone mount metadata from SQLite provider_mounts table.

    Returns:
        dict mapping mount_id -> mount metadata dict
        Returns empty dict on error
    """
    try:
        from . import path_index_sqlite as pix
        from . import migrations as _migs

        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, provider, root, created, status, extra_json FROM provider_mounts WHERE provider='rclone'"
            )
            rows = cur.fetchall() or []

            mounts = {}
            for (mid, provider, remote, created, status_persisted, extra) in rows:
                try:
                    extra_obj = json.loads(extra) if extra else {}
                except Exception:
                    extra_obj = {}

                mounts[mid] = {
                    'id': mid,
                    'name': mid,
                    'remote': remote,
                    'subpath': extra_obj.get('subpath'),
                    'path': extra_obj.get('path'),
                    'read_only': extra_obj.get('read_only'),
                    'started_at': created,
                    'process': None,  # Process handles not restored
                    'pid': None,
                    'log_file': extra_obj.get('log_file'),
                }

            return mounts
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return {}
