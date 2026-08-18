"""``POST /api/rocrate/build`` and its download route (Cycle 7, Task B).

Two things are worth testing here beyond the happy path.

**Auth.** The task block says "staff or admin". There is no ``staff`` role —
``auth_users`` constrains role to ``('admin','user')`` and ``require_role`` is a
flat membership test — so ``@require_role('staff')`` would 403 every real user,
including admins. The same mistake shipped once already (Cycle 2 Task E), so
both roles get an explicit test.

**The two empty cases.** "Nothing selected" and "nothing selected is in the graph
yet" are different problems with different fixes, and the second is the common
one on a fresh scan. Neither may produce a crate that looks fine until someone
opens it.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from scidk.app import create_app
from scidk.web.routes import api_rocrate
from tests.test_rocrate_bridge import GRAPH_EDGES, GRAPH_NODES, FakeNeo4j


@pytest.fixture
def crate_dir(tmp_path, monkeypatch):
    """Keep built crates inside the test's tmp dir, not ~/.scidk/crates."""
    store = tmp_path / 'crates'
    monkeypatch.setenv('SCIDK_ROCRATE_DIR', str(store))
    return store


@pytest.fixture
def graph(monkeypatch):
    """Substitute the fake graph for the route's Neo4j connection."""
    fake = FakeNeo4j(GRAPH_NODES, GRAPH_EDGES)
    fake.closed = False

    def close():
        fake.closed = True

    fake.close = close
    monkeypatch.setattr(api_rocrate, '_neo4j_client', lambda: fake)
    return fake


@pytest.fixture
def client(crate_dir):
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


def build(client, **body):
    return client.post('/api/rocrate/build', json=body)


#: What the Files page actually posts when a folder is checked: checking a folder
#: selects its children too (``selectFolderRecursive`` in datasets.html), so the
#: payload names every item, not just the folder.
COHORT_SELECTION = [
    '/data/aipt/cohortA',
    '/data/aipt/cohortA/slide_001.svs',
    '/data/aipt/cohortA/manifest.csv',
]


# ------------------------------------------------------------- happy path

def test_a_selection_of_paths_becomes_a_crate(client, graph, crate_dir):
    resp = build(client, paths=COHORT_SELECTION, name='AIPT cohort A', license='CC BY 4.0')

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['status'] == 'ok'
    assert body['entities'] == 3  # the folder and its two files
    assert body['download_url'] == f"/api/rocrate/{body['crate_id']}/metadata"

    written = crate_dir / body['crate_id'] / 'ro-crate-metadata.json'
    doc = json.loads(written.read_text(encoding='utf-8'))
    root = doc['@graph'][1]
    assert root['name'] == 'AIPT cohort A'
    assert root['license'] == 'CC BY 4.0'


def test_the_built_crate_downloads(client, graph):
    crate_id = build(client, paths=['/data/aipt/cohortA']).get_json()['crate_id']

    resp = client.get(f'/api/rocrate/{crate_id}/metadata')

    assert resp.status_code == 200
    assert 'ro-crate-metadata.json' in resp.headers['Content-Disposition']
    assert json.loads(resp.get_data(as_text=True))['@context'].endswith('/context')


def test_element_ids_work_as_well_as_paths(client, graph):
    body = build(client, node_ids=['4:aipt:4'], paths=['/data/aipt/cohortA/slide_001.svs']).get_json()

    assert body['entities'] == 2


def test_the_name_defaults_to_the_selection(client, graph, crate_dir):
    body = build(client, paths=['/data/aipt/cohortA']).get_json()

    written = crate_dir / body['crate_id'] / 'ro-crate-metadata.json'
    assert json.loads(written.read_text())['@graph'][1]['name'] == 'cohortA'


def test_a_folder_on_its_own_crates_only_that_folder(client, graph):
    """The crate describes what was selected; the route does not widen it.

    Expanding a folder is the file browser's job (and it does), so a caller that
    sends only the folder gets only the folder — which is a coherent crate, just
    a small one.
    """
    body = build(client, paths=['/data/aipt/cohortA']).get_json()

    assert body['entities'] == 1


def test_metadata_only_omits_the_pointer_at_the_bytes(client, graph, crate_dir):
    body = build(client, paths=COHORT_SELECTION, include_files=False).get_json()

    assert body['include_files'] is False
    text = (crate_dir / body['crate_id'] / 'ro-crate-metadata.json').read_text()
    assert 'contentUrl' not in text
    assert '/data/aipt' not in text
    # ...while still describing the files.
    assert 'image/tiff' in text


def test_the_graph_connection_is_closed_either_way(client, graph):
    build(client, paths=['/data/aipt/cohortA'])

    assert graph.closed is True


# ---------------------------------------------------------- error paths

def test_an_empty_selection_is_an_error_not_an_empty_crate(client, graph, crate_dir):
    resp = build(client, paths=[], name='Nothing')

    assert resp.status_code == 400
    body = resp.get_json()
    assert body['code'] == 'empty_selection'
    assert 'Select at least one' in body['error']
    # Nothing was written, so no half-crate is left lying around.
    assert not crate_dir.exists() or list(crate_dir.iterdir()) == []


def test_a_selection_that_is_not_in_the_graph_says_so(client, graph, crate_dir):
    """The common case right after a scan: indexed, but not committed to Neo4j."""
    resp = build(client, paths=['/data/not/scanned/yet.csv'])

    assert resp.status_code == 400
    body = resp.get_json()
    assert body['code'] == 'nothing_resolved'
    assert 'commit' in body['error'].lower()
    assert list(crate_dir.iterdir()) == [] if crate_dir.exists() else True


def test_no_graph_configured_is_a_503_with_something_to_do_about_it(client, monkeypatch):
    def unavailable():
        raise api_rocrate.Neo4jUnavailable('No Neo4j connection is configured. Settings → Connections.')

    monkeypatch.setattr(api_rocrate, '_neo4j_client', unavailable)

    resp = build(client, paths=['/data/aipt/cohortA'])

    assert resp.status_code == 503
    assert resp.get_json()['code'] == 'neo4j_unavailable'
    assert 'Settings' in resp.get_json()['error']


def test_a_query_failure_leaves_no_crate_behind(client, monkeypatch, crate_dir):
    class Broken:
        def execute_read(self, query, parameters=None):
            raise RuntimeError('Neo4j.ClientError.Statement.SyntaxError')

        def close(self):
            pass

    monkeypatch.setattr(api_rocrate, '_neo4j_client', lambda: Broken())

    resp = build(client, paths=['/data/aipt/cohortA'])

    assert resp.status_code == 500
    assert resp.get_json()['code'] == 'build_failed'
    assert not crate_dir.exists() or list(crate_dir.iterdir()) == []


@pytest.mark.parametrize('crate_id', ['../../../etc', 'not-hex', '', 'a' * 64])
def test_a_crate_id_that_is_not_ours_cannot_reach_the_filesystem(client, crate_id):
    resp = client.get(f'/api/rocrate/{crate_id}/metadata')

    # Either rejected as invalid or not routed at all; never a file outside the
    # crate store.
    assert resp.status_code in (400, 404)
    if resp.status_code == 400:
        assert resp.get_json()['error'] == 'invalid crate id'


def test_an_unknown_crate_is_a_404(client):
    resp = client.get('/api/rocrate/0123456789ab/metadata')

    assert resp.status_code == 404


# ------------------------------------------------------------------ auth

class TestBuildRouteAuth:
    """PYTEST_TEST_AUTH makes the decorators enforce instead of taking the
    test-mode bypass; creating a user is what flips AuthManager.is_enabled() on.
    Mirrors tests/test_canvas_export_auth.py.
    """

    @pytest.fixture
    def auth_app(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / 'auth.db')
        monkeypatch.setenv('PYTEST_TEST_AUTH', '1')
        monkeypatch.setenv('SCIDK_ROCRATE_DIR', str(tmp_path / 'crates'))
        app = create_app()
        app.config['TESTING'] = True
        app.config['SCIDK_SETTINGS_DB'] = db_path
        return app

    @pytest.fixture
    def auth(self, auth_app):
        from scidk.core.auth import get_auth_manager
        return get_auth_manager(db_path=auth_app.config['SCIDK_SETTINGS_DB'])

    @pytest.fixture
    def auth_client(self, auth_app, monkeypatch):
        fake = FakeNeo4j(GRAPH_NODES, GRAPH_EDGES)
        fake.close = lambda: None
        monkeypatch.setattr(api_rocrate, '_neo4j_client', lambda: fake)
        return auth_app.test_client()

    def token(self, auth, role):
        user_id = auth.create_user(f'{role}_person', 'password123', role=role)
        assert user_id is not None, f'no such role: {role}'
        return auth.create_user_session(user_id, f'{role}_person')

    def test_unauthenticated_is_rejected(self, auth_client):
        resp = auth_client.post('/api/rocrate/build', json={'paths': ['/data/aipt/cohortA']})

        assert resp.status_code == 401

    @pytest.mark.parametrize('role', ['user', 'admin'])
    def test_both_real_roles_can_build(self, auth_client, auth, role):
        resp = auth_client.post(
            '/api/rocrate/build',
            json={'paths': ['/data/aipt/cohortA']},
            headers={'Authorization': f'Bearer {self.token(auth, role)}'},
        )

        assert resp.status_code == 200, resp.get_data(as_text=True)

    def test_there_is_no_staff_role_to_gate_on(self, auth):
        """Why the route lists both roles instead of the task block's 'staff'."""
        assert auth.create_user('staffer', 'password123', role='staff') is None
