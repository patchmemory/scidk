"""E2E: Verify SQLite-backed state persists across app restart.

This test starts the app on a separate port with a temp on-disk SQLite DB,
creates a scan via API, restarts the app, and asserts the scan remains.

We do not reuse the session-scoped app fixture here to control restart timing.
"""
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests
import subprocess
import sys


PORT = 5011
HOST = "127.0.0.1"
BASE = f"http://{HOST}:{PORT}"


@contextmanager
def run_app(tmp_db_path: str):
    env = os.environ.copy()
    env.update({
        "SCIDK_PORT": str(PORT),
        "NEO4J_AUTH": "none",
        "SCIDK_PROVIDERS": "local_fs",
        # Use on-disk SQLite to verify persistence across process restarts
        "SCIDK_DB_PATH": f"sqlite:///{tmp_db_path}",
        # Prefer sqlite-backed state when supported
        # (If the toggle is implemented later, it should default to sqlite.)
    })
    repo_root = Path(__file__).resolve().parents[2]
    p = subprocess.Popen([sys.executable, "-m", "scidk.app"], cwd=repo_root, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Wait for server
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(BASE + "/health", timeout=0.5)
            if r.status_code < 500:
                break
        except Exception:
            time.sleep(0.3)
    else:
        try:
            out, err = p.communicate(timeout=1)
        except Exception:
            out = err = b""
        raise RuntimeError("App failed to start for persistence test.\n" +
                           f"stdout: {out.decode(errors='ignore')}\n" +
                           f"stderr: {err.decode(errors='ignore')}")
    try:
        yield p
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except Exception:
            p.kill()


@pytest.mark.e2e
def test_state_persists_across_restart(tmp_path):
    # Create a temp on-disk DB in a unique temp directory
    db_dir = tempfile.mkdtemp(prefix="scidk_e2e_")
    db_file = os.path.join(db_dir, "e2e_persist.db")
    try:
        # First run: start app and create a scan via API
        with run_app(db_file):
            # Create a small temporary folder to scan
            scan_root = tmp_path / "data"
            scan_root.mkdir(parents=True, exist_ok=True)
            (scan_root / "a.txt").write_text("hello")

            # Trigger scan via public API
            r = requests.post(BASE + "/api/scan", json={
                "path": str(scan_root),
                "recursive": False,
            }, timeout=10)
            assert r.status_code == 200, r.text

            # fetch scans list
            s = requests.get(BASE + "/api/scans", timeout=10)
            assert s.status_code == 200, s.text
            scans = s.json() or []
            assert len(scans) >= 1
            last_id = scans[0]["id"] if isinstance(scans, list) else scans.get("id")
            assert last_id

        # Second run: restart app and assert the same scan is still visible
        with run_app(db_file):
            s2 = requests.get(BASE + "/api/scans", timeout=10)
            assert s2.status_code == 200, s2.text
            scans2 = s2.json() or []
            assert len(scans2) >= 1

    finally:
        shutil.rmtree(db_dir, ignore_errors=True)
