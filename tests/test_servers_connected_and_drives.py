"""Task group J — ``/api/servers`` reports real reachability and includes
drives added at runtime.
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
def client(app, monkeypatch):
    monkeypatch.setattr(api_drives.shutil, 'which', lambda _: None)
    return authenticate_test_client(app.test_client(), app)


def _by_root(servers, root_id):
    return next((s for s in servers if s.get('root_id') == root_id), None)


# ── J1 — connected is probed ───────────────────────────────────────────────

def test_connected_is_false_for_a_root_that_does_not_exist(client, app, monkeypatch, tmp_path):
    """The old code returned True for any loaded provider, always."""
    gone = tmp_path / 'unmounted'

    class Root:
        id = str(gone)
        name = 'gone'
        path = str(gone)

    provs = app.extensions['scidk']['providers']
    local = provs.get('local_fs')
    monkeypatch.setattr(type(local), 'list_roots', lambda self: [Root()])

    servers = client.get('/api/servers').get_json()
    entry = _by_root(servers, str(gone))
    assert entry is not None
    assert entry['connected'] is False


def test_connected_is_true_for_a_readable_root(client, app, monkeypatch, tmp_path):
    readable = tmp_path / 'data'
    readable.mkdir()

    class Root:
        id = str(readable)
        name = 'data'
        path = str(readable)

    provs = app.extensions['scidk']['providers']
    local = provs.get('local_fs')
    monkeypatch.setattr(type(local), 'list_roots', lambda self: [Root()])

    assert _by_root(client.get('/api/servers').get_json(), str(readable))['connected'] is True


def test_rclone_roots_are_probed_with_lsjson(client, app, monkeypatch):
    """And the trailing colon from list_roots is stripped before probing."""
    probes = []

    class Root:
        id = 'dropbox:'
        name = 'dropbox'
        path = 'dropbox:'

    provs = app.extensions['scidk']['providers']
    rclone = provs.get('rclone')
    if rclone is None:
        pytest.skip('rclone provider not registered in this build')
    monkeypatch.setattr(type(rclone), 'list_roots', lambda self: [Root()])
    monkeypatch.setattr(api_drives.shutil, 'which', lambda _: '/usr/bin/rclone')

    def run(argv, **kwargs):
        probes.append(argv)
        return subprocess.CompletedProcess(argv, 1, '', 'no token')

    monkeypatch.setattr(api_drives.subprocess, 'run', run)

    assert _by_root(client.get('/api/servers').get_json(), 'dropbox:')['connected'] is False
    assert probes and probes[0][1:] == ['lsjson', 'dropbox:', '--max-depth', '0']


# ── J2 — drives added at runtime appear without a restart ──────────────────

def test_a_drive_added_via_the_api_shows_up_in_servers(client, tmp_path):
    target = tmp_path / 'lab'
    target.mkdir()
    assert client.post('/api/drives', json={
        'type': 'local_fs', 'path': str(target), 'label': 'Lab Server',
    }).status_code == 201

    entry = _by_root(client.get('/api/servers').get_json(), str(target))
    assert entry is not None
    assert entry['id'] == 'local_fs', 'must map onto a provider that can browse it'
    assert entry['display_name'] == 'Lab Server'
    assert entry['connected'] is True
    assert entry['drive_id'] == f'local:{target}'


def test_an_rclone_drive_is_listed_under_the_rclone_provider(client, monkeypatch):
    monkeypatch.setattr(api_drives.shutil, 'which', lambda _: '/usr/bin/rclone')
    monkeypatch.setattr(api_drives.subprocess, 'run',
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, '[]', ''))
    client.post('/api/drives', json={'type': 'rclone', 'name': 'dropbox'})

    entry = _by_root(client.get('/api/servers').get_json(), 'dropbox:')
    assert entry['id'] == 'rclone'
    assert entry['connected'] is True


def test_a_drive_a_provider_already_reports_is_not_listed_twice(client, app, monkeypatch, tmp_path):
    target = tmp_path / 'shared'
    target.mkdir()

    class Root:
        id = str(target)
        name = 'shared'
        path = str(target)

    provs = app.extensions['scidk']['providers']
    monkeypatch.setattr(type(provs.get('local_fs')), 'list_roots', lambda self: [Root()])
    client.post('/api/drives', json={'type': 'local_fs', 'path': str(target)})

    servers = client.get('/api/servers').get_json()
    matches = [s for s in servers if s.get('root_id') == str(target)]
    assert len(matches) == 1
    # The provider's entry wins; it is the one with no drive_id.
    assert 'drive_id' not in matches[0]


def test_servers_still_lists_providers_when_the_drives_table_is_unreadable(client, monkeypatch):
    def boom():
        raise RuntimeError('database is locked')

    monkeypatch.setattr(api_drives, '_load_drives', boom)
    r = client.get('/api/servers')
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)
