"""Telemetry data loader for hydrating last_scan info from SQLite on startup.

This module provides best-effort loading of telemetry.last_scan from the
path index SQLite database to restore session state across restarts.
"""

import json
from typing import Optional, Dict, Any


def load_last_scan_from_sqlite() -> Optional[Dict[str, Any]]:
    """Load telemetry.last_scan from SQLite settings table.

    Returns:
        dict with last scan info, or None if not found or on error
    """
    try:
        from . import path_index_sqlite as pix
        from . import migrations as _migs

        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            row = cur.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("telemetry.last_scan",)
            ).fetchone()

            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    return None
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return None
