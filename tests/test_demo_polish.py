"""Demo polish: Home/Settings navigation, Resources Ecosystem, Add Resource with no plugins, Guidance shell,
Browse recognition summary and the live-development launcher's stale state. Synthetic data only."""
import pathlib
import re
import socket

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'scidk' / 'ui' / 'templates'


@pytest.fixture
def client(tmp_path):
    from tests.gui.harness import make_gui_app
    app = make_gui_app()
    app.config.update(SCIDK_GUI_V3_ENABLED=True, SCIDK_SETTINGS_DB=str(tmp_path / 'settings.db'))
    return app.test_client()


def page(client, url):
    response = client.get(url)
    assert response.status_code == 200, url
    return response.get_data(as_text=True)


def header(html):
    return html[html.index('<header'):html.index('</header>')]


# ---------------------------------------------------------------- navigation

def test_logo_is_home_and_overview_is_not_a_sidebar_item(client):
    head = header(page(client, '/review'))
    assert re.search(r'<a href="/"[^>]*data-testid="nav-home"[^>]*aria-label="SciDK home"', head)
    nav = head[head.index('<nav'):head.index('</nav>')]
    assert re.findall(r'>([^<]+)</a>', nav) == ['Datasets', 'Resources', 'Knowledge', 'Review']


def test_settings_is_a_text_link_in_the_footer_not_primary_nav_and_not_a_gear(client):
    head = header(page(client, '/review'))
    nav = head[head.index('<nav'):head.index('</nav>')]
    assert 'Settings' not in nav
    link = re.search(r'<a [^>]*id="settings-link"[^>]*>Settings</a>', head).group(0)
    assert 'href="/settings"' in link and 'data-testid="nav-settings"' in link
    assert 'ti-settings' not in head and 'settings-gear' not in head and '<i ' not in head[head.index('id="user-area"'):]
    # Footer order: user name, session clock, then "Settings · Logout".
    order = ['id="auth-username"', 'id="session-clock"', 'id="settings-link"', 'id="logout-sep"', 'id="logout-btn"']
    assert [head.index(token) for token in order] == sorted(head.index(token) for token in order)
    assert 'datetime=' not in head[head.index('id="session-clock"'):head.index('</time>')]
    css = (ROOT / 'scidk' / 'ui' / 'static' / 'css' / 'gui_design.css').read_text()
    assert '.gui-v3 :focus-visible {outline:3px solid' in css and 'header :focus-visible' in css
    assert 'settings-gear' not in css
    # Settings shares the primary nav's blue left-bracket active treatment.
    assert '.gui-v3 header nav a.active,.gui-v3 .user-links a.settings-link.active {background:#2d4b68;color:white;box-shadow:inset 3px 0 #8bbfe9}' in css


def test_session_clock_is_browser_side_decorative_only():
    text = (TEMPLATES / 'base.html').read_text()
    script = text[text.index('function formatSessionClock'):text.index('// Check auth status on page load')]
    assert 'timeZoneName' in script and '60000' in script
    for forbidden in ('fetch(', 'localStorage', 'sessionStorage', 'document.cookie', 'XMLHttpRequest', 'sendBeacon', 'setInterval'):
        assert forbidden not in script, forbidden


@pytest.mark.parametrize('path, active', [
    ('/', 'home'), ('/overview', 'home'),
    ('/datasets?view=browse', 'Datasets'), ('/datasets?view=scans', 'Datasets'),
    ('/resources?view=ecosystem', 'Resources'), ('/resources?view=runs', 'Resources'),
    ('/datasets?view=collections', 'Datasets'), ('/review', 'Review'), ('/review?view=guidance', 'Review'),
    ('/settings', 'settings')])
def test_exactly_one_active_destination_per_page(client, path, active):
    head = header(page(client, path))
    marked = re.findall(r'<a [^>]*aria-current="page"[^>]*>(?:<i[^>]*></i>)?([^<]*)</a>', head)
    if active == 'home':
        assert 'brand-home active' in head and marked == ['-SciDK->'] or 'brand-home active' in head
    elif active == 'settings':
        assert 'settings-link active' in head and marked == ['Settings']
    else:
        assert marked == [active]


# ------------------------------------------------------- Resources Ecosystem

def test_ecosystem_tab_groups_and_honest_inventory(client):
    html = page(client, '/resources?view=ecosystem')
    assert re.findall(r'data-testid="resources-tab-(\w+)"', html) == ['ecosystem', 'sources', 'plugins', 'runs']
    assert '>Connections</a>' not in html
    for group in ('graph', 'inventory', 'storage', 'interpretation'):
        assert f'data-testid="eco-group-{group}"' in html, group
    assert html.index('eco-group-graph') < html.index('eco-group-inventory') < html.index('eco-group-storage') < html.index('eco-group-interpretation')
    assert 'powers <a href="/datasets?view=browse">Browse</a>' in html and 'Dataset recognition' in html
    assert 'only reads it' in html and '/api/external-index/scans' in html
    assert 'files.db' in html


def test_connections_alias_and_direct_routes_still_work(client):
    assert 'data-testid="eco-group-graph"' in page(client, '/resources?view=connections')
    for url in ('/resources', '/resources?view=sources', '/resources?view=plugins', '/resources?view=runs',
                '/resources?view=mappings', '/pipeline/sources', '/settings', '/review?view=assertions',
                '/review/assertions', '/datasets?view=browse', '/chat'):
        assert client.get(url).status_code in (200, 403), url


def test_ecosystem_never_writes_the_files_index():
    text = (TEMPLATES / '_resources_ecosystem.html').read_text()
    assert "method: 'POST'" not in text and "method:'POST'" not in text and 'files.db' in text
    assert 'fetch(BASE + \'/api/external-index/scans\'' in text


# --------------------------------------- Add Resource / Runs honesty

def test_add_resource_without_plugins_routes_to_plugins_and_keeps_real_wizard():
    text = (TEMPLATES / '_pipeline_sources_app.html').read_text()
    assert "/resources?view=plugins&from=add-resource" in text
    assert 'data-testid="add-source-btn"' in text and 'known === 0' in text and 'sheet.showModal()' in text   # real wizard retained


def test_plugins_tab_explains_add_resource_redirect(client):
    html = page(client, '/resources?view=plugins&from=add-resource')
    assert 'data-testid="add-resource-guidance"' in html and 'Add resource needs a source plugin' in html
    assert 'data-testid="add-resource-guidance"' not in page(client, '/resources?view=plugins')


def test_runs_does_not_imply_scheduling_when_no_scheduler_runs(client):
    html = page(client, '/resources?view=runs')
    assert 'data-testid="runs-manual-note"' in html and 'Manual runs only' in html
    assert 'data-testid="schedule-link"' in html   # code path present, gated by SCHEDULING=false at runtime
    assert 'const SCHEDULING = false' in html
    sources = page(client, '/resources?view=sources')
    assert 'const SCHEDULING = false' in sources


# ----------------------------------------------------------- Guidance shell

def test_review_card_links_to_guidance_and_legacy_assertions_route_is_kept(client):
    landing = page(client, '/review')
    assert 'href="/review?view=guidance"' in landing and 'Open Chat' in landing
    assert 'id="review-landing"' in landing


@pytest.mark.parametrize('url', ['/review?view=guidance', '/review/guidance'])
def test_guidance_shell_markup_is_static_and_honest(client, url):
    html = page(client, url)
    assert 'data-provider-state="not-configured"' in html and 'AI provider not configured' in html
    assert 'data-testid="guidance-messages"' in html and 'data-testid="guidance-input"' in html
    assert 'href="/review" data-testid="guidance-back"' in html
    body = html[html.index('id="guidance-shell"'):]
    script = body[body.index('<script>'):body.index('</script>')]
    for banned in ('fetch(', 'XMLHttpRequest', 'WebSocket', 'sendBeacon', 'EventSource', 'localStorage',
                   'sessionStorage', 'document.cookie', 'indexedDB'):
        assert banned not in script, banned


def visible_text(html):
    body = re.sub(r'(?s)<(script|style)\b.*?</\1>', '', html)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body))


def test_review_shows_chat_and_keeps_both_legacy_guidance_urls(client):
    landing = page(client, '/review')
    assert 'Open Chat' in visible_text(landing) and 'Get guidance' not in landing and 'Open Guidance' not in landing
    assert re.search(r'<h3>\s*Chat\s*(<|\n)', landing) or '>Chat<' in landing
    for url in ('/review?view=guidance', '/review/guidance'):
        html = page(client, url)
        assert '<h1 class="ws-title">Chat</h1>' in html and '<title>SciDK \u2014 Review \u00b7 Chat</title>' in html
        assert 'Guidance' not in visible_text(html), url           # visible copy says Chat
        assert 'data-testid="guidance-shell"' in html               # compatibility ids are unchanged
        assert 'data-provider-state="not-configured"' in html and 'AI provider not configured' in html


# ------------------------------------------------ sidebar alignment, Sources layout, technical disclosure

CSS = (ROOT / 'scidk' / 'ui' / 'static' / 'css' / 'gui_design.css').read_text()


def test_primary_sidebar_labels_are_right_aligned_with_symmetric_padding_and_bracket():
    assert '.gui-v3 header nav a {text-align:right}' in CSS
    assert 'padding:11px 12px;' in CSS and 'header nav a.active,' in CSS and 'box-shadow:inset 3px 0 #8bbfe9' in CSS
    # logo/Home and footer treatments are not right-aligned
    assert 'text-align:right' not in CSS[CSS.index('.gui-v3 header h1 a.brand-home {padding'):CSS.index('.gui-v3 header nav {')]
    assert 'text-align:right' not in CSS[CSS.index('.gui-v3 .user-area'):CSS.index('.gui-v3 header :focus-visible')]


def test_sources_uses_the_shared_resources_layout_without_a_duplicate_heading(client):
    sources = page(client, '/resources?view=sources')
    area = sources[sources.index('id="resources-workspace"'):]
    assert 'class="pipeline-page res-index"' in area
    assert '<h2>Sources</h2>' in area and '<h2>Resources</h2>' not in area
    assert sources.count('<h1 class="ws-title">Resources</h1>') == 1
    # empty state / redirect behavior is unchanged
    text = (TEMPLATES / '_pipeline_sources_app.html').read_text()
    for kept in ('data-testid="sources-no-plugins"', 'data-testid="sources-empty"',
                 "/resources?view=plugins&from=add-resource", 'data-testid="add-source-btn"'):
        assert kept in text, kept
    assert '.gui-v3 #resources-workspace .pipeline-page .source-card' in CSS


def test_legacy_pipeline_sources_page_keeps_its_own_heading(client):
    response = client.get('/pipeline/sources')
    if response.status_code == 200:
        assert '<h2>Resources</h2>' in response.get_data(as_text=True)


def test_graph_service_failures_use_concise_text_and_a_copyable_collapsed_disclosure():
    text = (TEMPLATES / 'settings' / '_connections_overview.html').read_text()
    assert 'Technical details' in text and '<details data-role="technical-details"' in text
    assert '<pre style="margin:.4rem 0 0; user-select:text;"><code data-role="technical-text">' in text
    assert 'Connection unavailable.' in text and 'Settings \\u2192 Connections' in text
    # Raw error text never goes straight into the visible result line.
    assert "setResult(id, j.error" not in text and "setResult(id, 'Request failed" not in text
    assert 'Config error: ${esc(b.config_error)}' not in text
    # Test/counts requests and Settings access are untouched.
    assert "`/api/connections/${encodeURIComponent(id)}/test`" in text and "{ method: 'POST' }" in text
    assert 'redact(' in text and '***' in text


# ---------------------------------------------------- Browse recognition

def test_browse_recognition_is_a_compact_summary_linking_to_datasets():
    text = (TEMPLATES / 'files' / 'datasets.html').read_text()
    for needle in ('data-testid', 'recognition-summary', 'recognition-count', 'recognition-preview',
                   'recognition-link', 'RECOG_PREVIEW', "view:'datasets'", 'indexed-add-datasets',
                   'CollectionBasket.checkbox', "scidk:inspect"):
        assert needle in text, needle
    assert 'POST' not in text[text.index('const RECOG_PREVIEW'):text.index('// Sidebar: saved shortcuts')]


# ------------------------------------------------------ launcher stale state

def make_state(tmp_path, monkeypatch, port):
    from scidk import live_development as ld
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(ld, 'load', lambda s: (dict(port=port), None, None))
    return ld, state


def test_stale_record_is_not_a_running_instance_and_stop_clears_only_that_record(tmp_path, monkeypatch, capsys):
    ld, state = make_state(tmp_path, monkeypatch, 59999)
    keep = state / 'files.db'
    keep.write_text('unrelated')
    (state / 'process.json').write_text('{"pid": 2147483000, "start_ticks": "1"}')
    assert ld.live_process(state) is None
    ld.stop(state)
    assert not (state / 'process.json').exists() and keep.read_text() == 'unrelated'
    assert 'No running instance' in capsys.readouterr().out


def test_unreadable_record_is_treated_as_stale(tmp_path, monkeypatch):
    ld, state = make_state(tmp_path, monkeypatch, 59999)
    (state / 'process.json').write_text('not json')
    assert ld.live_process(state) is None


def test_start_refuses_a_port_held_by_a_foreign_process_without_touching_it(tmp_path, monkeypatch):
    ld, state = make_state(tmp_path, monkeypatch, 0)
    with socket.socket() as holder:
        holder.bind(('127.0.0.1', 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        monkeypatch.setattr(ld, 'load', lambda s: (dict(port=port), None, None))
        (state / 'process.json').write_text('{"pid": 2147483000, "start_ticks": "1"}')
        with pytest.raises(ld.LaunchRefused, match='in use by another process'):
            ld.start(state)
        assert holder.fileno() != -1
    assert not (state / 'process.json').exists()   # the stale record was cleared, nothing else


def test_port_free_ignores_time_wait_leftovers():
    from scidk.live_development import port_free
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    port = server.getsockname()[1]
    client = socket.create_connection(('127.0.0.1', port))
    conn, _ = server.accept()
    conn.close(); client.close(); server.close()      # leaves the 4-tuple in TIME_WAIT
    assert port_free(port)
