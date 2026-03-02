def test_map_route_renders(client):
    # Basic smoke test: GET /map returns 200 and contains key UI elements
    resp = client.get('/map')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Check for new tabbed interface structure
    assert 'Maps' in html  # Page title
    assert 'Query Editor' in html  # Query editor section
    assert 'Schema Configuration' in html or 'schema-config' in html  # Schema config panel

    # Check for main panel classes (new structure)
    assert 'map-library-panel' in html  # Saved maps library
    assert 'map-workspace-panel' in html  # Main workspace with tabs

    # Check for tab functionality
    assert 'New Tab' in html or 'add-tab-btn' in html

    # Check for save/load functionality
    assert 'Save Map' in html or 'save-map' in html
