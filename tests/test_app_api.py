import json
from pathlib import Path


def test_api_datasets_empty(client):
    resp = client.get('/api/datasets')
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)
    assert resp.get_json() == []


def test_api_scan_and_interpret(client, tmp_path: Path):
    # Create a simple py file
    f = tmp_path / 'x.py'
    f.write_text('import os\n', encoding='utf-8')

    # Scan
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['scanned'] == 1

    # List datasets and pick first
    ds_resp = client.get('/api/datasets')
    ds_list = ds_resp.get_json()
    assert len(ds_list) == 1
    ds = ds_list[0]

    # Interpret using automatic selection
    interp_resp = client.post('/api/interpret', json={'dataset_id': ds['id']})
    assert interp_resp.status_code == 200
    assert interp_resp.get_json()['status'] == 'ok'


def test_api_interpret_missing_id(client):
    resp = client.post('/api/interpret', json={})
    assert resp.status_code == 400
    assert resp.get_json()['status'] == 'error'
    assert 'dataset_id required' in resp.get_json()['error']


def test_security_overview_api(client):
    """Test that the security overview API endpoint returns expected structure."""
    resp = client.get('/api/security/overview')
    assert resp.status_code == 200

    # Verify response structure
    data = resp.get_json()
    assert 'connections' in data
    assert 'auth_status' in data
    assert 'data_protection' in data
    assert 'readiness' in data

    # Verify auth_status structure
    assert 'mode' in data['auth_status']
    assert 'user_count' in data['auth_status']
    assert 'session_count' in data['auth_status']

    # Verify data_protection structure
    assert 'transit_encrypted' in data['data_protection']
    assert 'audit_enabled' in data['data_protection']

    # Verify readiness structure
    assert 'auth_enabled' in data['readiness']
    assert 'all_connections_encrypted' in data['readiness']
