def test_set_and_get_neo4j_settings(client):
    # Set configuration
    payload = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'secret',
        'database': 'neo4j'
    }
    r = client.post('/api/settings/neo4j', json=payload)
    assert r.status_code == 200
    # Get configuration (password should not be returned)
    g = client.get('/api/settings/neo4j')
    assert g.status_code == 200
    data = g.get_json()
    assert data['uri'] == payload['uri']
    assert data['user'] == payload['user']
    assert data['database'] == payload['database']
    assert 'connected' in data
    assert 'last_error' in data


def test_connect_disconnect_roundtrip_without_driver(client):
    # Ensure settings are present, but we don't rely on actual driver/server
    client.post('/api/settings/neo4j', json={'uri': 'bolt://localhost:7687', 'user': 'neo4j', 'password': 'secret'})
    c = client.post('/api/settings/neo4j/connect')
    # Connect may fail (no driver/server). We only assert a well-formed JSON with 'connected'
    assert c.status_code in (200, 400, 501, 502)
    cdata = c.get_json()
    assert 'connected' in cdata
    # Now disconnect should set connected to False regardless
    d = client.post('/api/settings/neo4j/disconnect')
    assert d.status_code == 200
    ddata = d.get_json()
    assert ddata.get('connected') is False
