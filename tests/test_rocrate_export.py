import io
import os
from pathlib import Path
from scidk.app import create_app


def test_rocrate_export_zip(monkeypatch, tmp_path):
    # Enable feature and set output dir
    monkeypatch.setenv('SCIDK_ENABLE_ROCRATE_REFERENCED', '1')
    monkeypatch.setenv('SCIDK_ROCRATE_DIR', str(tmp_path))

    app = create_app(); app.config.update({"TESTING": True})
    client = app.test_client()

    # Create a crate with no items is fine
    resp = client.post('/api/ro-crates/referenced', json={
        'dataset_ids': [],
        'title': 'Empty Crate'
    })
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    crate_id = data['crate_id']

    # Write an extra dummy metadata file to ensure zip includes files
    crate_dir = Path(tmp_path) / crate_id
    (crate_dir / 'extra.txt').write_text('hello')

    # Export as zip
    resp2 = client.post(f'/api/ro-crates/{crate_id}/export?target=zip')
    assert resp2.status_code == 200
    # Check zip mimetype
    assert 'application/zip' in (resp2.mimetype or '')
    # Ensure content looks like a zip (PK header)
    bio = io.BytesIO(resp2.data)
    head = bio.read(2)
    assert head == b'PK'


def test_rocrate_export_missing(monkeypatch, tmp_path):
    monkeypatch.setenv('SCIDK_ENABLE_ROCRATE_REFERENCED', '1')
    monkeypatch.setenv('SCIDK_ROCRATE_DIR', str(tmp_path))
    app = create_app(); app.config.update({"TESTING": True})
    client = app.test_client()
    resp = client.post('/api/ro-crates/does-not-exist/export?target=zip')
    assert resp.status_code == 404
    assert 'error' in resp.get_json()
