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
    expect(page.get_by_test_id('guidance-provider-status')).to_contain_text('Chat is unavailable')
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


OVERVIEW_ASK = {
    'browse': ('Help me find the relevant data.', '/datasets?view=browse'),
    'explore': ('Help me understand how these things relate.', '/knowledge?view=relationships'),
    'curate': ('Help me decide what to do next.', '/review'),
}


def test_overview_start_elsewhere_rows_offer_open_and_unsent_ask_chat(gui_page):
    page, origin, app = gui_page
    page.goto(origin + '/overview')
    page.wait_for_load_state('networkidle')
    expect(page.get_by_role('heading', name='Start elsewhere')).to_be_visible()
    seen = watch_network(page)
    before = len(app.extensions['gui_test_requests'])
    for name, (prompt, destination) in OVERVIEW_ASK.items():
        row = page.get_by_test_id('home-card-' + name)
        expect(row.locator('a.sn-open')).to_have_attribute('data-destination', destination)
        assert row.bounding_box()['height'] < 90                                  # a compact row, not a large card
        link = page.get_by_test_id('ask-chat-' + name)
        link.click()
        expect(page.get_by_test_id('chat-workbench')).to_be_visible()
        expect(page).to_have_url(origin + '/overview')                            # no URL parameters, no navigation
        expect(page.get_by_test_id('guidance-input')).to_have_value(prompt)       # visible in the draft box
        expect(page.get_by_test_id('guidance-input')).to_be_focused()
        expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)     # never sent
        page.keyboard.press('Escape')
        expect(page.get_by_test_id('chat-workbench')).to_be_hidden()
        expect(link).to_be_focused()                                              # focus returns to the launching link
    page.get_by_test_id('ask-chat-browse').click()
    page.get_by_test_id('chat-workbench-close').click()
    expect(page.get_by_test_id('ask-chat-browse')).to_be_focused()
    assert [s for s in seen if s[2] in ('fetch', 'xhr') or s[0] != 'GET'] == []
    assert [r for r in app.extensions['gui_test_requests'][before:] if not r[1].startswith('/static/')] == []
    assert page.evaluate('localStorage.length + sessionStorage.length + document.cookie.length') == 0
    for name, (_, destination) in OVERVIEW_ASK.items():                           # every Open link reaches a real page
        if name == 'explore':
            continue        # the harness profile has no graph grant (403); the live :5010 check covers Knowledge
        page.goto(origin + '/overview')
        page.locator('#home-card-%s a.sn-open' % name).click()
        page.wait_for_load_state('domcontentloaded')
        assert page.url.startswith(origin + destination.split('?')[0]), (name, page.url)


def test_review_task_navigator_is_ordered_compact_and_each_row_opens_chat_unsent(gui_page):
    page, origin, _ = gui_page
    tasks = ['curate', 'annotate', 'evaluate', 'enrich', 'publish']
    destinations = {'curate': '/datasets?view=collections', 'annotate': '/datasets?view=browse',
                    'evaluate': '/knowledge?view=relationships', 'enrich': '/resources?view=plugins',
                    'publish': '/datasets?view=collections'}
    for width in (1440, 1024):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(origin + '/review')
        page.wait_for_load_state('networkidle')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
        assert page.locator('ol.tn-list > li').evaluate_all('els => els.map(e => e.dataset.action)') == tasks
        expect(page.get_by_test_id('task-sequence')).to_contain_text('Curate → Annotate → Evaluate → Enrich → Publish')
        heights = page.locator('ol.tn-list > li').evaluate_all('els => els.map(e => e.getBoundingClientRect().height)')
        assert max(heights) < 115 and sum(heights) < 480, heights                   # no oversized equal-weight cards
        for task in tasks:
            expect(page.locator('#rl-card-%s a.rl-primary' % task)).to_have_attribute('data-destination', destinations[task])
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.goto(origin + '/review')
    for task in tasks:
        link = page.get_by_test_id('discuss-' + task)
        expect(link).to_have_text('Ask Chat')
        link.click()
        expect(page.get_by_test_id('chat-workbench')).to_be_visible()
        expect(page).to_have_url(origin + '/review')
        assert len(page.get_by_test_id('guidance-input').input_value()) > 20
        expect(page.get_by_test_id('guidance-user-message')).to_have_count(0)
        page.get_by_test_id('chat-workbench-close').click()
        expect(link).to_be_focused()
    expect(page.get_by_test_id('review-chat-note')).to_contain_text('No AI provider is configured')


def test_overview_has_no_horizontal_overflow_at_1024_and_1440(gui_page):
    page, origin, _ = gui_page
    for width in (1440, 1024):
        page.set_viewport_size({'width': width, 'height': 900})
        page.goto(origin + '/overview')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
