"""Production app factory with disposable integrated hook and actual GUI routes."""
import threading

import pytest
from flask import request
from playwright.sync_api import expect
from werkzeug.serving import make_server

from scidk.core.auth import AuthManager
from scidk.dev_gui import build_app
from scidk.ai import provider_settings
from scidk.agent_tools.security import PolicyStore
from tests.knowledge_e2e.test_prompt15 import fake_provider


@pytest.fixture
def gui_server(tmp_path, monkeypatch, fake_provider):
    for name in ('NEO4J_URI', 'BOLT_URI', 'CHAT_NEO4J_URI', 'SCIDK_CONCEPT_NEO4J_URI',
                 'NEO4J_AUTH', 'CHAT_NEO4J_AUTH', 'SCIDK_CONCEPT_NEO4J_AUTH'):
        monkeypatch.delenv(name, raising=False)
    for name in ('SCIDK_SETTINGS_DB', 'SCIDK_DB_PATH', 'SCIDK_SCAN_DB_DIR', 'SCIDK_ROCRATE_DIR',
                 'SCIDK_DISABLE_SCHEDULER', 'SCIDK_CONCEPT_GRAPH_ENABLED', 'SCIDK_GRAPH_BACKEND',
                 'PYTHON_DOTENV_DISABLED'):
        monkeypatch.setenv(name, '')
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / 'scidk_settings.db')
    auth = AuthManager(db)
    uid = auth.create_user('demo-admin', 'synthetic-password', role='admin')
    app = build_app(tmp_path, configure='scidk.dev_integrated_demo:seed_reviewed')
    app.extensions['gui_test_requests'] = []
    app.extensions['prompt17_session'] = auth.create_user_session(uid, 'demo-admin')
    app.extensions['prompt17_fake'] = fake_provider

    @app.before_request
    def record_request():
        app.extensions['gui_test_requests'].append((request.method, request.full_path))

    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', app
    server.shutdown(); thread.join(timeout=5); server.server_close(); auth.close()


@pytest.mark.parametrize('viewport', [(1440, 900), (1024, 768)])
def test_integrated_files_knowledge_review_ask_sharing(gui_page, gui_artifacts, viewport):
    page, origin, app = gui_page
    page.context.add_cookies([{'name': 'scidk_session', 'value': app.extensions['prompt17_session'], 'url': origin}])
    page.set_viewport_size(dict(width=viewport[0], height=viewport[1]))
    suffix = f'{viewport[0]}x{viewport[1]}'

    def capture(name):
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(gui_artifacts / f'prompt17-{name}-{suffix}.png'), full_page=True)

    page.goto(origin + '/demo/prompt17')
    expect(page.get_by_role('heading', name='Synthetic integrated demonstration')).to_be_visible()
    page.goto(origin + '/datasets')
    page.get_by_role('tab', name='Datasets', exact=True).click()
    page.locator('#dataset-query').fill('Synthetic')
    page.locator('#dataset-search button').click()
    page.locator('#dataset-results button').click()
    expect(page.locator('#inspector-title')).to_contain_text('Synthetic MRI microCT phantom study')
    capture('datasets')
    page.locator('#sharing-start').click()
    page.locator('#sharing-preview').click()
    expect(page.locator('#sharing-draft')).to_contain_text('NIH DMS')
    capture('sharing')
    with page.expect_download() as download:
        page.locator('#sharing-download').click()
    assert download.value.suggested_filename == 'dataset-sharing-draft.zip'
    page.locator('#dataset-knowledge').click()
    expect(page.locator('#kw-inspection')).to_contain_text('Synthetic MRI microCT phantom study')
    capture('knowledge-graph')
    page.get_by_role('tab', name='Entities', exact=True).click()
    capture('knowledge-entities')
    page.get_by_role('tab', name='Sketch', exact=True).click()
    capture('knowledge-sketch')
    pending = app.extensions['prompt17_demo']['pending']
    page.goto(origin + '/review?id=' + pending)
    # Review accepts entity context as well as assertion IDs; choose the pending item.
    page.locator('#rw-queue button').first.click()
    expect(page.locator('#rw-evidence')).to_contain_text('Fictional MRI/microCT')
    page.locator('#rw-prepare').click()
    expect(page.locator('#rw-decision')).to_be_visible()
    capture('review')
    page.locator('#rw-action').select_option('reject')
    page.locator('#rw-rationale').fill('Synthetic demonstration: retain original reviewed name')
    page.locator('#rw-confirm').check()
    page.locator('#rw-decide').click()
    expect(page.locator('#rw-summary')).to_contain_text('rejected')
    # Configure only the test's loopback fake, after provider-independent reads.
    endpoint, calls = app.extensions['prompt17_fake']
    db = app.config['SCIDK_SETTINGS_DB']
    auth = AuthManager(db)
    uid = auth.get_user_by_username('demo-admin')['id']
    auth.close()
    provider_settings.save(db, 'demo-admin', base_url=endpoint, model='synthetic-model')
    PolicyStore(db).approve_destination('test-loopback', endpoint, 'synthetic-model', 'low', admin_id=uid)
    page.goto(origin + '/overview')
    page.get_by_label('Your question').fill('Find synthetic phantom')
    page.locator('#overview-consent').check()
    page.get_by_role('button', name='Ask SciDK', exact=True).click()
    expect(page.locator('#overview-answer')).to_contain_text('Synthetic System context')
    assert calls and page.locator('#overview-source-links a').count() >= 1
    capture('overview')
    page.goto(origin + '/pipeline/sources')
    expect(page.get_by_role('heading', name='Resources', exact=True)).to_be_visible()
    capture('resources')
