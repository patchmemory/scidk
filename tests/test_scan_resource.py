"""Files-page scans kept as scan-database Resources, and scan delete (option A).

The snapshot and Resource half of dev/SCANNER_SWITCH.md A3 / A5, on the demo
fixture, plus DELETE /api/scans/<id> no longer orphaning its files rows.
"""
import os
import shutil
import socket
import sqlite3
import time

import pytest

from scidk.app import create_app
from scidk.pipeline import scan_resource
from scidk.pipeline.store import PipelineStore
from tests.conftest import authenticate_test_client

HOST = f'local:{socket.gethostname()}'


@pytest.fixture
def snapshot_copy(demo_files_db, tmp_path):
    db, scan_id = demo_files_db
    copy = tmp_path / 'scidk_scan_task1.db'
    shutil.copy(db, copy)
    return str(copy), scan_id


def test_keep_snapshot_one_per_root(snapshot_copy, tmp_path):
    db, _ = snapshot_copy
    scans = tmp_path / 'scans'
    scans.mkdir()
    first = scan_resource.keep_snapshot(db, str(scans), HOST, '/data/study')
    assert not os.path.exists(db) and os.path.exists(first)
    second_src = tmp_path / 'scidk_scan_task2.db'
    shutil.copy(first, second_src)
    second = scan_resource.keep_snapshot(str(second_src), str(scans), HOST, '/data/study')
    other = scan_resource.snapshot_path(str(scans), HOST, '/data/other')
    assert second == first and other != first
    assert sorted(os.listdir(scans)) == [os.path.basename(first)]
    # self-contained: no WAL sidecar, opens read-only
    with sqlite3.connect(f'file:{first}?mode=ro', uri=True) as conn:
        assert conn.execute('SELECT count(*) FROM files').fetchone()[0] > 0


def test_upsert_creates_then_updates_one_resource(tmp_path):
    settings = str(tmp_path / 'settings.db')
    a = scan_resource.upsert_scan_resource(settings, HOST, '/data/study', '/s/a.db', 'scan-1', 10, 2)
    b = scan_resource.upsert_scan_resource(settings, HOST, '/data/study', '/s/a.db', 'scan-2', 12, 2)
    c = scan_resource.upsert_scan_resource(settings, HOST, '/data/other', '/s/b.db', 'scan-3', 1, 1)
    sources = PipelineStore(settings).list_sources()
    assert a['id'] == b['id'] != c['id'] and len(sources) == 2
    assert b['plugin_type'] == 'scan_db'
    assert b['source_path'] == {'source_path': '/s/a.db', 'host': HOST, 'root': '/data/study',
                                'scan_id': 'scan-2', 'origin': 'files_page'}
    assert b['last_run_summary']['file_count'] == 12


def test_files_page_scan_leaves_a_snapshot_and_a_resource(demo_tree, tmp_path, monkeypatch):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    scan_dir = tmp_path / 'scans'
    monkeypatch.setenv('SCIDK_SCAN_DB_DIR', str(scan_dir))
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    client = authenticate_test_client(app.test_client(), app)

    r = client.post('/api/tasks', json={'type': 'scan', 'path': str(demo_tree), 'recursive': True,
                                        'provider_id': 'local_fs', 'root_id': '/'})
    assert r.status_code == 202, r.get_json()
    task_id = r.get_json()['task_id']
    for _ in range(120):
        task = client.get(f'/api/tasks/{task_id}').get_json()
        if task.get('status') in ('completed', 'error', 'canceled'):
            break
        time.sleep(0.25)
    assert task['status'] == 'completed', task
    assert 'not kept' not in task['status_message'] and 'not recorded' not in task['status_message']

    snap = task['snapshot_path']
    assert os.path.dirname(snap) == str(scan_dir) and os.listdir(scan_dir) == [os.path.basename(snap)]
    sources = PipelineStore(app.config['SCIDK_SETTINGS_DB']).list_sources()
    assert [s['id'] for s in sources] == [task['resource_id']]
    assert sources[0]['source_path']['source_path'] == snap
    assert sources[0]['source_path']['scan_id'] == task['scan_id']

    listed = client.get('/api/pipeline/sources').get_json()['sources']
    assert listed[0]['plugin_available'] is False  # no scan_db plugin yet (Task 2)
    assert listed[0]['display_path'] == snap


def test_delete_scan_removes_its_files_rows(tmp_path, monkeypatch):
    db = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db))
    app = create_app()
    app.config['TESTING'] = True
    app.config['state.backend'] = 'sqlite'
    client = authenticate_test_client(app.test_client(), app)
    data = tmp_path / 'data'
    data.mkdir()
    for n in ('a.txt', 'b.txt'):
        (data / n).write_text('x')
    scan_id = client.post('/api/scan', json={'path': str(data), 'recursive': True}).get_json()['scan_id']

    def rows():
        with sqlite3.connect(db) as conn:
            return conn.execute('SELECT count(*) FROM files WHERE scan_id=?', (scan_id,)).fetchone()[0]
    assert rows() > 0
    assert client.delete(f'/api/scans/{scan_id}').status_code == 200
    assert rows() == 0
