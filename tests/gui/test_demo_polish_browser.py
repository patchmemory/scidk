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
    page.goto(origin + '/review?view=guidance')       # the full-page Chat route (deep link); the dialog is covered in test_chat_workbench_browser
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
    expect(page.get_by_test_id('guidance-back')).to_have_count(0)
    page.get_by_test_id('chat-link-review').click()
    expect(page).to_have_url(origin + '/review')


def test_add_resource_without_plugins_opens_the_wizard_with_the_builtin_table_import(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/resources?view=sources')
    expect(page.get_by_test_id('add-source-btn')).to_have_text('+ Import a table or file')
    expect(page.get_by_test_id('sources-empty')).to_have_text('No Sources are configured yet. Import a table or file to create the first one.')
    page.get_by_test_id('add-source-btn').click()
    expect(page).to_have_url(origin + '/resources?view=sources')           # no redirect to Plugins
    expect(page.get_by_test_id('source-sheet')).to_be_visible()
    expect(page.get_by_test_id('pane-upload')).to_be_visible()             # straight to the built-in upload step
    expect(page.get_by_test_id('pane-remote')).to_be_hidden()
    expect(page.get_by_test_id('resources-tabs').locator('[aria-current=page]')).to_have_text('Sources')


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
    expect(page.get_by_role('button', name='Open Chat →')).to_be_visible()
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


# ---------------------------------------------------- Resources: connected-data-ecosystem dashboard

RES_SHOTS = pathlib.Path(os.environ['SCIDK_RESOURCES_SHOTS']) if os.environ.get('SCIDK_RESOURCES_SHOTS') else None
if RES_SHOTS:
    RES_SHOTS.mkdir(parents=True, exist_ok=True)
RES_LEDE = 'See the services, inputs, reusable capabilities, and recorded runs available to this workspace.'


def test_resources_walkthrough_tabs_roles_and_no_page_errors(gui_page):
    page, origin, _ = gui_page
    page.gui_expected_http.add('/api/external-index/scans')    # the harness has no external scan index (501)
    page.goto(origin + '/resources')
    expect(page.get_by_test_id('resources-lede')).to_have_text(RES_LEDE)
    expect(page.get_by_test_id('resources-tabs').get_by_role('link')).to_have_text(['Ecosystem', 'Sources', 'Plugins', 'Runs'])
    expect(page.get_by_test_id('resources-summary')).to_be_visible()
    expect(page.get_by_test_id('summary-scheduler')).to_contain_text('manual runs only')
    for key, caption in (('ecosystem', 'environment'), ('sources', 'inputs'), ('plugins', 'capabilities'), ('runs', 'activity')):
        page.get_by_test_id(f'resources-tab-{key}').click()
        expect(page).to_have_url(origin + f'/resources?view={key}')
        expect(page.get_by_test_id(f'resources-tab-{key}')).to_have_attribute('aria-current', 'page')
        assert page.evaluate("(k) => getComputedStyle(document.querySelector(`[data-testid=resources-tab-${k}]`), '::after').content", key) == f'"{caption}"'
        page.wait_for_load_state('networkidle')
        if RES_SHOTS:
            page.screenshot(path=str(RES_SHOTS / f'resources-{key}-1280.png'), full_page=True)
    # counts are filled in from existing APIs, never left as "Checking" nor invented
    expect(page.get_by_test_id('summary-sources')).not_to_have_text('Checking…')
    expect(page.get_by_test_id('summary-plugins')).not_to_have_text('Checking…')


def test_plugins_planned_integrations_are_visibly_non_actionable(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/resources?view=plugins')
    planned = page.get_by_test_id('plugins-group-planned')
    expect(planned).to_contain_text('None of these is installed, selectable as a Source type, or connected')
    expect(planned.get_by_test_id('roadmap-item')).to_have_count(8)
    assert planned.locator('a, button, input, select, [role=button], [tabindex]').count() == 0
    expect(page.get_by_test_id('plugins-group-builtin')).to_contain_text('CSV, TSV and Excel')
    expect(page.get_by_test_id('plugins-group-builtin')).to_contain_text('not a configured Source itself')
    expect(page.get_by_test_id('plugins-empty')).to_contain_text('No external plugins are installed')   # empty registry -> no claims
    expect(page.get_by_test_id('plugin-row')).to_have_count(0)
    expect(page.get_by_test_id('capability-row')).to_have_count(0)
    # a planned label is not a source choice: the wizard offers only the built-in type here
    page.goto(origin + '/resources?view=sources')
    page.get_by_test_id('add-source-btn').click()
    expect(page.get_by_test_id('type-option')).to_have_count(1)


def test_sources_import_opens_upload_wizard_and_back_reaches_type_selection(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/resources?view=sources')
    expect(page.get_by_test_id('resources-chain')).to_contain_text('Source')
    expect(page.get_by_test_id('resources-chain')).to_contain_text('preview and mapping')
    expect(page.get_by_test_id('resources-chain')).to_contain_text('FAIR / dry check')
    expect(page.get_by_test_id('resources-chain')).to_contain_text('recorded run')
    expect(page.get_by_test_id('sources-context')).to_contain_text('not a file format, and not a Plugin')
    expect(page.get_by_test_id('import-table-entry')).to_contain_text('CSV, TSV or Excel')
    page.get_by_test_id('add-source-btn').click()
    expect(page.get_by_test_id('source-sheet')).to_be_visible()
    expect(page.get_by_test_id('pane-upload')).to_be_visible()
    expect(page.get_by_test_id('upload-file')).to_have_attribute('accept', '.csv,.tsv,.tab,.txt,.xlsx,.xlsm')
    page.get_by_test_id('sheet-back').click()
    expect(page.get_by_test_id('step-type')).to_be_visible()
    expect(page.get_by_test_id('type-option').first).to_contain_text('Import a table or file')
    if RES_SHOTS:
        page.screenshot(path=str(RES_SHOTS / 'sources-wizard-type-selection-1280.png'))


def test_runs_empty_state_and_manual_only_wording(gui_page):
    page, origin, _ = gui_page
    page.goto(origin + '/resources?view=runs')
    expect(page.get_by_test_id('runs-manual-note')).to_contain_text('Manual runs only')
    expect(page.get_by_test_id('runs-empty')).to_contain_text('No runs recorded yet. Runs appear here after a Source is checked or executed')
    expect(page.get_by_test_id('schedule-link')).to_have_count(0)


import pytest


@pytest.mark.parametrize('width', [1024, 1440])
@pytest.mark.parametrize('view', ['ecosystem', 'sources', 'plugins', 'runs'])
def test_resources_has_no_horizontal_overflow(gui_page, view, width):
    page, origin, _ = gui_page
    page.gui_expected_http.add('/api/external-index/scans')
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(origin + f'/resources?view={view}')
    page.wait_for_load_state('networkidle')
    over = page.evaluate("() => ({doc: document.documentElement.scrollWidth - document.documentElement.clientWidth, body: document.body.scrollWidth - document.documentElement.clientWidth})")
    assert over['doc'] <= 0 and over['body'] <= 0, over
    if RES_SHOTS:
        page.screenshot(path=str(RES_SHOTS / f'resources-{view}-{width}.png'), full_page=True)
