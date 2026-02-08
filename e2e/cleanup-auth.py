#!/usr/bin/env python3
"""
Cleanup script to disable all authentication in the E2E test database.
This ensures auth state doesn't persist across test runs.
"""
import sqlite3
import sys
from pathlib import Path

def cleanup_auth(db_path='scidk_settings.db'):
    """Disable all auth in the settings database."""
    db_file = Path(db_path)
    if not db_file.exists():
        print(f'[cleanup-auth] DB not found: {db_path}')
        return

    try:
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()

        # Disable all users in multi-user auth system
        cur.execute("UPDATE auth_users SET enabled = 0 WHERE enabled = 1")
        users_disabled = cur.rowcount

        # Disable legacy single-user auth
        cur.execute("UPDATE auth_config SET enabled = 0 WHERE enabled = 1")
        legacy_disabled = cur.rowcount

        conn.commit()
        conn.close()

        print(f'[cleanup-auth] Disabled {users_disabled} auth users and {legacy_disabled} legacy auth configs')
        return True
    except Exception as e:
        print(f'[cleanup-auth] Error: {e}')
        return False

if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'scidk_settings.db'
    success = cleanup_auth(db_path)
    sys.exit(0 if success else 1)
