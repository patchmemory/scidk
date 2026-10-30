"""Actual legacy LabelService with explicit authority; no graph needed."""
import sqlite3
import pytest
from flask import Flask
from scidk.core.auth import AuthManager
from scidk.core import path_index_sqlite as pix
from scidk.core.migrations import migrate
from scidk.services.graph_management_policy import ManagementPolicyStore, connection_key
from scidk.web.auth_middleware import init_auth_middleware
from scidk.web.routes.api_labels import bp


@pytest.fixture
def management(tmp_path, monkeypatch):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.sqlite'))
    monkeypatch.setenv('NEO4J_AUTH', 'none')
    pix.init_db(); migrate()
    db = str(tmp_path / 'settings.sqlite')
    auth = AuthManager(db)
    admin = auth.create_user('admin', 'disposable-password', role='admin')
    user = auth.create_user('researcher', 'disposable-password', role='user')
    app = Flask(__name__)
    app.config.update(SCIDK_SETTINGS_DB=db)
    cfg = dict(uri='bolt://127.0.0.1:59998', user=None, database='neo4j')
    app.extensions['scidk'] = dict(neo4j_config=cfg)
    target = connection_key(cfg['uri'], None, 'neo4j', 'none')
    app.config['SCIDK_DEVELOPMENT_GRAPH_CONNECTIONS'] = [target]
    app.register_blueprint(bp); init_auth_middleware(app)
    policy = ManagementPolicyStore(db); policy.initialize(admin_id=admin)
    client = app.test_client()
    token = auth.create_user_session(user, 'researcher')
    client.set_cookie('scidk_session', token)
    yield app, client, auth, policy, admin, user, target, token
    auth.close()


BODY = dict(name='SyntheticSample', properties=[dict(name='name', type='string')], relationships=[])


def test_explicit_grants_and_destructive_confirmation(management):
    app, client, auth, policy, admin, user, target, _ = management
    assert client.post('/api/labels', json=BODY).status_code == 403
    policy.grant(user, target, 'graph_management_read', admin_id=admin)
    assert client.get('/api/labels').status_code == 200
    assert client.patch('/api/labels/SyntheticSample/instances/example', json={'property': 'name', 'value': 'denied'}).status_code == 403
    assert client.post('/api/labels', json=BODY).status_code == 403
    policy.grant(user, target, 'graph_schema_write', admin_id=admin)
    assert client.post('/api/labels', json=BODY).status_code == 200
    assert client.get('/api/labels/SyntheticSample').json['label']['name'] == 'SyntheticSample'
    assert client.delete('/api/labels/SyntheticSample').status_code == 403
    assert client.delete('/api/labels/SyntheticSample', headers={
        'X-SciDK-Confirm': 'destructive-shared-change'}).status_code == 200
    policy.grant(user, target, 'graph_schema_write', admin_id=admin, allow=False)
    assert client.post('/api/labels', json=BODY).status_code == 403
    with sqlite3.connect(app.config['SCIDK_SETTINGS_DB']) as conn:
        assert conn.execute("SELECT revision,enabled FROM graph_management_grant WHERE permission='graph_schema_write'").fetchone() == (2, 0)


@pytest.mark.parametrize('case', ['cross_origin', 'cross_site', 'header', 'anonymous', 'disabled', 'locked', 'changed_graph', 'admin', 'no_auth', 'api_token'])
def test_reject_invalid_management_sessions(management, case):
    app, client, auth, policy, admin, user, target, token = management
    for permission in ('graph_management_read', 'graph_schema_write'):
        policy.grant(user, target, permission, admin_id=admin)
    headers = {}
    if case == 'cross_origin': headers['Origin'] = 'https://elsewhere.invalid'
    if case == 'cross_site': headers['Sec-Fetch-Site'] = 'cross-site'
    if case == 'header': headers['Authorization'] = 'Bearer ' + token
    if case == 'anonymous': client = app.test_client()
    if case == 'api_token':
        client.set_cookie('scidk_session', auth.create_api_token(user, 'synthetic')['token'])
    if case == 'admin': client.set_cookie('scidk_session', auth.create_user_session(admin, 'admin'))
    if case == 'changed_graph': app.extensions['scidk']['neo4j_config']['database'] = 'other'
    if case == 'locked': auth.lock_session(token)
    if case in {'disabled', 'no_auth'}:
        with sqlite3.connect(app.config['SCIDK_SETTINGS_DB']) as conn:
            conn.execute('UPDATE auth_users SET enabled=0' + (' WHERE id=?' if case == 'disabled' else ''),
                         (user,) if case == 'disabled' else ())
    assert client.post('/api/labels', json=BODY, headers=headers).status_code == 403


def test_scopes_and_identifier_validation(management):
    app, client, _, policy, admin, user, target, _ = management
    for permission in ('graph_management_read', 'graph_entity_write', 'graph_schema_write'):
        policy.grant(user, target, permission, admin_id=admin)
    assert client.post('/api/labels', json={**BODY, 'name': 'X) MATCH (n) DELETE n //'}).status_code == 403
    app.config['SCIDK_DEVELOPMENT_GRAPH_CONNECTIONS'] = []
    assert client.get('/api/labels').status_code == 403


def test_graph_client_rechecks_actual_target(management):
    app, _, _, policy, admin, user, target, token = management
    policy.grant(user, target, 'graph_management_read', admin_id=admin)
    from scidk.services.neo4j_client import Neo4jClient
    from scidk.agent_tools.security import DisclosureDenied
    with app.test_request_context('/api/labels', headers={'Cookie': 'scidk_session=' + token}):
        with pytest.raises(DisclosureDenied):
            Neo4jClient('bolt://127.0.0.1:59997', None, None, 'neo4j', 'none').connect()
        from scidk.core.neo4j_graph import Neo4jGraph
        graph = object.__new__(Neo4jGraph)
        graph._uri, graph._auth, graph._db, graph._auth_mode = 'bolt://127.0.0.1:59997', None, 'neo4j', 'none'
        with pytest.raises(DisclosureDenied):
            graph._session()


def test_schema_removal_confirmation_and_unsafe_paths(management):
    _, client, _, policy, admin, user, target, _ = management
    for permission in ('graph_management_read', 'graph_schema_write', 'graph_entity_write'):
        policy.grant(user, target, permission, admin_id=admin)
    assert client.post('/api/labels', json=BODY).status_code == 200
    replacement = {**BODY, 'properties': []}
    assert client.post('/api/labels', json=replacement).status_code == 403
    assert client.post('/api/labels', json=replacement, headers={
        'X-SciDK-Confirm': 'destructive-shared-change'}).status_code == 200
    for path in ('/api/neo4j/query', '/api/links/discovered/import', '/api/links/x/run'):
        assert client.post(path, json={}).status_code == 403
    assert client.get('/api/labels/SyntheticSample/property-values/x%60%29').status_code == 403
    assert client.post('/api/neo4j/label-properties', json={'label': 'X) DELETE n //'}).status_code == 403


def test_manifest_is_explicit_and_does_not_grant(management, tmp_path, monkeypatch):
    import json
    from scidk.services.graph_management_policy import configure
    app, client, _, _, _, _, _, _ = management
    manifest = tmp_path / 'management.json'
    value = dict(development=True, uri='bolt://127.0.0.1:59998', database='neo4j', auth_mode='none')
    manifest.write_text(json.dumps(value))
    monkeypatch.setenv('SCIDK_GRAPH_MANAGEMENT_MANIFEST', str(manifest))
    configure(app)
    assert client.get('/api/labels').status_code == 403
    manifest.write_text(json.dumps({**value, 'development': False}))
    with pytest.raises(ValueError):
        configure(app)


def test_blueprint_alone_keeps_management_boundary(management):
    app, client, _, policy, admin, user, target, _ = management
    app.before_request_funcs[None] = []
    assert client.get('/api/labels').status_code == 403
    policy.grant(user, target, 'graph_management_read', admin_id=admin)
    assert client.get('/api/labels').status_code == 200
