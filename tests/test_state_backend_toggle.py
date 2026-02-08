import os
import tempfile
from pathlib import Path

import pytest

from scidk.app import create_app
from tests.conftest import authenticate_test_client


@pytest.mark.integration
def test_api_scans_uses_sqlite_when_backend_sqlite(monkeypatch, tmp_path):
    db_file = tmp_path / "toggle_sqlite.db"
    # Ensure sqlite backend and file path
    monkeypatch.setenv("SCIDK_DB_PATH", str(db_file))
    monkeypatch.setenv("SCIDK_STATE_BACKEND", "sqlite")

    app = create_app()
    client = authenticate_test_client(app.test_client(), app)

    # Create a small temp directory to scan
    scan_dir = tmp_path / "scanroot"
    scan_dir.mkdir(parents=True, exist_ok=True)
    (scan_dir / "a.txt").write_text("hello")

    # Trigger a scan via API
    r = client.post('/api/scan', json={"path": str(scan_dir), "recursive": False})
    assert r.status_code == 200, r.get_json()

    # Clear in-memory scans to ensure response comes from SQLite path
    try:
        app.extensions['scidk'].get('scans', {}).clear()
    except Exception:
        pass

    # Now request scans — should still return from SQLite
    s = client.get('/api/scans')
    assert s.status_code == 200
    scans = s.get_json() or []
    assert isinstance(scans, list)
    assert len(scans) >= 1


@pytest.mark.integration
def test_api_scans_uses_memory_when_backend_memory(monkeypatch, tmp_path):
    db_file = tmp_path / "toggle_memory.db"
    monkeypatch.setenv("SCIDK_DB_PATH", str(db_file))
    monkeypatch.setenv("SCIDK_STATE_BACKEND", "memory")

    app = create_app()
    client = authenticate_test_client(app.test_client(), app)

    # Create test dir
    scan_dir = tmp_path / "scanroot"
    scan_dir.mkdir(parents=True, exist_ok=True)
    (scan_dir / "b.txt").write_text("hello")

    # Trigger a scan to populate in-memory registry
    r = client.post('/api/scan', json={"path": str(scan_dir), "recursive": False})
    assert r.status_code == 200

    # Now clear in-memory scans and ensure endpoint returns empty (not reading from SQLite)
    try:
        app.extensions['scidk'].get('scans', {}).clear()
    except Exception:
        pass

    s = client.get('/api/scans')
    assert s.status_code == 200
    scans = s.get_json() or []
    assert isinstance(scans, list)
    assert len(scans) == 0


@pytest.mark.integration
def test_api_directories_sqlite_vs_memory(monkeypatch, tmp_path):
    # First with sqlite backend
    db_file = tmp_path / "dirs.db"
    monkeypatch.setenv("SCIDK_DB_PATH", str(db_file))
    monkeypatch.setenv("SCIDK_STATE_BACKEND", "sqlite")
    app = create_app()
    client = authenticate_test_client(app.test_client(), app)

    base = tmp_path / "root1"
    base.mkdir(parents=True, exist_ok=True)
    (base / "x.py").write_text("print(1)")

    r = client.post('/api/scan', json={"path": str(base), "recursive": False})
    assert r.status_code == 200

    # Clear in-memory dirs to force SQLite aggregation
    try:
        app.extensions['scidk'].get('directories', {}).clear()
    except Exception:
        pass

    d = client.get('/api/directories')
    assert d.status_code == 200
    dirs = d.get_json() or []
    assert isinstance(dirs, list)
    assert any(isinstance(it.get('path'), str) and it.get('path') for it in dirs)

    # Now with memory backend
    monkeypatch.setenv("SCIDK_STATE_BACKEND", "memory")
    app2 = create_app()
    client2 = authenticate_test_client(app2.test_client(), app2)

    base2 = tmp_path / "root2"
    base2.mkdir(parents=True, exist_ok=True)
    (base2 / "y.csv").write_text("a,b\n1,2")

    r2 = client2.post('/api/scan', json={"path": str(base2), "recursive": False})
    assert r2.status_code == 200

    # Clear in-memory directories and expect empty list (since memory path only)
    try:
        app2.extensions['scidk'].get('directories', {}).clear()
    except Exception:
        pass
    d2 = client2.get('/api/directories')
    assert d2.status_code == 200
    dirs2 = d2.get_json() or []
    assert isinstance(dirs2, list)
    assert len(dirs2) == 0


@pytest.mark.integration
def test_api_tasks_lists_without_error_under_both_backends(monkeypatch, tmp_path):
    db_file = tmp_path / "tasks.db"
    monkeypatch.setenv("SCIDK_DB_PATH", str(db_file))

    # First sqlite
    monkeypatch.setenv("SCIDK_STATE_BACKEND", "sqlite")
    app = create_app()
    client = authenticate_test_client(app.test_client(), app)

    # Start a background scan (creates a task)
    root = tmp_path / "t1"
    root.mkdir(parents=True, exist_ok=True)
    (root / "f.txt").write_text("hi")
    client.post('/api/scan', json={"path": str(root), "recursive": False})

    t = client.get('/api/tasks')
    assert t.status_code == 200
    items = t.get_json() or []
    assert isinstance(items, list)

    # Then memory
    monkeypatch.setenv("SCIDK_STATE_BACKEND", "memory")
    app2 = create_app()
    client2 = authenticate_test_client(app2.test_client(), app2)

    root2 = tmp_path / "t2"
    root2.mkdir(parents=True, exist_ok=True)
    (root2 / "g.txt").write_text("hi")
    client2.post('/api/scan', json={"path": str(root2), "recursive": False})

    t2 = client2.get('/api/tasks')
    assert t2.status_code == 200
    items2 = t2.get_json() or []
    assert isinstance(items2, list)
    # basic ordering check (non-increasing by started/ended)
    times = [it.get('ended') or it.get('started') or 0 for it in items2]
    assert times == sorted(times, reverse=True)
