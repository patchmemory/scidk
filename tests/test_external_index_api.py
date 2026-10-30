"""Read-only Scans browser over an external files.db (SCIDK_EXTERNAL_INDEX_DB)."""
import hashlib
import json
import os
import sqlite3

import pytest

from scidk.app import create_app

SCAN = 'scan-1'


def _build(path):
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
        CREATE TABLE scans (id TEXT PRIMARY KEY, root TEXT, started REAL, completed REAL, status TEXT, extra_json TEXT);
        CREATE TABLE scan_progress (scan_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL, updated REAL, PRIMARY KEY (scan_id, metric));
        CREATE TABLE files (path TEXT NOT NULL, parent_path TEXT, name TEXT NOT NULL, depth INTEGER NOT NULL, type TEXT NOT NULL,
            size INTEGER NOT NULL, modified_time REAL, file_extension TEXT, scan_id TEXT);
        CREATE INDEX idx_files_scan_parent ON files(scan_id, parent_path, name);
        CREATE TABLE data_objects (id TEXT PRIMARY KEY, pattern_name TEXT NOT NULL, root_path TEXT NOT NULL, scan_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate', confidence REAL NOT NULL DEFAULT 1.0, file_count INTEGER, total_bytes INTEGER);
    ''')
    conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?)", (SCAN, '/data0/core/atwai', 1.0, 2.0, 'complete', '{}'))
    conn.execute("INSERT INTO scans VALUES (?,?,?,?,?,?)", ('scan-2', '/mnt/old/thing', 1.0, 2.0, 'completed', json.dumps({'file_count': 7})))
    for metric, value in (('files_scanned', 12), ('bytes_scanned', 3000), ('dirs_scanned', 2)):
        conn.execute('INSERT INTO scan_progress VALUES (?,?,?,?)', (SCAN, metric, value, 0))
    for i in range(205):
        conn.execute('INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?)',
                     (f'/data0/core/atwai/f{i:03}.txt', '/data0/core/atwai', f'f{i:03}.txt', 1, 'file', i, 5.0, '.txt', SCAN))
    for pattern, root in (('vevo_ultrasound', '/data0/core/atwai/huang'), ('vevo_ultrasound', '/data0/core/atwai/huang/s1'),
                          ('vevo_ultrasound', '/data0/core/atwai/huangw/s2'), ('vevo_ultrasound', '/data0/core/atwai/hu_ng/s3'),
                          ('vevo_ultrasound', '/data0/core/atwai/huXng/s4')):
        conn.execute("INSERT INTO data_objects (id, pattern_name, root_path, scan_id, file_count, total_bytes) VALUES (?,?,?,?,1,10)",
                     (root, pattern, root, SCAN))
    conn.commit()
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    monkeypatch.delenv('SCIDK_ENCRYPTION_KEY', raising=False)
    db = tmp_path / 'files.db'
    _build(str(db))
    monkeypatch.setenv('SCIDK_EXTERNAL_INDEX_DB', str(db))
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    from scidk.core.auth import get_auth_manager
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])
    uid = auth.create_user('alice', 'password123', role='user')
    client = app.test_client()
    client.set_cookie('scidk_session', auth.create_user_session(uid, 'alice'))
    return db, client, app


def _digest(db):
    return hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns


def test_named_session_and_get_only(index):
    _, c, app = index
    anonymous = app.test_client()
    for route in ('scans', 'browse?scan_id=scan-1', 'datasets?scan_id=scan-1'):
        assert anonymous.get('/api/external-index/' + route).status_code in (401, 403)
    assert c.post('/api/external-index/scans').status_code in (403, 405)


def test_scans_totals_without_counting_files(index):
    _, c, _ = index
    scans = {s['id']: s for s in c.get('/api/external-index/scans').get_json()['scans']}
    assert scans[SCAN]['files'] == 12 and scans[SCAN]['bytes'] == 3000 and scans[SCAN]['share'] == 'atwai'
    assert scans['scan-2']['files'] == 7 and scans['scan-2']['bytes'] is None


def test_browse_pages_one_folder(index):
    _, c, _ = index
    first = c.get('/api/external-index/browse', query_string={'scan_id': SCAN}).get_json()
    assert len(first['entries']) == 200 and first['has_more'] and first['path'] == '/data0/core/atwai'
    second = c.get('/api/external-index/browse', query_string={'scan_id': SCAN, 'offset': first['next_offset']}).get_json()
    assert len(second['entries']) == 5 and not second['has_more']
    assert c.get('/api/external-index/browse', query_string={'scan_id': 'nope'}).status_code == 404


def test_datasets_match_the_folder_or_below_never_a_sibling_prefix(index):
    _, c, _ = index
    got = c.get('/api/external-index/datasets', query_string={'scan_id': SCAN, 'path': '/data0/core/atwai/huang'}).get_json()
    assert [d['root_path'] for d in got['datasets']] == ['/data0/core/atwai/huang', '/data0/core/atwai/huang/s1']
    # LIKE wildcards in the folder name are literal.
    got = c.get('/api/external-index/datasets', query_string={'scan_id': SCAN, 'path': '/data0/core/atwai/hu_ng'}).get_json()
    assert [d['root_path'] for d in got['datasets']] == ['/data0/core/atwai/hu_ng/s3']


def test_file_is_never_written_and_open_is_read_only(index):
    db, c, _ = index
    before = _digest(db)
    for route in ('scans', 'browse?scan_id=scan-1', 'datasets?scan_id=scan-1&path=/data0/core/atwai/huang'):
        assert c.get('/api/external-index/' + route).status_code == 200
    assert _digest(db) == before
    from scidk.web.routes.api_external_index import _open
    conn = _open()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO scans (id) VALUES ('x')")
    finally:
        conn.close()
    assert _digest(db) == before


def test_missing_configuration_is_a_clear_message(index, monkeypatch):
    _, c, _ = index
    monkeypatch.delenv('SCIDK_EXTERNAL_INDEX_DB')
    r = c.get('/api/external-index/scans')
    assert r.status_code == 503 and 'configured' in r.get_json()['error']
    monkeypatch.setenv('SCIDK_EXTERNAL_INDEX_DB', '/nonexistent/files.db')
    assert 'not found' in c.get('/api/external-index/scans').get_json()['error']
