def test_graphrag_observability_endpoint(client, monkeypatch):
    # By default disabled; endpoint should still return ok with structure
    monkeypatch.delenv('SCIDK_GRAPHRAG_ENABLED', raising=False)
    rv = client.get('/api/chat/observability/graphrag')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data.get('status') == 'ok'
    assert 'enabled' in data
    assert 'llm_provider' in data
    assert 'model' in data
    assert 'schema' in data and isinstance(data['schema'], dict)
    assert 'labels_count' in data['schema']
    assert 'relationships_count' in data['schema']
    assert 'audit' in data and isinstance(data['audit'], list)
