"""Task group I — the completeness sweep (the Collection write routes are in test_collections.py).

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
