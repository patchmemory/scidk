"""Cycle 8, Task C — export/import on the Connections page Concept Graph card.

`export_concept_graph` / `import_concept_graph` have existed since ``5d8da6e``, but
the card Cycle 4 shipped had no way to reach them. These cover the two routes and
the controls, including the shapes that must *not* import: a foreign JSON document
would otherwise upsert nothing and report success.

No live concept graph — the driver in ``app.extensions`` is replaced with a fake.
"""
from __future__ import annotations

import io
import json

import pytest


# ─────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows

    def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self._driver.calls.append((query, params))
        if 'SATISFIES' in query:
            return _Result(self._driver.rows.get('satisfies', []))
        if 'RETRIEVES' in query:
            return _Result(self._driver.rows.get('retrieves', []))
        if 'Concept_Tool' in query:
            return _Result(self._driver.rows.get('tools', []))
        return _Result(self._driver.rows.get('intents', []))


class _FakeDriver:
    def __init__(self, **rows):
        self.rows = rows
        self.calls = []

    def session(self):
        return _FakeSession(self)


TOOL_ROW = {
    'name': 'query_knowledge_graph',
    'description': 'Execute a read-only Cypher query.',
    'source': 'mcp',
    'active': True,
    'input_schema': '{"type": "object"}',
    'category': 'data_query',
}


@pytest.fixture()
def concept_client(app):
    """A test client whose concept graph is a fake. Yields (client, driver)."""
    ext = app.extensions['scidk']
    previous = ext.get('concept_driver')
    driver = _FakeDriver(tools=[TOOL_ROW])
    ext['concept_driver'] = driver
    try:
        yield app.test_client(), driver
    finally:
        ext['concept_driver'] = previous


@pytest.fixture()
def no_concept_client(app):
    """A test client on an instance with no concept graph."""
    ext = app.extensions['scidk']
    previous = ext.get('concept_driver')
    ext['concept_driver'] = None
    try:
        yield app.test_client()
    finally:
        ext['concept_driver'] = previous


def _snapshot(**overrides):
    data = {
        'scidk_concept_graph': '1.0',
        'exported_at': '2026-08-04T00:00:00Z',
        'source_instance': 'somewhere-else',
        'intents': [],
        'tools': [TOOL_ROW],
        'satisfies_edges': [],
        'retrieves_edges': [],
    }
    data.update(overrides)
    return data


def _upload(data):
    payload = json.dumps(data).encode('utf-8') if not isinstance(data, bytes) else data
    return {'file': (io.BytesIO(payload), 'concept_graph.json')}


# ─────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────

def test_export_returns_the_snapshot(concept_client):
    client, _ = concept_client

    resp = client.get('/api/connections/concept-graph/export')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['scidk_concept_graph'] == '1.0'
    assert body['tools'] == [TOOL_ROW]


def test_export_downloads_as_concept_graph_json(concept_client):
    client, _ = concept_client

    resp = client.get('/api/connections/concept-graph/export')

    assert 'attachment' in resp.headers['Content-Disposition']
    assert 'concept_graph.json' in resp.headers['Content-Disposition']


def test_export_carries_category(concept_client):
    """The field Cycle 6 deferred until the round trip could hold it."""
    client, _ = concept_client

    tools = client.get('/api/connections/concept-graph/export').get_json()['tools']
    assert tools[0]['category'] == 'data_query'


def test_export_reports_a_missing_concept_graph_rather_than_failing(no_concept_client):
    resp = no_concept_client.get('/api/connections/concept-graph/export')

    assert resp.status_code == 501
    assert resp.get_json()['status'] == 'disabled'


# ─────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────

def test_import_accepts_an_uploaded_file(concept_client):
    """A file input can only produce multipart; the older api_chat route takes
    a JSON body only, which is why these routes exist."""
    client, driver = concept_client

    resp = client.post('/api/connections/concept-graph/import',
                       data=_upload(_snapshot()),
                       content_type='multipart/form-data')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    assert body['tools_imported'] == 1
    assert body['errors'] == []


def test_import_writes_category_from_the_uploaded_snapshot(concept_client):
    client, driver = concept_client

    client.post('/api/connections/concept-graph/import',
                data=_upload(_snapshot()), content_type='multipart/form-data')

    merges = [params for query, params in driver.calls
              if 'MERGE (t:Concept_Tool' in query]
    assert merges[0]['category'] == 'data_query'


def test_import_also_accepts_a_raw_json_body(concept_client):
    """So `curl -d @concept_graph.json` works without a multipart wrapper."""
    client, _ = concept_client

    resp = client.post('/api/connections/concept-graph/import',
                       json=_snapshot())

    assert resp.status_code == 200
    assert resp.get_json()['tools_imported'] == 1


def test_import_round_trips_an_export(concept_client):
    """Export from this instance, post it back, and it applies."""
    client, _ = concept_client
    exported = client.get('/api/connections/concept-graph/export').get_json()

    resp = client.post('/api/connections/concept-graph/import',
                       data=_upload(exported),
                       content_type='multipart/form-data')

    assert resp.status_code == 200
    assert resp.get_json()['tools_imported'] == 1


def test_import_rejects_a_foreign_json_document(concept_client):
    """It would upsert nothing and report success — the worst possible answer."""
    client, driver = concept_client

    resp = client.post('/api/connections/concept-graph/import',
                       data=_upload({'nodes': [], 'edges': []}),
                       content_type='multipart/form-data')

    assert resp.status_code == 400
    assert 'scidk_concept_graph' in resp.get_json()['error']
    assert driver.calls == []


def test_import_rejects_a_future_format_version(concept_client):
    client, _ = concept_client

    resp = client.post('/api/connections/concept-graph/import',
                       data=_upload(_snapshot(scidk_concept_graph='2.0')),
                       content_type='multipart/form-data')

    assert resp.status_code == 400


def test_import_rejects_a_file_that_is_not_json(concept_client):
    client, driver = concept_client

    resp = client.post('/api/connections/concept-graph/import',
                       data=_upload(b'not json at all'),
                       content_type='multipart/form-data')

    assert resp.status_code == 400
    assert 'not JSON' in resp.get_json()['error']
    assert driver.calls == []


def test_import_rejects_a_json_array(concept_client):
    client, _ = concept_client

    resp = client.post('/api/connections/concept-graph/import',
                       data=_upload([{'name': 'x'}]),
                       content_type='multipart/form-data')

    assert resp.status_code == 400


def test_import_with_no_body_at_all_is_a_400_not_a_500(concept_client):
    client, _ = concept_client

    resp = client.post('/api/connections/concept-graph/import')

    assert resp.status_code == 400


def test_import_reports_a_missing_concept_graph(no_concept_client):
    resp = no_concept_client.post('/api/connections/concept-graph/import',
                                  json=_snapshot())

    assert resp.status_code == 501
    assert resp.get_json()['status'] == 'disabled'


def test_import_preserves_the_higher_weight_on_a_conflicting_edge(concept_client):
    """Provenance-tagging in the existing implementation: a snapshot cannot
    silently discard feedback this instance has learned."""
    client, driver = concept_client

    client.post('/api/connections/concept-graph/import',
                data=_upload(_snapshot(satisfies_edges=[{
                    'intent': 'data_lookup',
                    'tool': 'query_knowledge_graph',
                    'weight': 0.6,
                    'usage_count': 2,
                    'last_updated': '2026-08-01T00:00:00',
                }])),
                content_type='multipart/form-data')

    edge_merges = [q for q, _ in driver.calls if 'MERGE (i)-[r:SATISFIES]->(t)' in q]
    assert edge_merges, 'no SATISFIES edge was written'
    assert 'WHEN $weight > r.weight THEN $weight' in edge_merges[0]


# ─────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────

def test_the_routes_do_not_shadow_the_per_backend_routes(app):
    """`concept-graph` sits where `<backend_id>` also matches; both must resolve."""
    rules = {str(r.rule) for r in app.url_map.iter_rules()}

    assert '/api/connections/concept-graph/export' in rules
    assert '/api/connections/concept-graph/import' in rules
    assert '/api/connections/<backend_id>/counts' in rules


def test_the_per_backend_routes_still_work(app):
    """The registry's own id is concept_graph, with an underscore — a request to
    the hyphenated export path must not be read as a backend id."""
    client = app.test_client()

    resp = client.get('/api/connections/concept_graph/counts')
    assert resp.status_code == 200
    assert resp.get_json()['id'] == 'concept_graph'


# ─────────────────────────────────────────────
# The card
# ─────────────────────────────────────────────

@pytest.fixture()
def card_html():
    from pathlib import Path

    template = (Path(__file__).resolve().parent.parent / 'scidk' / 'ui' /
                'templates' / 'settings' / '_connections_concept_graph.html')
    return template.read_text()


def test_the_card_offers_export_and_import(card_html):
    assert 'id="link-export-concept-graph"' in card_html
    assert 'id="input-import-concept-graph"' in card_html
    assert 'type="file"' in card_html


def test_the_card_calls_the_new_routes(card_html):
    assert "'/api/connections/concept-graph/export'" in card_html
    assert "'/api/connections/concept-graph/import'" in card_html


def test_the_card_downloads_the_named_file(card_html):
    assert "a.download = 'concept_graph.json'" in card_html


def test_the_card_uses_scidk_base_for_the_subpath_deployment(card_html):
    """Reverse-proxied at /scidk — a bare path would 404 there."""
    for route in ('/api/connections/concept-graph/export',
                  '/api/connections/concept-graph/import'):
        assert f"window.SCIDK_BASE + '{route}'" in card_html


def test_the_card_clears_the_file_input_after_an_import(card_html):
    """Otherwise re-selecting the same file fires no change event."""
    assert 'importInput.value' in card_html
