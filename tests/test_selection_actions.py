"""Selection action bar + inspector re-homing (Files, Scans), and the legacy Annotate drawer flag.

Static checks render the Files page; the browser checks run the real page in Chromium on a loopback port.
Every API answer is a synthetic stand-in served by the test (no graph, no storage, no files.db), and all
names are synthetic. Browser tests skip when no local Chromium is available.
"""
import json
import os
import re
import shutil
import threading
from urllib.parse import urlsplit, parse_qs

import pytest
from werkzeug.serving import make_server

from scidk.app import create_app

FOLDER = '/synthetic/demo/notes'
FILE_A = '/synthetic/demo/a.csv'
FILE_B = '/synthetic/demo/b.csv'
SCAN_ROOT = '/synthetic/share'
DATASET_ROOT = '/synthetic/share/runA'


def _app(monkeypatch, tmp_path, **config):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    monkeypatch.delenv('SCIDK_LEGACY_ANNOTATE_ENABLED', raising=False)
    app = create_app()
    app.config['TESTING'] = True
    app.config.update(config)
    return app


def _page_html(app):
    return app.test_client().get('/datasets').data.decode('utf-8')


# ── static: flag and no duplicate ids ────────────────────────────────────────

def test_without_inspector_the_legacy_drawer_is_still_the_surface(monkeypatch, tmp_path):
    html = _page_html(_app(monkeypatch, tmp_path))
    assert 'id="annotate-drawer"' in html and 'id="annotate-btn"' in html
    assert html.count('id="attr-anchor-label-sel"') == 1
    assert 'id="shared-inspector"' not in html


def test_inspector_replaces_the_drawer_unless_the_flag_is_on(monkeypatch, tmp_path):
    html = _page_html(_app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True))
    assert 'id="annotate-drawer"' not in html and 'id="annotate-btn"' not in html
    # The Attribute controls move behind "More options" in the inspector, exactly once.
    assert html.count('id="attr-anchor-label-sel"') == 1
    more = html[html.index('id="inspector-more-options"'):]
    assert more.index('id="inspector-attribute-controls"') < more.index('id="attr-anchor-label-sel"')
    assert 'data-annotate-open-legacy' not in html
    for needed in ('data-inspector-tab="Interpret"', 'id="files-selection-actions"', 'id="scans-selection-actions"',
                   'js/selection_actions.js', 'js/inspector_actions.js'):
        assert needed in html, needed


@pytest.mark.parametrize('how', ['config', 'env'])
def test_legacy_flag_keeps_the_drawer_and_does_not_duplicate_ids(monkeypatch, tmp_path, how):
    app = _app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True)
    if how == 'config':
        app.config['SCIDK_LEGACY_ANNOTATE_ENABLED'] = True
    else:
        monkeypatch.setenv('SCIDK_LEGACY_ANNOTATE_ENABLED', '1')
    html = _page_html(app)
    assert 'id="annotate-drawer"' in html and 'id="annotate-btn"' in html
    assert html.count('id="attr-anchor-label-sel"') == 1
    assert 'id="inspector-attribute-controls"' not in html
    assert 'data-annotate-open-legacy' in html


def test_entities_page_mounts_the_same_bar():
    """The Entities page is behind the graph-management read grant, so check its template source."""
    from pathlib import Path
    source = Path('scidk/ui/templates/_labels_app.html').read_text()
    assert 'id="entities-selection-actions"' in source
    assert "SelectionActions.mount(actionsHost" in source and "surface: 'entities'" in source
    assert "kind: 'context'" in source
    assert 'js/selection_actions.js' in Path('scidk/ui/templates/base.html').read_text()


# ── browser ──────────────────────────────────────────────────────────────────

playwright_sync = pytest.importorskip('playwright.sync_api')


@pytest.fixture()
def serve(monkeypatch, tmp_path):
    started = []

    def start(**config):
        app = _app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True, **config)
        server = make_server('127.0.0.1', 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started.append((server, thread))
        return f'http://127.0.0.1:{server.server_port}'
    yield start
    for server, thread in started:
        server.shutdown(); thread.join(timeout=5); server.server_close()


class Api:
    """Synthetic answers for every /api call the page makes; records what was sent."""

    def __init__(self):
        self.posts = []        # (path, body)
        self.queries = []      # (path, query dict)
        self.unknown_paths = False

    def __call__(self, route):
        req = route.request
        url = urlsplit(req.url)
        path, query = url.path, parse_qs(url.query)
        body = None
        if req.method == 'POST':
            try:
                body = json.loads(req.post_data or '{}')
            except ValueError:
                body = {}
            self.posts.append((path, body))
        else:
            self.queries.append((path, query))
        status, data = 200, {}
        if path == '/api/servers':
            data = [{'id': 'local_fs', 'display_name': 'Synthetic drive', 'root_id': '/', 'root_path': '/', 'connected': True}]
        elif path == '/api/browse':
            data = {'entries': [{'id': FOLDER, 'path': FOLDER, 'name': 'notes', 'type': 'folder'}] + [
                {'id': f, 'path': f, 'name': f.rsplit('/', 1)[-1], 'type': 'file', 'size': 100 + i}
                for i, f in enumerate((FILE_A, FILE_B))]}
        elif path in ('/api/tasks', '/api/datasets', '/api/scans'):
            data = []
        elif path == '/api/tasks/queue':
            data = {'queue': {'running': [], 'queued': []}}
        elif path == '/api/annotations':
            data = {'items': []}
        elif path == '/api/collections':
            data = {'collections': []}
        elif path == '/api/schema/labels':
            data = {'labels': ['Investigator', 'Lab', 'Folder']}
        elif path == '/api/files/attribution/anchors':
            label = (query.get('anchor_label') or [''])[0]
            data = {'anchors': {'Investigator': [{'name': 'Ada Synthetic'}, {'name': 'Zed Other'}],
                                'Lab': [{'name': 'Synthetic Lab'}]}.get(label, [])}
        elif path == '/api/files/attribution/candidates':
            data = {'candidates': [{'path': '/synthetic/demo', 'confidence': 'HIGH', 'reason': 'name in path',
                                    'relative_depth': 1, 'host_id': 'h'}] if body.get('anchor_name') == 'Ada Synthetic' else []}
        elif path == '/api/files/attribution/relationship-suggestions':
            data = {'suggestions': ['OWNS']}
        elif path == '/api/files/attribution/confirm':
            data = {'written': 1, 'skipped': 0, 'errors': []}
        elif path == '/api/interpreters/status':
            paths = query.get('paths[]', [])
            known = [p for p in paths if p.endswith('.csv')]
            data = {'interpreters': [{'id': 'synthetic_interp', 'name': 'Synthetic interpreter', 'version': '1',
                                      'files': {p.rsplit('/', 1)[-1]: {'path': p, 'status': 'missing', 'interpreted_at': None} for p in known}}] if known else []}
            unknown = [p for p in paths if p not in known]
            if unknown:
                data['unknown_paths'] = unknown
        elif path == '/api/interpreters/run':
            status, data = 202, {'status': 'accepted', 'task_id': 'task1'}
        elif path == '/api/tasks/task1':
            data = {'id': 'task1', 'status': 'completed'}
        elif path == '/api/external-index/scans':
            data = {'scans': [{'id': 's1', 'root': SCAN_ROOT, 'host': 'synthetic-host', 'share': 'synthetic-share', 'date': '2026-01-01', 'files': 10, 'bytes': 1000, 'status': 'complete', 'complete': True}],
                    'shares': [{'share': 'synthetic-share', 'files': 10, 'date': '2026-01-01', 'primary_id': 's1', 'primary_is_full_root': True, 'older_ids': []}]}
        elif path == '/api/external-index/browse':
            data = {'entries': [{'name': 'raw', 'path': SCAN_ROOT + '/raw', 'type': 'folder'},
                                {'name': 'a.csv', 'path': SCAN_ROOT + '/a.csv', 'type': 'file', 'size': 10, 'modified': 1700000000, 'extension': 'csv'}],
                    'next_offset': 2, 'has_more': False}
        elif path == '/api/external-index/datasets':
            data = {'datasets': [{'root_path': DATASET_ROOT, 'pattern_name': 'synthetic_pattern', 'file_count': 3,
                                  'total_bytes': 300, 'confidence': 0.9, 'status': 'recognized'}], 'has_more': False}
        route.fulfill(status=status, content_type='application/json', body=json.dumps(data))


@pytest.fixture()
def browser_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('SCIDK_TEST_CHROME') or shutil.which('google-chrome'))
        except Exception as error:  # noqa: BLE001
            pytest.skip('Local Chromium unavailable: ' + str(error).splitlines()[0])
        try:
            page = browser.new_context(viewport={'width': 1400, 'height': 900}).new_page()
            api = Api()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/api/**', api)
            page.route(re.compile(r'https://(unpkg\.com|cdnjs\.cloudflare\.com)/.*'),
                       lambda r: r.fulfill(status=200, content_type='application/javascript', body=''))
            yield page, api, errors
        finally:
            browser.close()


def _check_rows(page, *ids):
    for i in ids:
        page.locator(f'.row-cb[data-id="{i}"]').check()


def test_files_bar_actions_and_checkbox_never_opens_inspector(serve, browser_page):
    from playwright.sync_api import expect
    page, api, errors = browser_page
    page.goto(serve() + '/datasets')
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)
    expect(page.locator('#annotate-btn')).to_have_count(0)           # legacy drawer is off by default here
    expect(page.locator('#files-selection-actions [data-testid="selection-actions-bar"]')).to_be_hidden()

    _check_rows(page, FILE_A, FOLDER)
    bar = page.locator('#files-selection-actions [data-testid="selection-actions-bar"]')
    expect(bar).to_be_visible()
    for label in ('Add to collection', 'Create dataset', 'Interpret', 'Ask about this'):
        expect(bar.get_by_role('button', name=label)).to_be_visible()
    expect(page.locator('#shared-inspector')).to_be_hidden()          # a checkbox click never opens the inspector

    # Create dataset → the existing manual Dataset dialog.
    page.locator('#create-dataset-btn').click()
    expect(page.locator('#manual-ds-dialog')).to_be_visible()
    page.locator('#manual-ds-cancel').click()

    # Interpret → the inspector opens on the Interpret tab and runs the existing interpreters (files only).
    bar.locator('[data-testid="selection-action-interpret"]').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    expect(page.locator('#inspector-tab-interpret')).to_have_attribute('aria-selected', 'true')
    expect(page.locator('#interpret-run-status')).to_contain_text('Done.')
    run = [b for p, b in api.posts if p == '/api/interpreters/run']
    assert run == [{'paths': [FILE_A], 'mode': 'missing_only'}]
    status_query = [q for p, q in api.queries if p == '/api/interpreters/status'][0]
    assert status_query['paths[]'] == [FILE_A]

    # Add to collection → the shared basket gets both rows.
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
    expect(bar).to_be_hidden()                                        # selection cleared → bar gone
    assert not errors, errors


def test_files_row_click_still_opens_inspector_and_who_confirm(serve, browser_page):
    from playwright.sync_api import expect
    page, api, errors = browser_page
    page.goto(serve() + '/datasets')
    page.locator(f'tr[data-id="{FILE_A}"] .col-name').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    page.locator('#inspector-tab-annotations').click()
    expect(page.locator('#who-start')).to_have_text('Who / which project is this?')
    expect(page.locator('#inspector-more-options')).to_be_visible()   # advanced controls are behind More options
    expect(page.locator('#attr-anchor-label-sel')).to_be_hidden()

    page.locator('#who-start').click()
    suggestion = page.locator('[data-testid="who-suggestion"]')
    expect(suggestion).to_have_count(1)
    expect(suggestion).to_contain_text('Ada Synthetic')
    expect(suggestion).to_contain_text('HIGH')
    suggestion.get_by_role('button', name=re.compile('Confirm')).click()
    expect(page.locator('#who-status')).to_contain_text('Linked to Ada Synthetic')
    confirm = [b for p, b in api.posts if p == '/api/files/attribution/confirm']
    assert confirm == [{'anchor_name': 'Ada Synthetic', 'anchor_label': 'Investigator', 'target_label': 'Folder',
                        'target_paths': ['/synthetic/demo'], 'relationship': 'OWNS'}]

    page.locator('#inspector-more-options summary').click()
    expect(page.locator('#attr-anchor-label-sel')).to_be_visible()
    assert not errors, errors


def test_scans_dataset_selection_collection_and_interpret(serve, browser_page):
    from playwright.sync_api import expect
    page, api, errors = browser_page
    page.goto(serve() + '/datasets')
    page.locator('#gui-scans-tab').click()
    page.locator('#scans-list summary').first.click()                 # the share is collapsed until opened
    page.locator('#scans-list button[data-scan-id="s1"]').click()
    expect(page.locator('#scans-rows tr')).to_have_count(2)
    bar = page.locator('#scans-selection-actions [data-testid="selection-actions-bar"]')
    expect(bar).to_be_hidden()

    page.locator('#scans-datasets input.coll-add-cb').check()
    expect(bar).to_be_visible()
    expect(page.locator('#scans-add')).to_be_visible()
    expect(bar.locator('[data-testid="selection-action-dataset"]')).to_be_hidden()   # recognized datasets aren't re-created
    expect(page.locator('#shared-inspector')).to_be_hidden()                          # ticking never opens the inspector

    bar.locator('[data-testid="selection-action-interpret"]').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    expect(page.locator('#inspector-title')).to_contain_text('Dataset: runA')
    expect(page.locator('#inspector-tab-interpret')).to_have_attribute('aria-selected', 'true')
    expect(page.locator('#interpret-status')).to_contain_text("not in SciDK's own file index")
    assert [q['paths[]'] for p, q in api.queries if p == '/api/interpreters/status'] == [[DATASET_ROOT]]
    assert not [1 for p, _ in api.posts if p == '/api/interpreters/run']              # nothing to run for unknown paths

    page.locator('#scans-add').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    expect(bar).to_be_hidden()

    # A scan-index file row: collection and interpret apply, Create dataset does not.
    page.locator('#scans-rows input.coll-add-cb').nth(1).check()
    expect(bar).to_be_visible()
    expect(bar.locator('[data-testid="selection-action-dataset"]')).to_be_hidden()
    assert not errors, errors


def test_ask_about_this_carries_the_selection_into_chat(serve, browser_page):
    from playwright.sync_api import expect
    page, api, errors = browser_page
    page.goto(serve() + '/datasets')
    _check_rows(page, FILE_A, FILE_B)
    page.locator('#files-selection-actions [data-testid="selection-action-ask"]').click()
    page.wait_for_url(re.compile(r'/chat\?scope=selection'))
    banner = page.locator('[data-testid="ask-scope-banner"]')
    expect(banner).to_contain_text('2 selected item(s)')
    expect(banner).to_contain_text('a.csv')
    assert 'a.csv' in page.locator('#chat-input').input_value()


def test_legacy_flag_keeps_the_old_drawer_working(serve, browser_page):
    from playwright.sync_api import expect
    page, api, errors = browser_page
    page.goto(serve(SCIDK_LEGACY_ANNOTATE_ENABLED=True) + '/datasets')
    page.locator('#annotate-btn').click()
    expect(page.locator('#annotate-drawer')).to_be_visible()
    expect(page.locator('#attr-anchor-label-sel')).to_be_visible()
    page.locator('[data-annotate-tab="interpret"]').click()
    expect(page.locator('#annotate-tab-interpret')).to_be_visible()
    page.locator('[data-annotate-tab="collect"]').click()
    expect(page.locator('#collect-name')).to_be_visible()
    assert not errors, errors
