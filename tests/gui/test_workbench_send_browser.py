"""Chromium checks for the shared Chat workbench send path (inset dialog and full page).

The server readiness is forced to "ready" and the single Ask request is fulfilled inside the browser by a stub, so no
provider (and no server write path) is ever contacted. Server-side gates are covered by tests/test_workbench_chat.py.
"""
import json

import pytest
from playwright.sync_api import expect
from tests.gui.test_workflows import *  # noqa: F401,F403  (reuse the gui_page fixture)

from scidk.services import workbench_chat

ANSWER = 'Stub answer with <b>markup</b> that must stay text.'
READY = {'ready': True, 'reason': '', 'message': ''}


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(workbench_chat, 'state', lambda app, identity: dict(READY))


def stub_ask(page, status=200, payload=None):
    posts = []

    def handle(route):
        request = route.request
        posts.append({'method': request.method, 'body': request.post_data_json, 'content_type': request.headers.get('content-type')})
        body = payload if payload is not None else {'status': 'success', 'reply': ANSWER, 'notice': 'AI-generated.', 'request_id': 'r1'}
        route.fulfill(status=status, content_type='application/json', headers={'Cache-Control': 'no-store'}, body=json.dumps(body))
    page.route('**/api/chat/workbench', handle)
    return posts


def storage(page):
    return page.evaluate('localStorage.length + sessionStorage.length + document.cookie.length')


def test_dialog_prefill_is_unsent_until_ask_then_answer_renders_as_text(gui_page, ready):
    page, origin, app = gui_page
    page.goto(origin + '/overview')
    page.wait_for_load_state('networkidle')
    posts = stub_ask(page)
    page.get_by_test_id('launcher-input').fill('synthetic draft')
    page.get_by_test_id('launcher-open').click()
    dialog = page.get_by_test_id('chat-workbench')
    expect(dialog).to_be_visible()
    expect(page.get_by_test_id('guidance-shell')).to_have_attribute('data-provider-state', 'configured')
    expect(page.get_by_test_id('guidance-input')).to_have_value('synthetic draft')
    expect(page.get_by_test_id('guidance-provider-status')).to_contain_text('connected to your approved AI provider')
    assert posts == [] and page.get_by_test_id('guidance-user-message').count() == 0   # opening/prefill sent nothing
    page.get_by_test_id('guidance-send').click()
    expect(page.get_by_test_id('guidance-assistant-message')).to_have_text(ANSWER)
    assert posts == [{'method': 'POST', 'body': {'message': 'synthetic draft', 'send_question': True},
                      'content_type': 'application/json'}]
    expect(page.get_by_test_id('guidance-user-message')).to_have_text('synthetic draft')
    expect(page.get_by_test_id('guidance-input')).to_have_value('')
    assert page.locator('[data-testid=guidance-assistant-message] b').count() == 0       # text, never HTML
    assert storage(page) == 0
    page.keyboard.press('Escape')
    expect(dialog).to_be_hidden()
    expect(page.get_by_test_id('launcher-open')).to_be_focused()
    page.get_by_test_id('launcher-open').click()
    page.get_by_test_id('chat-workbench-close').click()
    expect(dialog).to_be_hidden()
    assert len(posts) == 1
    assert [r for r in app.extensions['gui_test_requests'] if r[0] != 'GET'] == []     # no server write path reached


def test_task_prefills_open_the_ready_dialog_unsent(gui_page, ready):
    page, origin, _ = gui_page
    page.goto(origin + '/review')
    page.wait_for_load_state('networkidle')
    posts = stub_ask(page)
    for task in ('curate', 'annotate', 'evaluate'):
        page.get_by_test_id('discuss-' + task).click()
        expect(page.get_by_test_id('chat-workbench')).to_be_visible()
        assert len(page.get_by_test_id('guidance-input').input_value()) > 20
        expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
        page.keyboard.press('Escape')
        expect(page.get_by_test_id('chat-workbench')).to_be_hidden()
    assert posts == [] and storage(page) == 0


def test_full_page_prefill_is_unsent_and_enter_sends_once(gui_page, ready):
    page, origin, _ = gui_page
    page.goto(origin + '/review?view=guidance&prefill=synthetic+question')
    page.wait_for_load_state('networkidle')
    posts = stub_ask(page)
    expect(page.get_by_test_id('guidance-input')).to_have_value('synthetic question')
    page.wait_for_timeout(300)
    assert posts == []
    page.get_by_test_id('guidance-input').press('Enter')
    expect(page.get_by_test_id('guidance-assistant-message')).to_have_text(ANSWER)
    expect(page.get_by_test_id('chat-history-empty')).to_contain_text('does not keep a history')
    assert [p['body'] for p in posts] == [{'message': 'synthetic question', 'send_question': True}]
    page.reload()
    page.wait_for_load_state('networkidle')
    expect(page.get_by_test_id('guidance-assistant-message')).to_have_count(0)           # nothing persisted
    expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
    assert storage(page) == 0 and len(posts) == 1


@pytest.mark.parametrize('status,payload,text', [
    (503, {'status': 'unavailable', 'reason': 'full_access', 'error': 'Chat is unavailable while this instance runs in unrestricted full-access mode.'},
     'unrestricted full-access mode'),
    (429, {'status': 'rate_limited', 'reason': 'rate_limited', 'error': 'Too many Chat messages. Wait a minute and try again.'}, 'Too many Chat messages'),
    (500, None, 'Chat could not answer'),
])
def test_failed_turns_show_an_honest_notice_and_keep_the_draft(gui_page, ready, status, payload, text):
    page, origin, _ = gui_page
    page.gui_expected_http.add('/api/chat/workbench')    # the deliberate error replies under test
    page.goto(origin + '/review?view=guidance')
    page.wait_for_load_state('networkidle')
    stub_ask(page, status=status, payload=payload if payload else {})
    page.get_by_test_id('guidance-input').fill('synthetic question')
    page.get_by_test_id('guidance-send').click()
    expect(page.get_by_test_id('guidance-error-notice')).to_contain_text(text)
    expect(page.get_by_test_id('guidance-assistant-message')).to_have_count(0)
    expect(page.get_by_test_id('guidance-input')).to_have_value('synthetic question')
    expect(page.get_by_test_id('guidance-send')).to_be_enabled()


def test_ready_state_tests_fail_on_an_unexpected_endpoint_error(gui_page, ready):
    # Guard check: without the explicit allowance used only by the failure-reply test, an HTTP error from the
    # workbench endpoint is recorded by the harness (and would fail the test at teardown).
    page, origin, _ = gui_page
    assert '/api/chat/workbench' not in page.gui_expected_http
    page.goto(origin + '/review?view=guidance')
    page.wait_for_load_state('networkidle')
    stub_ask(page, status=503, payload={'status': 'unavailable', 'reason': 'provider', 'error': 'x'})
    page.get_by_test_id('guidance-input').fill('synthetic question')
    page.get_by_test_id('guidance-send').click()
    expect(page.get_by_test_id('guidance-error-notice')).to_be_visible()
    assert any('HTTP 503' in e and '/api/chat/workbench' in e for e in page.gui_errors)
    page.gui_errors.clear()       # this test intentionally provoked it; every other ready-state test keeps the guard


@pytest.mark.parametrize('url', ['/review?view=guidance', '/overview'])
def test_unavailable_state_never_posts(gui_page, url):
    page, origin, app = gui_page
    page.goto(origin + url)
    page.wait_for_load_state('networkidle')
    posts = stub_ask(page)
    if url == '/overview':
        page.get_by_test_id('launcher-input').fill('synthetic question')
        page.get_by_test_id('launcher-open').click()
    else:
        page.get_by_test_id('guidance-input').fill('synthetic question')
    expect(page.get_by_test_id('guidance-shell')).to_have_attribute('data-provider-state', 'not-configured')
    page.get_by_test_id('guidance-send').click()
    expect(page.get_by_test_id('guidance-not-configured-notice')).to_have_count(1)
    assert posts == [] and page.locator('script[src*="workbench_chat.js"]').count() == 0
    assert storage(page) == 0


@pytest.mark.parametrize('width', [1024, 1440])
@pytest.mark.parametrize('url', ['/review?view=guidance', '/overview'])
def test_no_horizontal_overflow_with_an_answer(gui_page, ready, url, width):
    page, origin, _ = gui_page
    page.set_viewport_size({'width': width, 'height': 800})
    page.goto(origin + url)
    page.wait_for_load_state('networkidle')
    stub_ask(page, payload={'status': 'success', 'reply': 'word ' * 400 + 'x' * 300, 'notice': 'AI-generated.'})
    if url == '/overview':
        page.get_by_test_id('launcher-input').fill('synthetic question')
        page.get_by_test_id('launcher-open').click()
        box_target = page.get_by_test_id('chat-workbench')
    else:
        page.get_by_test_id('guidance-input').fill('synthetic question')
        box_target = page.get_by_test_id('guidance-shell')
    page.get_by_test_id('guidance-send').click()
    expect(page.get_by_test_id('guidance-assistant-message')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    box = box_target.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= width
    assert page.evaluate("(() => { const m = document.querySelector('[data-testid=guidance-messages]');"
                         " return m.scrollWidth <= m.clientWidth + 1; })()")
