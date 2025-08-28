import sqlite3
import os
from pathlib import Path

from scidk.core import path_index_sqlite as pix


def test_sqlite_schema_and_wal(monkeypatch, tmp_path):
    db_path = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_path))

    # Connect and init
    conn = pix.connect()
    try:
        # Ensure WAL mode
        cur = conn.execute('PRAGMA journal_mode;')
        mode = cur.fetchone()[0].lower()
        assert mode == 'wal'
        # Ensure schema exists
        pix.init_db(conn)
        # Verify table columns
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(files);").fetchall()}
        expected_cols = [
            'path','parent_path','name','depth','type','size','modified_time',
            'file_extension','mime_type','etag','hash','remote','scan_id','extra_json'
        ]
        for c in expected_cols:
            assert c in cols
        # Verify indexes exist (by name or pragma data)
        idx_names = [r[1] for r in conn.execute("PRAGMA index_list('files');").fetchall()]
        assert any('idx_files_scan_parent_name' in n for n in idx_names)
        assert any('idx_files_scan_ext' in n for n in idx_names)
        assert any('idx_files_scan_type' in n for n in idx_names)
    finally:
        conn.close()


essential_row = (
    'remote:bucket/a.txt', 'remote:bucket', 'a.txt', 2, 'file', 123, None, '.txt', 'text/plain', None, None, 'remote', 'scanX', None
)


def test_batch_insert_and_counts(monkeypatch, tmp_path):
    db_path = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_path))

    # Insert a small batch
    total = pix.batch_insert_files([essential_row, essential_row])
    assert total == 2
    # Inspect rows
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert rows == 2
    finally:
        conn.close()
