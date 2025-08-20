from pathlib import Path

def test_commit_verbose_response(client, tmp_path: Path):
    # Prepare files and scan
    (tmp_path / 'a.py').write_text('print(1)\n', encoding='utf-8')
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert r.status_code == 200
    scan_id = r.get_json()['scan_id']

    # Commit
    c = client.post(f'/api/scans/{scan_id}/commit')
    assert c.status_code == 200
    data = c.get_json()
    # Verbose fields should be present
    assert data.get('status') == 'ok'
    assert 'files_in_scan' in data
    assert 'matched_in_graph' in data
    assert 'linked_edges_added' in data


def test_graph_health_endpoint_basic(client):
    r = client.get('/api/health/graph')
    assert r.status_code == 200
    data = r.get_json()
    assert 'backend' in data
    assert 'in_memory_ok' in data
    assert 'neo4j' in data
