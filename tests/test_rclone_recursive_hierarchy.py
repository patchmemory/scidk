import json
import os
from scidk.app import create_app
from tests.conftest import authenticate_test_client


def test_rclone_recursive_preserves_hierarchy_and_synthesizes_dirs(monkeypatch, tmp_path):
    # Enable rclone and sqlite index
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    monkeypatch.setenv('SCIDK_FEATURE_FILE_INDEX', '1')

    # Only a deep file returned; rclone does not emit intermediate folders here
    payload = [
        {"Name": "abcdef", "Path": "data-graph/.git/objects/09/abcdef", "IsDir": False, "Size": 10},
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

    app = create_app()
    app.config['TESTING'] = True
    client = authenticate_test_client(app.test_client(), app)

    resp = client.post('/api/scans', json={
        'provider_id': 'rclone',
        'root_id': 'dropbox:',
        'path': "dropbox:Adam Patch's files",
        'recursive': True,
        'fast_list': True,
    })
    assert resp.status_code == 200, resp.get_json()
    scan_id = resp.get_json()['scan_id']

    # Query SQLite
    from scidk.core import path_index_sqlite as pix
    conn = pix.connect(); pix.init_db(conn); cur = conn.cursor()

    # File row should have full deep path and correct parent
    cur.execute("""
        SELECT path,parent_path,name,type FROM files
        WHERE scan_id=? AND name='abcdef' AND type='file'
    """, (scan_id,))
    row = cur.fetchone(); assert row is not None
    path, parent, name, typ = row
    assert "/.git/objects/09/abcdef" in path
    assert parent.endswith("data-graph/.git/objects/09")

    # Intermediate folder rows should exist
    expected_dirs = [
        "dropbox:Adam Patch's files/data-graph",
        "dropbox:Adam Patch's files/data-graph/.git",
        "dropbox:Adam Patch's files/data-graph/.git/objects",
        "dropbox:Adam Patch's files/data-graph/.git/objects/09",
    ]
    for d in expected_dirs:
        cur.execute("SELECT COUNT(*) FROM files WHERE scan_id=? AND type='folder' AND path=?", (scan_id, d))
        assert cur.fetchone()[0] >= 1, f"Missing synthesized folder row: {d}"

    conn.close()
