"""Chromium checks for the shared Chat workbench dialog opened from Overview and Review: accessible open/close, unsent
prefills, draft kept across Advanced toggling, no network or storage, and the full-page Chat staying a deep link."""
from playwright.sync_api import expect
from tests.gui.test_workflows import *  # noqa: F401,F403  (reuse the gui_page fixture)


def watch_network(page):
    seen = []
    page.on('request', lambda request: seen.append((request.method, request.url, request.resource_type)))
    return seen


def test_overview_launcher_opens_and_closes_the_workbench_without_navigation(gui_page):
    page, origin, app = gui_page
    page.goto(origin + '/overview')
    dialog = page.get_by_test_id('chat-workbench')
    expect(dialog).to_be_hidden()
    page.wait_for_load_state('networkidle')
    seen = watch_network(page)
    before = len(app.extensions['gui_test_requests'])
    page.get_by_test_id('launcher-input').fill('draft from home')
    page.get_by_test_id('launcher-open').click()
    expect(dialog).to_be_visible()
    expect(page).to_have_url(origin + '/overview')
    expect(page.get_by_test_id('guidance-input')).to_have_value('draft from home')
    expect(page.get_by_test_id('guidance-input')).to_be_focused()
    expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
    expect(page.get_by_test_id('chat-history-empty')).to_contain_text('No conversations available yet')
    expect(page.get_by_test_id('guidance-provider-status')).to_contain_text('AI provider not configured')
    summary = page.locator('#chat-workbench #advanced-query > summary')
    summary.click()
    expect(page.locator('#chat-workbench #overview-question')).to_be_visible()
    summary.click()
    expect(page.get_by_test_id('guidance-input')).to_have_value('draft from home')
    page.keyboard.press('Escape')
    expect(dialog).to_be_hidden()
    expect(page.get_by_test_id('launcher-open')).to_be_focused()
    page.get_by_test_id('launcher-open').click()
    page.get_by_test_id('chat-workbench-close').click()
    expect(dialog).to_be_hidden()
    assert [s for s in seen if s[2] in ('fetch', 'xhr') or s[0] != 'GET'] == []
    app_calls = [r for r in app.extensions['gui_test_requests'][before:] if not r[1].startswith('/static/')]    # a lazily loaded icon font is not an application call
    assert app_calls == [], app_calls
    assert page.evaluate('localStorage.length + sessionStorage.length + document.cookie.length') == 0


def test_review_discuss_links_fill_the_same_workbench_unsent(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/review')
    seen = watch_network(page)
    for task in ('curate', 'annotate', 'evaluate', 'enrich', 'publish'):
        page.get_by_test_id('discuss-' + task).click()
        expect(page.get_by_test_id('chat-workbench')).to_be_visible()
        expect(page).to_have_url(origin + '/review')
        assert len(page.get_by_test_id('guidance-input').input_value()) > 20
        expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
        page.keyboard.press('Escape')
        expect(page.get_by_test_id('discuss-' + task)).to_be_focused()
    assert [s for s in seen if s[2] in ('fetch', 'xhr') or s[0] != 'GET'] == []


def test_workbench_fits_at_1024_and_full_page_chat_stays_a_deep_link(gui_page):
    page, origin, _ = gui_page
    page.set_viewport_size({'width': 1024, 'height': 800})
    page.goto(origin + '/review')
    page.get_by_test_id('review-chat-input').fill('I am working on X')
    page.get_by_test_id('review-chat-open').click()
    box = page.get_by_test_id('chat-workbench').bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 1024 and box['y'] + box['height'] <= 800
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.keyboard.press('Escape')
    for path in ('/review?view=guidance', '/review/guidance'):
        page.goto(origin + path)
        expect(page.get_by_test_id('guidance-shell')).to_be_visible()
        expect(page.locator('dialog')).to_have_count(0)
        expect(page.get_by_test_id('chat-history-empty')).to_be_visible()
