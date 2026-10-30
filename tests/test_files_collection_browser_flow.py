"""Browser flow: Files selection → shared basket → manual Dataset → saved Collection → plan.

The real Files page runs in Chromium against a throwaway app on a loopback port.
The graph is an in-memory fake and the browse/server answers are synthetic; names
are synthetic. Skipped when no local Chromium is available.
"""
import json
import os
import shutil
import threading

import pytest
from werkzeug.serving import make_server

from scidk.app import create_app
from scidk.web.routes import api_annotation
from tests.conftest import authenticate_test_client  # noqa: F401 - keeps auth helper import parity

playwright_sync = pytest.importorskip('playwright.sync_api')

FOLDER = '/synthetic/demo/notes'
FILE_A = '/synthetic/demo/a.csv'
FILE_B = '/synthetic/demo/b.csv'
FILE_C = '/synthetic/demo/c.csv'


class MemoryGraph:
    """Just enough Cypher routing for the collection routes; records every write."""

    def __init__(self):
        self.collections = {}      # id -> {name, description, members: [(labels, props)]}
        self.datasets = {}         # id -> {props, members: [(labels, props)]}
        self.writes = []

    def close(self):
        pass

    @staticmethod
    def _eid(labels, p):
        return f"{labels[0]}:{p.get('path') or p.get('id')}"

    def execute_write(self, query, parameters=None):
        p = parameters or {}
        self.writes.append(query)
        if 'MERGE (c:Collection {id: $id})' in query:
            c = self.collections.setdefault(p['id'], {'name': p['name'], 'description': None, 'members': []})
            if p.get('description'):
                c['description'] = p['description']
            return []
        if 'MERGE (d:Dataset {id: $id})' in query:
            self.datasets[p['id']] = {'props': {'id': p['id'], 'name': p['name'], 'source': 'manual'}, 'members': []}
            return []
        if 'MERGE (f:Folder' in query or 'MERGE (f:File' in query:
            label = 'Folder' if 'MERGE (f:Folder' in query else 'File'
            target = self.collections.get(p['id']) if 'INCLUDES' in query else self.datasets.get(p['id'])
            for row in p['rows']:
                props = {'path': row['path'], 'host': row['host']}
                props.update({'name': row['name']} if label == 'Folder' else {'filename': row['name'], 'size_bytes': row.get('size')})
                if not any(l == [label] and q['path'] == props['path'] for l, q in target['members']):
                    target['members'].append(([label], props))
            return [{'linked': len(p['rows'])}]
        return []

    def execute_read(self, query, parameters=None):
        p = parameters or {}
        if 'MATCH (c:Collection {name: $name})' in query:
            return [{'id': cid, 'members': len(c['members'])} for cid, c in self.collections.items() if c['name'] == p['name']]
        if 'ORDER BY c.created_at DESC' in query:
            out = []
            for cid, c in self.collections.items():
                kinds = [l[0] for l, _ in c['members']]
                out.append({'id': cid, 'name': c['name'], 'description': c['description'], 'created_by': 'tester',
                            'created_at': 1, 'members': len(kinds), 'datasets': kinds.count('Dataset'),
                            'folders': kinds.count('Folder'), 'files': kinds.count('File')})
            return out
        if 'RETURN c.id AS id, c.name AS name, c.description AS description' in query:
            c = self.collections.get(p['id'])
            return [{'id': p['id'], 'name': c['name'], 'description': c['description'], 'created_by': 'tester',
                     'created_at': 1, 'updated_at': 2}] if c else []
        if 'RETURN c.name AS name' in query:
            c = self.collections.get(p['id'])
            return [{'name': c['name'], 'description': c['description'], 'created_by': 'tester', 'created_at': 1}] if c else []
        if 'RETURN elementId(m) AS eid' in query and 'INCLUDES' in query:
            c = self.collections.get(p['id'])
            return [{'eid': self._eid(l, q), 'labels': l, 'p': q} for l, q in (c['members'] if c else [])]
        return []


@pytest.fixture()
def browser_env(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    app = create_app()
    app.config['TESTING'] = True
    app.config['SCIDK_DATASET_SHARING_ENABLED'] = True
    graph = MemoryGraph()
    monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: graph)
    from plugins.nih_dms import routes as nih_routes
    monkeypatch.setattr(nih_routes, '_neo4j_client', lambda: graph)
    from scidk.services import collection_service
    monkeypatch.setattr(collection_service, '_dataset_types', lambda scan, root: ({}, False))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', graph
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _browse(route):
    entries = [{'id': FOLDER, 'path': FOLDER, 'name': 'notes', 'type': 'folder'}] + [
        {'id': f, 'path': f, 'name': f.rsplit('/', 1)[-1], 'type': 'file', 'size': 100 + i}
        for i, f in enumerate((FILE_A, FILE_B, FILE_C))]
    route.fulfill(status=200, content_type='application/json', body=json.dumps({'entries': entries}))


def _servers(route):
    route.fulfill(status=200, content_type='application/json', body=json.dumps([
        {'id': 'local_fs', 'display_name': 'Synthetic drive', 'root_id': '/', 'root_path': '/', 'connected': True}]))


def test_files_selection_to_basket_manual_dataset_and_saved_collection(browser_env):
    from playwright.sync_api import sync_playwright, expect
    origin, graph = browser_env
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('SCIDK_TEST_CHROME') or shutil.which('google-chrome'))
        except Exception as error:  # noqa: BLE001
            pytest.skip('Local Chromium unavailable: ' + str(error).splitlines()[0])
        try:
            context = browser.new_context(viewport={'width': 1400, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route('**/api/servers', _servers)
            page.route('**/api/browse**', _browse)
            page.goto(origin + '/datasets')

            # One user-facing Collection control, and checkboxes visible by default.
            slot = page.locator('#files-collection-slot')
            expect(slot.locator('#cb-pill')).to_have_count(1)
            expect(page.locator('#cb-pill')).to_have_count(1)
            expect(page.locator('#coll-pill, #coll-panel')).to_have_count(0)
            expect(page.locator('#cb-pill')).to_have_text('Collection · 0 picks')
            expect(page.locator('#file-table')).to_have_class('file-table sel-mode')
            expect(page.locator('#file-list tr[data-id]')).to_have_count(4)
            expect(page.locator('#file-list .row-cb').first).to_be_visible()
            expect(page.locator('#toggle-sel-btn')).to_be_hidden()

            # Select one file and one folder → Add to collection (shared basket).
            page.locator(f'.row-cb[data-id="{FILE_A}"]').check()
            page.locator(f'.row-cb[data-id="{FOLDER}"]').check()
            expect(page.locator('#selection-bar')).to_be_visible()
            expect(page.locator('#add-to-coll-btn')).to_be_visible()
            expect(page.locator('#create-dataset-btn')).to_be_visible()
            page.locator('#add-to-coll-btn').click()
            expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
            expect(page.locator('#cb-panel')).to_have_class('open')
            panel_box = page.locator('#cb-panel').bounding_box()
            slot_box = slot.bounding_box()
            assert panel_box['y'] >= slot_box['y'] + slot_box['height'] - 1      # below the toolbar control
            expect(page.locator('#cb-summary h4[data-kind="folder"]')).to_have_attribute('data-count', '1')
            expect(page.locator('#cb-summary h4[data-kind="file"]')).to_have_attribute('data-count', '1')

            # Navigate away and back: dock state persists.
            page.goto(origin + '/entities')
            expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')
            expect(page.locator('#files-collection-slot')).to_have_count(0)      # fixed pill off the Files page
            page.goto(origin + '/datasets')
            expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')

            # Manual Dataset from a separate selection: never a Collection.
            page.locator(f'.row-cb[data-id="{FILE_B}"]').check()
            page.locator(f'.row-cb[data-id="{FILE_C}"]').check()
            page.locator('#create-dataset-btn').click()
            expect(page.locator('#manual-ds-dialog')).to_be_visible()
            page.locator('#manual-ds-create').click()
            expect(page.locator('#manual-ds-status')).to_contain_text('name is required')
            page.locator('#manual-ds-name').fill('Synthetic manual dataset')
            page.locator('#manual-ds-desc').fill('two csv files')
            page.locator('#manual-ds-create').click()
            expect(page.locator('#manual-ds-dialog')).to_have_count(0)
            assert len(graph.datasets) == 1 and not graph.collections
            made = next(iter(graph.datasets.values()))
            assert made['props']['source'] == 'manual' and len(made['members']) == 2
            expect(page.locator('#cb-pill')).to_have_text('Collection · 2 picks')   # picks untouched

            # Save the picks as a Collection; stored members show by kind.
            page.locator('#cb-pill').click()
            page.locator('#cb-name').fill('Synthetic collection')
            page.locator('#cb-desc').fill('for sharing')
            page.locator('#cb-save').click()
            expect(page.locator('#cb-pill')).to_have_text('Collection: Synthetic collection · 2 members')
            expect(page.locator('#cb-stored h4[data-kind="folder"]')).to_have_attribute('data-count', '1')
            expect(page.locator('#cb-stored h4[data-kind="file"]')).to_have_attribute('data-count', '1')
            expect(page.locator('#cb-stored')).to_contain_text('read-only')
            expect(page.locator('#cb-summary')).to_contain_text('Unsaved picks · 0')

            # Reload and reopen from the saved list.
            page.reload()
            page.locator('#cb-pill').click()
            card = page.locator('.cb-card[data-collection-id]')
            expect(card).to_have_count(1)
            expect(card).to_contain_text('folders 1')
            expect(card).to_contain_text('files 1')
            card.locator('[data-action="open-collection"]').click()
            expect(page.locator('#cb-stored h4[data-kind="file"]')).to_have_attribute('data-count', '1')

            # Draft the plan, close it (panel restored), reopen it.
            card.locator('[data-action="draft-plan"]').click()
            out = page.locator('#cb-plan-out')
            expect(out).to_be_visible()
            text = out.inner_text().lower()
            assert 'selected collection' in text
            assert 'planned future work' in text and 'does not export ro-crate' in text
            assert 'folder(s) are included as folders' in text
            assert 'generates these crates' not in text
            expect(page.locator('#cb-plan-copy')).to_be_visible()
            page.locator('#cb-plan-close').click()
            expect(page.locator('#cb-plan-out')).to_have_count(0)
            expect(page.locator('#cb-stored')).to_be_visible()
            expect(page.locator('#cb-pill')).to_have_text('Collection: Synthetic collection · 2 members')
            page.locator('.cb-card [data-action="draft-plan"]').click()
            expect(page.locator('#cb-plan-out')).to_be_visible()

            assert not errors, errors
        finally:
            browser.close()

    for query in graph.writes:
        assert 'DELETE' not in query.upper() and 'DETACH' not in query.upper()


def test_scans_and_entities_pages_use_the_same_shared_basket(browser_env):
    from playwright.sync_api import sync_playwright, expect
    origin, _graph = browser_env
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get('SCIDK_TEST_CHROME') or shutil.which('google-chrome'))
        except Exception as error:  # noqa: BLE001
            pytest.skip('Local Chromium unavailable: ' + str(error).splitlines()[0])
        try:
            page = browser.new_page()
            for path in ('/entities', '/labels'):
                page.goto(origin + path)
                expect(page.locator('#cb-pill')).to_have_count(1)
                expect(page.locator('#files-collection-slot')).to_have_count(0)
                assert page.evaluate("getComputedStyle(document.getElementById('cb-pill')).position") == 'fixed'
                assert page.evaluate('typeof window.CollectionBasket') == 'object'
        finally:
            browser.close()
