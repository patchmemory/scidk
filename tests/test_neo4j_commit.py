import os
import types
import time
from pathlib import Path

import pytest


class _FakeSingle:
    def __init__(self, data):
        self._data = data
    def single(self):
        return self._data
    def __iter__(self):
        return iter([self._data])


class _FakeIterable:
    def __iter__(self):
        return iter([{}])


class _Recorder:
    cyphers = []


class _FakeSession:
    def __init__(self):
        self._closed = False
    def run(self, cypher, **params):
        # record the cypher so the test can inspect it later
        _Recorder.cyphers.append(cypher)
        # Detect verification query by its prefix
        if isinstance(cypher, str) and cypher.strip().startswith("OPTIONAL MATCH (s:Scan"):
            return _FakeSingle({'scan_exists': True, 'files_cnt': 1, 'folders_cnt': 1})
        return _FakeIterable()
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
    def session(self, database=None):
        return _FakeSession()
    def close(self):
        pass


class _FakeGraphDatabase:
    @staticmethod
    def driver(uri, auth=None):
        return _FakeDriver(uri=uri, auth=auth)


@pytest.mark.usefixtures("client")
def test_standard_scan_and_commit_with_mock_neo4j(app, client, tmp_path, monkeypatch):
    # Inject fake neo4j driver
    fake_module = types.SimpleNamespace(GraphDatabase=_FakeGraphDatabase)
    monkeypatch.setitem(__import__('sys').modules, 'neo4j', fake_module)

    # Configure app to attempt neo4j (no-auth mode, URI set)
    os.environ['NEO4J_URI'] = 'bolt://localhost:7687'
    os.environ['NEO4J_AUTH'] = 'none'

    # Create a small standard test scan: one file in a folder
    base: Path = tmp_path / "scanroot"
    base.mkdir(parents=True, exist_ok=True)
    sub = base / "subfolder"
    sub.mkdir()
    f = sub / "file1.txt"
    f.write_text("hello", encoding="utf-8")

    # Run scan (non-recursive to populate folders list, then recursive false)
    r = client.post('/api/scan', json={'path': str(base), 'recursive': False})
    assert r.status_code == 200, r.get_json()
    scan_id = r.get_json()['scan_id']

    # Direct commit endpoint, expect our fake driver to be used
    rc = client.post(f'/api/scans/{scan_id}/commit')
    assert rc.status_code == 200, rc.get_json()
    payload = rc.get_json()

    # It should report an attempt and positive prepared counts via verification
    assert payload.get('neo4j_attempted') is True
    # From our fake verification: db_verified True and some counts
    assert payload.get('neo4j_db_verified') is True
    assert (payload.get('neo4j_db_files') or 0) >= 1
    assert (payload.get('neo4j_db_folders') or 0) >= 0

    # Inspect the recorded Cypher for the correct SET ... WITH ... CALL shape
    commit_cyphers = [c for c in _Recorder.cyphers if isinstance(c, str) and 'MERGE (s:Scan' in c]
    assert commit_cyphers, "Expected commit Cypher to be executed"
    cy = commit_cyphers[-1]
    # Ensure simplified multi-pass Cypher structure
    assert 'UNWIND $folders AS folder' in cy
    assert 'UNWIND $rows AS r' in cy

    # Cleanup env
    os.environ.pop('NEO4J_URI', None)
    os.environ.pop('NEO4J_AUTH', None)
