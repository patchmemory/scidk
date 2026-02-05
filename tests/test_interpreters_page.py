def test_interpreters_page_lists_ipynb_mapping(client, tmp_path):
    # /interpreters now redirects to /settings#interpreters
    r = client.get('/interpreters')
    assert r.status_code == 302
    assert '/settings#interpreters' in r.location
    # Follow redirect to settings page which contains the interpreter info
    r = client.get('/settings')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    # Expect to see .ipynb mapping -> ipynb in settings page
    assert '.ipynb' in html
    assert 'ipynb' in html
