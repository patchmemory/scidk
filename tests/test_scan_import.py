"""Importing a scanner snapshot into files.db (merge_scan_results), on the demo fixture.

Covers the option A import normalisation (dev/SCANNER_SWITCH.md R1, R2):
the scanner's interpreted_as is a hint and lands in interpreter_hint, and
remote gets the host label commit keys File nodes on.
"""
import sqlite3
import socket

import pytest

from scidk.core import path_index_sqlite as pix
from scidk.core.scanner_subprocess import merge_scan_results


@pytest.fixture
def imported(demo_files_db, tmp_path, monkeypatch):
    snap_db, scan_id = demo_files_db
    files_db = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(files_db))
    task = {'provider_id': 'local_fs', 'root_id': '/'}
    merged = merge_scan_results(str(snap_db), str(files_db), scan_id, task)
    return snap_db, files_db, scan_id, merged


def _one(db, sql, *args):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, args).fetchone()


def test_hints_move_to_interpreter_hint(imported):
    snap_db, files_db, scan_id, _ = imported
    hinted = _one(snap_db, "SELECT count(*) FROM files WHERE scan_id=? AND interpreted_as IS NOT NULL", scan_id)[0]
    assert hinted > 0, 'the demo tree should give the scanner something to hint'
    assert _one(files_db, "SELECT count(*) FROM files WHERE scan_id=? AND interpreter_hint IS NOT NULL", scan_id)[0] == hinted
    assert _one(files_db, "SELECT count(*) FROM files WHERE scan_id=? AND interpreted_as IS NOT NULL", scan_id)[0] == 0
    assert _one(files_db, "SELECT count(*) FROM files WHERE scan_id=? AND interpretation_json IS NOT NULL", scan_id)[0] == 0


def test_remote_is_the_committed_host(imported):
    _, files_db, scan_id, merged = imported
    hosts = {r for (r,) in sqlite3.connect(files_db).execute(
        "SELECT DISTINCT remote FROM files WHERE scan_id=?", (scan_id,))}
    assert hosts == {f'local:{socket.gethostname()}'}
    assert merged['file_count'] > 0


def test_merge_is_idempotent(imported):
    snap_db, files_db, scan_id, merged = imported
    merge_scan_results(str(snap_db), str(files_db), scan_id, {'provider_id': 'local_fs', 'root_id': '/'})
    n = _one(files_db, "SELECT count(*) FROM files WHERE scan_id=?", scan_id)[0]
    assert n == merged['file_count'] + merged['folder_count']


def test_commit_rows_ignore_hints(imported, monkeypatch):
    _, _, scan_id, _ = imported
    from scidk.core.commit_rows_from_index import build_rows_for_scan_from_index
    rows, _folders = build_rows_for_scan_from_index(scan_id, {'path': '/'}, include_hierarchy=False)
    assert rows and not any(r['interps'] or r['interpreted_as'] for r in rows)


def test_legacy_hint_in_interpreted_as_is_not_a_run(imported):
    """Rows merged before interpreter_hint still carry hints in interpreted_as."""
    _, files_db, scan_id, _ = imported
    with sqlite3.connect(files_db) as conn:
        conn.execute("UPDATE files SET interpreted_as = interpreter_hint, interpreter_hint = NULL WHERE scan_id=?", (scan_id,))
    from scidk.core.commit_rows_from_index import build_rows_for_scan_from_index
    rows, _ = build_rows_for_scan_from_index(scan_id, {'path': '/'}, include_hierarchy=False)
    assert not any(r['interps'] for r in rows)


def test_init_db_adds_hint_column_to_an_old_files_table(tmp_path, monkeypatch):
    db = tmp_path / 'old.db'
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE files (path TEXT NOT NULL, parent_path TEXT, name TEXT NOT NULL, depth INTEGER NOT NULL,"
                     " type TEXT NOT NULL, size INTEGER NOT NULL, modified_time REAL, file_extension TEXT, mime_type TEXT,"
                     " etag TEXT, hash TEXT, remote TEXT, scan_id TEXT, extra_json TEXT)")
    monkeypatch.setenv('SCIDK_DB_PATH', str(db))
    pix.init_db()
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(files)")}
    assert 'interpreter_hint' in cols


def test_import_into_fresh_files_db_leaves_the_snapshot_intact(demo_files_db, tmp_path, monkeypatch):
    """A fresh files.db has no scans/scan_items tables until migrations run. The
    unqualified table names used to resolve to the attached snapshot instead:
    the import deleted the snapshot's scan rows and wrote none to files.db."""
    import hashlib
    import shutil
    snap_src, scan_id = demo_files_db
    snap = tmp_path / 'snap.db'
    shutil.copy(snap_src, snap)
    before = hashlib.sha256(snap.read_bytes()).hexdigest()
    files_db = tmp_path / 'fresh.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(files_db))
    merge_scan_results(str(snap), str(files_db), scan_id, {'provider_id': 'local_fs', 'root_id': '/'})
    assert hashlib.sha256(snap.read_bytes()).hexdigest() == before
    assert _one(files_db, "SELECT status FROM scans WHERE id=?", scan_id) == ('completed',)
    assert _one(files_db, "SELECT count(*) FROM scan_items WHERE scan_id=?", scan_id)[0] == \
        _one(snap, "SELECT count(*) FROM scan_items WHERE scan_id=?", scan_id)[0] > 0
