import os
import time
from pathlib import Path


def _poll_task(client, task_id, timeout=10):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f'/api/tasks/{task_id}')
        assert r.status_code == 200
        tj = r.get_json()
        last = tj
        if tj.get('status') in ('completed', 'error', 'canceled'):
            return tj
        time.sleep(0.05)
    return last


def test_max_concurrent_tasks_enforced(app, client, tmp_path, monkeypatch):
    # Allow only 1 running task
    monkeypatch.setenv('SCIDK_MAX_BG_TASKS', '1')

    # Create a directory with many files to keep the task running briefly
    base: Path = tmp_path / 'root1'
    base.mkdir(parents=True, exist_ok=True)
    for i in range(300):
        (base / f'f{i}.txt').write_text('x\n', encoding='utf-8')

    # Start first task
    r1 = client.post('/api/tasks', json={'type': 'scan', 'path': str(base), 'recursive': False})
    assert r1.status_code in (200, 202)
    t1 = r1.get_json()['task_id']

    # Immediately attempt to start a second task; should be rejected with 429
    base2: Path = tmp_path / 'root2'
    base2.mkdir(parents=True, exist_ok=True)
    (base2 / 'a.txt').write_text('hello', encoding='utf-8')
    r2 = client.post('/api/tasks', json={'type': 'scan', 'path': str(base2), 'recursive': False})
    assert r2.status_code == 429, r2.get_json()
    body2 = r2.get_json()
    assert body2.get('code') == 'max_tasks'

    # Let first task finish to avoid hanging
    done = _poll_task(client, t1, timeout=10)
    assert done.get('status') in ('completed', 'canceled', 'error')


def test_cancel_scan_task(app, client, tmp_path, monkeypatch):
    # Create a directory with many files to allow cancel mid-flight
    base: Path = tmp_path / 'root_cancel'
    base.mkdir(parents=True, exist_ok=True)
    for i in range(500):
        (base / f'f{i}.py').write_text('print(1)\n', encoding='utf-8')

    # Start background scan
    r = client.post('/api/tasks', json={'type': 'scan', 'path': str(base), 'recursive': False})
    assert r.status_code in (200, 202)
    tid = r.get_json()['task_id']

    # Request cancel promptly
    rc = client.post(f'/api/tasks/{tid}/cancel')
    assert rc.status_code == 202

    # Poll until final state
    final = _poll_task(client, tid, timeout=10)
    assert final.get('status') == 'canceled', final
    # canceled tasks should not have a scan_id
    assert final.get('scan_id') in (None, '')
    # And progress should be < 1
    assert (final.get('progress') or 0.0) < 1.0
