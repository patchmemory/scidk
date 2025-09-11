import types
import pytest

from scidk.app import commit_to_neo4j_batched


class _FakeResult:
    def __init__(self, data=None):
        self._data = data or {}
    def single(self):
        return self._data
    def __iter__(self):
        # allow iteration if needed
        return iter([self._data])
    def consume(self):
        # neo4j Result.consume() no-op for tests
        return None


class _Recorder:
    calls = []  # list of dicts: {cypher, params}


class _FakeSession:
    def __init__(self):
        self.closed = False
    def run(self, cypher, **params):
        # record every cypher and its params for assertions
        _Recorder.calls.append({"cypher": cypher, "params": dict(params)})
        c = (cypher or '').strip()
        if c.startswith("OPTIONAL MATCH (s:Scan"):
            # verification query
            return _FakeResult({'scan_exists': True, 'files_cnt': 1, 'folders_cnt': 2})
        return _FakeResult({})
    def close(self):
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        self.close()


class _FakeDriver:
    def __init__(self, uri=None, auth=None):
        self.uri = uri
        self.auth = auth
    def session(self, database=None):
        return _FakeSession()
    def close(self):
        pass


class _FakeGraphDatabase:
    @staticmethod
    def driver(uri, auth=None):
        return _FakeDriver(uri=uri, auth=auth)


@pytest.mark.usefixtures("client")
def test_commit_executes_folder_upsert_and_link_with_node_host(monkeypatch):
    # Patch neo4j module so internal import in function picks this fake
    fake_module = types.SimpleNamespace(GraphDatabase=_FakeGraphDatabase)
    monkeypatch.setitem(__import__('sys').modules, 'neo4j', fake_module)

    # Arrange scan and simple nested structure
    scan = {
        'id': 'scanX',
        'path': 'dropbox:AIPT/CAC protocols/Active protocols',
        'provider_id': 'rclone',
        'host_type': 'remote',
        'host_id': 'host123',
        'root_id': 'rootX',
        'root_label': 'base',
        'scan_source': 'index',
    }
    rows = [
        {
            'path': 'dropbox:AIPT/CAC protocols/Active protocols/folderA/file1.txt',
            'filename': 'file1.txt',
            'extension': '.txt',
            'size_bytes': 10,
            'created': 0.0,
            'modified': 0.0,
            'mime_type': 'text/plain',
            'folder': 'dropbox:AIPT/CAC protocols/Active protocols/folderA',
        }
    ]
    folder_rows = [
        {
            'path': 'dropbox:AIPT/CAC protocols/Active protocols/folderA',
            'name': 'folderA',
            'parent': 'dropbox:AIPT/CAC protocols/Active protocols',
        },
        {
            'path': 'dropbox:AIPT/CAC protocols/Active protocols',
            'name': 'Active protocols',
            'parent': 'dropbox:AIPT/CAC protocols',
        },
    ]

    # Act
    _Recorder.calls.clear()
    events = []
    def _on(e,p):
        events.append((e,p))
    res = commit_to_neo4j_batched(
        rows,
        folder_rows,
        scan,
        ("bolt://localhost:7687", "user", "pass", "neo4j", "basic"),
        file_batch_size=50,
        folder_batch_size=50,
        max_retries=0,
        on_progress=_on,
    )

    # Assert: function attempted and produced batches
    assert res["attempted"] is True
    assert res["batches_total"] >= 1
    # We expect at least: constraints (2), scan_upsert (1), folder upsert (1), folder link (1), file stage (1), verify (1)
    assert len(_Recorder.calls) >= 6

    # Find queries by distinctive substrings
    upsert_calls = [c for c in _Recorder.calls if 'MERGE (fo:Folder' in c['cypher'] and ':SCANNED_IN' in c['cypher']]
    link_calls = [c for c in _Recorder.calls if 'MERGE (child:Folder' in c['cypher'] and '(parent)-[:CONTAINS]->(child)' in c['cypher']]
    file_calls = [c for c in _Recorder.calls if 'MERGE (f:File' in c['cypher']]

    assert upsert_calls, "Expected folder upsert cypher to be executed"
    assert link_calls, "Expected folder link cypher to be executed"
    assert file_calls, "Expected file cypher to be executed"

    # Verify node_host parameter is passed in both folder stages
    assert upsert_calls[0]['params'].get('node_host') == scan['host_id']
    assert link_calls[0]['params'].get('node_host') == scan['host_id']

    # Verify link cypher contains parent->child MERGE pattern
    assert '(parent)-[:CONTAINS]->(child)' in link_calls[0]['cypher']

    # on_progress should include neo4j_params event
    assert any(e == 'neo4j_params' for (e, _) in events)
