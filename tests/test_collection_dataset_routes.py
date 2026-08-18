"""Task group I — Collection → Dataset, and the completeness sweep.

Driven against a fake Neo4j client that records the Cypher it is handed, so no
live graph is needed. Several of these assert on the *query text*: the audit
found that the obvious spellings (``f.name``, ``f.size``, matching File on path
alone) return empty results rather than errors, so a regression there would be
invisible to a behavioural test against a fake.
"""
import pytest

from scidk.app import create_app
from scidk.web.routes import api_annotation
from tests.conftest import authenticate_test_client


class FakeNeo4jClient:
    """Records queries; returns whatever the test queued."""

    def __init__(self, write_results=None, read_results=None):
        self.calls = []
        self._write_results = list(write_results or [])
        self._read_results = read_results or []

    def execute_write(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        return self._write_results.pop(0) if self._write_results else []

    def execute_read(self, query, parameters=None):
        self.calls.append((query, parameters or {}))
        return self._read_results

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    app = create_app()
    app.config['TESTING'] = True
    return authenticate_test_client(app.test_client(), app)


@pytest.fixture()
def fake_graph(monkeypatch):
    """Install a fake client and hand the test a handle on it."""
    holder = {}

    def install(**kwargs):
        holder['client'] = FakeNeo4jClient(**kwargs)
        monkeypatch.setattr(api_annotation, '_neo4j_client', lambda: holder['client'])
        return holder['client']

    return install


def _query_for(client, needle):
    return next(q for q, _ in client.calls if needle in q)


def _params_for(client, needle):
    return next(p for q, p in client.calls if needle in q)


# ── I1 — POST /api/datasets/collections ────────────────────────────────────

def test_create_dataset_links_files_and_reports_counts(client, fake_graph):
    graph = fake_graph(write_results=[
        [{'dataset_id': '4:abc:1', 'created': True}],
        [{'linked': 2, 'stubs': 0}],
    ])

    r = client.post('/api/datasets/collections', json={
        'name': 'AIPT Vevo June 2026 Cohort',
        'modality': 'Flow Cytometry',
        'description': 'Preclinical FCS data',
        'files': [
            {'name': 'session_001.fcs', 'path': 'labserver/data/vevo', 'host': 'labserver'},
            {'name': 'session_002.fcs', 'path': 'labserver/data/vevo', 'host': 'labserver'},
        ],
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body == {
        'status': 'ok',
        'dataset_id': '4:abc:1',
        'name': 'AIPT Vevo June 2026 Cohort',
        'files_linked': 2,
        'stubs_created': 0,
    }

    params = _params_for(graph, 'MERGE (d)-[:CONTAINS]->(f)')
    # The folder in `path` was joined with the filename: File nodes are keyed on
    # the file's own path.
    assert params['files'] == [
        {'path': 'labserver/data/vevo/session_001.fcs', 'filename': 'session_001.fcs', 'host': 'labserver'},
        {'path': 'labserver/data/vevo/session_002.fcs', 'filename': 'session_002.fcs', 'host': 'labserver'},
    ]


def test_create_dataset_accepts_full_paths_without_doubling_the_filename(client, fake_graph):
    graph = fake_graph(write_results=[[{'dataset_id': 'x', 'created': True}], [{'linked': 1, 'stubs': 0}]])
    client.post('/api/datasets/collections', json={
        'name': 'D',
        'files': [{'name': 'a.fcs', 'path': 'labserver/data/a.fcs', 'host': 'labserver'}],
    })
    assert _params_for(graph, 'MERGE (d)-[:CONTAINS]->(f)')['files'][0]['path'] == 'labserver/data/a.fcs'


def test_create_dataset_matches_file_on_path_and_host(client, fake_graph):
    graph = fake_graph(write_results=[[{'dataset_id': 'x', 'created': True}], [{'linked': 1, 'stubs': 1}]])
    client.post('/api/datasets/collections', json={
        'name': 'D', 'files': [{'name': 'a.fcs', 'path': 'p/a.fcs', 'host': 'h'}],
    })
    link = _query_for(graph, 'CONTAINS')
    # Composite key, both halves. path-only would be a scan of every File node.
    assert 'MERGE (f:File {path: row.path, host: row.host})' in link
    # File nodes spell it `filename`, not `name`.
    assert 'f.filename = row.filename' in link
    assert 'f.name =' not in link


def test_create_dataset_stubs_files_the_graph_has_never_seen(client, fake_graph):
    graph = fake_graph(write_results=[[{'dataset_id': 'x', 'created': True}], [{'linked': 3, 'stubs': 2}]])
    r = client.post('/api/datasets/collections', json={
        'name': 'D', 'files': [{'name': f'{i}.fcs', 'path': 'p', 'host': 'h'} for i in range(3)],
    })
    assert r.get_json()['stubs_created'] == 2
    assert 'ON CREATE SET f.filename = row.filename, f.stub = true' in _query_for(graph, 'CONTAINS')


def test_create_dataset_deduplicates_the_same_file_twice(client, fake_graph):
    graph = fake_graph(write_results=[[{'dataset_id': 'x', 'created': True}], [{'linked': 1, 'stubs': 0}]])
    client.post('/api/datasets/collections', json={
        'name': 'D', 'files': [
            {'name': 'a.fcs', 'path': 'p', 'host': 'h'},
            {'name': 'a.fcs', 'path': 'p', 'host': 'h'},
        ],
    })
    assert len(_params_for(graph, 'CONTAINS')['files']) == 1


def test_create_dataset_requires_a_name_and_files(client, fake_graph):
    fake_graph(write_results=[])
    assert client.post('/api/datasets/collections', json={'files': [{'name': 'a', 'path': 'p'}]}).status_code == 400
    assert client.post('/api/datasets/collections', json={'name': 'D'}).status_code == 400
    assert client.post('/api/datasets/collections', json={'name': 'D', 'files': []}).status_code == 400


def test_create_dataset_reports_malformed_entries_alongside_the_good_ones(client, fake_graph):
    fake_graph(write_results=[[{'dataset_id': 'x', 'created': True}], [{'linked': 1, 'stubs': 0}]])
    r = client.post('/api/datasets/collections', json={
        'name': 'D', 'files': [{'name': 'a.fcs', 'path': 'p', 'host': 'h'}, {'name': 'orphan.fcs'}],
    })
    assert r.status_code == 200
    assert any('orphan.fcs' in p for p in r.get_json()['problems'])


def test_create_dataset_says_so_when_neo4j_is_not_configured(client, monkeypatch):
    def unavailable():
        raise api_annotation.Neo4jUnavailable('No Neo4j connection is configured')

    monkeypatch.setattr(api_annotation, '_neo4j_client', unavailable)
    r = client.post('/api/datasets/collections', json={
        'name': 'D', 'files': [{'name': 'a', 'path': 'p', 'host': 'h'}],
    })
    assert r.status_code == 503
    # The reason reaches the caller rather than becoming a bare 503.
    assert r.get_json()['error'] == 'No Neo4j connection is configured'


def test_create_dataset_does_not_collide_with_scan_derived_datasets(client, fake_graph):
    """dataset_node_service keys its Datasets on (path, host); these on name."""
    graph = fake_graph(write_results=[[{'dataset_id': 'x', 'created': True}], [{'linked': 0, 'stubs': 0}]])
    client.post('/api/datasets/collections', json={
        'name': 'D', 'files': [{'name': 'a', 'path': 'p', 'host': 'h'}],
    })
    merge = _query_for(graph, 'MERGE (d:Dataset')
    assert "MERGE (d:Dataset {name: $name, source: 'collection'})" in merge


# ── I2 — POST /api/collections/sweep ───────────────────────────────────────

def test_sweep_reports_a_partially_covered_dataset(client, fake_graph):
    fake_graph(read_results=[{
        'dataset_name': 'AIPT Vevo June 2026',
        'path': 'labserver/data/vevo',
        'host': 'labserver',
        'present': 3,
        'total': 5,
        'missing': ['session_004.fcs', 'session_005.fcs'],
    }])

    r = client.post('/api/collections/sweep', json={
        'files': [{'name': f'session_00{i}.fcs', 'path': 'labserver/data/vevo', 'host': 'labserver'}
                  for i in (1, 2, 3)],
    })
    assert r.status_code == 200
    assert r.get_json()['gaps'] == [{
        'dataset_name': 'AIPT Vevo June 2026',
        'path': 'labserver/data/vevo',
        'host': 'labserver',
        'present': 3,
        'total': 5,
        'missing': ['session_004.fcs', 'session_005.fcs'],
    }]


def test_sweep_matches_on_path_and_host_and_returns_filename(client, fake_graph):
    graph = fake_graph(read_results=[])
    client.post('/api/collections/sweep', json={
        'files': [{'name': 'a.fcs', 'path': 'p', 'host': 'h'}],
    })
    query = _query_for(graph, ':Dataset')
    assert 'MATCH (f:File {path: row.path, host: row.host})' in query
    # The audit's headline trap: File has `filename`, not `name`. Cypher written
    # against f.name silently returns nothing.
    assert 'm.filename' in query
    assert 'f.name' not in query
    assert 'f.size ' not in query
    # The "all members" match is labelled, so a non-File child could not inflate
    # the total.
    assert 'MATCH (d)-[:CONTAINS]->(all_f:File)' in query


def test_sweep_of_an_empty_collection_asks_nothing(client, monkeypatch):
    def unexpected():
        pytest.fail('sweep must not open a Neo4j connection for an empty collection')

    monkeypatch.setattr(api_annotation, '_neo4j_client', unexpected)
    r = client.post('/api/collections/sweep', json={'files': []})
    assert r.status_code == 200
    assert r.get_json() == {'gaps': []}


def test_sweep_is_quiet_when_nothing_overlaps(client, fake_graph):
    fake_graph(read_results=[])
    r = client.post('/api/collections/sweep', json={
        'files': [{'name': 'a.fcs', 'path': 'p', 'host': 'h'}],
    })
    assert r.get_json() == {'gaps': []}


def test_sweep_is_quiet_when_neo4j_is_not_configured(client, monkeypatch):
    """The panel opens on every collection; a missing graph is not an alert."""
    def unavailable():
        raise api_annotation.Neo4jUnavailable('nope')

    monkeypatch.setattr(api_annotation, '_neo4j_client', unavailable)
    r = client.post('/api/collections/sweep', json={
        'files': [{'name': 'a.fcs', 'path': 'p', 'host': 'h'}],
    })
    assert r.status_code == 200
    assert r.get_json() == {'gaps': []}


def test_sweep_accepts_path_host_pairs_with_no_name(client, fake_graph):
    """The shape collection.js actually sends — the basename is derivable."""
    graph = fake_graph(read_results=[])
    r = client.post('/api/collections/sweep', json={
        'files': [{'path': 'labserver/data/vevo/session_001.fcs', 'host': 'labserver'}],
    })
    assert r.status_code == 200
    params = _params_for(graph, ':Dataset')
    assert params['files'] == [{
        'path': 'labserver/data/vevo/session_001.fcs',
        'filename': 'session_001.fcs',
        'host': 'labserver',
    }]


def test_sweep_excludes_the_collection_from_the_missing_list(client, fake_graph):
    graph = fake_graph(read_results=[])
    client.post('/api/collections/sweep', json={
        'files': [{'name': 'a.fcs', 'path': 'p/a.fcs', 'host': 'h'}],
    })
    params = _params_for(graph, ':Dataset')
    assert params['keys'] == [['p/a.fcs', 'h']]
    assert 'WHERE NOT [m.path, m.host] IN $keys' in _query_for(graph, ':Dataset')
