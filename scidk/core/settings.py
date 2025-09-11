import sqlite3
import json
from datetime import datetime
from typing import Set


class InterpreterSettings:
    """Minimal settings persistence for interpreter toggles using SQLite.
    If DB is unavailable, caller can ignore persistence errors.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = sqlite3.connect(db_path)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.init_tables()

    def init_tables(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS interpreter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.db.commit()

    def save_enabled_interpreters(self, enabled_set: Set[str]):
        payload = json.dumps(sorted(list(enabled_set)))
        now = datetime.utcnow().isoformat()
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
