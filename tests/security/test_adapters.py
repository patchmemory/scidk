import asyncio
import json

import pytest
from flask import Flask

from .test_disclosure import secured
from tests.curation.test_foundation import foundation
from scidk.agent_tools.security import REFUSAL


def test_http_chat_mcp_refusal_parity_before_any_query(secured, monkeypatch):
    from scidk.web.routes import api_agent, api_chat
    from scidk.agent_tools import context
    from scidk.mcp_server import ScidkMcpServer
    s = secured
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=s.db)
    app.register_blueprint(api_agent.bp)
    app.register_blueprint(api_chat.bp)
    monkeypatch.setattr(context, '_driver', lambda *a: pytest.fail('Graph driver initialized'))
    monkeypatch.setattr(api_chat, '_get_ext', lambda: pytest.fail('Legacy graph path executed'))
    client = app.test_client()
    headers = {'Authorization': 'Bearer ' + s.token['token'], 'X-Model': 'approved', 'X-Endpoint': 'approved'}
    http = client.post('/api/agent/tools/query_knowledge_graph', headers=headers,
                       json={'cypher': 'MATCH (n) RETURN count(n)'})
    assert http.json == REFUSAL
    for suffix in ('graphrag', 'graphrag/stream', 'graphrag/v2', 'graphrag/v2/stream', 'schema/refresh-embeddings'):
        chat = client.post('/api/chat/' + suffix, headers=headers, json={'message': 'secret question'})
        assert chat.json == http.json and chat.status_code == 403
    monkeypatch.setenv('SCIDK_SETTINGS_DB', s.db)
    from neo4j import GraphDatabase
    monkeypatch.setattr(GraphDatabase, 'driver', lambda *a, **kw: pytest.fail('MCP connection attempted'))
    mcp = ScidkMcpServer()
    assert mcp.dispatch('query_knowledge_graph', {'cypher': 'MATCH (n) RETURN count(n)'}) == http.json
    assert asyncio.run(mcp.query_knowledge_graph('RETURN 1')) == http.json
    assert asyncio.run(mcp.get_schema()) == http.json
    assert asyncio.run(mcp.list_labels()) == http.json


def test_http_ignores_claimed_destination_and_user(secured):
    from scidk.web.routes.api_agent import bp
    s = secured
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=s.db)
    app.register_blueprint(bp)
    client = app.test_client()
    assert client.post('/api/agent/tools/scan_summary', headers={
        'Authorization': 'Bearer ' + s.token['token'], 'X-User': 'admin', 'X-Destination': 'parley'}, json={}).json == REFUSAL
    # Revoked/unrecognized bearer credentials cannot be authenticated by the
    # existing decorators, regardless of caller-supplied identity headers.
    response = client.post('/api/agent/tools/scan_summary', headers={'Authorization': 'Bearer invalid',
                                                                  'X-User': 'alice'}, json={})
    assert response.status_code == 401


def test_embedding_helpers_refuse_unscoped_text_without_network(monkeypatch):
    import requests
    from scidk.services import schema_intelligence, concept_graph_service
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: pytest.fail('Embedding content sent'))
    assert schema_intelligence.embed_text('private schema', 'http://localhost:11434') is None
    assert concept_graph_service.embed_text('private example', 'http://localhost:11434') is None


def test_provider_redirect_cannot_forward_approved_content(monkeypatch):
    from scidk.ai import openai_compatible
    calls = []
    class Redirect:
        status_code = 307
        ok = True
    def post(*args, **kwargs):
        calls.append(kwargs)
        return Redirect()
    monkeypatch.setattr(openai_compatible.requests, 'post', post)
    with pytest.raises(openai_compatible.ProviderError, match='redirect refused'):
        openai_compatible.chat_completion('https://approved.example/v1', None, 'm', [{'role': 'user', 'content': 'fixture'}])
    assert len(calls) == 1 and calls[0]['allow_redirects'] is False


def test_api_tokens_cannot_read_human_api_or_change_policy(secured):
    from scidk.web.auth_middleware import init_auth_middleware
    s = secured
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=s.db)
    init_auth_middleware(app)
    @app.route('/api/private-graph', methods=['GET'])
    def private_graph():
        return {'secret': 'human-only fixture'}
    @app.route('/api/settings/security/auth', methods=['POST'])
    def public_bootstrap():
        pytest.fail('API token reached bootstrap configuration')
    client = app.test_client()
    # Covers both unbound and bound tokens, including an admin token.
    for token in (s.token, s.auth.create_api_token(s.admin, 'admin integration')):
        headers = {'Authorization': 'Bearer ' + token['token']}
        assert client.get('/api/private-graph', headers=headers).json == REFUSAL
        assert client.post('/api/settings/security/auth', headers=headers, json={}).json == REFUSAL
    # An explicit named human session still uses the existing human API.
    session = s.auth.create_user_session(s.alice, 'alice')
    client.set_cookie('scidk_session', session)
    assert client.get('/api/private-graph').json == {'secret': 'human-only fixture'}
    # A cookie must not hide an accompanying external-client token.
    assert client.get('/api/private-graph', headers={'Authorization': 'Bearer ' + s.token['token']}).json == REFUSAL
