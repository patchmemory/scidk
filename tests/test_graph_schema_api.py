def test_graph_schema_api_shape_empty(client):
    # On a fresh app with no datasets, returns nodes and edges keys
    resp = client.get('/api/graph/schema')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'nodes' in data and isinstance(data['nodes'], list)
    assert 'edges' in data and isinstance(data['edges'], list)
    assert 'truncated' in data


def test_graph_schema_csv_download(client):
    # CSV endpoint returns text/csv and contains both sections headers
    resp = client.get('/api/graph/schema.csv')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    text = resp.get_data(as_text=True)
    assert 'NodeLabels' in text
    assert 'RelationshipTypes' in text
