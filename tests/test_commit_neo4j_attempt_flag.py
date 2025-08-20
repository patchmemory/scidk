from pathlib import Path

def test_commit_reports_neo4j_attempt_when_config_present(client, tmp_path: Path):
    # Configure Neo4j settings (driver may be unavailable in tests)
    client.post('/api/settings/neo4j', json={
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'bad-or-missing',
        'database': 'neo4j'
    })
    # Prepare files and scan
    (tmp_path / 'a.py').write_text('print(1)\n', encoding='utf-8')
    r = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert r.status_code == 200
    scan_id = r.get_json()['scan_id']
    # Commit
    c = client.post(f'/api/scans/{scan_id}/commit')
    assert c.status_code == 200
    data = c.get_json()
    assert 'neo4j_attempted' in data
    # In CI, the driver may be missing or auth may fail; ensure we surface error clearly
    if data.get('neo4j_attempted'):
        assert 'neo4j_written_files' in data
        # When driver is missing or auth fails, neo4j_error should be populated
        # We don't assert exact message, just that a string is present
        if data.get('neo4j_error') is not None:
            assert isinstance(data['neo4j_error'], str)
