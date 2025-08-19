def test_interpreters_page_lists_ipynb_mapping(client, tmp_path):
    # touching a file is not necessary; just load app and hit page
    r = client.get('/interpreters')
    assert r.status_code == 200
    html = r.data.decode('utf-8')
    # Expect to see .ipynb mapping -> ipynb
    assert '.ipynb' in html
    assert 'ipynb' in html
