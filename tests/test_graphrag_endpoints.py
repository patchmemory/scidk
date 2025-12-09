import os

def test_graphrag_capabilities_disabled(client, monkeypatch):
    monkeypatch.delenv('SCIDK_GRAPHRAG_ENABLED', raising=False)
    rv = client.get('/api/chat/capabilities')
    assert rv.status_code == 200
    data = rv.get_json()
    assert 'graphrag' in data
    assert data['graphrag']['enabled'] in (False, 0)


def test_graphrag_post_disabled(client, monkeypatch):
    monkeypatch.delenv('SCIDK_GRAPHRAG_ENABLED', raising=False)
    rv = client.post('/api/chat/graphrag', json={'message': 'hello'})
    assert rv.status_code == 501
    data = rv.get_json()
    assert data.get('status') == 'disabled'
    assert 'SCIDK_GRAPHRAG_ENABLED' in (data.get('hint') or '')


def test_chat_history_endpoint(client):
    # should exist and return structure
    rv = client.get('/api/chat/history')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data.get('status') == 'ok'
    assert isinstance(data.get('history'), list)
