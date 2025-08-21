import time
from pathlib import Path


def test_background_scan_task_lifecycle(app, client, tmp_path):
    # Create a tiny directory with a couple of files
    base: Path = tmp_path / "scanroot"
    base.mkdir(parents=True, exist_ok=True)
    (base / "a.py").write_text("print('hi')\n", encoding="utf-8")
    (base / "b.txt").write_text("hello\nworld\n", encoding="utf-8")

    # Start a background scan task
    r = client.post('/api/tasks', json={
        'type': 'scan',
        'path': str(base),
        'recursive': False,
    })
    assert r.status_code in (200, 202), r.get_json()
    body = r.get_json()
    task_id = body.get('task_id')
    assert task_id

    # Poll until completion (with timeout)
    progress_samples = []
    deadline = time.time() + 10
    status = None
    while time.time() < deadline:
        rd = client.get(f'/api/tasks/{task_id}')
        assert rd.status_code == 200
        tj = rd.get_json()
        status = tj.get('status')
        progress_samples.append(tj.get('progress') or 0.0)
        if status in ('completed', 'error', 'canceled'):
            break
        time.sleep(0.05)

    assert status == 'completed', f"final status={status}, samples={progress_samples}"
    # Ensure progress generally moved up
    assert any(p > 0 for p in progress_samples), progress_samples
    assert progress_samples[-1] >= 1.0 - 1e-9

    # Verify a scan record exists and is linked to the task
    tj = client.get(f'/api/tasks/{task_id}').get_json()
    scan_id = tj.get('scan_id')
    assert scan_id

    scans = client.get('/api/scans').get_json() or []
    assert any(s.get('id') == scan_id for s in scans)
