from pathlib import Path

def _get_schema(client):
    resp = client.get('/api/graph/schema')
    assert resp.status_code == 200
    return resp.get_json()


def test_commit_scan_adds_scan_nodes_and_edges(client, tmp_path: Path):
    # Create files and scan
    (tmp_path / 'a.py').write_text('import os\n', encoding='utf-8')
    (tmp_path / 'b.csv').write_text('h1,h2\n1,2\n', encoding='utf-8')
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    scan_id = resp.get_json()['scan_id']

    # Before commit: no Scan node or SCANNED_IN edge in schema
    sch0 = _get_schema(client)
    labels0 = {n['label']: n['count'] for n in sch0['nodes']}
    assert 'Scan' not in labels0 or labels0['Scan'] == 0
    edge_types0 = {(e['rel_type'], e['end_label']) for e in sch0['edges']}
    assert ('SCANNED_IN', 'Scan') not in edge_types0

    # Commit the scan into the graph
    c = client.post(f'/api/scans/{scan_id}/commit')
    assert c.status_code == 200

    sch1 = _get_schema(client)
    labels1 = {n['label']: n['count'] for n in sch1['nodes']}
    assert labels1.get('Scan', 0) >= 1
    # SCANNED_IN edges should appear
    edge_map1 = {(e['rel_type'], e['end_label']) for e in sch1['edges']}
    assert ('SCANNED_IN', 'Scan') in edge_map1


def test_delete_scan_removes_scan_nodes_and_edges(client, tmp_path: Path):
    # Prepare and scan
    (tmp_path / 'x.py').write_text('import sys\n', encoding='utf-8')
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    scan_id = resp.get_json()['scan_id']

    # Commit then delete
    client.post(f'/api/scans/{scan_id}/commit')
    d = client.delete(f'/api/scans/{scan_id}')
    assert d.status_code == 200

    sch2 = _get_schema(client)
    labels2 = {n['label']: n['count'] for n in sch2['nodes']}
    # Scan node count goes to 0 or missing
    assert labels2.get('Scan', 0) == 0
    # SCANNED_IN edges should be gone
    assert all(e['rel_type'] != 'SCANNED_IN' for e in sch2['edges'])
