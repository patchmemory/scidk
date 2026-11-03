"""Resources workspace (Connections | Sources | Plugins | Runs) and the visual Knowledge -> Sketch canvas.

Everything here is UI re-homing over existing tools and APIs: synthetic names only, a temporary settings database, no
graph, no files.db.
"""
import os
import pathlib
import re
import shutil
import threading

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'scidk' / 'ui' / 'templates'
STATIC_JS = ROOT / 'scidk' / 'ui' / 'static' / 'js'


@pytest.fixture
def gui_app(tmp_path):
    from tests.gui.harness import make_gui_app
    app = make_gui_app()
    app.config['SCIDK_GUI_V3_ENABLED'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    return app


@pytest.fixture
def client(gui_app, monkeypatch):
    monkeypatch.setattr('scidk.agent_tools.security.FULL_ACCESS', True)
    return gui_app.test_client()


@pytest.fixture
def source_id(gui_app):
    """A synthetic configured source, created through the store the Sources page uses."""
    from scidk.pipeline.store import PipelineStore
    store = PipelineStore(gui_app.config['SCIDK_SETTINGS_DB'])
    return store.create_source(name='Synthetic source', plugin_type='table_loader',
                               source_path={'source_path': '/synthetic/table.csv'})['id']


def page(client, url, status=200):
    response = client.get(url)
    assert response.status_code == status, (url, response.status_code)
    return response.get_data(as_text=True)


def tabs(html):
    nav = re.search(r'<nav class="[^"]*\bresources-tabs\b[^"]*".*?</nav>', html, re.S).group(0)
    return re.findall(r'<a\b[^>]*>([^<]*)</a>', nav)


def current_tab(html):
    nav = re.search(r'<nav class="[^"]*\bresources-tabs\b[^"]*".*?</nav>', html, re.S).group(0)
    return re.search(r'<a\b[^>]*aria-current="page"[^>]*>([^<]*)</a>', nav).group(1)


# ---------------------------------------------------------------- Resources: routing

def test_exactly_four_resources_tabs_on_every_view_and_alias(client):
    for url, expected in [('/resources', 'Sources'), ('/resources?view=ecosystem', 'Ecosystem'),
                          ('/resources?view=connections', 'Ecosystem'),
                          ('/resources?view=sources', 'Sources'), ('/resources?view=plugins', 'Plugins'),
                          ('/resources?view=runs', 'Runs'), ('/resources?view=bogus', 'Sources'),
                          ('/resources?view=mappings', 'Plugins')]:
        html = page(client, url)
        assert tabs(html) == ['Ecosystem', 'Sources', 'Plugins', 'Runs'], url
        assert current_tab(html) == expected, url
        assert 'Mappings' not in tabs(html)


def test_resources_sidebar_leads_to_the_useful_default_tab(client):
    html = page(client, '/resources')
    assert 'data-testid="add-source-btn"' in html and 'id="sources-list"' in html


def test_the_shell_nav_points_resources_at_the_workspace(client):
    nav = re.search(r'<nav data-testid="nav"[^>]*>.*?</nav>', page(client, '/resources'), re.S).group(0)
    assert '/resources?view=sources" data-testid="nav-resources"' in nav


def test_resources_workspace_is_only_available_in_the_gui_shell(gui_app):
    gui_app.config['SCIDK_GUI_V3_ENABLED'] = False
    assert gui_app.test_client().get('/resources').status_code == 404


# ------------------------------------------------- Resources: real tools under each tab

def test_sources_tab_is_the_real_sources_page_shared_with_the_legacy_route(client):
    workspace = page(client, '/resources?view=sources')
    legacy = page(client, '/pipeline/sources')
    for needle in ('data-testid="add-source-btn"', 'id="source-sheet"', 'id="schedule-sheet"',
                   'data-testid="test-connection-btn"', 'data-testid="upload-btn"', "/api/pipeline/sources/test-connection",
                   "/api/pipeline/sources/upload", '/api/pipeline/sources/${sourceId}/run', 'data-testid="fair-check-btn"'):
        assert needle in workspace, needle
        assert needle in legacy, needle
    assert 'resources-tabs' not in legacy and 'sources-context' not in legacy      # legacy keeps its own shell
    assert 'iframe' not in workspace.lower().replace('no iframe', '')
    # one implementation: both pages include the same partial
    assert "{% include '_pipeline_sources_app.html' %}" in (TEMPLATES / 'pipeline_sources.html').read_text()
    assert "{% include '_pipeline_sources_app.html' %}" in (TEMPLATES / 'gui' / 'resources_workspace.html').read_text()


def test_sources_explains_configured_inputs_and_offers_the_builtin_import_without_redirecting_to_plugins(client):
    workspace = page(client, '/resources?view=sources')
    assert 'data-testid="sources-no-plugins"' not in workspace and 'data-testid="sources-to-plugins"' not in workspace
    assert '/resources?view=plugins' in workspace and 'configured, repeatable input' in workspace
    legacy = page(client, '/pipeline/sources')
    assert 'const WORKSPACE = false' in legacy and 'const WORKSPACE = true' in workspace
    assert 'data-testid="sources-empty"' in workspace and 'data-testid="sources-empty"' in legacy   # plugin-less legacy copy kept


def test_plugins_tab_is_a_registry_over_the_existing_plugin_apis(client):
    html = page(client, '/resources?view=plugins')
    for needle in ('data-testid="plugins-registry"', 'data-testid="plugins-installed"', 'data-testid="plugins-capabilities"',
                   "get('/api/plugins')", "get('/api/plugins/templates')", "get('/api/pipeline/sources')",
                   'Source connectors', 'Enrichment', 'No external plugins are installed',
                   'data-testid="plugins-source-tools"'):
        assert needle in html, needle
    assert 'Settings &rarr; Plugins' in html


def test_plugin_registry_uses_existing_endpoints_and_no_new_backend(client):
    plugins = (ROOT / 'scidk' / 'web' / 'routes' / 'api_plugins.py').read_text()
    assert "@bp.get('')" in plugins and "@bp.get('/templates')" in plugins            # the registry's data, already there
    rules = {r.rule for r in client.application.url_map.iter_rules()}
    assert not [r for r in rules if r.startswith('/api/resources') or r.startswith('/api/runs')]


def test_schema_and_mapping_tools_open_as_plugin_capabilities_for_a_source(client, source_id):
    schema = page(client, f'/resources?view=plugins&source={source_id}&step=schema')
    mapping = page(client, f'/resources?view=plugins&source={source_id}&step=mapping')
    assert tabs(schema) == tabs(mapping) == ['Ecosystem', 'Sources', 'Plugins', 'Runs'] and current_tab(schema) == 'Plugins'
    # the real schema canvas (Arrows import/export, derive, save) and the real column-mapping tool
    for needle in ('data-testid="schema-canvas-page"', 'data-testid="import-arrows"', 'data-testid="export-arrows"',
                   'Save schema', f'/api/pipeline/sources/${{SOURCE_ID}}/schema'):
        assert needle in schema, needle
    for needle in ('data-testid="mapping-page"', 'data-testid="save-mapping"', 'data-testid="columns-panel"',
                   'js/pipeline_mapping.js'):
        assert needle in mapping, needle
    for html in (schema, mapping):
        assert 'data-testid="plugin-steps"' in html and 'data-testid="crumb-plugins"' in html and 'data-testid="plugin-to-runs"' in html
        assert 'Synthetic source' in html
        assert 'data-testid="mapping-page"' not in html or html is mapping
    assert 'Mappings' not in tabs(mapping)
    # the unknown-step default is the column mapping, an unknown source is a 404
    assert 'data-testid="mapping-page"' in page(client, f'/resources?view=plugins&source={source_id}')
    page(client, '/resources?view=plugins&source=missing&step=schema', status=404)


def test_old_mappings_links_still_work_and_land_on_plugins(client, source_id):
    assert current_tab(page(client, '/resources?view=mappings')) == 'Plugins'
    html = page(client, f'/resources?view=mappings&source={source_id}&step=schema')
    assert 'data-testid="schema-canvas-page"' in html and current_tab(html) == 'Plugins'


def test_sources_cards_send_schema_and_mapping_to_plugins_in_the_workspace_and_keep_legacy_urls(client):
    workspace = page(client, '/resources?view=sources')
    assert '/resources?view=plugins&source=${encodeURIComponent(sourceId)}&step=schema' in workspace
    assert '/resources?view=plugins&source=${encodeURIComponent(sourceId)}&step=mapping' in workspace
    assert 'view=mappings' not in workspace
    legacy = page(client, '/pipeline/sources')
    assert '`${BASE}/pipeline/sources/${sourceId}/schema`' in legacy and '`${BASE}/pipeline/sources/${sourceId}/mapping`' in legacy


def test_legacy_pipeline_pages_keep_their_urls_shell_and_breadcrumbs(client, source_id):
    for step, marker in (('schema', 'data-testid="schema-canvas-page"'), ('mapping', 'data-testid="mapping-page"')):
        html = page(client, f'/pipeline/sources/{source_id}/{step}')
        assert marker in html and 'resources-tabs' not in html and 'data-testid="plugin-steps"' not in html
        assert '/pipeline/sources">Resources</a>' in html and 'crumb-plugins' not in html
        assert f'/pipeline/sources?source={source_id}' in html
    page(client, '/pipeline/sources/missing/schema', status=404)
    page(client, '/pipeline/sources/missing/mapping', status=404)
    assert "{% include '_pipeline_schema_app.html' %}" in (TEMPLATES / 'pipeline_schema.html').read_text()
    assert "{% include '_pipeline_mapping_app.html' %}" in (TEMPLATES / 'pipeline_mapping.html').read_text()


def test_working_legacy_tools_are_not_replaced_by_placeholders():
    for name, needles in {'_pipeline_sources_app.html': ('/api/pipeline/sources/${sourceId}/fair-check', '/schedule', 'DELETE'),
                          '_pipeline_schema_app.html': ('/schema/import/arrows', '/schema/export/arrows', 'cytoscape'),
                          '_pipeline_mapping_app.html': ('/api/pipeline/sources/${SOURCE_ID}/mapping', '/columns')}.items():
        text = (TEMPLATES / name).read_text()
        assert len(text.splitlines()) > 700 or name == '_pipeline_mapping_app.html'
        for needle in needles:
            assert needle in text, (name, needle)


def test_ecosystem_tab_reuses_the_settings_connection_partials(client):
    html = page(client, '/resources?view=ecosystem')
    assert 'id="connections-overview-section"' in html and 'id="connections-rclone-mounts-section"' in html
    assert "/api/connections" in html and '/api/rclone/mounts' in html
    assert 'Settings &rarr; Connections' in html


def test_runs_tab_launches_schedules_and_reviews_with_existing_endpoints(client):
    html = page(client, '/resources?view=runs')
    for needle in ('data-testid="runs-launch"', 'data-testid="runs-list"', "get('/api/pipeline/pipelines')",
                   '/api/pipeline/pipelines/${encodeURIComponent(p.id)}/runs', '/api/pipeline/sources/${encodeURIComponent(row.dataset.sourceId)}/run',
                   "'?dry_run=1'", 'data-testid="schedule-link"', 'resources?view=sources&schedule=', 'data-testid="runs-empty"',
                   'No runs recorded yet', 'data-testid="launch-empty"'):
        assert needle in html, needle
    assert 'data-testid="runs-workspace"' in html and 'view=plugins' in html


def test_runs_adds_no_scheduler_or_run_backend():
    source = (ROOT / 'scidk' / 'web' / 'routes' / 'ui.py').read_text()
    assert 'apscheduler' not in source.lower() and 'add_job' not in source
    runs = (TEMPLATES / '_resources_runs.html').read_text()
    assert "/schedule'" not in runs and '/schedule`' not in runs   # schedules are edited by the existing Sources dialog
    sources = (TEMPLATES / '_pipeline_sources_app.html').read_text()
    assert "query.get('schedule')" in sources and 'openSchedule(scheduleId' in sources


def test_runs_history_and_launch_work_against_a_real_source(gui_app, monkeypatch, source_id):
    """The same JSON the Runs tab renders from: sources, pipelines and per-pipeline history."""
    from scidk.web.routes import api_pipeline
    gui_app.register_blueprint(api_pipeline.bp)
    client = gui_app.test_client()
    sources = client.get('/api/pipeline/sources').get_json()['sources']
    assert [s['id'] for s in sources] == [source_id]
    pipelines = client.get('/api/pipeline/pipelines').get_json()['pipelines']
    assert all('source_ids' in p for p in pipelines)
    for p in pipelines:
        assert client.get(f"/api/pipeline/pipelines/{p['id']}/runs").get_json()['status'] == 'ok'


# ------------------------------------------------------------------ Sketch (template)

def sketch_html(client):
    return page(client, '/knowledge?view=sketch')


def test_sketch_toolbar_is_visual_first(client):
    html = sketch_html(client)
    bar = re.search(r'<div class="kw-toolbar" role="toolbar" aria-label="Sketch tools".*?</div>', html, re.S).group(0)
    labels = [re.sub(r'<[^>]+>', '', b).strip() for b in re.findall(r'<button\b.*?</button>', bar, re.S)]
    assert labels[:4] == ['Select / move', 'Pan canvas', 'Add node', 'Connect nodes']
    for expected in ('Arrange', 'Fit', 'Save private draft', 'Reopen private draft'):
        assert expected in labels
    assert 'undo' not in bar.lower() and 'redo' not in bar.lower()     # no history system is invented
    assert 'private draft' in html.lower() and 'not live graph data' in html


def test_sketch_ordinary_flow_has_no_raw_id_or_marker_fields(client):
    html = sketch_html(client)
    advanced = re.search(r'<details id="kw-draft-tools".*?</details>', html, re.S).group(0)
    outside = html.replace(advanced, '')
    for raw in ('kw-edge-source', 'kw-edge-target', 'Source draft ID', 'Target draft ID', 'kw-marker', 'Planning marker',
                'kw-set-marker', 'kw-add-edge'):
        assert raw not in outside, raw
        assert raw in advanced, raw        # still reachable, for compatibility, behind the Advanced disclosure
    assert '<details id="kw-draft-tools"' in html and 'open' not in re.search(r'<details id="kw-draft-tools"[^>]*>', html).group(0)
    assert 'Advanced / debug' in advanced
    # visual node and relationship flow
    for needle in ('id="kw-add-panel"', 'id="kw-add-type"', 'Schema entity types', 'Freeform concept', 'id="kw-rel-panel"',
                   'data-testid="connect-type"', 'data-testid="connect-create"'):
        assert needle in html, needle


def test_sketch_inspector_edits_ordinary_fields_and_labels_drafts_private(client):
    html = sketch_html(client)
    aside = re.search(r'<aside id="kw-inspector".*?</aside>', html, re.S).group(0)
    ordinary = aside.replace(re.search(r'<details id="kw-draft-tools".*?</details>', aside, re.S).group(0), '')
    for needle in ('data-testid="edit-name"', 'data-testid="edit-type"', 'data-testid="edit-notes"', 'data-testid="edit-rel"',
                   'data-testid="edge-source-name"', 'data-testid="edge-target-name"', 'data-testid="edit-edge-notes"',
                   'Private proposal', 'not live graph data', 'data-testid="inspector-empty"'):
        assert needle in ordinary, needle


def test_sketch_save_and_reopen_use_the_private_canvas_session_never_the_graph():
    source = (STATIC_JS / 'knowledge_workspace.js').read_text()
    visual = source[source.index('const SKETCH_CONTEXT'):source.index('async function load(kind)')]
    assert "/api/canvas/session" in visual and "knowledge:research:sketch" in visual
    assert "provisional" in visual                       # only draft elements are stored
    for forbidden in ('/api/neo4j', '/api/canvas/commit', '/api/links', '/api/labels/', '/api/pipeline', 'MERGE', 'execute'):
        assert forbidden not in source[source.index('// ---- Visual Sketch tools'):source.index('async function changeDomain()')], forbidden
    # the only server read the visual tools make is the schema vocabulary (GET /api/labels)
    tools = source[source.index('// ---- Visual Sketch tools'):source.index('async function changeDomain()')]
    assert tools.count("fetch(") == 1 and "fetch(base + '/api/labels')" in tools


def test_other_knowledge_views_and_the_governed_sketch_controls_are_unchanged(client):
    for view, marker in (('entities', 'knowledge-tab-entities'), ('maps', 'knowledge-tab-maps')):
        assert marker in page(client, f'/knowledge?view={view}')
    assert tabs_knowledge(sketch_html(client)) == ['Entities', 'Relationships', 'Maps', 'Sketch']
    governed = page(client, '/knowledge?view=governed')
    assert 'kw-rel-panel' not in governed          # the governed workspace keeps its original controls


def tabs_knowledge(html):
    nav = re.search(r'<nav class="[^"]*\bknowledge-tabs\b[^"]*".*?</nav>', html, re.S).group(0)
    return re.findall(r'<a\b[^>]*>([^<]*)</a>', nav)


# ------------------------------------------------------------------ Sketch (browser)

@pytest.fixture
def live(tmp_path, monkeypatch):
    """The real UI + canvas-session blueprints behind a loopback server; every non-GET request is recorded."""
    from flask import jsonify, request
    from werkzeug.serving import make_server
    from scidk.web.routes import api_canvas
    from tests.gui.harness import make_gui_app
    monkeypatch.setattr('scidk.agent_tools.security.FULL_ACCESS', True)
    app = make_gui_app()
    app.config.update(SCIDK_GUI_V3_ENABLED=True, SCIDK_SETTINGS_DB=str(tmp_path / 'settings.db'))
    app.register_blueprint(api_canvas.bp)
    writes = []

    @app.before_request
    def record():
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            writes.append((request.method, request.path))

    @app.get('/api/labels')
    def labels():
        return jsonify(status='success', labels=[{'name': 'SyntheticSample', 'relationships': [{'type': 'DERIVED_FROM'}]},
                                                  {'name': 'SyntheticRun', 'relationships': []}])

    @app.get('/api/auth/status')
    def auth():
        return jsonify(authenticated=True, auth_enabled=False)

    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', writes, app.config['SCIDK_SETTINGS_DB']
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()


def cy(page, expression):
    return page.evaluate('(function(){const cy = document.getElementById("kw-sketch")._cyreg.cy; return (' + expression + ');})()')


def in_thread(function, *args):
    """Run Playwright's sync API on a thread with no event loop (other GUI tests leave one running in-process)."""
    outcome = {}

    def target():
        try:
            function(*args)
        except BaseException as error:   # noqa: BLE001 - re-raised on the test thread
            outcome['error'] = error
    thread = threading.Thread(target=target)
    thread.start(); thread.join()
    if 'error' in outcome:
        raise outcome['error']


def test_sketch_visual_flow_place_connect_edit_arrange_save_and_reopen(live):
    pytest.importorskip('playwright.sync_api')
    origin, writes, settings_db = live
    in_thread(visual_flow, origin)
    # Private draft ownership: the only write is the per-user canvas session; no graph, links, labels or pipeline write
    assert {path for _, path in writes} == {'/api/canvas/session'} and {m for m, _ in writes} == {'POST'}
    from scidk.services.canvas_service import CanvasService
    stored = CanvasService(settings_db).load_session('anonymous', 'knowledge:research:sketch')
    assert stored and all(e['data'].get('provisional') for e in stored['canvas']['elements'])


def visual_flow(origin):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('SCIDK_TEST_CHROME') or shutil.which('google-chrome'))
        try:
            page = browser.new_page(viewport={'width': 1400, 'height': 1700})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(origin + '/knowledge?view=sketch'); page.wait_for_selector('#kw-sketch')
            page.wait_for_function("document.querySelectorAll('#kw-add-schema-types option').length > 0")
            canvas = page.locator('#kw-sketch')
            # raw ids are not on screen in the ordinary flow
            for raw in ('#kw-edge-source', '#kw-edge-target', '#kw-marker'):
                assert not page.locator(raw).is_visible(), raw
            # Add node: schema entity type or freeform
            page.get_by_test_id('tool-add-node').click()
            assert 'SyntheticSample' in page.locator('#kw-add-type').inner_text()
            page.get_by_test_id('add-node-type').select_option('SyntheticSample')
            page.get_by_test_id('add-node-name').fill('Synthetic idea A'); canvas.click(position={'x': 160, 'y': 120})
            page.get_by_test_id('add-node-type').select_option('__free__')
            page.get_by_test_id('add-node-freeform').fill('Hypothesis')
            page.get_by_test_id('add-node-name').fill('Synthetic idea B'); canvas.click(position={'x': 420, 'y': 220})
            assert cy(page, 'cy.nodes().length') == 2
            assert cy(page, 'cy.nodes().map(n => n.data("label")).sort().join()') == 'Hypothesis,SyntheticSample'
            # Connect nodes visually: click source, click target, choose the relationship
            page.get_by_test_id('tool-connect').click()
            canvas.click(position={'x': 160, 'y': 120}); canvas.click(position={'x': 420, 'y': 220})
            assert page.get_by_test_id('connect-panel').is_visible()
            assert page.get_by_test_id('connect-source').inner_text() == 'Synthetic idea A'
            assert page.get_by_test_id('connect-target').inner_text() == 'Synthetic idea B'
            page.get_by_test_id('connect-type').fill('INFORMS'); page.get_by_test_id('connect-create').click()
            assert cy(page, 'cy.edges().length') == 1 and cy(page, 'cy.edges()[0].data("label")') == 'INFORMS'
            # Relationship inspector: source, type, target, notes
            assert page.get_by_test_id('edge-source-name').inner_text() == 'Synthetic idea A'
            assert page.get_by_test_id('edge-target-name').inner_text() == 'Synthetic idea B'
            page.get_by_test_id('edit-edge-notes').fill('Synthetic relationship note')
            # Node inspector: display name, type, notes
            page.get_by_test_id('tool-select').click(); canvas.click(position={'x': 160, 'y': 120})
            page.get_by_test_id('edit-name').fill('Synthetic idea A (renamed)'); page.get_by_test_id('edit-notes').fill('Synthetic note')
            assert cy(page, 'cy.nodes().filter(n => n.data("displayLabel") === "Synthetic idea A (renamed)").length') == 1
            # Arrange / fit
            page.get_by_test_id('tool-arrange').click(); page.get_by_test_id('tool-fit').click()
            # Save the private draft, reload, reopen
            page.get_by_test_id('tool-save').click()
            page.wait_for_function("document.getElementById('kw-status').textContent.includes('Saved private sketch')")
            page.reload(); page.wait_for_selector('#kw-sketch')
            assert cy(page, 'cy.nodes().length') == 0
            page.get_by_test_id('tool-reopen').click()
            page.wait_for_function("document.getElementById('kw-status').textContent.includes('Reopened private sketch')")
            assert cy(page, 'cy.nodes().length') == 2 and cy(page, 'cy.edges().length') == 1
            assert cy(page, 'cy.nodes().map(n => n.data("displayLabel")).sort().join()') == 'Synthetic idea A (renamed),Synthetic idea B'
            assert cy(page, 'cy.edges()[0].data("properties").notes') == 'Synthetic relationship note'
            assert cy(page, 'cy.nodes().filter(n => n.data("provisional")).length') == 2
            assert not errors, errors
        finally:
            browser.close()
