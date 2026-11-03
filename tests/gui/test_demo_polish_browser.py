"""Chromium checks for the demo-polish pass: Settings footer link, session clock, Guidance makes no request, Add Resource routing."""
import json
from datetime import datetime, timezone

from playwright.sync_api import expect
from tests.gui.test_workflows import *  # noqa: F401,F403  (reuse the gui_page fixture helpers)


def sign_in(page):
    page.route('**/api/auth/status', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps({'authenticated': True, 'username': 'synthetic.user'})))


def test_settings_link_is_keyboard_reachable_with_visible_focus(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/review')
    link = page.get_by_role('link', name='Settings', exact=True)
    expect(link).to_have_text('Settings')
    expect(page.locator('header .ti-settings')).to_have_count(0)
    link.focus()
    expect(link).to_be_focused()
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") != 'none'
    page.keyboard.press('Enter')
    expect(page).to_have_url(origin + '/settings')


def test_signed_in_footer_layout_and_browser_clock(gui_page):
    page, origin, app = gui_page
    sign_in(page)
    page.clock.install(time=datetime(2025, 11, 3, 21, 42, 10, tzinfo=timezone.utc))
    page.goto(origin + '/review')
    clock = page.get_by_test_id('session-clock')
    expect(clock).to_have_text('Mon Nov 3 \u00b7 9:42 PM UTC')
    # Layout: name / date-time / "Settings \u00b7 Logout", stacked top to bottom, left aligned.
    name, links = page.get_by_test_id('auth-username'), page.get_by_test_id('user-links')
    expect(name).to_have_text('synthetic.user')
    expect(links).to_have_text('Settings \u00b7 Logout')
    boxes = [e.bounding_box() for e in (name, clock, links)]
    assert boxes[0]['y'] < boxes[1]['y'] < boxes[2]['y']
    assert abs(boxes[0]['x'] - boxes[1]['x']) < 1
    assert page.get_by_test_id('user-area').bounding_box()['x'] < 190   # inside the sidebar
    expect(page.locator('header .ti-settings')).to_have_count(0)
    expect(page.locator('header nav').get_by_role('link')).to_have_text(['Datasets', 'Resources', 'Knowledge', 'Review'])
    # The clock never stores, sends, or exposes an audit timestamp.
    assert page.evaluate('[localStorage.length, sessionStorage.length]') == [0, 0]
    assert page.get_by_test_id('session-clock').get_attribute('datetime') is None


def test_session_clock_updates_at_most_once_per_minute_and_sends_nothing(gui_page):
    page, origin, app = gui_page
    sign_in(page)
    page.clock.install(time=datetime(2025, 11, 3, 21, 42, 10, tzinfo=timezone.utc))
    page.goto(origin + '/review')
    clock = page.get_by_test_id('session-clock')
    expect(clock).to_have_text('Mon Nov 3 \u00b7 9:42 PM UTC')
    page.evaluate("""() => { window.__clockWrites = 0;
        new MutationObserver(() => window.__clockWrites++).observe(document.getElementById('session-clock'), {childList: true, characterData: true, subtree: true}); }""")
    before = len(app.extensions['gui_test_requests'])
    network = []
    page.on('request', lambda request: network.append(request.url))
    page.clock.run_for(30_000)                    # 9:42:40 - same minute, no rewrite
    assert page.evaluate('window.__clockWrites') == 0
    page.clock.run_for(60_000)                    # 9:43:40
    expect(clock).to_have_text('Mon Nov 3 \u00b7 9:43 PM UTC')
    page.clock.run_for(5 * 60_000)                # five more minutes
    expect(clock).to_have_text('Mon Nov 3 \u00b7 9:48 PM UTC')
    assert page.evaluate('window.__clockWrites') <= 7   # one per elapsed minute at most (6.5 min elapsed)
    assert network == [] and len(app.extensions['gui_test_requests']) == before


def test_settings_keeps_the_shared_blue_left_bracket_when_open(gui_page):
    page, origin, _ = gui_page
    sign_in(page)
    page.goto(origin + '/settings')
    link = page.get_by_test_id('nav-settings')
    expect(link).to_have_attribute('aria-current', 'page')
    expect(page.locator('header [aria-current=page]')).to_have_count(1)
    shadow = link.evaluate('e => getComputedStyle(e).boxShadow')
    background = link.evaluate('e => getComputedStyle(e).backgroundColor')
    assert 'rgb(139, 191, 233)' in shadow and 'inset' in shadow and '3px' in shadow
    page.goto(origin + '/review')
    nav = page.locator('header nav a.active')
    assert nav.evaluate('e => getComputedStyle(e).boxShadow') == shadow
    assert nav.evaluate('e => getComputedStyle(e).backgroundColor') == background == 'rgb(45, 75, 104)'


def test_guidance_shell_sends_nothing_and_fabricates_no_answer(gui_page):
    page, origin, app = gui_page
    page.goto(origin + '/review')
    page.get_by_role('link', name='Open Guidance').click()
    expect(page).to_have_url(origin + '/review?view=guidance')
    expect(page.get_by_test_id('guidance-provider-status')).to_contain_text('AI provider not configured')
    page.wait_for_load_state('networkidle')
    network = []
    page.on('request', lambda request: network.append(request.url))
    before = len(app.extensions['gui_test_requests'])
    page.get_by_test_id('guidance-input').fill('synthetic question')
    page.get_by_test_id('guidance-send').click()
    page.get_by_test_id('guidance-input').fill('second question')
    page.keyboard.press('Enter')
    expect(page.get_by_test_id('guidance-user-message')).to_have_count(2)
    expect(page.get_by_test_id('guidance-not-configured-notice')).to_have_count(2)
    expect(page.get_by_test_id('guidance-messages')).not_to_contain_text('Here is')
    assert network == [] and len(app.extensions['gui_test_requests']) == before
    page.get_by_test_id('guidance-back').click()
    expect(page).to_have_url(origin + '/review')


def test_add_resource_without_plugins_leads_to_plugins_guidance(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/resources?view=sources')
    page.get_by_test_id('add-source-btn').click()
    expect(page).to_have_url(origin + '/resources?view=plugins&from=add-resource')
    expect(page.get_by_test_id('add-resource-guidance')).to_be_visible()
    expect(page.get_by_test_id('resources-tabs').locator('[aria-current=page]')).to_have_text('Plugins')
