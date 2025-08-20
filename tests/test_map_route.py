def test_map_route_renders(client):
    # Basic smoke test: GET /map returns 200 and contains key headings
    resp = client.get('/map')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Graph Schema' in html
    assert 'Node Labels' in html
    assert 'Relationship Types' in html
    # Interactive graph elements present
    assert 'id="schema-graph"' in html
    assert 'Download Schema (CSV)' in html
    # Filters present
    assert 'id="filter-labels"' in html
    assert 'id="filter-reltypes"' in html
