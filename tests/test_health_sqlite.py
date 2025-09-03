import os
from pathlib import Path

import pytest

from scidk.app import create_app


def test_health_sqlite_endpoint(monkeypatch, tmp_path):
    db_path = tmp_path / 'files.db'
    monkeypatch.setenv('SCIDK_DB_PATH', str(db_path))

    app = create_app()
    client = app.test_client()

    resp = client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'sqlite' in data
    s = data['sqlite']
    assert s['path'] == str(db_path)
    assert s['journal_mode'] == 'wal'
    assert s['select1'] is True
    # DB file should be created on disk as a side-effect of health check
    assert Path(s['path']).exists()
