from pathlib import Path

def test_directories_saved_after_scan(client, tmp_path: Path):
    # create a simple file to be found
    f = tmp_path / 'a.txt'
    f.write_text('hello', encoding='utf-8')

    # scan the directory (non-recursive)
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'

    # fetch directories list
    d_resp = client.get('/api/directories')
    assert d_resp.status_code == 200
    dirs = d_resp.get_json()
    assert isinstance(dirs, list)
    # one entry for the scanned tmp_path
    matched = [d for d in dirs if d.get('path') == str(tmp_path)]
    assert matched, 'scanned directory path should be recorded'
    entry = matched[0]
    assert entry.get('scanned') >= 1
    assert entry.get('recursive') is False
