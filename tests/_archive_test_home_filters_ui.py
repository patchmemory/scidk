from pathlib import Path

def test_home_page_contains_filters_and_scanned_sources_list(client, tmp_path: Path):
    # Arrange: create a file and scan its directory (non-recursive to test flag)
    f = tmp_path / 'file1.txt'
    f.write_text('hello', encoding='utf-8')
    resp = client.post('/api/scan', json={'path': str(tmp_path), 'recursive': False, 'provider_id': 'local_fs'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'

    # Act: fetch home page
    html_resp = client.get('/')
    assert html_resp.status_code == 200
    html = html_resp.data.decode('utf-8')

    # Assert: filter UI exists
    assert 'id="source-filter-form"' in html, 'Expected source filter form on Home page'
    assert 'id="filter-provider"' in html
    assert 'id="filter-path"' in html
    assert 'id="filter-recursive"' in html

    # Assert: scanned sources list contains li entries with data attributes
    assert 'id="scanned-sources-list"' in html
    # Expect data-provider, data-path, data-recursive attributes present on list items
    assert 'data-provider="local_fs"' in html
    assert f'data-path="{str(tmp_path)}"' in html
    assert 'data-recursive="false"' in html
