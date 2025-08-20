from pathlib import Path

def test_instances_json_empty(client):
    resp = client.get('/api/graph/instances?label=File')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['label'] == 'File'
    assert 'rows' in data and isinstance(data['rows'], list)


def test_instances_csv_after_scan(client, tmp_path: Path):
    (tmp_path / 'a.py').write_text('print(1)\n', encoding='utf-8')
    (tmp_path / 'b.txt').write_text('x\n', encoding='utf-8')
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert r.status_code == 200
    # Download File instances CSV
    resp = client.get('/api/graph/instances.csv?label=File')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    text = resp.get_data(as_text=True)
    assert 'filename' in text and 'path' in text
