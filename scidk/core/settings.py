import sqlite3
import json
from datetime import datetime
from typing import Set, Dict, Optional
import os


class InterpreterSettings:
    """Minimal settings persistence for interpreter toggles using SQLite.
    If DB is unavailable, caller can ignore persistence errors.

    The connection is opened on first use, not in __init__. This instance is
    stored on app.extensions by create_app(), and gunicorn runs create_app() in
    the master process under --preload: an open SQLite handle there would be
    inherited by all forked workers, which would then share one file descriptor
    and one set of WAL locks. Opening lazily means each worker gets its own
    connection after the fork.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db = None

    @property
    def db(self) -> sqlite3.Connection:
        """Open (and remember) this process's connection on first access."""
        if self._db is None:
            self._db = sqlite3.connect(self.db_path)
            self._db.execute('PRAGMA journal_mode=WAL;')
            self.init_tables()
        return self._db

    def close(self):
        """Close this process's connection, if one is open.

        Called at the end of create_app() so the gunicorn master holds nothing
        across fork. The next attribute access reopens lazily, so the object
        stays usable in workers and in-process.
        """
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

    def init_tables(self):
        # Normally reached from the db property, which has already assigned
        # _db. Tolerate a direct external call by opening first.
        if self._db is None:
            self.db  # noqa: B018 — opens the connection and calls back in
            return
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS interpreter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._db.commit()

    def save_enabled_interpreters(self, enabled_set: Set[str]):
        payload = json.dumps(sorted(list(enabled_set)))
        from datetime import timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        self.db.execute(
            "INSERT OR REPLACE INTO interpreter_settings(key, value, updated_at) VALUES (?, ?, ?)",
            ("enabled_interpreters", payload, now),
        )
        self.db.commit()

    def load_enabled_interpreters(self) -> Set[str]:
        try:
            cur = self.db.execute(
                "SELECT value FROM interpreter_settings WHERE key = 'enabled_interpreters'"
            )
            row = cur.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                return set(data)
        except Exception:
            return set()
        return set()


# Global settings helpers (use same table as InterpreterSettings)
def _get_db_path() -> str:
    """Get path to settings database."""
    return os.environ.get('SCIDK_DB_PATH', os.path.join(os.getcwd(), 'scidk.db'))


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a setting value from the database.

    Args:
        key: Setting key
        default: Default value if key not found

    Returns:
        Setting value, or default if not found
    """
    try:
        db_path = _get_db_path()
        db = sqlite3.connect(db_path)
        cur = db.execute(
            "SELECT value FROM interpreter_settings WHERE key = ?",
            (key,)
        )
        row = cur.fetchone()
        db.close()
        if row and row[0] is not None:
            return row[0]
    except Exception:
        pass
    return default


def set_setting(key: str, value: str):
    """Set a setting value in the database.

    Args:
        key: Setting key
        value: Setting value
    """
    db_path = _get_db_path()
    db = sqlite3.connect(db_path)
    # Ensure table exists
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS interpreter_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    from datetime import timezone
    now = datetime.now(tz=timezone.utc).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO interpreter_settings(key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, now),
    )
    db.commit()
    db.close()


def get_settings_by_prefix(prefix: str) -> Dict[str, str]:
    """Get all settings with a given prefix.

    Args:
        prefix: Key prefix to filter by

    Returns:
        Dict mapping keys to values
    """
    try:
        db_path = _get_db_path()
        db = sqlite3.connect(db_path)
        cur = db.execute(
            "SELECT key, value FROM interpreter_settings WHERE key LIKE ?",
            (prefix + '%',)
        )
        results = {row[0]: row[1] for row in cur.fetchall()}
        db.close()
        return results
    except Exception:
        return {}
