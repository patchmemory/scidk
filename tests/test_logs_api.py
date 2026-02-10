"""Tests for logs API endpoints."""

import pytest
import os
from pathlib import Path


@pytest.fixture
def temp_log_file():
    """Create a temporary log file with sample entries."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'scidk.log'

    # Create sample log entries
    sample_logs = [
        '[2026-02-09 14:07:32] [INFO] [scidk.core.scanner] Scan started: /demo_data/',
        '[2026-02-09 14:07:33] [INFO] [scidk.core.scanner] Processing files...',
        '[2026-02-09 14:07:34] [WARNING] [scidk.core.scanner] Large file detected: data.csv',
        '[2026-02-09 14:07:35] [ERROR] [scidk.core.scanner] Failed to read file: corrupt.dat',
        '[2026-02-09 14:07:36] [INFO] [scidk.web.routes.api_files] API request: /api/files',
        '[2026-02-09 14:07:37] [INFO] [scidk.core.scanner] Scan completed',
    ]

    with log_file.open('w') as f:
        f.write('\n'.join(sample_logs))

    yield log_file

    # Cleanup
    if log_file.exists():
        log_file.unlink()


def test_logs_list_all(client, temp_log_file):
    """Test listing all log entries."""
    response = client.get('/api/logs/viewer')
    assert response.status_code == 200

    data = response.get_json()
    assert 'entries' in data
    assert len(data['entries']) == 6  # All 6 sample logs


def test_logs_filter_by_level(client, temp_log_file):
    """Test filtering logs by level."""
    response = client.get('/api/logs/viewer?level=ERROR')
    assert response.status_code == 200

    data = response.get_json()
    assert 'entries' in data
    assert len(data['entries']) == 1
    assert data['entries'][0]['level'] == 'ERROR'
    assert 'Failed to read file' in data['entries'][0]['message']


def test_logs_filter_by_source(client, temp_log_file):
    """Test filtering logs by source."""
    response = client.get('/api/logs/viewer?source=scanner')
    assert response.status_code == 200

    data = response.get_json()
    assert 'entries' in data
    assert len(data['entries']) == 5  # 5 scanner logs
    for entry in data['entries']:
        assert 'scanner' in entry['source'].lower()


def test_logs_search(client, temp_log_file):
    """Test searching logs by message content."""
    response = client.get('/api/logs/viewer?search=file')
    assert response.status_code == 200

    data = response.get_json()
    assert 'entries' in data
    # Should match entries containing "file" (case-insensitive)
    for entry in data['entries']:
        assert 'file' in entry['message'].lower()


def test_logs_limit(client, temp_log_file):
    """Test limiting number of returned entries."""
    response = client.get('/api/logs/viewer?limit=2')
    assert response.status_code == 200

    data = response.get_json()
    assert 'entries' in data
    assert len(data['entries']) == 2


def test_logs_combined_filters(client, temp_log_file):
    """Test combining multiple filters."""
    response = client.get('/api/logs/viewer?level=INFO&source=scanner')
    assert response.status_code == 200

    data = response.get_json()
    assert 'entries' in data
    # Should only return INFO logs from scanner
    for entry in data['entries']:
        assert entry['level'] == 'INFO'
        assert 'scanner' in entry['source'].lower()


def test_logs_no_file(client):
    """Test API response when no log file exists."""
    # Temporarily rename logs directory if it exists
    log_dir = Path('logs')
    backup_dir = None

    if log_dir.exists():
        backup_dir = Path('logs.backup')
        if backup_dir.exists():
            import shutil
            shutil.rmtree(backup_dir)
        log_dir.rename(backup_dir)

    try:
        response = client.get('/api/logs/viewer')
        assert response.status_code == 200

        data = response.get_json()
        assert 'entries' in data
        assert len(data['entries']) == 0
    finally:
        # Restore logs directory
        if backup_dir and backup_dir.exists():
            if log_dir.exists():
                import shutil
                shutil.rmtree(log_dir)
            backup_dir.rename(log_dir)


def test_logs_export(client, temp_log_file):
    """Test exporting logs as a file."""
    response = client.get('/api/logs/export')
    assert response.status_code == 200
    assert response.content_type == 'application/octet-stream'
    assert 'attachment' in response.headers.get('Content-Disposition', '')

    # Verify content
    content = response.data.decode('utf-8')
    assert 'Scan started' in content
    assert '[INFO]' in content
    assert '[ERROR]' in content


def test_logs_export_no_file(client):
    """Test export endpoint when no log file exists."""
    # Temporarily rename logs directory if it exists
    log_dir = Path('logs')
    backup_dir = None

    if log_dir.exists():
        backup_dir = Path('logs.backup')
        if backup_dir.exists():
            import shutil
            shutil.rmtree(backup_dir)
        log_dir.rename(backup_dir)

    try:
        response = client.get('/api/logs/export')
        assert response.status_code == 404

        data = response.get_json()
        assert 'error' in data
        assert 'No log file found' in data['error']
    finally:
        # Restore logs directory
        if backup_dir and backup_dir.exists():
            if log_dir.exists():
                import shutil
                shutil.rmtree(log_dir)
            backup_dir.rename(log_dir)


def test_logs_entry_format(client, temp_log_file):
    """Test that log entries have the correct format."""
    response = client.get('/api/logs/viewer')
    assert response.status_code == 200

    data = response.get_json()
    assert len(data['entries']) > 0

    entry = data['entries'][0]
    assert 'timestamp' in entry
    assert 'level' in entry
    assert 'source' in entry
    assert 'message' in entry

    # Verify timestamp format
    assert len(entry['timestamp']) == 19  # YYYY-MM-DD HH:MM:SS
    assert entry['timestamp'][4] == '-'
    assert entry['timestamp'][10] == ' '
    assert entry['timestamp'][13] == ':'
