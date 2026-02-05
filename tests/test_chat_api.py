import os
import pytest


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


def test_api_chat_missing_message(client):
    resp = client.post('/api/chat', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['status'] == 'error'
    assert 'message required' in data['error']


def test_api_chat_history(client):
    # Post a message first
    client.post('/api/chat', json={'message': 'Test'})

    # Get history
    resp = client.get('/api/chat/history')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert 'history' in data
    assert len(data['history']) >= 2


def test_api_chat_capabilities(client):
    resp = client.get('/api/chat/capabilities')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'graphrag' in data
    assert 'enabled' in data['graphrag']
    assert 'llm_provider' in data['graphrag']
    assert 'model' in data['graphrag']


def test_api_chat_graphrag_disabled_by_default(client):
    # GraphRAG should be disabled without SCIDK_GRAPHRAG_ENABLED
    resp = client.post('/api/chat/graphrag', json={'message': 'Test query'})
    assert resp.status_code == 501
    data = resp.get_json()
    assert data['status'] == 'disabled'
    assert 'SCIDK_GRAPHRAG_ENABLED' in data.get('hint', '')


def test_api_chat_graphrag_missing_message(client, monkeypatch):
    monkeypatch.setenv('SCIDK_GRAPHRAG_ENABLED', '1')
    resp = client.post('/api/chat/graphrag', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['status'] == 'error'
    assert 'message required' in data['error']


def test_api_chat_context_refresh_disabled(client):
    resp = client.post('/api/chat/context/refresh')
    assert resp.status_code == 501
    data = resp.get_json()
    assert data['status'] == 'disabled'


def test_api_chat_observability_graphrag(client):
    resp = client.get('/api/chat/observability/graphrag')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert 'enabled' in data
    assert 'llm_provider' in data
    assert 'model' in data
    assert 'schema' in data
    assert 'audit' in data
    assert isinstance(data['audit'], list)
