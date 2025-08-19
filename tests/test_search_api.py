from pathlib import Path


def test_api_search_by_filename_and_interpreter(client, tmp_path: Path):
    # Create files
    pyf = tmp_path / 'alpha_script.py'
    pyf.write_text('print("hello")\n', encoding='utf-8')
    csvf = tmp_path / 'beta_data.csv'
    csvf.write_text('a,b\n1,2\n', encoding='utf-8')

    # Scan directory (will also run interpretations per registry rules)
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['scanned'] == 2

    # Search by filename token
    r1 = client.get('/api/search?q=alpha')
    assert r1.status_code == 200
    results1 = r1.get_json()
    assert isinstance(results1, list)
    # Expect at least the .py file to be present
    assert any('alpha_script.py' == (r.get('filename') or '') for r in results1)
    # matched_on should include 'filename'
    for r in results1:
        if r.get('filename') == 'alpha_script.py':
            assert 'filename' in (r.get('matched_on') or [])
            break

    # Search by interpreter id (python_code or csv)
    r2 = client.get('/api/search?q=python_code')
    assert r2.status_code == 200
    results2 = r2.get_json()
    assert any(r.get('filename') == 'alpha_script.py' for r in results2)

    r3 = client.get('/api/search?q=csv')
    assert r3.status_code == 200
    results3 = r3.get_json()
    assert any(r.get('filename') == 'beta_data.csv' for r in results3)
