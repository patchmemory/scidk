"""Review browser workflows over actual isolated ledger/policy/review services."""
import json
import re
import threading
from urllib.parse import unquote

import pytest
from flask import g, jsonify, request
from jinja2 import FileSystemLoader
from playwright.sync_api import expect
from werkzeug.serving import make_server

from tests.knowledge_e2e.conftest import scenario, ROOT
from tests.knowledge_e2e.test_review_workspace import review_workspace


@pytest.fixture
def gui_server(review_workspace, monkeypatch):
    d, _, records, hidden = review_workspace
    app = d.app
    app.jinja_loader = FileSystemLoader(str(ROOT / 'scidk/ui/templates'))
    app.static_folder = str(ROOT / 'scidk/ui/static')
    app.extensions['gui_test_requests'] = []
    app.extensions['review_fixture'] = (d, records, hidden)

    @app.before_request
    def track():
        app.extensions['gui_test_requests'].append((request.method, request.full_path))

    @app.get('/api/auth/status')
    def auth_status():
        return jsonify(authenticated=True, auth_enabled=True, username=getattr(g, 'scidk_user', 'reviewer'))

    @app.get('/api/settings/security/auto-lock')
    def lock_config():
        return jsonify(status='success', config={'enabled': False})

    def provider(*args, **kwargs):
        return {'content': 'Synthetic assistant: this inferred proposal requires human evidence review.'}
    monkeypatch.setattr('scidk.services.overview_chat.chat_completion', provider)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', app
    server.shutdown(); thread.join(timeout=5); server.server_close()


def open_review(gui_page, principal='reviewer', context=None):
    page, origin, app = gui_page
    d, records, hidden = app.extensions['review_fixture']
    if principal == 'alice':
        from tests.knowledge_e2e.test_prompt12 import session
        session(d)
    page.context.add_cookies([{'name': 'scidk_session', 'value': d.auth.create_user_session(getattr(d, principal), principal), 'url': origin}])
    path = '/review' + ('?domain=research&id=' + records[context]['assertion_id'] if context else '')
    page.goto(origin + path)
    expect(page.locator('#rw-status')).not_to_contain_text('Loading')
    return page, d, records, hidden


@pytest.mark.parametrize('viewport', [(1440, 900), (1280, 800), (1024, 768)])
def test_review_queue_inspector_keyboard_and_screenshots(gui_page, gui_artifacts, viewport):
    page, _, records, hidden = open_review(gui_page)
    page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
    page.get_by_label('Assertion kind', exact=True).select_option('relationship')
    page.get_by_role('button', name='Apply filters', exact=True).click()
    expect(page.locator('#rw-queue button')).to_have_count(1)
    item = page.locator('#rw-queue button'); item.focus(); page.keyboard.press('Enter')
    expect(page.locator('#rw-detail-heading')).to_be_focused()
    expect(page.locator('#rw-summary')).to_contain_text('inferred')
    expect(page.locator('#rw-claim')).to_contain_text('PI_OF')
    expect(page.locator('#rw-evidence')).to_contain_text('Synthetic intake')
    assert all(row['assertion_id'] not in page.locator('#review-workspace').inner_text() for row in hidden.values())
    expect(page.locator('#rw-return')).to_have_attribute('href', re.compile('/knowledge\\?domain=research&id='))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # Every form field is explicitly labelled; native controls support keyboard.
    assert page.locator('#review-workspace input, #review-workspace select, #review-workspace textarea').evaluate_all(
        'fields => fields.every(field => field.labels.length > 0)')
    page.screenshot(path=str(gui_artifacts / f'review-inspector-{viewport[0]}x{viewport[1]}.png'), full_page=True)
    page.get_by_label('Status', exact=True).select_option('accepted')
    page.get_by_role('button', name='Apply filters', exact=True).click()
    expect(page.locator('#rw-status')).to_contain_text('No permitted assertions match')
    expect(page.locator('#rw-claim')).to_have_text('')


def test_human_confirmation_assistant_and_deep_link(gui_page, gui_artifacts):
    page, d, records, _ = open_review(gui_page, context='pi')
    expect(page.locator('#rw-selection')).to_contain_text(records['pi']['assertion_id'])
    page.get_by_label('Question about selected assertion').fill('Explain this uncertainty')
    page.get_by_label('Send my question and the selected authorized assertion').check()
    page.get_by_role('button', name='Ask Review assistant').click()
    expect(page.locator('#rw-answer')).to_contain_text('requires human evidence review')
    page.get_by_role('button', name='Prepare human decision').click()
    expect(page.locator('#rw-decision')).to_be_visible()
    page.get_by_label('Rationale', exact=True).fill('Reviewed the synthetic citation; existence only.')
    # Native validation prevents a decision without explicit confirmation.
    page.get_by_role('button', name='Record decision').click()
    expect(page.locator('#rw-summary')).to_contain_text('proposed')
    page.get_by_label('I examined the evidence and confirm this human decision.').check()
    page.get_by_role('button', name='Record decision').click()
    expect(page.locator('#rw-status')).to_contain_text('Recorded accepted decision')
    expect(page.locator('#rw-summary')).to_contain_text('accepted')
    expect(page.locator('#rw-summary')).to_contain_text('inferred')
    expect(page.locator('#rw-answer')).to_have_text('')
    page.screenshot(path=str(gui_artifacts / 'review-accepted-decision.png'), full_page=True)
    page.locator('#rw-return').click()
    assert records['pi']['claim']['entity_ref'] in unquote(page.url)
    page.go_back()
    expect(page.locator('#rw-selection')).to_contain_text(records['pi']['assertion_id'])
    page.reload()
    expect(page.locator('#rw-summary')).to_contain_text('accepted')


def test_nonreviewer_refusal_and_selection_clearing(gui_page, gui_artifacts):
    page, _, _, _ = open_review(gui_page, principal='alice', context='pi')
    page.gui_expected_http.add('/api/review/preview')
    page.get_by_role('button', name='Prepare human decision').click()
    expect(page.locator('#rw-status')).to_contain_text('Access unavailable')
    expect(page.locator('#rw-decision')).to_be_hidden()
    page.screenshot(path=str(gui_artifacts / 'review-nonreviewer-refusal.png'), full_page=True)
    page.get_by_role('button', name='Show permitted queue').click()
    expect(page.locator('#rw-claim')).to_have_text('')
    expect(page.locator('#rw-send')).to_be_disabled()


def test_denied_context_and_revoked_inspection_show_no_retained_claim(gui_page):
    page, d, records, hidden = open_review(gui_page, context='pi')
    page.gui_expected_http.add('/api/review/inspect')
    d.policy.grant_evidence(d.reviewer, records['pi']['assertion_id'], admin_id=d.reviewer, allow=False)
    page.locator('#rw-queue button').click()
    expect(page.locator('#rw-status')).to_contain_text('Access unavailable')
    expect(page.locator('#rw-claim')).to_have_text('')
    expect(page.locator('#rw-evidence')).to_have_text('')
    page.goto(gui_page[1] + '/review?id=' + hidden['pi']['assertion_id'])
    expect(page.locator('#rw-status')).to_contain_text('No permitted assertions match')
    assert hidden['pi']['claim']['entity_ref'] not in page.locator('#review-workspace').inner_text()
