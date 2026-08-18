"""Task group G — the Drives API behind the Add Drive drawer.

rclone is not assumed to be installed on the machine running these tests, so
every rclone path is exercised through a patched ``subprocess.run`` and a
patched ``shutil.which``. The local_fs paths use real directories.
"""
import subprocess

import pytest

from scidk.app import create_app
from scidk.core import path_index_sqlite as pix
from scidk.web.routes import api_drives
from tests.conftest import authenticate_test_client


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    conn = pix.connect()
    try:
        pix.init_db(conn)
    finally:
        conn.close()
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture()
def client(app):
    return authenticate_test_client(app.test_client(), app)


@pytest.fixture()
def no_rclone(monkeypatch):
    """A host without rclone — the default assumption for these tests."""
    monkeypatch.setattr(api_drives.shutil, 'which', lambda _: None)


def _fake_rclone(monkeypatch, handler):
    """Route ``rclone`` subprocess calls to ``handler(argv) -> CompletedProcess``."""
    monkeypatch.setattr(api_drives.shutil, 'which', lambda _: '/usr/bin/rclone')

    def run(argv, **kwargs):
        return handler(argv)

    monkeypatch.setattr(api_drives.subprocess, 'run', run)


# ── G1 / G2 — local drives ─────────────────────────────────────────────────

def test_list_is_empty_before_anything_is_added(client, no_rclone):
    r = client.get('/api/drives')
    assert r.status_code == 200
    assert r.get_json() == {'drives': []}


def test_add_local_drive_then_list_it(client, tmp_path, no_rclone):
    target = tmp_path / 'lab'
    target.mkdir()

    r = client.post('/api/drives', json={'type': 'local_fs', 'path': str(target), 'label': 'Lab Server'})
    assert r.status_code == 201
    assert r.get_json()['id'] == f'local:{target}'

    drives = client.get('/api/drives').get_json()['drives']
    assert len(drives) == 1
    assert drives[0]['type'] == 'local_fs'
    assert drives[0]['label'] == 'Lab Server'
    assert drives[0]['path'] == str(target)
    # Probed, not hardcoded: the directory exists and is readable.
    assert drives[0]['connected'] is True


def test_local_drive_reports_disconnected_when_it_disappears(app, client, tmp_path, no_rclone):
    target = tmp_path / 'gone'
    target.mkdir()
    client.post('/api/drives', json={'type': 'local_fs', 'path': str(target)})
    target.rmdir()
    with app.app_context():
        api_drives.invalidate_connectivity_cache()

    assert client.get('/api/drives').get_json()['drives'][0]['connected'] is False


def test_add_local_drive_rejects_missing_path(client, tmp_path, no_rclone):
    assert client.post('/api/drives', json={'type': 'local_fs'}).status_code == 400
    r = client.post('/api/drives', json={'type': 'local_fs', 'path': str(tmp_path / 'nope')})
    assert r.status_code == 400


def test_adding_the_same_path_twice_is_a_conflict(client, tmp_path, no_rclone):
    target = tmp_path / 'lab'
    target.mkdir()
    body = {'type': 'local_fs', 'path': str(target)}
    assert client.post('/api/drives', json=body).status_code == 201
    r = client.post('/api/drives', json=body)
    assert r.status_code == 409


def test_unknown_type_is_rejected(client, no_rclone):
    assert client.post('/api/drives', json={'type': 'ftp'}).status_code == 400


# ── G2 — rclone drives ─────────────────────────────────────────────────────

def test_add_rclone_remote_with_params_calls_config_create(client, monkeypatch):
    seen = {}

    def handler(argv):
        seen['argv'] = argv
        return subprocess.CompletedProcess(argv, 0, '', '')

    _fake_rclone(monkeypatch, handler)
    r = client.post('/api/drives', json={
        'type': 'rclone', 'name': 'lab-s3', 'remote_type': 's3',
        'params': {'access_key_id': 'AKIA', 'secret_access_key': 's3cret', 'region': ''},
    })
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['id'] == 'rclone:lab-s3'
    argv = seen['argv']
    assert argv[1:5] == ['config', 'create', 'lab-s3', 's3']
    assert 'access_key_id=AKIA' in argv
    # An empty form field is not a setting.
    assert not any(a.startswith('region=') for a in argv)


def test_rclone_config_create_failure_is_reported_with_stderr(client, monkeypatch):
    _fake_rclone(monkeypatch, lambda argv: subprocess.CompletedProcess(argv, 1, '', 'bad credentials'))
    r = client.post('/api/drives', json={
        'type': 'rclone', 'name': 'broken', 'remote_type': 's3', 'params': {'access_key_id': 'x'},
    })
    assert r.status_code == 500
    assert 'bad credentials' in r.get_json()['error']
    # A remote that could not be created is not recorded as a drive.
    assert client.get('/api/drives').get_json()['drives'] == []


def test_add_rclone_remote_without_params_imports_an_existing_one(client, monkeypatch):
    def handler(argv):
        if argv[1:3] == ['config', 'show']:
            return subprocess.CompletedProcess(argv, 0, '[dropbox]\ntype = dropbox\n', '')
        return subprocess.CompletedProcess(argv, 0, '[]', '')

    _fake_rclone(monkeypatch, handler)
    r = client.post('/api/drives', json={'type': 'rclone', 'name': 'dropbox', 'remote_type': 'dropbox'})
    assert r.status_code == 201
    assert client.get('/api/drives').get_json()['drives'][0]['connected'] is True


def test_importing_a_remote_that_does_not_exist_is_a_400(client, monkeypatch):
    _fake_rclone(monkeypatch, lambda argv: subprocess.CompletedProcess(argv, 1, '', 'not found'))
    r = client.post('/api/drives', json={'type': 'rclone', 'name': 'ghost'})
    assert r.status_code == 400
    assert 'rclone config' in r.get_json()['error']


@pytest.mark.parametrize('name', ['--config', '-v', 'has space', '', 'a' * 65])
def test_rclone_names_that_could_be_read_as_flags_are_rejected(client, monkeypatch, name):
    _fake_rclone(monkeypatch, lambda argv: pytest.fail('rclone must not be invoked'))
    r = client.post('/api/drives', json={'type': 'rclone', 'name': name, 'remote_type': 's3',
                                         'params': {'access_key_id': 'x'}})
    assert r.status_code == 400


def test_rclone_param_keys_that_could_be_read_as_flags_are_rejected(client, monkeypatch):
    _fake_rclone(monkeypatch, lambda argv: pytest.fail('rclone must not be invoked'))
    r = client.post('/api/drives', json={
        'type': 'rclone', 'name': 'ok', 'remote_type': 's3', 'params': {'--config': '/etc/passwd'},
    })
    assert r.status_code == 400
    assert 'invalid parameter name' in r.get_json()['error']


# ── G3 — delete ────────────────────────────────────────────────────────────

def test_delete_removes_the_drive(client, tmp_path, no_rclone):
    target = tmp_path / 'lab'
    target.mkdir()
    drive_id = client.post('/api/drives', json={'type': 'local_fs', 'path': str(target)}).get_json()['id']

    assert client.delete(f'/api/drives/{drive_id}').status_code == 200
    assert client.get('/api/drives').get_json()['drives'] == []
    assert client.delete(f'/api/drives/{drive_id}').status_code == 404


def test_delete_leaves_the_rclone_config_alone_unless_asked(client, monkeypatch):
    calls = []

    def handler(argv):
        calls.append(argv[1:3])
        return subprocess.CompletedProcess(argv, 0, '[]', '')

    _fake_rclone(monkeypatch, handler)
    client.post('/api/drives', json={'type': 'rclone', 'name': 'dropbox'})

    calls.clear()
    client.delete('/api/drives/rclone:dropbox')
    assert ['config', 'delete'] not in calls

    client.post('/api/drives', json={'type': 'rclone', 'name': 'dropbox'})
    calls.clear()
    r = client.delete('/api/drives/rclone:dropbox?delete_remote=true')
    assert r.get_json()['remote_deleted'] is True
    assert ['config', 'delete'] in calls


# ── G4 — browse-local ──────────────────────────────────────────────────────

def test_browse_local_lists_directories_only_by_default(client, tmp_path):
    # A subdirectory, because tmp_path itself also holds this test's files.db.
    root = tmp_path / 'host'
    root.mkdir()
    (root / 'data').mkdir()
    (root / '.hidden').mkdir()
    (root / 'notes.txt').write_text('x')

    d = client.get('/api/drives/browse-local', query_string={'path': str(root)}).get_json()
    assert [e['name'] for e in d['entries']] == ['data']
    assert d['entries'][0]['type'] == 'dir'
    assert d['entries'][0]['readable'] is True

    d = client.get('/api/drives/browse-local',
                   query_string={'path': str(root), 'show_files': 'true'}).get_json()
    assert [e['name'] for e in d['entries']] == ['data', 'notes.txt']


def test_browse_local_404s_on_a_missing_path(client, tmp_path):
    r = client.get('/api/drives/browse-local', query_string={'path': str(tmp_path / 'nope')})
    assert r.status_code == 404
    assert r.get_json()['entries'] == []


def test_browse_local_403s_when_the_directory_cannot_be_read(client, tmp_path, monkeypatch):
    # chmod is not enough when the suite runs as root, so raise directly.
    import pathlib

    def boom(self):
        raise PermissionError(13, 'Permission denied')

    monkeypatch.setattr(pathlib.Path, 'iterdir', boom)
    r = client.get('/api/drives/browse-local', query_string={'path': str(tmp_path)})
    assert r.status_code == 403
    assert r.get_json()['entries'] == []


def test_browse_local_caps_its_listing(client, tmp_path):
    root = tmp_path / 'host'
    root.mkdir()
    for i in range(api_drives._BROWSE_LIMIT + 10):
        (root / f'dir{i:04d}').mkdir()
    d = client.get('/api/drives/browse-local', query_string={'path': str(root)}).get_json()
    assert len(d['entries']) == api_drives._BROWSE_LIMIT
    assert d['truncated'] is True


# ── G5 — test ──────────────────────────────────────────────────────────────

def test_test_endpoint_reports_a_readable_local_path(client, tmp_path):
    r = client.get('/api/drives/test', query_string={'path': str(tmp_path)})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_test_endpoint_counts_items_at_an_rclone_root(client, monkeypatch):
    _fake_rclone(monkeypatch, lambda argv: subprocess.CompletedProcess(argv, 0, '[{},{},{}]', ''))
    d = client.get('/api/drives/test', query_string={'name': 'dropbox'}).get_json()
    assert d['status'] == 'ok'
    assert '3 item(s)' in d['message']


def test_test_endpoint_surfaces_the_rclone_error(client, monkeypatch):
    _fake_rclone(monkeypatch, lambda argv: subprocess.CompletedProcess(
        argv, 1, '', 'NOTICE: skipping\nFailed to create client: no token'))
    r = client.get('/api/drives/test', query_string={'name': 'dropbox'})
    assert r.status_code == 400
    assert 'no token' in r.get_json()['error']


def test_test_endpoint_reports_a_timeout_rather_than_hanging(client, monkeypatch):
    monkeypatch.setattr(api_drives.shutil, 'which', lambda _: '/usr/bin/rclone')

    def run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get('timeout', 5))

    monkeypatch.setattr(api_drives.subprocess, 'run', run)
    r = client.get('/api/drives/test', query_string={'name': 'dropbox'})
    assert r.status_code == 400
    assert 'timed out' in r.get_json()['error']


# ── G6 — OAuth ─────────────────────────────────────────────────────────────

def test_oauth_declines_and_names_the_command_that_works(client, monkeypatch):
    _fake_rclone(monkeypatch, lambda argv: subprocess.CompletedProcess(argv, 0, '', ''))
    r = client.post('/api/drives/rclone/oauth', json={'type': 'dropbox', 'name': 'my-dropbox'})
    assert r.status_code == 501
    body = r.get_json()
    assert body['manual_command'] == 'rclone config create my-dropbox dropbox'
    assert 'localhost:53682' in body['error']


def test_oauth_status_polls_for_the_remote_appearing(client, monkeypatch):
    exists = {'yet': False}

    def handler(argv):
        return subprocess.CompletedProcess(argv, 0 if exists['yet'] else 1, '', '')

    _fake_rclone(monkeypatch, handler)
    assert client.get('/api/drives/rclone/oauth/status',
                      query_string={'name': 'my-dropbox'}).get_json()['status'] == 'pending'
    exists['yet'] = True
    assert client.get('/api/drives/rclone/oauth/status',
                      query_string={'name': 'my-dropbox'}).get_json() == {
        'status': 'ok', 'remote': 'my-dropbox'}


# ── connectivity cache ─────────────────────────────────────────────────────

def test_connectivity_is_probed_once_per_ttl(client, monkeypatch):
    calls = []

    def handler(argv):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '[]', '')

    _fake_rclone(monkeypatch, handler)
    client.post('/api/drives', json={'type': 'rclone', 'name': 'dropbox'})

    calls.clear()
    client.get('/api/drives')
    client.get('/api/drives')
    client.get('/api/drives')
    assert len(calls) == 1, 'the sidebar must not shell out once per render'
