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



def test_scan_contract_local_fs(client, tmp_path):
    # Create a temporary file to ensure directory is non-empty
    p = tmp_path / 'sample.txt'
    p.write_text('hello', encoding='utf-8')
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert r.status_code == 200
    data = r.get_json()
    # legacy /api/scan may return a dict or minimal payload; accept either id or ok
    assert isinstance(data, dict)
    assert 'id' in data or 'ok' in data or 'scan_id' in data


def test_scan_status_contract(client, tmp_path):
    # kick off a small scan
    (tmp_path / 'a.txt').write_text('x', encoding='utf-8')
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert r.status_code == 200
    payload = r.get_json() or {}
    scan_id = payload.get('id') or payload.get('scan_id') or payload.get('scanId')
    # If synchronous legacy scan, status may be available via last item in /api/scans
    if not scan_id:
        scans_resp = client.get('/api/scans')
        assert scans_resp.status_code == 200
        scans = scans_resp.get_json() or []
        assert isinstance(scans, list)
        if scans:
            scan_id = scans[-1].get('id')
    # If still missing, skip to keep contract minimal/non-flaky
    if not scan_id:
        pytest.skip('scan_id not available from API after legacy /api/scan response')
    st = client.get(f'/api/scans/{scan_id}/status')
    assert st.status_code == 200
    sd = st.get_json()
    assert isinstance(sd, dict)
    # Expect at least a status/state field
    assert any(k in sd for k in ('status', 'state', 'done'))


def test_directories_contract(client, tmp_path):
    # Ensure at least one directory exists in the registry by running a quick scan
    (tmp_path / 'b.txt').write_text('y', encoding='utf-8')
    client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    d = client.get('/api/directories')
    assert d.status_code == 200
    arr = d.get_json()
    assert isinstance(arr, list)
    # Minimal shape
    if arr:
        for item in arr:
            assert isinstance(item, dict)
            assert 'path' in item
            # optional helpful fields
            _ = item.get('scanned') if isinstance(item, dict) else None
            _ = item.get('recursive') if isinstance(item, dict) else None
