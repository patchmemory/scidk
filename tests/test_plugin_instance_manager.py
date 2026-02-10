"""Tests for Plugin Instance Manager.

Tests the management of user-created plugin instances stored in SQLite.
"""

import pytest
import tempfile
import os
from scidk.core.plugin_instance_manager import PluginInstanceManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def manager(temp_db):
    """Create a plugin instance manager for testing."""
    return PluginInstanceManager(db_path=temp_db)


def test_create_instance(manager):
    """Test creating a plugin instance."""
    instance_id = manager.create_instance(
        template_id='table_loader',
        name='Test Equipment',
        config={'file_path': '/data/test.csv', 'table_name': 'test_equipment'}
    )

    assert instance_id is not None
    instance = manager.get_instance(instance_id)
    assert instance['name'] == 'Test Equipment'
    assert instance['template_id'] == 'table_loader'
    assert instance['config']['file_path'] == '/data/test.csv'
    assert instance['enabled'] is True
    assert instance['status'] == 'pending'


def test_create_duplicate_name_fails(manager):
    """Test that creating instance with duplicate name fails."""
    manager.create_instance(
        template_id='table_loader',
        name='Test Equipment',
        config={}
    )

    with pytest.raises(ValueError, match="already exists"):
        manager.create_instance(
            template_id='table_loader',
            name='Test Equipment',
            config={}
        )


def test_get_instance_by_name(manager):
    """Test retrieving instance by name."""
    manager.create_instance(
        template_id='table_loader',
        name='Test Equipment',
        config={}
    )

    instance = manager.get_instance_by_name('Test Equipment')
    assert instance is not None
    assert instance['name'] == 'Test Equipment'


def test_list_instances(manager):
    """Test listing all instances."""
    manager.create_instance(template_id='table_loader', name='Instance 1', config={})
    manager.create_instance(template_id='table_loader', name='Instance 2', config={})
    manager.create_instance(template_id='api_fetcher', name='Instance 3', config={})

    all_instances = manager.list_instances()
    assert len(all_instances) == 3

    # Filter by template
    table_loader_instances = manager.list_instances(template_id='table_loader')
    assert len(table_loader_instances) == 2


def test_list_enabled_only(manager):
    """Test filtering instances by enabled status."""
    id1 = manager.create_instance(template_id='table_loader', name='Enabled', config={})
    id2 = manager.create_instance(template_id='table_loader', name='Disabled', config={})

    # Disable second instance
    manager.update_instance(id2, enabled=False)

    enabled_instances = manager.list_instances(enabled_only=True)
    assert len(enabled_instances) == 1
    assert enabled_instances[0]['name'] == 'Enabled'


def test_update_instance(manager):
    """Test updating instance fields."""
    instance_id = manager.create_instance(
        template_id='table_loader',
        name='Original Name',
        config={'key': 'value'}
    )

    # Update name
    success = manager.update_instance(instance_id, name='New Name')
    assert success is True

    instance = manager.get_instance(instance_id)
    assert instance['name'] == 'New Name'

    # Update config
    manager.update_instance(instance_id, config={'key': 'new_value', 'new_key': 'data'})
    instance = manager.get_instance(instance_id)
    assert instance['config']['key'] == 'new_value'
    assert instance['config']['new_key'] == 'data'

    # Update enabled status
    manager.update_instance(instance_id, enabled=False)
    instance = manager.get_instance(instance_id)
    assert instance['enabled'] is False
    assert instance['status'] == 'inactive'


def test_delete_instance(manager):
    """Test deleting an instance."""
    instance_id = manager.create_instance(
        template_id='table_loader',
        name='To Delete',
        config={}
    )

    # Verify it exists
    instance = manager.get_instance(instance_id)
    assert instance is not None

    # Delete it
    success = manager.delete_instance(instance_id)
    assert success is True

    # Verify it's gone
    instance = manager.get_instance(instance_id)
    assert instance is None

    # Delete again should return False
    success = manager.delete_instance(instance_id)
    assert success is False


def test_record_execution(manager):
    """Test recording execution results."""
    instance_id = manager.create_instance(
        template_id='table_loader',
        name='Test Instance',
        config={}
    )

    # Record successful execution
    result = {
        'status': 'success',
        'rows_imported': 45,
        'columns': ['name', 'location']
    }
    success = manager.record_execution(instance_id, result, status='active')
    assert success is True

    # Verify recorded
    instance = manager.get_instance(instance_id)
    assert instance['status'] == 'active'
    assert instance['last_run'] is not None
    assert instance['last_result']['rows_imported'] == 45

    # Record failed execution
    error_result = {'error': 'File not found'}
    manager.record_execution(instance_id, error_result, status='error')

    instance = manager.get_instance(instance_id)
    assert instance['status'] == 'error'
    assert instance['last_result']['error'] == 'File not found'


def test_get_stats(manager):
    """Test getting instance statistics."""
    manager.create_instance(template_id='table_loader', name='Instance 1', config={})
    manager.create_instance(template_id='table_loader', name='Instance 2', config={})
    manager.create_instance(template_id='api_fetcher', name='Instance 3', config={})

    # Record some executions
    instances = manager.list_instances()
    manager.record_execution(instances[0]['id'], {}, status='active')
    manager.record_execution(instances[1]['id'], {}, status='error')

    stats = manager.get_stats()

    assert stats['total'] == 3
    assert stats['by_template']['table_loader'] == 2
    assert stats['by_template']['api_fetcher'] == 1
    assert 'active' in stats['by_status']
    assert 'error' in stats['by_status']


def test_instance_timestamps(manager):
    """Test that timestamps are set correctly."""
    import time

    before = time.time()
    instance_id = manager.create_instance(
        template_id='table_loader',
        name='Test Instance',
        config={}
    )
    after = time.time()

    instance = manager.get_instance(instance_id)
    assert before <= instance['created_at'] <= after
    assert before <= instance['updated_at'] <= after
    assert instance['created_at'] == instance['updated_at']

    # Update should change updated_at
    time.sleep(0.1)
    manager.update_instance(instance_id, name='Updated Name')
    instance = manager.get_instance(instance_id)
    assert instance['updated_at'] > instance['created_at']
