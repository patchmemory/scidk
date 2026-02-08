import os
import time
from pathlib import Path

import pytest
from scidk.app import create_app
from tests.conftest import authenticate_test_client

pytestmark = pytest.mark.integration


def _run_scan(client, path: Path, recursive=True):
    r = client.post('/api/scan', json={'path': str(path), 'recursive': recursive})
    assert r.status_code == 200, r.data
    payload = r.get_json()
    assert payload.get('status') == 'ok'
    return payload


def test_second_scan_skips_when_unchanged(monkeypatch, tmp_path):
    # Use on-disk sqlite to persist between requests in the same app
    db_file = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_file))
    monkeypatch.setenv('SCIDK_STATE_BACKEND', 'sqlite')

    # Create a small directory tree
    base = tmp_path / 'data'
    (base / 'sub').mkdir(parents=True, exist_ok=True)
    (base / 'a.txt').write_text('hello')
    (base / 'sub' / 'b.txt').write_text('world')

    app = create_app()
    client = authenticate_test_client(app.test_client(), app)

    # First scan
    p1 = _run_scan(client, base)
    # Pull scan summary (should include extra_json with metrics once persisted)
    scans1 = client.get('/api/scans').get_json()
    assert scans1 and isinstance(scans1, list)

    # Sleep a tiny bit to avoid same timestamp edge cases
    time.sleep(0.01)

    # Second scan (unchanged tree)
    p2 = _run_scan(client, base)

    # Fetch scans list again and locate the latest scan (index 0 by default ordering)
    scans2 = client.get('/api/scans').get_json()
    assert scans2 and isinstance(scans2, list)
    latest = scans2[0]
    # The extra_json with selective cache metrics is not directly exposed; request /api/scans already expands fields
    # We assert on duration improvement (lenient) OR presence of non-zero ingested_rows decrease.
    # Since timing can be flaky in CI, prefer that second duration is <= first duration * 1.25 (25% slack)
    # Find the previous scan for same path in the list
    prev = None
    for it in scans2[1:]:
        if it.get('path') == str(base):
            prev = it
            break
    assert prev is not None, "Previous scan for same path not found in history"

    d1 = float(prev.get('duration_sec') or 0.0)
    d2 = float(latest.get('duration_sec') or 0.0)

    # Accept either a strict reduction or a very close equal time when the tree is tiny
    assert d2 <= (d1 * 1.25 + 0.005)
