"""
Tests for progress indicators: ETA, status messages, and real-time updates.
"""
import time
from pathlib import Path


def test_scan_progress_eta_and_status_messages(app, client, tmp_path):
    """Test that scan tasks provide ETA and status messages during execution."""
    # Create a directory with multiple files to allow progress tracking
    base: Path = tmp_path / "progressroot"
    base.mkdir(parents=True, exist_ok=True)
    for i in range(20):
        (base / f"file_{i}.txt").write_text(f"content {i}\n", encoding="utf-8")

    # Start a background scan task
    r = client.post('/api/tasks', json={
        'type': 'scan',
        'path': str(base),
        'recursive': True,
    })
    assert r.status_code in (200, 202), r.get_json()
    body = r.get_json()
    task_id = body.get('task_id')
    assert task_id

    # Poll and collect status messages and ETA values
    deadline = time.time() + 10
    status_messages = []
    eta_values = []

    while time.time() < deadline:
        rd = client.get(f'/api/tasks/{task_id}')
        assert rd.status_code == 200
        tj = rd.get_json()
        status = tj.get('status')

        # Collect progress indicators
        if 'status_message' in tj and tj['status_message']:
            status_messages.append(tj['status_message'])
        if 'eta_seconds' in tj and tj['eta_seconds'] is not None:
            eta_values.append(tj['eta_seconds'])

        if status in ('completed', 'error', 'canceled'):
            break
        time.sleep(0.05)

    # Verify task completed successfully
    final_task = client.get(f'/api/tasks/{task_id}').get_json()
    assert final_task.get('status') == 'completed'

    # Verify we got status messages during execution
    assert len(status_messages) > 0, "Should have status messages"
    # Check that we got meaningful status messages (not just empty strings)
    assert any('files' in msg.lower() or 'processing' in msg.lower() or 'counting' in msg.lower()
               for msg in status_messages), f"Status messages should be informative: {status_messages}"

    # Note: ETA may not always be present for very fast scans, so we don't assert it must exist
    # but if it does exist, it should be positive
    if eta_values:
        assert all(eta >= 0 for eta in eta_values), f"ETAs should be non-negative: {eta_values}"


def test_commit_progress_status_messages(app, client, tmp_path):
    """Test that commit tasks provide status messages during execution."""
    # Create and scan a directory first
    base: Path = tmp_path / "commitroot"
    base.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (base / f"file_{i}.txt").write_text(f"content {i}\n", encoding="utf-8")

    # Run a scan first
    scan_r = client.post('/api/tasks', json={
        'type': 'scan',
        'path': str(base),
        'recursive': True,
    })
    assert scan_r.status_code in (200, 202)
    scan_task_id = scan_r.get_json().get('task_id')

    # Wait for scan to complete
    deadline = time.time() + 10
    while time.time() < deadline:
        rd = client.get(f'/api/tasks/{scan_task_id}')
        if rd.get_json().get('status') in ('completed', 'error'):
            break
        time.sleep(0.05)

    scan_task = client.get(f'/api/tasks/{scan_task_id}').get_json()
    assert scan_task.get('status') == 'completed'
    scan_id = scan_task.get('scan_id')
    assert scan_id

    # Now start a commit task
    commit_r = client.post('/api/tasks', json={
        'type': 'commit',
        'scan_id': scan_id,
    })
    assert commit_r.status_code in (200, 202)
    commit_task_id = commit_r.get_json().get('task_id')

    # Collect status messages
    status_messages = []
    deadline = time.time() + 10

    while time.time() < deadline:
        rd = client.get(f'/api/tasks/{commit_task_id}')
        assert rd.status_code == 200
        tj = rd.get_json()
        status = tj.get('status')

        if 'status_message' in tj and tj['status_message']:
            status_messages.append(tj['status_message'])

        if status in ('completed', 'error', 'canceled'):
            break
        time.sleep(0.05)

    # Verify commit completed
    final_task = client.get(f'/api/tasks/{commit_task_id}').get_json()
    assert final_task.get('status') == 'completed'

    # Verify we got status messages
    assert len(status_messages) > 0, "Should have status messages for commit"
    # Check for commit-related status messages
    assert any('commit' in msg.lower() or 'neo4j' in msg.lower() or 'rows' in msg.lower()
               for msg in status_messages), f"Status messages should be commit-related: {status_messages}"


def test_task_progress_fields_present(app, client, tmp_path):
    """Test that all expected progress fields are present in task responses."""
    base: Path = tmp_path / "fieldsroot"
    base.mkdir(parents=True, exist_ok=True)
    (base / "test.txt").write_text("test", encoding="utf-8")

    # Start a scan task
    r = client.post('/api/tasks', json={
        'type': 'scan',
        'path': str(base),
        'recursive': False,
    })
    assert r.status_code in (200, 202)
    task_id = r.get_json().get('task_id')

    # Get task details
    time.sleep(0.1)  # Give it a moment to start
    rd = client.get(f'/api/tasks/{task_id}')
    assert rd.status_code == 200
    task = rd.get_json()

    # Verify expected fields exist
    assert 'progress' in task, "Task should have progress field"
    assert 'processed' in task, "Task should have processed field"
    assert 'total' in task, "Task should have total field"
    assert 'status' in task, "Task should have status field"
    assert 'status_message' in task, "Task should have status_message field"
    assert 'eta_seconds' in task, "Task should have eta_seconds field"

    # Wait for completion
    deadline = time.time() + 10
    while time.time() < deadline:
        rd = client.get(f'/api/tasks/{task_id}')
        if rd.get_json().get('status') in ('completed', 'error'):
            break
        time.sleep(0.05)
