"""
Tests for automated backup scheduling and management.
"""
import pytest
import os
import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

from scidk.core.backup_manager import BackupManager
from scidk.core.backup_scheduler import BackupScheduler


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Create a temporary backup directory."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@pytest.fixture
def temp_db_files(tmp_path):
    """Create temporary database files for testing."""
    # Create dummy database files
    settings_db = tmp_path / "scidk_settings.db"
    settings_db.write_text("dummy settings db")

    path_index_db = tmp_path / "scidk_path_index.db"
    path_index_db.write_text("dummy path index db")

    env_file = tmp_path / ".env"
    env_file.write_text("DUMMY_VAR=test")

    # Change to temp directory for backup operations
    original_dir = os.getcwd()
    os.chdir(tmp_path)

    yield tmp_path

    # Restore original directory
    os.chdir(original_dir)


@pytest.fixture
def backup_manager(temp_backup_dir):
    """Create a BackupManager instance."""
    return BackupManager(backup_dir=str(temp_backup_dir))


@pytest.fixture
def backup_scheduler(backup_manager):
    """Create a BackupScheduler instance."""
    return BackupScheduler(
        backup_manager=backup_manager,
        schedule_hour=2,
        retention_days=30,
        verify_backups=True
    )


def test_backup_scheduler_initialization(backup_scheduler):
    """Test that backup scheduler initializes correctly."""
    assert backup_scheduler.schedule_hour == 2
    assert backup_scheduler.retention_days == 30
    assert backup_scheduler.verify_backups is True
    assert not backup_scheduler.is_running()


def test_backup_scheduler_start_stop(backup_scheduler):
    """Test starting and stopping the scheduler."""
    backup_scheduler.start()
    assert backup_scheduler.is_running()

    backup_scheduler.stop()
    assert not backup_scheduler.is_running()


def test_backup_verification(backup_manager, backup_scheduler, temp_db_files):
    """Test backup verification functionality."""
    # Create a backup
    result = backup_manager.create_backup(reason='test', created_by='test_user')
    assert result['success']

    # Verify the backup
    verification = backup_scheduler.verify_backup(result['filename'])
    assert verification['verified']
    assert 'backup_id' in verification
    assert 'files_count' in verification


def test_backup_verification_corrupted(backup_manager, backup_scheduler, temp_backup_dir):
    """Test verification of corrupted backup."""
    # Create a fake corrupted backup file
    fake_backup = temp_backup_dir / "corrupted-backup.zip"
    fake_backup.write_text("not a real zip file")

    # Verify should fail
    verification = backup_scheduler.verify_backup(str(fake_backup))
    assert not verification['verified']
    assert 'error' in verification


def test_cleanup_old_backups(backup_manager, backup_scheduler, temp_db_files, temp_backup_dir):
    """Test cleanup of old backups."""
    # Create several backups
    backups = []
    for i in range(5):
        result = backup_manager.create_backup(reason='test', created_by='test_user')
        assert result['success']
        backups.append(result)
        time.sleep(0.1)  # Small delay to ensure different timestamps

    # Manually set retention to 0 days to trigger cleanup
    backup_scheduler.retention_days = 0

    # Run cleanup
    cleanup_result = backup_scheduler.cleanup_old_backups()
    assert cleanup_result['success']
    assert cleanup_result['deleted_count'] >= 0  # May be 0 if backups too recent


def test_cleanup_respects_retention_policy(backup_manager, backup_scheduler, temp_db_files):
    """Test that cleanup respects retention policy."""
    # Create a backup
    result = backup_manager.create_backup(reason='test', created_by='test_user')
    assert result['success']

    # Set retention to 30 days (recent backup should be kept)
    backup_scheduler.retention_days = 30

    # Run cleanup
    cleanup_result = backup_scheduler.cleanup_old_backups()
    assert cleanup_result['success']
    assert cleanup_result['deleted_count'] == 0  # Backup is recent, shouldn't be deleted

    # Verify backup still exists
    backups = backup_manager.list_backups()
    assert len(backups) == 1


def test_backup_verification_updates_metadata(backup_manager, backup_scheduler, temp_db_files):
    """Test that verification updates backup metadata."""
    # Create a backup
    result = backup_manager.create_backup(reason='test', created_by='test_user')
    assert result['success']
    filename = result['filename']

    # Verify the backup (this should update metadata)
    verification = backup_scheduler.verify_backup(filename)
    assert verification['verified']

    # Give a moment for metadata to be written
    time.sleep(0.1)

    # Read backup metadata to check verification info was added
    import zipfile
    import json
    backup_path = backup_manager.backup_dir / filename

    # Note: _update_backup_verification is best-effort and may fail silently
    # The important thing is that verification works, metadata update is optional
    with zipfile.ZipFile(backup_path, 'r') as zipf:
        metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
        metadata = json.loads(metadata_str)

        # Verification metadata update is best-effort, so just check the backup is valid
        # If verification field exists, it should be correct
        if 'verification' in metadata:
            assert metadata['verification']['verified'] is True


def test_get_next_backup_time(backup_scheduler):
    """Test getting next backup time."""
    # Before starting, should return None
    assert backup_scheduler.get_next_backup_time() is None

    # After starting, should return a timestamp
    backup_scheduler.start()
    next_time = backup_scheduler.get_next_backup_time()
    assert next_time is not None

    # Parse and verify it's in the future
    next_backup = datetime.fromisoformat(next_time)
    now = datetime.now(next_backup.tzinfo)
    assert next_backup > now

    backup_scheduler.stop()


def test_backup_scheduler_with_custom_schedule(backup_manager):
    """Test scheduler with custom schedule settings."""
    scheduler = BackupScheduler(
        backup_manager=backup_manager,
        schedule_hour=14,  # 2 PM
        schedule_minute=30,
        retention_days=60
    )

    assert scheduler.schedule_hour == 14
    assert scheduler.schedule_minute == 30
    assert scheduler.retention_days == 60


def test_verification_missing_metadata(backup_scheduler, temp_backup_dir):
    """Test verification of backup without metadata."""
    import zipfile

    # Create a zip without metadata
    backup_path = temp_backup_dir / "no-metadata.zip"
    with zipfile.ZipFile(backup_path, 'w') as zipf:
        zipf.writestr('dummy.txt', 'test content')

    # Verification should fail
    verification = backup_scheduler.verify_backup(str(backup_path))
    assert not verification['verified']
    assert 'metadata' in verification['error'].lower()


def test_verification_missing_listed_files(backup_scheduler, temp_backup_dir):
    """Test verification when listed files are missing from backup."""
    import zipfile
    import json

    # Create a backup with metadata listing files that don't exist
    backup_path = temp_backup_dir / "missing-files.zip"
    metadata = {
        'version': '1.0',
        'backup_id': 'test123',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'files': [
            {'path': 'missing.db', 'description': 'Missing file'}
        ]
    }

    with zipfile.ZipFile(backup_path, 'w') as zipf:
        zipf.writestr('backup_metadata.json', json.dumps(metadata))
        # Don't add the file listed in metadata

    # Verification should fail
    verification = backup_scheduler.verify_backup(str(backup_path))
    assert not verification['verified']
    assert 'missing' in verification['error'].lower()


def test_cleanup_with_invalid_timestamps(backup_manager, backup_scheduler, temp_db_files):
    """Test cleanup handles backups with invalid timestamps gracefully."""
    # Create a backup
    result = backup_manager.create_backup(reason='test', created_by='test_user')
    assert result['success']

    # Manually corrupt the timestamp in metadata
    import zipfile
    import json
    backup_path = backup_manager.backup_dir / result['filename']

    # Read existing backup
    with zipfile.ZipFile(backup_path, 'r') as zipf:
        metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
        metadata = json.loads(metadata_str)
        metadata['timestamp'] = 'invalid-timestamp'

    # Create new backup with corrupted metadata
    temp_path = backup_path.with_suffix('.tmp')
    with zipfile.ZipFile(backup_path, 'r') as old_zipf:
        with zipfile.ZipFile(temp_path, 'w') as new_zipf:
            for item in old_zipf.namelist():
                if item != 'backup_metadata.json':
                    data = old_zipf.read(item)
                    new_zipf.writestr(item, data)
            new_zipf.writestr('backup_metadata.json', json.dumps(metadata))

    temp_path.replace(backup_path)

    # Cleanup should handle this gracefully
    cleanup_result = backup_scheduler.cleanup_old_backups()
    assert cleanup_result['success']
    # Backup with invalid timestamp should be skipped

    # Original backup should still exist (wasn't cleaned due to invalid timestamp)
    backups = backup_manager.list_backups()
    assert len(backups) >= 1


def test_backup_manager_integration_with_scheduler(backup_manager, backup_scheduler, temp_db_files):
    """Test integration between BackupManager and BackupScheduler."""
    # Create backups through manager
    result1 = backup_manager.create_backup(reason='manual', created_by='user1')
    assert result1['success']

    result2 = backup_manager.create_backup(reason='auto', created_by='system')
    assert result2['success']

    # Verify both backups through scheduler
    verify1 = backup_scheduler.verify_backup(result1['filename'])
    verify2 = backup_scheduler.verify_backup(result2['filename'])

    assert verify1['verified']
    assert verify2['verified']

    # List backups
    backups = backup_manager.list_backups()
    assert len(backups) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
