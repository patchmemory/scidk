import json
import os
import types
from tests.conftest import authenticate_test_client

def test_commit_from_index_synthesizes_folder_chain(monkeypatch, tmp_path):
    # Enable index-driven commit
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    monkeypatch.setenv('SCIDK_FEATURE_FILE_INDEX', '1')
    monkeypatch.setenv('SCIDK_COMMIT_FROM_INDEX', '1')

    # Fake rclone: return a single deep file only
    payload = [
        {"Name": "abcdef", "Path": "a/b/c/abcdef", "IsDir": False, "Size": 10},
    ]

    from scidk.core import providers as prov_mod
    def fake_run(args):
        if args and args[0] == 'lsjson':
            return json.dumps(payload)
        if args and args[0] == 'listremotes':
            return 'dropbox:\n'
        if args and args[0] == 'version':
            return 'rclone v1.67.0\n'
        raise RuntimeError('unexpected args: ' + ' '.join(args))
    monkeypatch.setattr(prov_mod.RcloneProvider, '_run', staticmethod(fake_run))

    # Create app and perform scan
    from scidk.app import create_app
    app = create_app(); app.config['TESTING'] = True
    client = authenticate_test_client(app.test_client(), app)
    r = client.post('/api/scans', json={
        'provider_id': 'rclone',
        'root_id': 'dropbox:',
        'path': "dropbox:Adam Patch's files",
        'recursive': True,
        'fast_list': True,
    })
    assert r.status_code == 200, r.get_json()
    scan_id = r.get_json()['scan_id']

    # Monkeypatch neo4j driver to capture parameters instead of connecting
    captured = {}
    class FakeResult:
        def __iter__(self):
            return iter(())
    class FakeSession:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def run(self, cypher, **params):
            # capture rows/folders used in commit
            captured['rows'] = params.get('rows')
            captured['folders'] = params.get('folders')
            class R:
                def consume(self_inner):
                    return None
                def single(self_inner):
                    # post-commit verification return
                    return types.SimpleNamespace(get=lambda k: {'scan_exists': True, 'files_cnt': len(captured.get('rows') or []), 'folders_cnt': len(captured.get('folders') or [])}.get(k))
            return R()
    class FakeDriver:
        def __init__(self, *a, **k):
            pass
        def session(self, database=None):
            return FakeSession()
        def close(self):
            pass
    def fake_graphdb_driver(uri, auth=None):
        return FakeDriver()

    import scidk.app as app_mod
    # _get_neo4j_params is nested inside create_app scope; instead set env for no-auth
    monkeypatch.setenv('NEO4J_AUTH', 'none')
    monkeypatch.setenv('NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setenv('SCIDK_NEO4J_DATABASE', 'neo4j')
    import neo4j
    monkeypatch.setattr(neo4j, 'GraphDatabase', types.SimpleNamespace(driver=fake_graphdb_driver))

    # Commit
    rc = client.post(f'/api/scans/{scan_id}/commit')
    assert rc.status_code == 200, rc.get_json()
    # Verify synthesized folder chain exists in folders payload
    folders = captured.get('folders') or []
    # Should include base→a, a→b, b→c edges
    paths = {(f.get('parent'), f.get('path')) for f in folders}
    assert any(p and c and c.endswith("a") for (p,c) in paths) or any('/a' in (c or '') for (_,c) in paths)
    assert any((p and c and c.endswith('b') and ('/a' in (p or '') or p.endswith('a'))) for (p,c) in paths)
    assert any((p and c and c.endswith('c') and ('/b' in (p or '') or p.endswith('b'))) for (p,c) in paths)
