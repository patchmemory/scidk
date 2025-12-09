def test_graphrag_disabled_error_envelope(client, monkeypatch):
    # Ensure disabled, then check normalized error
    monkeypatch.delenv('SCIDK_GRAPHRAG_ENABLED', raising=False)
    rv = client.post('/api/chat/graphrag', json={'message': 'x'})
    assert rv.status_code == 501
    data = rv.get_json()
    assert data.get('status') == 'disabled'
    assert data.get('code') == 'GR_DISABLED'
    assert 'hint' in data


def test_graphrag_refresh_disabled_error_envelope(client, monkeypatch):
    monkeypatch.delenv('SCIDK_GRAPHRAG_ENABLED', raising=False)
    rv = client.post('/api/chat/context/refresh')
    assert rv.status_code == 501
    data = rv.get_json()
    assert data.get('status') == 'disabled'
    assert data.get('code') == 'GR_DISABLED'
