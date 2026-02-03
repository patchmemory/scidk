"""
Tests for Neo4jGraph adapter implementation.
Validates that commit_scan with rows/folders works correctly with mocked driver.
"""
import types
import pytest


class _FakeSingle:
    def __init__(self, data):
        self._data = data

    def single(self):
        return self._data

    def get(self, key):
        return self._data.get(key)

    def __iter__(self):
        return iter([self._data])


class _FakeResult:
    def __init__(self, data=None):
        self._data = data or {}

    def consume(self):
        pass

    def single(self):
        return _FakeSingle(self._data)

    def data(self):
        return [self._data]

    def __iter__(self):
        """Make result iterable for list() calls in Neo4jClient.write_scan."""
        return iter([self._data])


class _FakeSession:
    def __init__(self):
        self._closed = False
        self.queries = []

    def run(self, cypher, **params):
        self.queries.append({'cypher': cypher, 'params': params})
        # Detect verification query
        if isinstance(cypher, str) and 'OPTIONAL MATCH (s:Scan' in cypher:
            return _FakeResult({
                'scan_exists': True,
                'files_cnt': params.get('expected_files', 2),
                'folders_cnt': params.get('expected_folders', 1)
            })
        # Detect constraint creation
        if 'CREATE CONSTRAINT' in cypher:
            return _FakeResult()
        # write_scan query
        if 'MERGE (s:Scan' in cypher and 'UNWIND $rows' in cypher:
            return _FakeResult({'scan_id': params.get('scan_id')})
        return _FakeResult()

    def close(self):
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class _FakeDriver:
    def __init__(self, uri=None, auth=None):
        self.uri = uri
        self.auth = auth
        self._session_obj = _FakeSession()

    def session(self, database=None):
        return self._session_obj

    def close(self):
        pass


class _FakeGraphDatabase:
    @staticmethod
    def driver(uri, auth=None):
        return _FakeDriver(uri=uri, auth=auth)


def test_neo4j_adapter_commit_with_rows(monkeypatch):
    """Test that Neo4jGraph.commit_scan writes files and folders when rows provided."""
    # Inject fake neo4j driver
    fake_module = types.SimpleNamespace(GraphDatabase=_FakeGraphDatabase)
    monkeypatch.setitem(__import__('sys').modules, 'neo4j', fake_module)

    from scidk.core.neo4j_graph import Neo4jGraph

    # Create adapter
    graph = Neo4jGraph(uri='bolt://localhost:7687', auth=('neo4j', 'test'), auth_mode='basic')

    # Prepare test data
    scan = {
        'id': 'test-scan-1',
        'path': '/test',
        'started': 123456789.0,
        'ended': 123456790.0,
        'provider_id': 'local',
        'host_type': 'local',
        'host_id': 'localhost'
    }

    rows = [
        {'path': '/test/file1.txt', 'filename': 'file1.txt', 'extension': 'txt',
         'size_bytes': 100, 'created': 123456789.0, 'modified': 123456789.0,
         'mime_type': 'text/plain', 'folder': '/test', 'interps': []},
        {'path': '/test/file2.py', 'filename': 'file2.py', 'extension': 'py',
         'size_bytes': 200, 'created': 123456789.0, 'modified': 123456789.0,
         'mime_type': 'text/x-python', 'folder': '/test', 'interps': ['python']},
    ]

    folder_rows = [
        {'path': '/test', 'name': 'test', 'parent': '/', 'parent_name': ''}
    ]

    # Commit with rows
    result = graph.commit_scan(scan, rows=rows, folder_rows=folder_rows)

    # Verify result structure
    assert result is not None
    assert 'db_scan_exists' in result
    assert 'db_files' in result
    assert 'db_folders' in result
    assert 'db_verified' in result

    # Verify counts (from our fake verification)
    assert result['db_scan_exists'] is True
    assert result['db_files'] >= 2
    assert result['db_folders'] >= 1
    assert result['db_verified'] is True

    graph.close()


def test_neo4j_adapter_commit_without_rows(monkeypatch):
    """Test that Neo4jGraph.commit_scan works without rows (backward compat)."""
    fake_module = types.SimpleNamespace(GraphDatabase=_FakeGraphDatabase)
    monkeypatch.setitem(__import__('sys').modules, 'neo4j', fake_module)

    from scidk.core.neo4j_graph import Neo4jGraph

    graph = Neo4jGraph(uri='bolt://localhost:7687', auth=('neo4j', 'test'), auth_mode='basic')

    scan = {
        'id': 'test-scan-2',
        'path': '/test2',
        'started': 123456789.0,
        'ended': 123456790.0,
    }

    # Commit without rows (backward compat mode)
    result = graph.commit_scan(scan)

    # Should return minimal result
    assert result is not None
    assert result['db_scan_exists'] is True
    assert result['db_verified'] is False  # No write_scan call

    graph.close()


def test_inmemory_adapter_commit_returns_dict():
    """Test that InMemoryGraph.commit_scan returns verification dict."""
    from scidk.core.graph import InMemoryGraph

    graph = InMemoryGraph()

    # Add some datasets
    graph.upsert_dataset({
        'checksum': 'abc123',
        'path': '/test/file1.txt',
        'filename': 'file1.txt',
        'extension': 'txt',
        'size_bytes': 100,
        'created': 123456789.0,
        'modified': 123456789.0,
        'mime_type': 'text/plain',
        'lifecycle_state': 'active'
    })

    scan = {
        'id': 'test-scan-3',
        'path': '/test',
        'started': 123456789.0,
        'ended': 123456790.0,
        'checksums': ['abc123']
    }

    # Commit
    result = graph.commit_scan(scan)

    # Verify result structure matches Neo4j adapter
    assert result is not None
    assert 'db_scan_exists' in result
    assert 'db_files' in result
    assert 'db_folders' in result
    assert 'db_verified' in result

    # Verify counts
    assert result['db_scan_exists'] is True
    assert result['db_files'] == 1  # One file linked
    assert result['db_verified'] is True


def test_app_fallback_to_inmemory_when_neo4j_incomplete(monkeypatch):
    """Test that app.py falls back to in-memory when Neo4j env is incomplete."""
    import os

    # Set incomplete Neo4j config
    monkeypatch.setenv('SCIDK_GRAPH_BACKEND', 'neo4j')
    monkeypatch.setenv('NEO4J_URI', '')  # Empty URI should trigger fallback

    # Import after env is set
    from scidk.app import create_app

    app = create_app()

    # Should have fallen back to InMemoryGraph
    graph = app.extensions['scidk']['graph']
    from scidk.core.graph import InMemoryGraph
    assert isinstance(graph, InMemoryGraph)
