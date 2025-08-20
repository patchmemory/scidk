from pathlib import Path


def test_scans_summary_includes_committed_flag(client, tmp_path: Path):
    # Create files and run a scan
    (tmp_path / 'a.py').write_text('print(1)\n', encoding='utf-8')
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert r.status_code == 200

    # Initially committed should be False in /api/scans
    s = client.get('/api/scans')
    assert s.status_code == 200
    scans = s.get_json()
    assert isinstance(scans, list) and len(scans) >= 1
    found = [x for x in scans if x.get('path') == str(tmp_path)]
    assert found, "Expected to find the scan in summaries"
    assert found[0].get('committed') is False
    assert 'committed_at' in found[0]

    # Commit the scan
    scan_id = r.get_json()['scan_id']
    c = client.post(f'/api/scans/{scan_id}/commit')
    assert c.status_code == 200

    # Now committed should be True
    s2 = client.get('/api/scans')
    scans2 = s2.get_json()
    found2 = [x for x in scans2 if x.get('id') == scan_id]
    assert found2 and found2[0].get('committed') is True
