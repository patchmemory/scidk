def test_interpreters_page_lists_ipynb_mapping(client, tmp_path):
    # /interpreters now redirects to /#interpreters (backward compatibility)
    r = client.get('/interpreters')
    assert r.status_code == 302
    # /interpreters redirects to /#interpreters
    assert '/#interpreters' in r.location or '/settings#interpreters' in r.location

    # Interpreters section was moved from Settings to Files page sidebar
    # Check that the API endpoint returns ipynb interpreter
    r = client.get('/api/interpreters')
    assert r.status_code == 200
    data = r.get_json()

    # Should have ipynb interpreter in the list
    ipynb_found = any(
        interp.get('id') == 'ipynb' or
        '.ipynb' in interp.get('globs', [])
        for interp in data
    )
    assert ipynb_found, "ipynb interpreter not found in API response"
