"""Focused runtime provisioning, redaction and management boundary checks."""
import argparse
import json
import os
import sqlite3
import pytest
from tests.security.test_graph_management import management  # noqa: F401
from scidk.live_development import initialize, load, owned_process


def test_explicit_private_provisioning_and_connection_drift(tmp_path):
    source = tmp_path / '.env'
    source.write_text('NEO4J_URI=bolt://127.0.0.1:59998\nNEO4J_USER=dev\nNEO4J_PASSWORD=private-secret\n')
    state = tmp_path / 'operator-state'
    args = argparse.Namespace(confirm_development_source=True, grant_read=False,
        source_env=str(source), database='neo4j', operator='operator', port=5010)
    with pytest.raises(ValueError):
        initialize(state, args)
    assert not state.exists()
    args.grant_read = True
    initialize(state, args)
    assert state.stat().st_mode & 0o777 == 0o700
    assert (state / 'operator-login.json').stat().st_mode & 0o777 == 0o600
    assert 'private-secret' not in (state / 'runtime.json').read_text()
    assert 'private-secret' not in (state / 'management.json').read_text()
    with sqlite3.connect(state / 'scidk_settings.db') as c:
        assert c.execute('SELECT permission FROM graph_management_grant').fetchall() == [('graph_management_read',)]
    load(state)
    with pytest.raises(FileExistsError):
        initialize(state, args)
    source.write_text(source.read_text().replace('59998', '59997'))
    with pytest.raises(ValueError):
        load(state)


def test_refuse_foreign_pid(tmp_path):
    (tmp_path / 'process.json').write_text(json.dumps(dict(pid=os.getpid(), start_ticks='0')))
    with pytest.raises(ValueError):
        owned_process(tmp_path)


def test_connection_identity_requires_grant_and_is_redacted(management):
    from scidk.web.routes.ui import bp
    app, client, _, policy, admin, user, target, _ = management
    app.register_blueprint(bp)
    assert client.get('/api/graph/management-connection').status_code == 403
    policy.grant(user, target, 'graph_management_read', admin_id=admin)
    response = client.get('/api/graph/management-connection')
    assert response.status_code == 200
    connection = response.json['connection']
    assert connection['connection_id'] == target
    assert connection['id'] == 'PRIMARY' and connection['backend'] == 'Neo4j'
    assert connection['raw_query_execution'] is False
    assert '59998' not in response.get_data(as_text=True)
    assert 'uri' not in connection and 'user' not in connection
    assert client.post('/api/development/readiness', json={}).status_code == 403


def test_admin_readiness_does_not_bypass_management_grant(management):
    from scidk.web.routes.ui import bp
    app, client, auth, _, admin, _, _, _ = management
    app.register_blueprint(bp)
    client.set_cookie('scidk_session', auth.create_user_session(admin, 'admin'))
    response = client.post('/api/development/readiness', json={})
    assert response.status_code == 200
    checks = response.json['checks']
    assert checks['graph']['status'] == 'configured_but_unauthorized'
    assert checks['graph']['reachability'] == 'not_probed'
    assert checks['ai']['disclosure_approved'] is False
    assert '59998' not in response.get_data(as_text=True)
    assert client.post('/api/development/readiness', json={}, headers={'Origin':'https://foreign.invalid'}).status_code == 403


def test_live_profile_blocks_legacy_graph_write_paths():
    from flask import Flask
    from scidk.live_development import read_only_request
    app = Flask(__name__)
    for path in ('/api/pipeline/sources/x/run', '/api/graph/commit', '/api/settings/neo4j',
                 '/api/llm/import-parley-env', '/api/neo4j/query', '/api/chat'):
        with app.test_request_context(path, method='POST', json={}):
            assert read_only_request()[1] == 403
    with app.test_request_context('/api/llm/settings', method='PUT', json={}):
        assert read_only_request() is None
    with app.test_request_context('/api/llm/test', method='POST', json={}):
        assert read_only_request() is None
    with app.test_request_context('/api/settings/neo4j/profiles', method='POST', json={}):
        assert read_only_request() is None
    for method, path in (('DELETE', '/api/settings/neo4j/profiles/x'), ('PUT', '/api/settings/neo4j/profiles/x/activate'),
                         ('POST', '/api/settings/neo4j/profiles/x')):
        with app.test_request_context(path, method=method, json={}):
            assert read_only_request()[1] == 403
    for path in ('/api/auth/login', '/api/development/readiness', '/api/canvas/session',
                 '/api/graph/query', '/api/canvas/nodes/expand', '/api/canvas/nodes/verify',
                 '/api/chat/overview', '/admin/chat-readiness'):
        with app.test_request_context(path, method='POST', json={}):
            assert read_only_request() is None
