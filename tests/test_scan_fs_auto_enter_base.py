import json
from pathlib import Path


def test_fs_auto_enters_base_rclone(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    monkeypatch.setenv('SCIDK_FEATURE_FILE_INDEX', '1')

    from scidk.core import providers as prov_mod

    lsjson_payload = [
        {"Name": "data-graph", "Path": "data-graph", "IsDir": True, "Size": 0},
        {"Name": "Home", "Path": "Home", "IsDir": True, "Size": 0},
        {"Name": "README.md", "Path": "README.md", "IsDir": False, "Size": 99, "MimeType": "text/markdown"},
        {"Name": ".git/objects/09/abcdef", "Path": ".git/objects/09/abcdef", "IsDir": False, "Size": 10},
    ]

    def fake_run(args):
        if args and args[0] == 'lsjson':
            return json.dumps(lsjson_payload)
        if args and args[0] == 'version':
            return 'rclone v1.67.0\n'
        if args and args[0] == 'listremotes':
            return 'dropbox:\n'
        return ''

    monkeypatch.setattr(prov_mod.RcloneProvider, '_run', staticmethod(fake_run))

    from scidk.app import create_app
    app = create_app()
    client = app.test_client()

    resp = client.post('/api/scans', json={
        'provider_id': 'rclone',
        'root_id': 'dropbox:',
        'path': "dropbox:Adam Patch's files",
        'recursive': True,
        'fast_list': True,
    })
    assert resp.status_code == 200
    scan_id = resp.get_json()['scan_id']

    fs = client.get(f'/api/scans/{scan_id}/fs').get_json()
    folder_names = [f['name'] for f in fs.get('folders', [])]
    assert 'data-graph' in folder_names
    assert 'Home' in folder_names
    assert '09' not in folder_names

    path = "dropbox:Adam Patch's files/.git/objects"
    fs2 = client.get(f'/api/scans/{scan_id}/fs', query_string={'path': path}).get_json()
    inner_folders = [f['name'] for f in fs2.get('folders', [])]
    # Depending on ingestion, objects subfolders may be synthesized as folder nodes;
    # allow either exact '09' or names that start with '09'
    assert ('09' in inner_folders) or any(x.startswith('09') for x in inner_folders)
