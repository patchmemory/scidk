"""Prompt 15 browser readiness and real transport over isolated synthetic state."""
import threading

import pytest
from flask import g, jsonify, request
from jinja2 import FileSystemLoader
from playwright.sync_api import expect
from werkzeug.serving import make_server

from tests.knowledge_e2e.conftest import scenario, ROOT
from tests.knowledge_e2e.test_prompt15 import ready_app, fake_provider
from scidk.ai import provider_settings


@pytest.fixture
def gui_server(ready_app, fake_provider):
    d, _ = ready_app
    endpoint, calls = fake_provider
    d.policy.approve_destination('browser-fake', endpoint, 'synthetic-model', 'medium', admin_id=d.reviewer)
    provider_settings.save(d.db, 'reviewer', base_url=endpoint, model='synthetic-model')
    app = d.app
    app.jinja_loader = FileSystemLoader(str(ROOT / 'scidk/ui/templates'))
    app.static_folder = str(ROOT / 'scidk/ui/static')
    app.extensions['gui_test_requests'] = []
    app.extensions['prompt15_fixture'] = (d, calls)

    @app.before_request
    def track():
        app.extensions['gui_test_requests'].append((request.method, request.full_path))

    @app.get('/favicon.ico')
    def favicon():
        return app.send_static_file('favicon.ico')

    @app.get('/api/auth/status')
    def status():
        return jsonify(authenticated=True, auth_enabled=True, username=getattr(g, 'scidk_user', 'reviewer'))

    @app.get('/api/settings/security/auto-lock')
    def lock():
        return jsonify(config={'enabled': False})

    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', app
    server.shutdown(); thread.join(timeout=5); server.server_close()


def login(page, origin, d, name='reviewer'):
    page.context.add_cookies([{'name': 'scidk_session', 'value': d.auth.create_user_session(getattr(d, name), name), 'url': origin}])


def test_readiness_and_system_fake_provider(gui_page, gui_artifacts):
    page, origin, app = gui_page
    d, calls = app.extensions['prompt15_fixture']
    login(page, origin, d)
    page.goto(origin + '/admin/chat-readiness')
    page.get_by_label('Selected stable context ID (optional)').fill('system:synthetic-demo')
    page.get_by_role('button', name='Check readiness').click()
    expect(page.locator('#readiness-status')).to_contain_text('Configured for the selected bounded context')
    expect(page.locator('#readiness-checks')).to_contain_text('Ready: approved_provider')
    assert not calls
    page.screenshot(path=str(gui_artifacts / 'prompt15-admin-readiness.png'), full_page=True)
    page.goto(origin + '/overview')
    page.get_by_label('Your question').fill('Explain this synthetic System context.')
    page.get_by_label('Source context', exact=True).select_option('get_system_context')
    page.get_by_label('Fact or context node ID').fill('system:synthetic-demo')
    page.locator('#overview-consent').check()
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#overview-answer')).to_contain_text('Synthetic System context')
    assert len(calls) == 1 and 'tools' not in calls[0][1]
    page.screenshot(path=str(gui_artifacts / 'prompt15-system-fake-chat.png'), full_page=True)
    app.config['SCIDK_OVERVIEW_CHAT_ENABLED'] = False
    page.reload()
    expect(page.get_by_label('Your question')).to_be_disabled()
    assert len(calls) == 1


def test_readiness_nonadmin_and_disabled(gui_page):
    page, origin, app = gui_page
    d, calls = app.extensions['prompt15_fixture']
    login(page, origin, d, 'alice')
    page.gui_expected_http.add('/admin/chat-readiness')
    page.goto(origin + '/admin/chat-readiness')
    assert page.locator('#readiness-form').count() == 0
    login(page, origin, d)
    app.config['SCIDK_CHAT_READINESS_ENABLED'] = False
    page.goto(origin + '/admin/chat-readiness')
    assert page.locator('#readiness-form').count() == 0 and not calls
