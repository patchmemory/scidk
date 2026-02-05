from pathlib import Path
import pytest
from scidk.app import create_app


@pytest.mark.integration
def test_list_providers(client):
    resp = client.get('/api/providers')
    assert resp.status_code == 200
    data = resp.get_json()
    ids = {p['id'] for p in data}
    assert 'local_fs' in ids
    assert 'mounted_fs' in ids  # may be empty at runtime but should be registered


@pytest.mark.integration
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


def test_provider_roots_default(client):
    # Test default provider (local_fs)
    resp = client.get('/api/provider_roots')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Validate structure
    for root in data:
        assert 'id' in root
        assert 'name' in root
        assert 'path' in root


def test_provider_roots_specific_provider(client):
    resp = client.get('/api/provider_roots?provider_id=local_fs')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_provider_roots_invalid_provider(client):
    resp = client.get('/api/provider_roots?provider_id=nonexistent')
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'error' in data


def test_rclone_mounts_list(client):
    # Should return empty list initially (or existing mounts)
    resp = client.get('/api/rclone/mounts')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


def test_rclone_mounts_create_missing_rclone(client, monkeypatch):
    # Mock rclone not available
    monkeypatch.setattr('shutil.which', lambda x: None)
    resp = client.post('/api/rclone/mounts', json={'remote': 'test:', 'name': 'testmount'})
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'rclone not installed' in data['error']


def test_rclone_mounts_create_missing_remote(client, monkeypatch):
    # Mock rclone available so we can test validation logic
    monkeypatch.setattr('scidk.web.routes.api_providers.shutil.which', lambda x: '/usr/bin/rclone')
    resp = client.post('/api/rclone/mounts', json={'name': 'testmount'})
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'remote required' in data['error']


def test_rclone_mounts_create_missing_name(client, monkeypatch):
    # Mock rclone available so we can test validation logic
    monkeypatch.setattr('scidk.web.routes.api_providers.shutil.which', lambda x: '/usr/bin/rclone')
    resp = client.post('/api/rclone/mounts', json={'remote': 'test:'})
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'name required' in data['error']
