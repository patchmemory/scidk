def test_graph_subschema_api_shape_empty(client):
    # On a fresh app with no datasets, returns nodes and edges keys
    resp = client.get('/api/graph/subschema')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'nodes' in data and isinstance(data['nodes'], list)
    assert 'edges' in data and isinstance(data['edges'], list)
    assert 'truncated' in data


def test_graph_subschema_named_query(client):
    # Named query should respond and not error even on empty graph
    resp = client.get('/api/graph/subschema?name=interpreted_as')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'nodes' in data and 'edges' in data
