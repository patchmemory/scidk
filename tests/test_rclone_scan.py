from scidk.app import create_app
from tests.conftest import authenticate_test_client


def test_scan_rclone_path_metadata_only(monkeypatch):
    # Enable rclone provider and mock presence
    monkeypatch.setenv('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone')
    import shutil as _shutil
    monkeypatch.setattr(_shutil, 'which', lambda name: '/usr/bin/rclone' if name == 'rclone' else None)

    app = create_app(); app.config.update({"TESTING": True})
    client = authenticate_test_client(app.test_client(), app)

    # Perform a scan with an rclone path; should not error and should return ok with provider_id
    resp = client.post('/api/scan', json={
        'provider_id': 'rclone',
        'root_id': 'gdrive:',
        'path': 'gdrive:folder',
        'recursive': False,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('status') == 'ok'
    assert data.get('provider_id') == 'rclone'
    # Metadata-only: scanned count is 0 in MVP
    assert data.get('scanned') == 0
