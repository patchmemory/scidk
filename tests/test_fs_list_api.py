from pathlib import Path

def test_fs_list_basic(client, tmp_path: Path):
    # Create structure
    base = tmp_path
    sub = base / 'subdir'
    sub.mkdir()
    (base / 'a.txt').write_text('x', encoding='utf-8')
    # Register a scan so base is recognized
    r = client.post('/api/scan', json={'path': str(base), 'recursive': False})
    assert r.status_code == 200
    # List base
    resp = client.get('/api/fs/list', query_string={'base': str(base)})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['base'] == str(base.resolve())
    assert 'items' in data and isinstance(data['items'], list)
    # Should include subdir and a.txt
    names = {it['name'] for it in data['items']}
    assert 'subdir' in names
    assert 'a.txt' in names
    # Navigate into subdir
    resp2 = client.get('/api/fs/list', query_string={'base': str(base), 'path': str(sub)})
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2['path'] == str(sub.resolve())
    # Security: path outside base should snap back to base
    root = Path('/')
    resp3 = client.get('/api/fs/list', query_string={'base': str(base), 'path': str(root)})
    assert resp3.status_code == 200
    data3 = resp3.get_json()
    assert data3['path'] == str(base.resolve())
