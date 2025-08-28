import json
import os
from scidk.app import create_app


def test_rclone_scan_ingest_monkeypatched(monkeypatch, tmp_path):
    # Ensure rclone provider is enabled and SQLite DB points to temp file
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')
    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))

    # Fake rclone lsjson output: 2 files and 1 folder when non-recursive
    lsjson_payload = [
        {"Name": "folderA", "Path": "folderA", "IsDir": True, "Size": 0},
        {"Name": "file1.txt", "Path": "file1.txt", "IsDir": False, "Size": 123, "MimeType": "text/plain"},
        {"Name": "file2.csv", "Path": "file2.csv", "IsDir": False, "Size": 456, "MimeType": "text/csv"},
    ]

    from scidk.core import providers as prov_mod

    def fake_run(args):
        # Simulate only lsjson calls used by list_files
        if args and args[0] == 'lsjson':
            # Respect fast-list and depth flags but ignore them in output
            return json.dumps(lsjson_payload)
        if args and args[0] == 'listremotes':
            return 'remote:\n'  # not used in this test
        if args and args[0] == 'version':
            return 'rclone v1.67.0\n'
        raise RuntimeError('unexpected args: ' + ' '.join(args))

    monkeypatch.setattr(prov_mod.RcloneProvider, '_run', staticmethod(fake_run))

    app = create_app()
    client = app.test_client()

    # Trigger a scan using rclone provider, non-recursive with fast_list
    resp = client.post('/api/scans', json={
        'provider_id': 'rclone',
        'root_id': 'remote:',
        'path': 'remote:bucket',
        'recursive': False,
        'fast_list': True,
    })
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    scan_id = data['scan_id']

    # Status should reflect counts and ingestion
    st = client.get(f'/api/scans/{scan_id}/status')
    assert st.status_code == 200
    status = st.get_json()
    # 2 files were reported; file_count counts datasets added (files only)
    assert status['file_count'] == 2
    # ingested_rows should include both file and folder rows (3 total)
    assert status['ingested_rows'] >= 3
    assert status['source'].startswith('provider:rclone')

    # Validate fs listing for this scan's virtual roots works at least at the top-level
    fs_resp = client.get(f'/api/scans/{scan_id}/fs')
    assert fs_resp.status_code == 200
    fs_data = fs_resp.get_json()
    # Should have a virtual root with folders list possibly empty for this synthetic data
    assert fs_data['scan_id'] == scan_id
