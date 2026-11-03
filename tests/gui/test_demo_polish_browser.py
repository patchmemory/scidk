"""Chromium checks for the demo-polish pass: Settings footer link, session clock, Chat (legacy Guidance URLs) makes no request, Add Resource routing."""
import json
from datetime import datetime, timezone

from playwright.sync_api import expect
from tests.gui.test_workflows import *  # noqa: F401,F403  (reuse the gui_page fixture helpers)
import os
import pathlib

# Optional: set SCIDK_FINAL_POLISH_SHOTS to a directory to also save structural screenshots from these tests.
SHOTS = pathlib.Path(os.environ['SCIDK_FINAL_POLISH_SHOTS']) if os.environ.get('SCIDK_FINAL_POLISH_SHOTS') else None
if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)


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
    page.get_by_role('link', name='Open Chat').click()
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


def test_sidebar_labels_are_right_aligned_with_equal_padding_and_bracket(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/review')
    expect(page.locator('header nav a')).to_have_text(['Datasets', 'Resources', 'Knowledge', 'Review'])
    rows = page.evaluate("""() => [...document.querySelectorAll('header nav a')].map(a => {
        const r = document.createRange(); r.selectNodeContents(a);
        const t = r.getBoundingClientRect(), b = a.getBoundingClientRect(), cs = getComputedStyle(a);
        return {align: cs.textAlign, right: Math.round(b.right - t.right), padL: cs.paddingLeft, padR: cs.paddingRight, active: a.classList.contains('active'), shadow: cs.boxShadow};})""")
    for row in rows:
        assert row['align'] == 'right' and row['padL'] == row['padR'] == '12px'
        assert row['right'] == 12, row
    active = [row for row in rows if row['active']]
    assert len(active) == 1 and 'rgb(139, 191, 233)' in active[0]['shadow'] and '3px' in active[0]['shadow']
    home = page.get_by_test_id('nav-home').evaluate('e => getComputedStyle(e).textAlign')
    assert home != 'right'
    page.screenshot(path=str(SHOTS / 'sidebar-right-aligned.png'), clip={'x': 0, 'y': 0, 'width': 200, 'height': 420}) if SHOTS else None


def test_failed_graph_service_shows_concise_text_and_copyable_technical_details(gui_page):
    page, origin, app = gui_page
    page.gui_expected_http.add('/api/external-index/scans')    # the harness has no external scan index (501)
    secret = 'synthetic-secret-7'
    raw = f'Neo.ClientError: unable to connect to neo4j://svc-user:{secret}@db.internal:7687 password={secret}'
    backend = {'id': 'research', 'name': 'Research Graph', 'role': 'primary', 'description': 'Synthetic', 'configured': True,
               'uri': 'neo4j://db.internal:7687', 'auth_mode': 'basic', 'user': 'svc-user', 'database': 'neo4j',
               'env_vars': [], 'nav_section': None, 'last_verified': None, 'config_error': None}
    page.route('**/api/connections', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'backends': [backend]})))
    page.route('**/api/connections/research/test', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps({'ok': False, 'error': raw})))
    page.goto(origin + '/resources?view=ecosystem')
    page.locator('.conn-card[data-backend-id=research] [data-role=test]').click()
    result = page.locator('.conn-card[data-backend-id=research] [data-role=result]')
    summary = result.locator('[data-role=failure-summary]')
    expect(summary).to_have_text('Connection unavailable. Check Settings \u2192 Connections.')
    assert summary.locator('a').get_attribute('href').endswith('/settings#connections/overview')
    details = result.locator('details[data-role=technical-details]')
    expect(details.locator('summary')).to_have_text('Technical details')
    assert details.evaluate('e => e.open') is False
    assert 'Neo.ClientError' not in summary.inner_text() and 'Neo.ClientError' not in result.evaluate('e => [...e.childNodes].filter(n => n.nodeType === 3 || n.tagName === "SPAN").map(n => n.textContent).join("")')
    code = details.locator('pre > code')
    expect(code).to_be_hidden()
    details.locator('summary').click()
    expect(code).to_be_visible()
    expect(code).to_contain_text('Neo.ClientError: unable to connect')
    assert secret not in code.inner_text() and '***' in code.inner_text()   # credentials are masked
    assert code.evaluate('e => getComputedStyle(e).userSelect') != 'none'
    code.evaluate("e => { const r = document.createRange(); r.selectNodeContents(e); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }")
    assert 'Neo.ClientError' in page.evaluate('getSelection().toString()')       # selectable plain text
    shots = SHOTS
    if shots:
        result.locator('xpath=ancestor::div[contains(@class,"conn-card")]').screenshot(path=str(shots / 'graph-service-failure-details.png'))


def test_sources_shares_the_resources_gutter_and_card_scale(gui_page):
    page, origin, _ = gui_page
    page.gui_expected_http.add('/api/external-index/scans')    # Ecosystem reads it; the harness has none (501)
    def left(url, selector):
        page.goto(origin + url)
        page.wait_for_load_state('networkidle')
        box = page.locator(selector).first.bounding_box()
        return round(box['x']), round(box['width'])
    ws = left('/resources?view=ecosystem', '#resources-workspace')
    eco = left('/resources?view=ecosystem', '.eco-group')
    runs = left('/resources?view=runs', '.res-runs')
    src = left('/resources?view=sources', '.pipeline-page')
    assert eco[0] == runs[0] == src[0] == ws[0]
    assert abs(src[1] - eco[1]) <= 1 and abs(runs[1] - eco[1]) <= 1
    expect(page.locator('#resources-workspace h2')).to_have_text(['Sources'])
    expect(page.get_by_role('heading', name='Resources', exact=True)).to_have_count(1)     # only the outer workspace title
    expect(page.get_by_test_id('sources-no-plugins').or_(page.get_by_test_id('sources-empty'))).to_be_visible()
    sizes = page.evaluate("""() => { const h = document.querySelector('#resources-workspace h2'); const cs = getComputedStyle(h); return [cs.fontSize]; }""")
    page.goto(origin + '/resources?view=runs')
    assert page.evaluate("getComputedStyle(document.querySelector('#resources-workspace h2')).fontSize") == sizes[0] == '18px'
    if SHOTS:
        page.goto(origin + '/resources?view=sources')
        page.screenshot(path=str(SHOTS / 'sources-layout.png'))


def test_chat_labels_and_legacy_guidance_urls_make_no_provider_calls(gui_page):
    page, origin, app = gui_page
    page.goto(origin + '/review')
    expect(page.get_by_role('link', name='Open Chat')).to_be_visible()
    expect(page.get_by_text('Get guidance')).to_have_count(0)
    for url in ('/review?view=guidance', '/review/guidance'):
        page.goto(origin + url)
        expect(page.locator('#guidance-shell h1')).to_have_text('Chat')
        expect(page.get_by_test_id('guidance-provider-status')).to_contain_text('AI provider not configured')
        assert 'Guidance' not in page.locator('#guidance-shell').inner_text()
    page.wait_for_load_state('networkidle')
    network, before = [], len(app.extensions['gui_test_requests'])
    page.on('request', lambda request: network.append(request.url))
    page.get_by_test_id('guidance-input').fill('synthetic question')
    page.get_by_test_id('guidance-send').click()
    expect(page.get_by_test_id('guidance-not-configured-notice')).to_have_count(1)
    assert network == [] and len(app.extensions['gui_test_requests']) == before
    if SHOTS:
        page.screenshot(path=str(SHOTS / 'review-chat.png'))
