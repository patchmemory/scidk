def test_interpreters_page_lists_ipynb_mapping(client, tmp_path):
    # /interpreters now redirects to /#interpreters (settings is now at /)
    r = client.get('/interpreters')
    assert r.status_code == 302
    # /interpreters redirects to /#interpreters
    assert '/#interpreters' in r.location or '/settings#interpreters' in r.location
    # Settings page is now at / (landing page)
    r = client.get('/')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    # Expect to see .ipynb mapping -> ipynb in settings page
    assert '.ipynb' in html
    assert 'ipynb' in html
