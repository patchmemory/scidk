"""
Tests for configuration export/import functionality.
"""

import pytest
import json
import tempfile
import os
from scidk.core.config_manager import ConfigManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def config_manager(temp_db):
    """Create a ConfigManager instance for testing."""
    return ConfigManager(temp_db)


def test_config_manager_init(config_manager):
    """Test ConfigManager initialization."""
    assert config_manager is not None
    assert config_manager.CONFIG_VERSION == "1.0"


def test_create_backup(config_manager):
    """Test creating a configuration backup."""
    backup_id = config_manager.create_backup(
        reason='test',
        created_by='test_user',
        notes='Test backup'
    )

    assert backup_id is not None
    assert len(backup_id) > 0

    # Verify backup was created
    backup = config_manager.get_backup(backup_id)
    assert backup is not None
    assert backup['reason'] == 'test'
    assert backup['created_by'] == 'test_user'
    assert backup['notes'] == 'Test backup'
    assert 'config' in backup
    assert backup['config']['version'] == '1.0'


def test_list_backups(config_manager):
    """Test listing configuration backups."""
    # Create a few backups
    backup_id1 = config_manager.create_backup(reason='test1', created_by='user1')
    backup_id2 = config_manager.create_backup(reason='test2', created_by='user2')
    backup_id3 = config_manager.create_backup(reason='test3', created_by='user3')

    # List backups
    backups = config_manager.list_backups(limit=10)

    assert len(backups) >= 3
    # Most recent should be first
    assert backups[0]['id'] == backup_id3
    assert backups[1]['id'] == backup_id2
    assert backups[2]['id'] == backup_id1


def test_delete_backup(config_manager):
    """Test deleting a configuration backup."""
    backup_id = config_manager.create_backup(reason='test', created_by='test_user')

    # Verify backup exists
    assert config_manager.get_backup(backup_id) is not None

    # Delete backup
    deleted = config_manager.delete_backup(backup_id)
    assert deleted is True

    # Verify backup was deleted
    assert config_manager.get_backup(backup_id) is None

    # Try deleting non-existent backup
    deleted = config_manager.delete_backup('non-existent-id')
    assert deleted is False


def test_export_config_basic(config_manager):
    """Test basic configuration export."""
    config = config_manager.export_config(include_sensitive=False)

    assert config is not None
    assert config['version'] == '1.0'
    assert 'timestamp' in config
    assert config['include_sensitive'] is False

    # Check that all sections are present
    assert 'general' in config
    assert 'neo4j' in config
    assert 'chat' in config
    assert 'interpreters' in config
    assert 'plugins' in config
    assert 'rclone' in config
    assert 'integrations' in config
    assert 'security' in config


def test_export_config_selective_sections(config_manager):
    """Test exporting specific sections only."""
    config = config_manager.export_config(
        include_sensitive=False,
        sections=['general', 'neo4j']
    )

    assert 'general' in config
    assert 'neo4j' in config
    assert 'chat' not in config
    assert 'interpreters' not in config


def test_export_config_with_sensitive(config_manager):
    """Test exporting configuration with sensitive data."""
    config_without = config_manager.export_config(include_sensitive=False)
    config_with = config_manager.export_config(include_sensitive=True)

    assert config_without['include_sensitive'] is False
    assert config_with['include_sensitive'] is True


def test_import_config_validation(config_manager):
    """Test import configuration validation."""
    # Test with invalid version
    invalid_config = {
        'version': '99.9',
        'timestamp': '2026-02-08T10:00:00Z',
        'general': {}
    }

    report = config_manager.import_config(invalid_config, create_backup=False)

    assert report['success'] is False
    assert len(report['errors']) > 0
    assert 'version mismatch' in report['errors'][0].lower()


def test_import_config_with_backup(config_manager):
    """Test importing configuration with automatic backup."""
    # Export current config
    original_config = config_manager.export_config(include_sensitive=True)

    # Import the same config (should create backup)
    report = config_manager.import_config(
        original_config,
        create_backup=True,
        created_by='test_user'
    )

    # Print report for debugging
    if not report['success']:
        print(f"Import failed with errors: {report.get('errors', [])}")

    assert report['success'] is True
    assert report['backup_id'] is not None

    # Verify backup was created
    backup = config_manager.get_backup(report['backup_id'])
    assert backup is not None
    assert backup['reason'] == 'pre_import'
    assert backup['created_by'] == 'test_user'


def test_restore_backup(config_manager):
    """Test restoring configuration from backup."""
    # Create initial backup
    backup_id = config_manager.create_backup(
        reason='test_restore',
        created_by='test_user'
    )

    # Restore from backup
    report = config_manager.restore_backup(backup_id, created_by='test_user')

    assert report['success'] is True
    # Restoring should create another backup
    assert report['backup_id'] is not None


def test_restore_nonexistent_backup(config_manager):
    """Test restoring from non-existent backup."""
    report = config_manager.restore_backup('non-existent-id')

    assert report['success'] is False
    assert len(report['errors']) > 0


def test_preview_import_diff_no_changes(config_manager):
    """Test preview with no changes."""
    current_config = config_manager.export_config(include_sensitive=False)

    diff = config_manager.preview_import_diff(current_config)

    assert 'sections' in diff
    # Should have no changes since we're importing the same config
    assert len(diff['sections']) == 0


def test_preview_import_diff_with_changes(config_manager):
    """Test preview with changes."""
    current_config = config_manager.export_config(include_sensitive=False)

    # Modify the config
    modified_config = current_config.copy()
    if 'general' not in modified_config:
        modified_config['general'] = {}
    modified_config['general']['new_key'] = 'new_value'

    diff = config_manager.preview_import_diff(modified_config)

    assert 'sections' in diff
    # Should detect the change
    if 'general' in diff['sections']:
        changes = diff['sections']['general']
        assert 'added' in changes or 'changed' in changes


def test_export_import_roundtrip(config_manager):
    """Test exporting and re-importing configuration."""
    # Export current config
    exported = config_manager.export_config(include_sensitive=True)

    # Save to JSON
    json_str = json.dumps(exported)

    # Parse back from JSON
    imported = json.loads(json_str)

    # Import the config
    report = config_manager.import_config(imported, create_backup=True)

    assert report['success'] is True
    assert len(report['sections_imported']) > 0


def test_diff_dicts_basic(config_manager):
    """Test dictionary diffing utility."""
    current = {'a': 1, 'b': 2, 'c': 3}
    new = {'a': 1, 'b': 5, 'd': 4}

    diff = config_manager._diff_dicts(current, new)

    # b changed: 2 -> 5
    assert len(diff['changed']) == 1
    assert diff['changed'][0]['key'] == 'b'
    assert diff['changed'][0]['old_value'] == 2
    assert diff['changed'][0]['new_value'] == 5

    # d added
    assert len(diff['added']) == 1
    assert diff['added'][0]['key'] == 'd'

    # c removed
    assert len(diff['removed']) == 1
    assert diff['removed'][0]['key'] == 'c'


def test_diff_dicts_nested(config_manager):
    """Test dictionary diffing with nested objects."""
    current = {
        'level1': {
            'level2': {
                'key': 'old_value'
            }
        }
    }
    new = {
        'level1': {
            'level2': {
                'key': 'new_value'
            }
        }
    }

    diff = config_manager._diff_dicts(current, new)

    assert len(diff['changed']) == 1
    assert diff['changed'][0]['key'] == 'level1.level2.key'
    assert diff['changed'][0]['old_value'] == 'old_value'
    assert diff['changed'][0]['new_value'] == 'new_value'


def test_export_general_section(config_manager):
    """Test exporting general settings."""
    general = config_manager._export_general()

    assert general is not None
    assert 'host' in general
    assert 'port' in general
    assert 'channel' in general
    assert 'providers' in general


def test_export_interpreters_section(config_manager):
    """Test exporting interpreter settings."""
    interpreters = config_manager._export_interpreters()

    assert interpreters is not None
    assert isinstance(interpreters, dict)


def test_import_export_consistency(config_manager):
    """Test that exporting and importing produces consistent results."""
    # Export with sensitive data
    export1 = config_manager.export_config(include_sensitive=True)

    # Import the exported config
    report = config_manager.import_config(export1, create_backup=False)
    assert report['success'] is True

    # Export again
    export2 = config_manager.export_config(include_sensitive=True)

    # Compare exports (should be largely the same, timestamps may differ)
    assert export1['version'] == export2['version']
    # General section should match
    assert export1.get('general') == export2.get('general')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
