from pathlib import Path
from scidk.app import create_app


def test_list_providers(client):
    resp = client.get('/api/providers')
    assert resp.status_code == 200
    data = resp.get_json()
    ids = {p['id'] for p in data}
    assert 'local_fs' in ids
    assert 'mounted_fs' in ids  # may be empty at runtime but should be registered


def test_browse_local_root(client, tmp_path: Path):
    # Ensure tmp directory exists and has files
    f = tmp_path / 'a.txt'
    f.write_text('hello')
    resp = client.get('/api/browse', query_string={'provider_id': 'local_fs', 'root_id': '/', 'path': str(tmp_path)})
    assert resp.status_code == 200
    data = resp.get_json()
    entries = data.get('entries', [])
    names = {e['name'] for e in entries}
    assert 'a.txt' in names
