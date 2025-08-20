from pathlib import Path


def test_schema_includes_file_and_folder_after_scan(client, tmp_path: Path):
    # Create a small directory structure
    sub = tmp_path / 'subdir'
    sub.mkdir()
    (tmp_path / 'root.txt').write_text('a', encoding='utf-8')
    (sub / 'child.csv').write_text('b', encoding='utf-8')

    # Scan non-recursive first: only top-level file
    resp1 = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp1.status_code == 200

    sch1 = client.get('/api/graph/schema').get_json()
    labels1 = {n['label']: n['count'] for n in sch1['nodes']}
    assert labels1.get('File', 0) >= 1
    # Folder count exists (parent of root file)
    assert 'Folder' in labels1

    # Now recursive scan to include nested file, folder count should be >= 2 (tmp_path and subdir)
    resp2 = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': True})
    assert resp2.status_code == 200
    sch2 = client.get('/api/graph/schema').get_json()
    labels2 = {n['label']: n['count'] for n in sch2['nodes']}
    assert labels2.get('File', 0) >= 2
    assert labels2.get('Folder', 0) >= 2

    # Relationship types include CONTAINS; ensure Folder→Folder appears when nested
    rel_types = {e['rel_type'] for e in sch2['edges']}
    assert 'CONTAINS' in rel_types
    has_folder_folder = any(e['rel_type'] == 'CONTAINS' and e['start_label'] == 'Folder' and e['end_label'] == 'Folder' for e in sch2['edges'])
    assert has_folder_folder, 'Expected Folder CONTAINS Folder triple when nested folders are present'
