"""Rclone interpretation settings loader.

This module loads rclone-specific settings from SQLite on startup,
including suggest_mount_threshold and max_files_per_batch.
"""

import os
from typing import Dict


def load_rclone_interpretation_settings(app) -> Dict[str, int]:
    """Load rclone interpretation settings from SQLite with env overrides.

    Args:
        app: Flask application instance to set config on

    Returns:
        dict with 'suggest_mount_threshold' and 'max_files_per_batch'

    Side effects:
        Sets app.config['rclone.interpret.suggest_mount_threshold']
        Sets app.config['rclone.interpret.max_files_per_batch']
    """
    def _env_int(name: str, dflt: int) -> int:
        """Parse integer from environment with fallback."""
        try:
            v = os.environ.get(name)
            return int(v) if v is not None and v != '' else dflt
        except Exception:
            return dflt

    # Environment defaults (can override SQLite)
    suggest_dflt = _env_int('SCIDK_RCLONE_INTERPRET_SUGGEST_MOUNT', 400)
    max_batch_dflt = _env_int('SCIDK_RCLONE_INTERPRET_MAX_FILES', 1000)
    max_batch_dflt = min(max(100, max_batch_dflt), 2000)

    try:
        from . import path_index_sqlite as pix
        from . import migrations as _migs

        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()

            def _get_setting_int(key: str, dflt: int) -> int:
                """Fetch integer setting from SQLite settings table."""
                row = cur.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (key,)
                ).fetchone()
                if row and row[0] not in (None, ''):
                    try:
                        return int(row[0])
                    except Exception:
                        return dflt
                return dflt

            # Load from SQLite, fallback to env defaults
            suggest_mount_threshold = _get_setting_int(
                'rclone.interpret.suggest_mount_threshold',
                suggest_dflt
            )
            max_files_per_batch = _get_setting_int(
                'rclone.interpret.max_files_per_batch',
                max_batch_dflt
            )

            # Clamp max_files_per_batch to sane range
            max_files_per_batch = min(max(100, int(max_files_per_batch)), 2000)

            app.config['rclone.interpret.suggest_mount_threshold'] = int(suggest_mount_threshold)
            app.config['rclone.interpret.max_files_per_batch'] = int(max_files_per_batch)

            return {
                'suggest_mount_threshold': int(suggest_mount_threshold),
                'max_files_per_batch': int(max_files_per_batch),
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        # Defaults if hydration fails
        app.config.setdefault('rclone.interpret.suggest_mount_threshold', 400)
        app.config.setdefault('rclone.interpret.max_files_per_batch', 1000)

        return {
            'suggest_mount_threshold': 400,
            'max_files_per_batch': 1000,
        }
