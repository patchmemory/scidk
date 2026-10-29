import json

import pytest
from flask import Flask

from scidk.core.auth import get_auth_manager
from scidk.core.settings import InterpreterSettings
from scidk.curation.auth import GRANT_KEY, granted_user
from scidk.curation.review import ReviewService
from scidk.web.routes.api_curation import register_curation
from .test_foundation import foundation, submit_node


@pytest.fixture
def api(foundation, tmp_path):
    ledger, _, eid = foundation
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_CURATION_ENABLED=True,
                      SCIDK_SETTINGS_DB=str(tmp_path / 'settings.sqlite'))
    register_curation(app)
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])
    aid = submit_node(ledger, eid)['assertion_id']
    ledger.can_read_evidence = lambda actor, evidence: True
    app.extensions['curation_review'] = ReviewService(ledger, granted_user)
    return app, auth, aid


def grant(app, ids):
    settings = InterpreterSettings(app.config['SCIDK_SETTINGS_DB'])
    try:
        settings.db.execute('INSERT OR REPLACE INTO interpreter_settings(key,value) VALUES (?,?)',
                            (GRANT_KEY, json.dumps(ids)))
        settings.db.commit()
    finally:
        settings.close()


def login(client, auth, uid):
    user = auth.get_user(uid)
    token = auth.create_user_session(uid, user['username'])
    client.set_cookie('scidk_session', token)
    return token


def test_default_off_routes_absent(monkeypatch):
    monkeypatch.delenv('SCIDK_CURATION_ENABLED', raising=False)
    app = Flask(__name__)
    register_curation(app)
    assert app.test_client().post('/api/curation/assertions/any/review', json={}).status_code == 404


def test_auth_disabled_and_no_session_denied(api):
    app, auth, aid = api
    client = app.test_client()
    path = f'/api/curation/assertions/{aid}/preview'
    assert client.post(path).status_code == 401
    auth.create_user('admin', 'fixture-password', role='admin')
    assert client.post(path).status_code == 401


def test_explicit_admin_human_grant_and_audit(api):
    app, auth, aid = api
    uid = auth.create_user('reviewer', 'fixture-password', role='admin')
    client = app.test_client()
    login(client, auth, uid)
    path = f'/api/curation/assertions/{aid}'
    assert client.post(path + '/preview').status_code == 403
    grant(app, [uid])
    preview = client.post(path + '/preview')
    assert preview.status_code == 200
    preview = preview.json
    body = dict(action='accept', expected_revision=preview['expected_revision'],
                preview_digest=preview['preview_digest'], rationale='Human reviewed synthetic input')
    assert client.post(path + '/review', json=body).status_code == 200
    assert client.post(path + '/review', json=body).status_code == 409
    assert any(row['action'] == 'curation_review' for row in auth.get_audit_log())
    grant(app, [])
    assert client.post(path + '/preview').status_code == 403


def test_api_tokens_ordinary_users_and_cross_origin_denied(api):
    app, auth, aid = api
    uid = auth.create_user('admin', 'fixture-password', role='admin')
    ordinary = auth.create_user('reader', 'fixture-password', role='user')
    grant(app, [uid, ordinary])
    client = app.test_client()
    path = f'/api/curation/assertions/{aid}/preview'
    token = auth.create_api_token(uid, 'agent')['token']
    assert client.post(path, headers={'Authorization': 'Bearer ' + token}).status_code == 403
    login(client, auth, ordinary)
    assert client.post(path).status_code == 403
    login(client, auth, uid)
    assert client.post(path, headers={'Authorization': 'Bearer ' + token}).status_code == 403
    assert client.post(path, headers={'Origin': 'https://untrusted.invalid'}).status_code == 403
    assert client.post(path, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert client.post(path).status_code == 200


def test_malformed_input_and_no_raw_errors(api):
    app, auth, aid = api
    uid = auth.create_user('reviewer', 'fixture-password', role='admin')
    grant(app, [uid])
    client = app.test_client()
    login(client, auth, uid)
    path = f'/api/curation/assertions/{aid}/review'
    assert client.post(path, data='bad json', content_type='application/json').status_code == 400
    assert client.post(path, json={}).status_code == 422
    app.extensions['curation_review'].authorize_reviewer = lambda _: 1 / 0
    result = client.post(path, json={})
    assert result.status_code == 503
    assert 'division' not in result.text


def test_locked_disabled_and_legacy_sessions_denied(api):
    app, auth, aid = api
    uid = auth.create_user('reviewer', 'fixture-password', role='admin')
    grant(app, [uid])
    client = app.test_client()
    path = f'/api/curation/assertions/{aid}/preview'
    token = login(client, auth, uid)
    assert auth.lock_session(token)
    assert client.post(path).status_code == 403
    token = login(client, auth, uid)
    auth.update_user(uid, enabled=False)
    assert client.post(path).status_code == 401
    auth.update_user(uid, enabled=True)
    client.set_cookie('scidk_session', auth.create_session('legacy-reviewer'))
    assert client.post(path).status_code == 401


def test_grants_fail_closed_on_malformed_settings(api):
    app, auth, aid = api
    uid = auth.create_user('reviewer', 'fixture-password', role='admin')
    client = app.test_client()
    login(client, auth, uid)
    settings = InterpreterSettings(app.config['SCIDK_SETTINGS_DB'])
    try:
        for value in ('invalid-json', '{}', 'true', json.dumps([str(uid)]), '[true]'):
            settings.db.execute('INSERT OR REPLACE INTO interpreter_settings(key,value) VALUES (?,?)', (GRANT_KEY, value))
            settings.db.commit()
            assert client.post(f'/api/curation/assertions/{aid}/preview').status_code == 403
    finally:
        settings.close()
