def test_api_chat_echo(client):
    # First message
    resp1 = client.post('/api/chat', json={'message': 'Hello'})
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1['status'] == 'ok'
    assert data1['reply'].startswith('Echo:')
    assert len(data1['history']) == 2  # user + assistant

    # Second message should append
    resp2 = client.post('/api/chat', json={'message': 'How are you?'})
    data2 = resp2.get_json()
    assert len(data2['history']) == 4
