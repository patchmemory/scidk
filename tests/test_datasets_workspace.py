"""Datasets workspace: Browse | Datasets | Collections | Scans.

Static checks render the pages; API checks use a synthetic scan index (opened read-only) and a fake graph client;
browser checks run the real pages in Chromium on a loopback port against synthetic API answers. All names are
synthetic. Browser tests skip when no local Chromium is available.
"""
import hashlib
import json
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.test_collections import FakeNeo4jClient, _writes
from tests.test_external_index_api import _build, SCAN
from tests.test_selection_actions import (  # noqa: F401 - fixtures and shared constants
    Api, DATASET_ROOT, FILE_A, FOLDER, SCAN_ROOT, _app, browser_page, serve)

VIEWS = ('browse', 'datasets', 'collections', 'scans')


def _gui_client(monkeypatch, tmp_path, **config):
    app = _app(monkeypatch, tmp_path, SCIDK_GUI_V3_ENABLED=True, **config)
    return app.test_client()


def _html(client, url):
    response = client.get(url)
    assert response.status_code == 200, url
    return response.get_data(as_text=True)


def _tabs(html):
    nav = re.search(r'<nav class="datasets-tabs".*?</nav>', html, re.S).group(0)
    return re.findall(r'<a\b[^>]*>([^<]*)</a>', nav)


# ── sidebar and tab strip ────────────────────────────────────────────────────

def test_sidebar_says_datasets_and_tabs_are_exactly_the_four(monkeypatch, tmp_path):
    client = _gui_client(monkeypatch, tmp_path)
    for view in VIEWS:
        html = _html(client, f'/datasets?view={view}')
        nav = re.search(r'<nav data-testid="nav">.*?</nav>', html, re.S).group(0)
        assert re.search(r'<a href="/datasets\?view=browse">Datasets</a>', nav)
        assert 'Files &amp; Datasets' not in nav and 'Files & Datasets' not in nav
        assert _tabs(html) == ['Browse', 'Datasets', 'Collections', 'Scans']
        assert re.search(rf'data-testid="datasets-tab-{view}" aria-current="page"', html)
        for key in VIEWS:  # every tab is a bookmarkable link
            assert f'href="/datasets?view={key}"' in html


def test_view_aliases_and_unknown_views_land_on_browse(monkeypatch, tmp_path):
    client = _gui_client(monkeypatch, tmp_path)
    for url in ('/datasets?view=files', '/datasets?view=nonsense', '/datasets?view='):
        assert 'data-testid="datasets-tab-browse" aria-current="page"' in _html(client, url), url


def test_each_view_mounts_real_content(monkeypatch, tmp_path):
    client = _gui_client(monkeypatch, tmp_path)
    browse = _html(client, '/datasets?view=browse')
    for needle in ('data-testid="files-root"', 'id="file-table"', 'id="files-selection-actions"', 'id="files-collection-slot"',
                   'js/selection_actions.js', 'js/collection.js', 'data-ws-view="browse"'):
        assert needle in browse, needle
    datasets = _html(client, '/datasets?view=datasets')
    for needle in ('id="datasets-list"', 'js/datasets_workspace.js', 'data-ws-view="datasets"',
                   'id="inspector-add-to-collection"'):
        assert needle in datasets, needle
    assert 'id="file-table"' not in datasets
    collections = _html(client, '/datasets?view=collections')
    for needle in ('id="collections-list"', 'id="collection-detail"', 'id="collection-plan-panel"',
                   'id="collection-plan-close"', 'js/datasets_workspace.js', 'data-ws-view="collections"'):
        assert needle in collections, needle
    scans = _html(client, '/datasets?view=scans')
    for needle in ('id="scans-table"', 'id="scans-datasets"', 'id="scans-selection-actions"', 'js/external_index.js',
                   'data-ws-view="scans"'):
        assert needle in scans, needle


def test_legacy_files_and_scans_routes_are_unchanged(monkeypatch, tmp_path):
    client = _gui_client(monkeypatch, tmp_path)
    for url in ('/datasets', '/datasets?scan_id=missing', '/datasets?panel=annotations'):
        html = _html(client, url)
        assert 'data-testid="files-root"' in html and 'id="file-table"' in html, url
        assert 'datasets-tabs' not in html and 'data-ws-view' not in html, url
        assert 'id="gui-files-tab"' in html and 'id="gui-scans-tab"' in html and 'id="gui-datasets-tab"' in html, url
        assert 'Files &amp; Datasets' in html, url
    assert client.get('/annotations').status_code == 302
    # Without the GUI shell the classic Files page is served whatever ?view= says.
    classic = _app(monkeypatch, tmp_path).test_client()
    for view in VIEWS:
        html = _html(classic, f'/datasets?view={view}')
        assert 'data-testid="files-root"' in html and 'datasets-tabs' not in html


def test_knowledge_keeps_its_three_tabs(monkeypatch, tmp_path):
    html = _html(_gui_client(monkeypatch, tmp_path), '/knowledge?view=sketch')
    nav = re.search(r'<nav class="knowledge-tabs".*?</nav>', html, re.S).group(0)
    assert re.findall(r'<a\b[^>]*>([^<]*)</a>', nav) == ['Entities', 'Maps', 'Sketch']
    assert 'datasets-tabs' not in html


def test_no_delete_controls_in_the_collections_page():
    from pathlib import Path
    source = Path('scidk/ui/static/js/datasets_workspace.js').read_text() + \
        Path('scidk/ui/templates/gui/files_inspector.html').read_text()
    for word in ('Delete', 'Dissolve', 'Remove from collection', "method: 'DELETE'"):
        assert word not in source, word


# ── read-only APIs ───────────────────────────────────────────────────────────

@pytest.fixture
def signed_in(tmp_path, monkeypatch):
    """An ordinary signed-in user (role 'user'), a synthetic scan index, and a fake graph."""
    from scidk.app import create_app
    from scidk.core.auth import get_auth_manager
    from scidk.web.routes import api_annotation
    monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
    monkeypatch.delenv('SCIDK_ENCRYPTION_KEY', raising=False)
    db = tmp_path / 'files.db'
    _build(str(db))
    monkeypatch.setenv('SCIDK_EXTERNAL_INDEX_DB', str(db))
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_SETTINGS_DB'] = str(tmp_path / 'settings.db')
    auth = get_auth_manager(db_path=app.config['SCIDK_SETTINGS_DB'])
    uid = auth.create_user('alice', 'password123', role='user')
    client = app.test_client()
    client.set_cookie('scidk_session', auth.create_user_session(uid, 'alice'))
    holder = {}

    def graph(**kwargs):
        holder['graph'] = FakeNeo4jClient(**kwargs)
        monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: holder['graph'])
        return holder['graph']
    return client, app, db, graph


def _digest(db):
    return hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns


def test_recognized_dataset_list_is_alphabetical_with_provenance_and_read_only(signed_in):
    client, app, db, _ = signed_in
    before = _digest(db)
    body = client.get('/api/external-index/datasets/all').get_json()
    assert body['status'] == 'success' and body['read_only'] is True
    names = [d['name'] for d in body['datasets']]
    assert names and names == sorted(names, key=str.lower)
    first = body['datasets'][0]
    # A reference keyed by scan + root, with where it came from; never file rows.
    for key in ('scan_id', 'root_path', 'name', 'pattern_name', 'file_count', 'total_bytes', 'host', 'share', 'scan_root'):
        assert key in first, key
    assert first['scan_id'] == SCAN and first['share'] == 'atwai' and first['host'] == 'data0'
    assert not [k for k in first if k in ('entries', 'files', 'members')]
    only = client.get('/api/external-index/datasets/all?scan_id=scan-2').get_json()
    assert only['datasets'] == []
    assert _digest(db) == before                                  # files.db untouched (mode=ro)
    assert client.post('/api/external-index/datasets/all').status_code == 405
    assert app.test_client().get('/api/external-index/datasets/all').status_code in (401, 403)


def test_manual_dataset_list_is_read_only_and_alphabetical(signed_in):
    client, _, _, graph = signed_in
    g = graph(read_results=[[
        {'id': 'm1', 'name': 'Alpha manual', 'description': None, 'created_at': 5, 'updated_at': 6,
         'members': 3, 'folders': 1, 'files': 2, 'bytes': 300},
        {'id': 'm2', 'name': 'Beta manual', 'description': 'd', 'created_at': 7, 'updated_at': 8,
         'members': 0, 'folders': 0, 'files': 0, 'bytes': None}]])
    r = client.get('/api/datasets/manual')
    assert r.status_code == 200
    rows = r.get_json()['datasets']
    assert [d['name'] for d in rows] == ['Alpha manual', 'Beta manual']
    assert rows[0]['files'] == 2 and rows[0]['folders'] == 1 and rows[0]['bytes'] == 300 and rows[1]['bytes'] == 0
    (kind, query, params), = g.calls
    assert kind == 'read' and 'd.source = $source' in query and params == {'source': 'manual'} and 'ORDER BY toLower' in query
    assert not _writes(g)


def test_collection_list_reports_known_size_and_times(signed_in):
    client, _, _, graph = signed_in
    g = graph(read_results=[[{'id': 'c1', 'name': 'Synthetic', 'description': None, 'created_by': 'x', 'created_at': 1,
                              'updated_at': 2, 'members': 3, 'datasets': 1, 'folders': 1, 'files': 1, 'bytes': 1234}]])
    row = client.get('/api/collections').get_json()['collections'][0]
    assert row['bytes'] == 1234 and row['updated_at'] == 2 and row['context_members'] == 0
    assert not _writes(g)


def test_manual_dataset_joins_a_collection_by_its_id_with_the_same_includes_edge(signed_in):
    client, _, _, graph = signed_in
    g = graph(write_results=[[], [{'linked': 1}], [{'linked': 1}]])
    r = client.post('/api/collections', json={'name': 'Synthetic mixed', 'members': [
        {'kind': 'dataset', 'dataset_id': 'm1', 'name': 'Synthetic manual'},
        {'kind': 'dataset', 'scan_id': 's1', 'root_path': DATASET_ROOT, 'profile': 'p', 'file_count': 3, 'bytes': 300}]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['linked']['dataset'] == 2 and 'not_found' not in r.get_json()
    by_id_q, by_id_p = next((q, p) for q, p in _writes(g) if 'MATCH (d:Dataset {id: row.dataset_id})' in q)
    assert 'MERGE (c)-[:INCLUDES]->(d)' in by_id_q and 'MERGE (d:Dataset' not in by_id_q      # linked, never created
    assert by_id_p['rows'] == [{'dataset_id': 'm1', 'name': 'Synthetic manual'}]
    ref_q, ref_p = next((q, p) for q, p in _writes(g) if 'MERGE (d:Dataset {scan_id' in q)
    assert ref_p['rows'][0]['scan_id'] == 's1' and 'dataset_id' not in ref_p['rows'][0]
    for q, _ in _writes(g):
        assert 'DELETE' not in q.upper() and 'DETACH' not in q.upper() and 'CREATE (' not in q.upper()
    # A manual id that is not in the graph is reported, not created.
    graph(write_results=[[], [{'linked': 0}]])
    r = client.post('/api/collections', json={'name': 'Synthetic missing', 'members': [{'kind': 'dataset', 'dataset_id': 'nope'}]})
    assert r.status_code == 200 and r.get_json()['not_found'] == {'dataset': 1}


def test_collection_detail_returns_manual_dataset_members_with_their_id(signed_in):
    client, _, _, graph = signed_in
    graph(read_results=[[{'id': 'c1', 'name': 'Synthetic', 'description': None, 'created_by': 'x', 'created_at': 1, 'updated_at': None}],
                        [{'eid': 'e1', 'labels': ['Dataset'], 'p': {'id': 'm1', 'name': 'Synthetic manual', 'source': 'manual'}}]])
    member = client.get('/api/collections/c1').get_json()['members']['dataset'][0]
    assert member['dataset_id'] == 'm1' and member['source'] == 'manual' and member['name'] == 'Synthetic manual'


def test_graph_dataset_list_is_read_only(signed_in):
    client, _, _, graph = signed_in
    g = graph(read_results=[[{'id': 'm1', 'name': 'B', 'source': 'manual', 'members': 2, 'folders': 0, 'files': 2, 'bytes': 5},
                             {'id': None, 'name': 'A', 'source': 'files.db', 'scan_id': 's1', 'root_path': '/x', 'members': 0}]])
    rows = client.get('/api/datasets/graph').get_json()['datasets']
    assert [r['name'] for r in rows] == ['B', 'A']                 # order is the graph query's; the page sorts for display
    (kind, query, _), = g.calls
    assert kind == 'read' and 'ORDER BY toLower' in query and not _writes(g)


def test_ordinary_signed_in_user_can_create_a_collection_and_a_manual_dataset(signed_in):
    client, app, _, graph = signed_in
    g = graph(write_results=[[], [{'linked': 1}]])
    member = [{'kind': 'dataset', 'scan_id': 's1', 'root_path': DATASET_ROOT, 'profile': 'p', 'file_count': 3, 'bytes': 300}]
    r = client.post('/api/collections', json={'name': 'Synthetic collection', 'members': member})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['created'] is True and r.get_json()['linked']['dataset'] == 1
    for q, _ in _writes(g):
        assert 'DELETE' not in q.upper() and 'DETACH' not in q.upper() and 'CREATE (' not in q.upper()
    graph(write_results=[[], [{'linked': 1}]])
    r = client.post('/api/datasets/collections', json={'name': 'Synthetic files', 'files': [
        {'name': 'a.csv', 'path': '/synthetic/demo/a.csv', 'host': 'files.db:synthetic', 'type': 'file'}]})
    assert r.status_code == 200, r.get_json()
    # Same audience as manual Dataset creation, and no new gate: an unauthenticated caller is still refused.
    graph(write_results=[[], [{'linked': 1}]])
    assert client.post('/api/datasets/manual', json={'name': 'M', 'members': [
        {'kind': 'file', 'path': '/synthetic/demo/a.csv', 'name': 'a.csv', 'host': 'files.db:synthetic'}]}).status_code == 200
    assert app.test_client().post('/api/collections', json={'name': 'x', 'members': member}).status_code in (401, 403)


# ── browser ──────────────────────────────────────────────────────────────────

COLLECTIONS = [
    {'id': 'c-z', 'name': 'zeta synthetic', 'description': 'Last one', 'members': 1, 'datasets': 1, 'folders': 0, 'files': 0,
     'context_members': 0, 'bytes': 300, 'created_at': 1700000000000, 'updated_at': 1700000100000},
    {'id': 'c-a', 'name': 'Alpha synthetic', 'description': 'Has every kind', 'members': 4, 'datasets': 1, 'folders': 1, 'files': 1,
     'context_members': 1, 'bytes': 400, 'created_at': 1700000000000, 'updated_at': None},
    {'id': 'c-b', 'name': 'beta synthetic', 'description': None, 'members': 0, 'datasets': 0, 'folders': 0, 'files': 0,
     'context_members': 0, 'bytes': 0, 'created_at': None, 'updated_at': None},
]
DETAIL = {'collection': {'id': 'c-a', 'name': 'Alpha synthetic', 'description': 'Has every kind', 'created_at': 1700000000000, 'updated_at': None},
          'members': {'dataset': [{'scan_id': 's1', 'root_path': DATASET_ROOT, 'name': 'runA', 'profile': 'synthetic_pattern', 'file_count': 3, 'bytes': 300}],
                      'folder': [{'path': FOLDER, 'host': 'files.db:synthetic', 'name': 'notes'}],
                      'file': [{'path': FILE_A, 'host': 'files.db:synthetic', 'filename': 'a.csv', 'size_bytes': 100}],
                      'context': [{'id': '4:x:1', 'label': 'Sample', 'display': 'Synthetic sample'}]}}
RECOGNIZED = [
    {'id': 'o2', 'scan_id': 's1', 'name': 'runB', 'pattern_name': 'synthetic_pattern', 'root_path': SCAN_ROOT + '/runB', 'file_count': 8,
     'total_bytes': 800, 'confidence': 0.9, 'status': 'recognized', 'scan_root': SCAN_ROOT, 'host': 'synthetic-host', 'share': 'synthetic-share', 'scan_date': '2026-01-01'},
    {'id': 'o1', 'scan_id': 's1', 'name': 'runA', 'pattern_name': 'synthetic_pattern', 'root_path': DATASET_ROOT, 'file_count': 3,
     'total_bytes': 300, 'confidence': 0.9, 'status': 'recognized', 'scan_root': SCAN_ROOT, 'host': 'synthetic-host', 'share': 'synthetic-share', 'scan_date': '2026-01-01'},
]
GRAPH = [
    {'id': 'm1', 'name': 'Synthetic manual', 'description': 'By hand', 'source': 'manual', 'scan_id': None, 'root_path': None,
     'created_at': 1700000000000, 'updated_at': None, 'members': 3, 'folders': 1, 'files': 2, 'bytes': 300},
    {'id': None, 'name': 'runA', 'description': None, 'source': 'files.db', 'scan_id': 's1', 'root_path': DATASET_ROOT,
     'profile': 'synthetic_pattern', 'file_count': 3, 'dataset_bytes': 300, 'members': 0, 'folders': 0, 'files': 0, 'bytes': 0}]


LOCATIONS = [
    {'scan_id': 'loc-mounted', 'host': 'synthetic-host', 'share': 'mounted-share', 'root': '/synthetic/mounted', 'label': 'synthetic-host · mounted-share',
     'files': 5, 'bytes': 50, 'date': '2026-01-01', 'role': 'primary', 'access': 'mounted'},
    {'scan_id': 's1', 'host': 'synthetic-host', 'share': 'indexed-share', 'root': SCAN_ROOT, 'label': 'synthetic-host · indexed-share',
     'files': 12, 'bytes': 3000, 'date': '2026-01-01', 'role': 'primary', 'access': 'indexed'}]


class WsApi(Api):
    """Catalog answers come from the real merge/paging code over synthetic rows; confirm and edit change a private copy."""

    def __init__(self):
        super().__init__()
        import copy
        self.graph = copy.deepcopy(GRAPH)
        self.candidates = list(RECOGNIZED)

    def catalog(self, query):
        from scidk.services import dataset_catalog as dc
        one = lambda k, d='': (query.get(k) or [d])[0]  # noqa: E731
        page = dc.catalog_page(dc.build_items(self.candidates, self.graph), q=one('q'), state=one('state', 'all'),
                               limit=int(one('limit', '50')), offset=int(one('offset', '0')))
        return dict(page, status='success', read_only=True, notes=[])

    def write(self, path, body):
        if path == '/api/datasets/confirm':
            row = next(r for r in RECOGNIZED if r['scan_id'] == body['scan_id'] and r['root_path'] == body['root_path'])
            if not any(g.get('scan_id') == row['scan_id'] and g.get('root_path') == row['root_path'] for g in self.graph):
                self.graph.append({'id': None, 'name': row['name'], 'name_source': 'observed', 'source': 'files.db', 'scan_id': row['scan_id'],
                                   'root_path': row['root_path'], 'profile': row['pattern_name'], 'file_count': row['file_count'],
                                   'dataset_bytes': row['total_bytes'], 'confirmed_at': 1700000000000, 'confirmed_by': 'synthetic'})
            g = next(g for g in self.graph if g.get('scan_id') == row['scan_id'] and g.get('root_path') == row['root_path'])
            return {'status': 'ok', 'state': 'confirmed', 'name': g['name'], 'description': g.get('description'),
                    'human_profile': g.get('human_profile'), 'observed_profile': row['pattern_name']}
        g = next(g for g in self.graph if (body.get('dataset_id') and g.get('id') == body['dataset_id'])
                 or (body.get('scan_id') and g.get('scan_id') == body['scan_id'] and g.get('root_path') == body['root_path']))
        for key in ('name', 'description', 'human_profile'):
            if key in body:
                g[key] = body[key]
                if key == 'name':
                    g['name_source'] = 'human'
        return {'status': 'ok', 'name': g.get('name'), 'description': g.get('description'),
                'human_profile': g.get('human_profile'), 'observed_profile': g.get('profile')}

    def __call__(self, route):
        req = route.request
        split = urlsplit(req.url)
        path = split.path
        data = None
        if path == '/api/datasets/catalog':
            self.queries.append((path, parse_qs(split.query)))
            data = self.catalog(parse_qs(split.query))
        elif path in ('/api/datasets/confirm', '/api/datasets/metadata') and req.method == 'POST':
            body = json.loads(req.post_data or '{}')
            self.posts.append((path, body))
            data = self.write(path, body)
        elif path == '/api/external-index/locations':
            wanted = [x for x in (parse_qs(split.query).get('shortcuts') or [''])[0].split(',') if x]
            known = {x['scan_id'] for x in LOCATIONS}
            data = {'status': 'success', 'read_only': True, 'locations': LOCATIONS,
                    'unavailable': [{'scan_id': x, 'access': 'unavailable', 'label': 'Unavailable', 'root': None} for x in wanted if x not in known]}
        elif path == '/api/collections' and req.method == 'GET':
            data = {'collections': COLLECTIONS}
        elif path == '/api/collections/c-a':
            data = DETAIL
        elif path == '/api/plugins/nih_dms/collections/c-a/draft_plan':
            self.posts.append((path, {}))
            data = {'markdown': '# Synthetic sharing plan draft\n\nInvestigator review required.'}
        if data is None:
            return super().__call__(route)
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))


@pytest.fixture()
def ws_page(browser_page):
    page, api, errors = browser_page
    page.unroute('**/api/**')
    api = WsApi()
    page.route('**/api/**', api)
    return page, api, errors


def test_browse_view_selection_actions_and_add_to_collection(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=browse')
    expect(page.locator('[data-testid="datasets-tabs"] a')).to_have_text(['Browse', 'Datasets', 'Collections', 'Scans'])
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)
    for i in (FILE_A, FOLDER):
        page.locator(f'.row-cb[data-id="{i}"]').check()
    bar = page.locator('#files-selection-actions [data-testid="selection-actions-bar"]')
    expect(bar).to_be_visible()
    for label in ('Add to collection', 'Create dataset', 'Interpret', 'Ask about this'):
        expect(bar.get_by_role('button', name=label)).to_be_visible()
    page.locator('#add-to-coll-btn').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
    assert not errors, errors


def test_datasets_view_merges_candidate_confirmed_and_manual_and_adds_each_to_the_basket(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=datasets')
    cards = page.locator('#datasets-list .ds-card')
    expect(cards).to_have_count(3)
    expect(page.locator('#datasets-list .ds-name')).to_have_text(['runA', 'runB', 'Synthetic manual'])   # one alphabetical list
    expect(cards.nth(0).locator('.ds-state-confirmed')).to_have_text('confirmed')     # in the graph, keyed to scan + root
    expect(cards.nth(1).locator('.ds-state-candidate')).to_have_text('candidate')     # recognized in a scan only
    expect(cards.nth(2).locator('.ds-state-manual')).to_have_text('manual')
    expect(cards.nth(0)).to_contain_text('synthetic_pattern')
    expect(cards.nth(0)).to_contain_text('3 files · 300 B')
    expect(cards.nth(0)).to_contain_text('synthetic-host / synthetic-share')
    expect(cards.nth(0)).to_contain_text('Provenance: scan s1')
    expect(cards.nth(2)).to_contain_text('2 files · 1 folders')
    expect(cards.nth(2)).to_contain_text('not a scan reference')
    expect(page.locator('#datasets-count')).to_contain_text('3 Datasets — in this search: 3 all, 1 candidate, 1 confirmed, 1 manual')
    expect(page.locator('#datasets-range')).to_have_text('Showing 1–3 of 3')
    expect(page.locator('[data-testid="datasets-tab-datasets"]')).to_have_attribute('aria-current', 'page')

    # Open one in the inspector, then add it from there.
    cards.nth(0).locator('.ds-name').click()
    expect(page.locator('#shared-inspector')).to_be_visible()
    expect(page.locator('#inspector-title')).to_contain_text('Dataset: runA')
    page.locator('#inspector-add-to-collection').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    expect(page.locator('#inspector-collection-status')).to_contain_text('Added')
    cards.nth(0).get_by_role('button', name='Add to collection').click()               # not added twice
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    # A manual Dataset joins the same basket, by its own id, through the same member shape.
    cards.nth(2).get_by_role('button', name='Add to collection').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
    cards.nth(1).locator('input.coll-add-cb').check()
    page.locator('#datasets-add-checked').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 3 picks')
    stored = page.evaluate("JSON.parse(localStorage.getItem('scidk.collection.draft.v1'))")
    assert [x['kind'] for x in stored] == ['dataset'] * 3
    manual = next(x for x in stored if x['key'] == 'dataset|manual|m1')
    assert manual['p'] == {'dataset_id': 'm1', 'name': 'Synthetic manual'}
    refs = [x['p'] for x in stored if x['key'] != 'dataset|manual|m1']
    assert all(set(p) == {'scan_id', 'root_path', 'profile', 'file_count', 'bytes'} for p in refs)
    # A manual Dataset opens in the inspector and can be added from there too.
    page.locator('#datasets-list .ds-card').nth(2).locator('.ds-name').click()
    expect(page.locator('#inspector-add-to-collection')).to_be_visible()
    assert not errors, errors


def test_collections_view_lists_alphabetically_and_shows_grouped_detail(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=collections')
    expect(page.locator('#collections-list .ds-name')).to_have_text(['Alpha synthetic', 'beta synthetic', 'zeta synthetic'])
    alpha = page.locator('#collections-list .ds-card').first
    expect(alpha).to_contain_text('1 datasets · 1 folders · 1 files · 1 context')
    expect(alpha).to_contain_text('400 B known size')
    expect(alpha).to_contain_text('folder contents are not enumerated')
    expect(alpha).to_contain_text('created 2023')
    alpha.get_by_role('button', name='Open').click()
    detail = page.locator('#collection-detail')
    expect(detail).to_be_visible()
    expect(page.locator('#collection-detail-name')).to_have_text('Alpha synthetic')
    expect(page.locator('#collection-detail-description')).to_have_text('Has every kind')
    expect(page.locator('#collection-folder-note')).to_contain_text('not enumerated')
    expect(detail.locator('.cd-group h4')).to_have_text(['Datasets (1)', 'Folders (1)', 'Files (1)', 'Context (1)'])
    expect(detail.locator('.cd-group[data-kind="dataset"] a').first).to_have_attribute('href', re.compile(r'/datasets\?view=datasets&highlight='))
    expect(detail.locator('.cd-group[data-kind="folder"] a').first).to_have_attribute('href', '/datasets?view=browse')
    expect(detail.locator('.cd-group[data-kind="context"] a').first).to_have_attribute('href', '/knowledge?view=entities')
    assert 'collection=c-a' in page.url
    for word in ('Delete', 'Remove', 'Dissolve'):
        expect(detail.get_by_role('button', name=re.compile(word))).to_have_count(0)
    assert not errors, errors


def test_sharing_plan_panel_opens_and_closes_without_reloading(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=collections&collection=c-a')           # a bookmarkable Collection URL
    expect(page.locator('#collection-detail-name')).to_have_text('Alpha synthetic')
    page.evaluate("window.__marker = 'same-document'")
    panel = page.locator('#collection-plan-panel')
    expect(panel).to_be_hidden()
    page.get_by_role('button', name='Draft sharing plan').click()
    expect(panel).to_be_visible()
    expect(page.locator('#collection-plan-out')).to_contain_text('Synthetic sharing plan draft')
    expect(page.locator('#collection-plan-status')).to_contain_text('not a compliance determination')
    page.locator('#collection-plan-close').click()                              # the visible Close control
    expect(panel).to_be_hidden()
    expect(page.locator('#collection-detail-name')).to_be_visible()             # back on the Collection
    assert page.evaluate('window.__marker') == 'same-document'                  # no reload
    page.get_by_role('button', name='Draft sharing plan').click()
    expect(panel).to_be_visible()
    page.keyboard.press('Escape')                                               # Escape also closes it
    expect(panel).to_be_hidden()
    assert page.evaluate('window.__marker') == 'same-document'
    assert [p for p, _ in api.posts].count('/api/plugins/nih_dms/collections/c-a/draft_plan') == 2
    assert not errors, errors


def test_scans_view_shows_a_recognized_dataset_that_joins_the_basket_by_reference(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    page.goto(serve() + '/datasets?view=scans')
    expect(page.locator('[data-testid="datasets-tab-scans"]')).to_have_attribute('aria-current', 'page')
    page.locator('#scans-list summary').first.click()
    page.locator('#scans-list button[data-scan-id="s1"]').click()
    expect(page.locator('#scans-datasets input.coll-add-cb')).to_have_count(1)
    page.locator('#scans-datasets input.coll-add-cb').check()
    bar = page.locator('#scans-selection-actions [data-testid="selection-actions-bar"]')
    expect(bar).to_be_visible()
    page.locator('#scans-add').click()
    expect(page.locator('#cb-pill')).to_have_text('Collection · 1 pick')
    stored = page.evaluate("JSON.parse(localStorage.getItem('scidk.collection.draft.v1'))")
    assert stored[0]['kind'] == 'dataset' and stored[0]['p']['scan_id'] == 's1' and stored[0]['p']['root_path'] == DATASET_ROOT
    assert 'files' not in stored[0]['p'] and 'entries' not in stored[0]['p']          # a reference, never file rows
    assert not errors, errors


def test_legacy_routes_still_work_in_the_browser(serve, ws_page):
    from playwright.sync_api import expect
    page, api, errors = ws_page
    base = serve()
    page.goto(base + '/datasets')
    expect(page.locator('#file-list tr[data-id]')).to_have_count(3)
    expect(page.locator('[data-testid="datasets-tabs"]')).to_have_count(0)
    page.locator('#gui-scans-tab').click()
    expect(page.locator('#gui-scans')).to_be_visible()
    page.locator('#scans-list summary').first.click()
    page.locator('#scans-list button[data-scan-id="s1"]').click()
    expect(page.locator('#scans-datasets input.coll-add-cb')).to_have_count(1)
    assert not errors, errors
