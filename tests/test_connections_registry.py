"""Cycle 4, Task A — Settings → Connections.

Covers the registry contract (what a card needs, and that a dead backend degrades
rather than raising) and the three API routes. Deliberately does not require a
live Neo4j: ``verify()`` and ``counts()`` are asserted to *report* failure, which
is the behaviour the page depends on.
"""
import pytest

from scidk.services import connection_registry as registry


def _fake_backend(backend_id='fake_backend', read_config=None, open_probe=None):
    """A GraphBackend with substituted callables.

    GraphBackend is frozen, so a fake is built rather than monkeypatched onto a
    registered one — which also keeps the real registry untouched between tests.
    """
    return registry.GraphBackend(
        id=backend_id,
        name='Fake Backend',
        role='Test',
        description='Stand-in used by tests.',
        nav_section='',
        env_vars=('FAKE_URI',),
        read_config=read_config or (lambda: {'configured': True, 'uri': 'bolt://fake:7687'}),
        open_probe=open_probe or (lambda: None),
    )


# ─────────────────────────────────────────────
# Registry shape
# ─────────────────────────────────────────────

def test_three_neo4j_backends_are_registered():
    ids = [b.id for b in registry.list_backends()]
    assert ids == ['research_graph', 'chat_history', 'concept_graph']


def test_backend_lookup_by_id():
    assert registry.get_backend('chat_history').name == 'Chat History'
    assert registry.get_backend('no_such_backend') is None


def test_every_backend_declares_what_a_card_needs():
    for backend in registry.list_backends():
        assert backend.name and backend.role and backend.description
        assert backend.env_vars, f"{backend.id} documents no env vars"
        assert callable(backend.read_config)
        assert callable(backend.open_probe)


def test_describe_returns_card_fields_without_touching_the_network(app):
    for info in registry.describe_all():
        for key in ('id', 'name', 'role', 'description', 'nav_section', 'env_vars',
                    'configured', 'uri', 'user', 'database', 'auth_mode',
                    'last_verified'):
            assert key in info, f"{info.get('id')} missing {key}"
        assert isinstance(info['configured'], bool)
        assert isinstance(info['env_vars'], list)
        # Never leak a password through the card payload.
        assert 'password' not in info


def test_describe_never_raises_on_a_broken_config_reader(app):
    def explode():
        raise RuntimeError('config is wedged')

    info = registry.describe(_fake_backend(read_config=explode))
    assert info['config_error'] == 'config is wedged'
    assert info['configured'] is False


def test_chat_history_is_unconfigured_without_env(app, monkeypatch):
    monkeypatch.delenv('CHAT_NEO4J_URI', raising=False)
    info = registry.describe(registry.get_backend('chat_history'))
    assert info['configured'] is False
    assert info['uri'] == ''
    assert 'CHAT_NEO4J_URI' in info['env_vars']


def test_chat_history_reads_env(app, monkeypatch):
    monkeypatch.setenv('CHAT_NEO4J_URI', 'bolt://chat.example:7688')
    monkeypatch.setenv('CHAT_NEO4J_AUTH', 'chatuser/chatpass')
    info = registry.describe(registry.get_backend('chat_history'))
    assert info['configured'] is True
    assert info['uri'] == 'bolt://chat.example:7688'
    assert info['user'] == 'chatuser'
    assert 'chatpass' not in str(info)


def test_concept_graph_reports_the_uri_it_would_dial(app, monkeypatch):
    monkeypatch.setenv('SCIDK_CONCEPT_NEO4J_URI', 'bolt://concept.example:7689')
    monkeypatch.setenv('SCIDK_CONCEPT_NEO4J_AUTH', 'none')
    info = registry.describe(registry.get_backend('concept_graph'))
    assert info['uri'] == 'bolt://concept.example:7689'
    assert info['auth_mode'] == 'none'


# ─────────────────────────────────────────────
# verify() / counts() degrade instead of raising
# ─────────────────────────────────────────────

def test_verify_reports_unconfigured_backend_without_raising(app, monkeypatch):
    monkeypatch.delenv('CHAT_NEO4J_URI', raising=False)
    monkeypatch.delenv('CHAT_NEO4J_AUTH', raising=False)
    monkeypatch.delenv('CHAT_NEO4J_USER', raising=False)
    monkeypatch.delenv('CHAT_NEO4J_PASSWORD', raising=False)
    result = registry.verify(registry.get_backend('chat_history'))
    assert result['ok'] is False
    assert 'CHAT_NEO4J_URI' in result['error']


def test_verify_reports_an_unreachable_backend_without_raising(app, monkeypatch):
    # Port 1 has nothing listening, so this exercises the failure path end to end.
    monkeypatch.setenv('CHAT_NEO4J_URI', 'bolt://127.0.0.1:1')
    monkeypatch.setenv('CHAT_NEO4J_AUTH', 'neo4j/nope')
    result = registry.verify(registry.get_backend('chat_history'))
    assert result['ok'] is False
    assert result['error']


def test_verify_records_last_verified_on_success(app):
    class FakeProbe:
        closed = False

        def run(self, cypher):
            assert cypher == 'RETURN 1 AS ok'
            return [{'ok': 1}]

        def close(self):
            FakeProbe.closed = True

    backend = _fake_backend('verify_probe_backend', open_probe=lambda: FakeProbe())
    result = registry.verify(backend)
    assert result['ok'] is True
    assert result['error'] is None
    assert result['latency_ms'] is not None
    assert FakeProbe.closed is True
    assert registry.get_last_verified('verify_probe_backend')


def test_counts_uses_a_directed_relationship_pattern(app):
    """``MATCH ()-[r]-()`` would double-count every relationship."""
    seen = []

    class FakeProbe:
        def run(self, cypher):
            seen.append(cypher)
            return [{'c': 41 if 'count(n)' in cypher else 7}]

        def close(self):
            pass

    result = registry.counts(_fake_backend(open_probe=lambda: FakeProbe()))
    assert result == {'nodes': 41, 'edges': 7, 'error': None}
    assert 'MATCH ()-[r]->() RETURN count(r) AS c' in seen


def test_counts_reports_failure_without_raising(app):
    def explode():
        raise RuntimeError('graph is down')

    result = registry.counts(_fake_backend(open_probe=explode))
    assert result == {'nodes': None, 'edges': None, 'error': 'graph is down'}


def test_probe_does_not_close_the_shared_concept_driver(app):
    """The app-level concept driver is reused across requests."""
    closed = []

    class FakeDriver:
        def close(self):
            closed.append(True)

    app.extensions['scidk']['concept_driver'] = FakeDriver()
    try:
        probe = registry.get_backend('concept_graph').open_probe()
        probe.close()
        assert closed == []
    finally:
        app.extensions['scidk']['concept_driver'] = None


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

def test_list_connections_returns_every_backend(client):
    r = client.get('/api/connections')
    assert r.status_code == 200
    backends = r.get_json()['backends']
    assert [b['id'] for b in backends] == ['research_graph', 'chat_history', 'concept_graph']
    for b in backends:
        assert 'uri' in b and 'configured' in b and 'last_verified' in b


def test_test_route_answers_reachability_with_200(client):
    r = client.post('/api/connections/chat_history/test')
    assert r.status_code == 200
    body = r.get_json()
    assert body['id'] == 'chat_history'
    assert 'ok' in body and 'error' in body and 'latency_ms' in body


def test_counts_route_returns_a_well_formed_body(client):
    r = client.get('/api/connections/chat_history/counts')
    assert r.status_code == 200
    body = r.get_json()
    assert body['id'] == 'chat_history'
    assert 'nodes' in body and 'edges' in body and 'error' in body


@pytest.mark.parametrize('path, method', [
    ('/api/connections/nope/test', 'post'),
    ('/api/connections/nope/counts', 'get'),
])
def test_unknown_backend_is_a_404(client, path, method):
    r = getattr(client, method)(path)
    assert r.status_code == 404
    assert 'nope' in r.get_json()['error']
