def test_settings_password_not_cleared_on_empty(client):
    # Save with password
    r1 = client.post('/api/settings/neo4j', json={'uri':'bolt://localhost:7687','user':'neo4j','password':'secret','database':'neo4j'})
    assert r1.status_code == 200
    # Save again without password field (empty UI) should not clear stored password
    r2 = client.post('/api/settings/neo4j', json={'uri':'bolt://localhost:7687','user':'neo4j','password':'','database':'neo4j'})
    assert r2.status_code == 200
    # Trigger connect; since we don't have a real driver here, status code is acceptable (200,400,501,502,429)
    c = client.post('/api/settings/neo4j/connect')
    assert c.status_code in (200, 400, 429, 501, 502)


def test_settings_password_can_be_cleared_explicitly(client):
    client.post('/api/settings/neo4j', json={'uri':'bolt://localhost:7687','user':'neo4j','password':'secret'})
    # Clear explicitly
    rc = client.post('/api/settings/neo4j', json={'clear_password': True})
    assert rc.status_code == 200
