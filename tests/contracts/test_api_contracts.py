import pytest


def test_providers_contract(client):
    r = client.get('/api/providers')
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    # each provider has id and display_name at minimum
    assert all(isinstance(p, dict) for p in data)
    assert all('id' in p and 'display_name' in p for p in data)


def test_provider_roots_contract_local_fs(client):
    # local_fs is always available; ensure shape of roots is a list of {id,name,path}
    r = client.get('/api/provider_roots', query_string={'provider_id': 'local_fs'})
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    for item in data:
        assert isinstance(item, dict)
        assert 'id' in item and 'name' in item and 'path' in item


def test_browse_contract_local_fs_root_listing(client):
    # Basic browse shape for local_fs at root
    r = client.get('/api/browse', query_string={'provider_id': 'local_fs', 'root_id': '/'})
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, dict)
    assert 'entries' in data and isinstance(data['entries'], list)
    # entries have minimal fields
    for e in data['entries']:
        assert isinstance(e, dict)
        assert 'name' in e and 'type' in e
