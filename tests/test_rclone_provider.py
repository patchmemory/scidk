import json as _json
import types
from scidk.app import create_app
from tests.conftest import authenticate_test_client


def make_client_with_rclone(monkeypatch, listremotes_output=None, lsjson_map=None):
    """Create a Flask test client with SCIDK_PROVIDERS including rclone and mocked rclone subprocess.
    listremotes_output: string for `rclone listremotes` stdout
    lsjson_map: dict mapping target -> stdout JSON string for `rclone lsjson <target> --max-depth 1`
    """
    # Ensure rclone is enabled
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')

    # Mock shutil.which to pretend rclone exists
    import shutil as _shutil
    monkeypatch.setattr(_shutil, 'which', lambda name: '/usr/bin/rclone' if name == 'rclone' else None)

    # Mock subprocess.run to handle rclone commands
    import subprocess as _subprocess

    def fake_run(args, stdout=None, stderr=None, text=False, check=False):
        # args is like ['/usr/bin/rclone', 'listremotes'] or ['/usr/bin/rclone', 'lsjson', target, '--max-depth', '1']
        if isinstance(args, (list, tuple)) and args and ('rclone' in args[0]):
            cmd = args[1] if len(args) > 1 else ''
            if cmd == 'version':
                out = 'rclone v1.66.0\n'
                return types.SimpleNamespace(returncode=0, stdout=out, stderr='')
            if cmd == 'listremotes':
                out = listremotes_output if (listremotes_output is not None) else 'gdrive:\n'
                return types.SimpleNamespace(returncode=0, stdout=out, stderr='')
            if cmd == 'lsjson':
                target = args[2] if len(args) > 2 else ''
                out = (lsjson_map or {}).get(target, '[]')
                return types.SimpleNamespace(returncode=0, stdout=out, stderr='')
            # default ok
            return types.SimpleNamespace(returncode=0, stdout='', stderr='')
        # Fallback
        return _subprocess.run(args, stdout=stdout, stderr=stderr, text=text, check=check)

    monkeypatch.setattr('subprocess.run', fake_run)

    app = create_app()
    app.config.update({"TESTING": True})
    return authenticate_test_client(app.test_client(), app)


def test_providers_includes_rclone_and_roots_listing(monkeypatch):
    client = make_client_with_rclone(monkeypatch, listremotes_output='gdrive:\nother:')

    # /api/providers should include rclone
    resp = client.get('/api/providers')
    assert resp.status_code == 200
    ids = {p['id'] for p in resp.get_json()}
    assert 'rclone' in ids

    # /api/provider_roots should list remotes
    resp2 = client.get('/api/provider_roots', query_string={'provider_id': 'rclone'})
    assert resp2.status_code == 200
    roots = resp2.get_json()
    names = {r['id'] for r in roots}
    assert 'gdrive:' in names
    assert 'other:' in names


def test_browse_rclone_path_lists_entries(monkeypatch):
    # Mock lsjson returning a folder and a file under gdrive:folder
    lsjson = _json.dumps([
        {"Path": "folder/sub", "Name": "sub", "Size": 0, "IsDir": True},
        {"Path": "folder/a.txt", "Name": "a.txt", "Size": 5, "IsDir": False},
    ])
    client = make_client_with_rclone(monkeypatch, listremotes_output='gdrive:', lsjson_map={'gdrive:folder': lsjson})

    resp = client.get('/api/browse', query_string={'provider_id': 'rclone', 'root_id': 'gdrive:', 'path': 'gdrive:folder'})
    assert resp.status_code == 200
    data = resp.get_json()
    entries = data.get('entries')
    assert isinstance(entries, list)
    names = [e['name'] for e in entries]
    assert 'sub' in names
    assert 'a.txt' in names
    # Ensure provider_id backfills
    for e in entries:
        assert e['provider_id'] == 'rclone'


def test_rclone_not_installed_gives_clear_error(monkeypatch):
    # Enable rclone but pretend it's not installed
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')
    # which returns None
    import shutil as _shutil
    monkeypatch.setattr(_shutil, 'which', lambda name: None)

    app = create_app(); app.config.update({"TESTING": True})
    client = authenticate_test_client(app.test_client(), app)

    resp = client.get('/api/provider_roots', query_string={'provider_id': 'rclone'})
    # Our API wraps provider errors as 500 with {error: message}
    assert resp.status_code == 500
    err = resp.get_json().get('error', '')
    assert 'rclone' in err.lower()
    assert 'install' in err.lower() or 'path' in err.lower()
