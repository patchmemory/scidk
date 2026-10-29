"""Actual synthetic demo assembly, reviewer decisions and simulated application."""
import io
import sqlite3
import zipfile
import subprocess

import pytest
from flask import Flask

from scidk.core.auth import AuthManager
from scidk.dev_integrated_demo import seed_reviewed, configure
from scidk.web.routes.ui import bp
from scidk.web.auth_middleware import init_auth_middleware
from scidk.agent_tools.security import REFUSAL
from scidk.services.human_policy import HumanPolicyStore


def make_app(state):
    app = Flask(__name__)
    app.config.update(TESTING=True, SCIDK_SETTINGS_DB=str(state / 'settings.sqlite'),
        SCIDK_GUI_V3_ENABLED=True, SCIDK_KNOWLEDGE_CONTEXT_ENABLED=True,
        SCIDK_CURATION_ENABLED=True, SCIDK_REVIEW_WORKSPACE_ENABLED=True,
        SCIDK_OVERVIEW_CHAT_ENABLED=True, SCIDK_DATASET_SHARING_ENABLED=True)
    app.register_blueprint(bp)
    from scidk.web.routes.api_chat import bp as chat_bp
    app.register_blueprint(chat_bp)
    init_auth_middleware(app)
    return app


@pytest.fixture
def integrated(tmp_path):
    app = make_app(tmp_path)
    auth = AuthManager(app.config['SCIDK_SETTINGS_DB'])
    uid = auth.create_user('demo-admin', 'synthetic-password', role='admin')
    seed_reviewed(app)
    client = app.test_client()
    client.set_cookie('scidk_session', auth.create_user_session(uid, 'demo-admin'))
    yield app, client, auth, uid
    auth.close()


def test_demo_current_legacy_review_sharing_and_restart(integrated):
    app, client, auth, uid = integrated
    info = app.extensions['prompt17_demo']
    search = client.post('/api/knowledge/research/search', json={})
    assert search.status_code == 200, search.json
    nodes = search.json['result']['nodes']
    assert {n['curation_status'] for n in nodes} == {'accepted', 'legacy/unreviewed'}
    legacy = next(n for n in nodes if n['curation_status'] == 'legacy/unreviewed')
    assert legacy['support'] == [] and legacy['materialization_status'] == 'unverified'
    current = client.post('/api/knowledge/research/expand', json={'id': info['dataset']})
    assert len(current.json['result']['edges']) == 2
    assert len(current.json['result']['nodes']) == 3
    queue = client.post('/api/review/queue', json={'status': 'proposed'})
    assert [i['assertion_id'] for i in queue.json['result']['items']] == [info['pending']]
    sharing = '/api/plugins/nih_dms/datasets/' + info['dataset'] + '/prepare'
    draft = client.post(sharing, json={})
    assert draft.status_code == 200, draft.json
    assert len(draft.json['snapshot']['files']) == 2
    download = client.post(sharing, json={'download': True})
    assert download.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(download.data))
    assert any(name.endswith('.ps1') for name in archive.namelist())
    assert any(name.endswith('.sh') for name in archive.namelist())
    package_dir = info['ledger'].path.parent / 'package'
    archive.extractall(package_dir)
    destination = info['ledger'].path.parent / 'staged'
    copied = subprocess.run(['bash', str(package_dir / 'prepare.sh'), info['source_root'], str(destination)],
                            input='COPY\n', text=True, capture_output=True)
    assert copied.returncode == 0, copied.stderr
    for relative in ('MRI/phantom.txt', 'microCT/phantom.txt'):
        from pathlib import Path
        assert (destination / relative).read_bytes() == (Path(info['source_root']) / relative).read_bytes()
    assert client.post('/api/chat/overview', json={'message': 'Find synthetic phantom',
        'send_question': True, 'scope': 'accessible'}).json == REFUSAL
    with sqlite3.connect(info['ledger'].path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM decisions').fetchone()[0] == 12
        assert conn.execute("SELECT COUNT(*) FROM receipts WHERE outcome='applied'").fetchone()[0] == 12
    restarted = make_app(info['ledger'].path.parent)
    configure(restarted)
    assert restarted.extensions['prompt17_demo']['graph'].nodes == info['graph'].nodes
    assert restarted.extensions['prompt17_demo']['graph'].markers == {
        key: list(value) for key, value in info['graph'].markers.items()}
    with pytest.raises(ValueError, match='fresh'):
        seed_reviewed(restarted)


def test_demo_ordinary_user_requires_explicit_record_and_source_grants(integrated):
    app, _, auth, admin = integrated
    uid = auth.create_user('researcher', 'synthetic-password', role='user')
    client = app.test_client()
    client.set_cookie('scidk_session', auth.create_user_session(uid, 'researcher'))
    endpoint = '/api/knowledge/research/search'
    assert client.post(endpoint, json={}).json == REFUSAL
    human = HumanPolicyStore(app.config['SCIDK_SETTINGS_DB'])
    human.grant_purpose(uid, 'research_browse', 'low', admin_id=admin)
    assert client.post(endpoint, json={}).json['result']['nodes'] == []
    from scidk.dev_system_demo import RESOURCE
    human.grant_resource(uid, **RESOURCE, admin_id=admin)
    assert client.post(endpoint, json={}).json['result']['nodes'] == []
    info = app.extensions['prompt17_demo']
    human.grant_evidence(uid, info['evidence'], admin_id=admin)
    nodes = client.post(endpoint, json={}).json['result']['nodes']
    assert any(n['curation_status'] == 'accepted' for n in nodes)
    assert not any(n['curation_status'] == 'legacy/unreviewed' for n in nodes)
    legacy = app.extensions['knowledge_services'].legacy
    for ref in legacy._records:
        human.grant_evidence(uid, ref, admin_id=admin)
    assert any(n['curation_status'] == 'legacy/unreviewed' for n in client.post(endpoint, json={}).json['result']['nodes'])
