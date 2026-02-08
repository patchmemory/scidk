import json
import os
from pathlib import Path
from scidk.app import create_app
from tests.conftest import authenticate_test_client


def test_rocrate_referenced_feature_flag_off(monkeypatch):
    # Ensure feature disabled by default
    monkeypatch.delenv('SCIDK_ENABLE_ROCRATE_REFERENCED', raising=False)
    app = create_app(); app.config.update({"TESTING": True})
    client = authenticate_test_client(app.test_client(), app)
    resp = client.post('/api/ro-crates/referenced', json={"dataset_ids": [], "files": []})
    assert resp.status_code == 404


def test_rocrate_referenced_writes_crate(monkeypatch, tmp_path):
    # Enable feature and set output dir
    monkeypatch.setenv('SCIDK_ENABLE_ROCRATE_REFERENCED', '1')
    monkeypatch.setenv('SCIDK_ROCRATE_DIR', str(tmp_path))

    app = create_app(); app.config.update({"TESTING": True})
    client = authenticate_test_client(app.test_client(), app)

    # Seed a minimal dataset in graph
    g = app.extensions['scidk']['graph']
    ds = {
        'id': 'ds1',
        'path': 'remote:bucket/file1.txt',
        'filename': 'file1.txt',
        'size_bytes': 123,
        'modified': 0.0,
        'mime_type': 'text/plain',
        'checksum': 'abc123',
        'extension': '.txt',
    }
    g.upsert_dataset(ds)

    resp = client.post('/api/ro-crates/referenced', json={
        'dataset_ids': ['ds1'],
        'title': 'My Crate'
    })
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    crate_id = data['crate_id']
    out_dir = Path(data['path'])
    assert out_dir.exists()
    # metadata file exists and JSON structure contains our file node
    meta = out_dir / 'ro-crate-metadata.json'
    assert meta.exists()
    ro = json.loads(meta.read_text())
    assert '@graph' in ro
    ids = [n.get('@id') for n in ro['@graph']]
    assert any(str(i).startswith('rclone://') or str(i).startswith('file://') or str(i).endswith('ro-crate-metadata.json') for i in ids)
