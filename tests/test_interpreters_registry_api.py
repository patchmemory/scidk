import json
from scidk.app import create_app

def test_api_interpreters_schema(client):
    resp = client.get('/api/interpreters')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert any(it.get('id') == 'python_code' for it in data)
    # Validate required fields exist for each item
    for it in data:
        assert 'id' in it
        assert 'version' in it
        assert 'globs' in it
        assert 'default_enabled' in it
        assert 'cost' in it  # may be None
    # Effective view placeholder
    resp2 = client.get('/api/interpreters?view=effective')
    assert resp2.status_code == 200
    eff = resp2.get_json()
    assert isinstance(eff, list)
    for it in eff:
        assert 'enabled' in it
        assert 'source' in it


def test_api_interpreters_effective_debug(client):
    resp = client.get('/api/interpreters/effective_debug')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'source' in data
    assert 'effective_enabled' in data
    assert 'default_enabled' in data
    assert 'loaded_settings' in data
    assert 'env' in data
    assert isinstance(data['effective_enabled'], list)
    assert isinstance(data['default_enabled'], list)


def test_api_interpreters_toggle_enable(client):
    # Enable an interpreter
    resp = client.post('/api/interpreters/csv/toggle', json={'enabled': True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'updated'
    assert data['enabled'] is True


def test_api_interpreters_toggle_disable(client):
    # Disable an interpreter
    resp = client.post('/api/interpreters/csv/toggle', json={'enabled': False})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'updated'
    assert data['enabled'] is False


def test_api_interpreters_toggle_default_enabled(client):
    # Toggle without explicit enabled flag (defaults to True)
    resp = client.post('/api/interpreters/python_code/toggle', json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'updated'
    assert data['enabled'] is True
