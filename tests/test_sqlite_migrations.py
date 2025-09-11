import os
import sqlite3
from pathlib import Path

from scidk.app import create_app
from scidk.core import path_index_sqlite as pix


def test_sqlite_migrations_bootstrap(monkeypatch, tmp_path):
    db_path = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_path))

    # App boot should auto-migrate
    app = create_app()
    assert app is not None

    # Connect and verify schema
    conn = pix.connect()
    try:
        # schema_migrations exists and version >= 2
        row = conn.execute('SELECT version FROM schema_migrations LIMIT 1').fetchone()
        assert row is not None
        assert int(row[0]) >= 2

        # Check presence of v1 and v2 tables
        def has_table(name: str) -> bool:
            r = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            return r is not None

        assert has_table('selections')
        assert has_table('selection_items')
        assert has_table('annotations')

        for t in ['scans','scan_items','scan_progress','settings','metrics','logs','background_tasks','directory_cache','provider_mounts']:
            assert has_table(t), f"missing table: {t}"
    finally:
        conn.close()

    # DB file should exist
    assert Path(db_path).exists()
