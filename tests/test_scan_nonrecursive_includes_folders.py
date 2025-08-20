from pathlib import Path


def test_nonrecursive_scan_includes_immediate_folders(client, tmp_path: Path):
    # Prepare: create a top-level folder and a file inside it; plus one file at root
    sub = tmp_path / 'subdir'
    sub.mkdir()
    (sub / 'inside.txt').write_text('x', encoding='utf-8')
    (tmp_path / 'root.txt').write_text('y', encoding='utf-8')

    # Non-recursive scan should only scan files at the base level, but also record immediate subfolders
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    scan_id = resp.get_json()['scan_id']

    # Fetch scan detail and assert folders info present
    d = client.get(f'/api/scans/{scan_id}')
    assert d.status_code == 200
    scan = d.get_json()
    assert isinstance(scan, dict)
    # Should include folder_count and a non-empty folders list containing our subdir
    assert 'folder_count' in scan
    assert 'folders' in scan
    folders = scan['folders'] or []
    assert scan['folder_count'] == len(folders)
    # Our subdir should be included
    paths = {f['path'] for f in folders}
    assert str(sub.resolve()) in paths
    # Verify expected keys present per folder row
    row = next(f for f in folders if f['path'] == str(sub.resolve()))
    assert 'name' in row and row['name'] == 'subdir'
    assert 'parent' in row and row['parent']
    assert 'parent_name' in row
