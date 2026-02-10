"""Tests for plugin settings framework."""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime

from scidk.core.plugin_settings import (
    get_plugin_setting,
    set_plugin_setting,
    get_all_plugin_settings,
    delete_plugin_setting,
    delete_all_plugin_settings,
    validate_settings_against_schema,
    apply_schema_defaults,
    _encrypt_value,
    _decrypt_value
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Set environment variable for tests
    old_path = os.environ.get('SCIDK_DB_PATH')
    os.environ['SCIDK_DB_PATH'] = db_path

    # Initialize database with migrations
    from scidk.core.migrations import migrate
    conn = sqlite3.connect(db_path)
    migrate(conn)
    conn.close()

    yield db_path

    # Cleanup
    if old_path:
        os.environ['SCIDK_DB_PATH'] = old_path
    else:
        del os.environ['SCIDK_DB_PATH']

    try:
        os.unlink(db_path)
    except Exception:
        pass


def test_set_and_get_plugin_setting(temp_db):
    """Test setting and getting a plugin setting."""
    set_plugin_setting('test_plugin', 'api_key', 'secret123')
    value = get_plugin_setting('test_plugin', 'api_key')
    assert value == 'secret123'


def test_get_plugin_setting_default(temp_db):
    """Test getting a plugin setting with default value."""
    value = get_plugin_setting('nonexistent_plugin', 'key', default='default_value')
    assert value == 'default_value'


def test_set_plugin_setting_encrypted(temp_db):
    """Test setting an encrypted plugin setting."""
    set_plugin_setting('test_plugin', 'password', 'secret_password', encrypted=True)

    # Get directly from database to verify it's encrypted
    conn = sqlite3.connect(temp_db)
    cur = conn.execute(
        "SELECT value, encrypted FROM plugin_settings WHERE plugin_name = ? AND key = ?",
        ('test_plugin', 'password')
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[1] == 1  # encrypted flag
    assert row[0] != 'secret_password'  # value is encrypted

    # But get_plugin_setting should decrypt it
    value = get_plugin_setting('test_plugin', 'password')
    assert value == 'secret_password'


def test_set_plugin_setting_complex_types(temp_db):
    """Test setting complex types (dict, list)."""
    # Test dict
    set_plugin_setting('test_plugin', 'config', {'key1': 'value1', 'key2': 'value2'})
    value = get_plugin_setting('test_plugin', 'config')
    assert value == {'key1': 'value1', 'key2': 'value2'}

    # Test list
    set_plugin_setting('test_plugin', 'items', ['item1', 'item2', 'item3'])
    value = get_plugin_setting('test_plugin', 'items')
    assert value == ['item1', 'item2', 'item3']


def test_get_all_plugin_settings(temp_db):
    """Test getting all settings for a plugin."""
    set_plugin_setting('test_plugin', 'key1', 'value1')
    set_plugin_setting('test_plugin', 'key2', 'value2')
    set_plugin_setting('test_plugin', 'key3', 'value3')

    settings = get_all_plugin_settings('test_plugin')

    assert len(settings) == 3
    assert settings['key1'] == 'value1'
    assert settings['key2'] == 'value2'
    assert settings['key3'] == 'value3'


def test_get_all_plugin_settings_with_encrypted(temp_db):
    """Test getting all settings including encrypted ones."""
    set_plugin_setting('test_plugin', 'public_key', 'public_value')
    set_plugin_setting('test_plugin', 'secret_key', 'secret_value', encrypted=True)

    # Include encrypted
    settings = get_all_plugin_settings('test_plugin', include_encrypted=True)
    assert len(settings) == 2
    assert settings['public_key'] == 'public_value'
    assert settings['secret_key'] == 'secret_value'

    # Exclude encrypted
    settings = get_all_plugin_settings('test_plugin', include_encrypted=False)
    assert len(settings) == 1
    assert settings['public_key'] == 'public_value'
    assert 'secret_key' not in settings


def test_delete_plugin_setting(temp_db):
    """Test deleting a plugin setting."""
    set_plugin_setting('test_plugin', 'key1', 'value1')
    set_plugin_setting('test_plugin', 'key2', 'value2')

    delete_plugin_setting('test_plugin', 'key1')

    assert get_plugin_setting('test_plugin', 'key1') is None
    assert get_plugin_setting('test_plugin', 'key2') == 'value2'


def test_delete_all_plugin_settings(temp_db):
    """Test deleting all settings for a plugin."""
    set_plugin_setting('test_plugin', 'key1', 'value1')
    set_plugin_setting('test_plugin', 'key2', 'value2')
    set_plugin_setting('other_plugin', 'key3', 'value3')

    delete_all_plugin_settings('test_plugin')

    assert len(get_all_plugin_settings('test_plugin')) == 0
    assert len(get_all_plugin_settings('other_plugin')) == 1


def test_validate_settings_against_schema():
    """Test validating settings against a schema."""
    schema = {
        'required_field': {
            'type': 'text',
            'required': True
        },
        'optional_field': {
            'type': 'text',
            'required': False
        },
        'number_field': {
            'type': 'number',
            'required': False
        }
    }

    # Valid settings
    settings = {
        'required_field': 'value',
        'number_field': 42
    }
    is_valid, errors = validate_settings_against_schema(settings, schema)
    assert is_valid
    assert len(errors) == 0

    # Missing required field
    settings = {
        'optional_field': 'value'
    }
    is_valid, errors = validate_settings_against_schema(settings, schema)
    assert not is_valid
    assert len(errors) > 0
    assert any('required_field' in err for err in errors)

    # Invalid type
    settings = {
        'required_field': 'value',
        'number_field': 'not_a_number'
    }
    is_valid, errors = validate_settings_against_schema(settings, schema)
    assert not is_valid
    assert any('number_field' in err for err in errors)


def test_apply_schema_defaults():
    """Test applying default values from schema."""
    schema = {
        'field1': {
            'type': 'text',
            'default': 'default_value1'
        },
        'field2': {
            'type': 'number',
            'default': 42
        },
        'field3': {
            'type': 'boolean',
            'default': True
        }
    }

    # Settings with some fields
    settings = {
        'field1': 'custom_value'
    }

    result = apply_schema_defaults(settings, schema)

    assert result['field1'] == 'custom_value'  # Not overwritten
    assert result['field2'] == 42  # Default applied
    assert result['field3'] is True  # Default applied


def test_encrypt_decrypt():
    """Test encryption and decryption."""
    original = "secret_value"
    encrypted = _encrypt_value(original)

    # Should be different from original
    assert encrypted != original

    # Should decrypt back to original
    decrypted = _decrypt_value(encrypted)
    assert decrypted == original


def test_setting_update_timestamp(temp_db):
    """Test that updated_at timestamp is set correctly."""
    before = datetime.utcnow().timestamp()
    set_plugin_setting('test_plugin', 'key', 'value')
    after = datetime.utcnow().timestamp()

    # Check timestamp in database
    conn = sqlite3.connect(temp_db)
    cur = conn.execute(
        "SELECT updated_at FROM plugin_settings WHERE plugin_name = ? AND key = ?",
        ('test_plugin', 'key')
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None
    timestamp = row[0]
    assert before <= timestamp <= after


def test_multiple_plugins_isolation(temp_db):
    """Test that settings for different plugins are isolated."""
    set_plugin_setting('plugin1', 'key1', 'value1')
    set_plugin_setting('plugin2', 'key1', 'value2')

    assert get_plugin_setting('plugin1', 'key1') == 'value1'
    assert get_plugin_setting('plugin2', 'key1') == 'value2'

    delete_all_plugin_settings('plugin1')

    assert get_plugin_setting('plugin1', 'key1') is None
    assert get_plugin_setting('plugin2', 'key1') == 'value2'


def test_setting_overwrite(temp_db):
    """Test that setting a value twice overwrites the first value."""
    set_plugin_setting('test_plugin', 'key', 'value1')
    set_plugin_setting('test_plugin', 'key', 'value2')

    value = get_plugin_setting('test_plugin', 'key')
    assert value == 'value2'

    # Check there's only one row in the database
    conn = sqlite3.connect(temp_db)
    cur = conn.execute(
        "SELECT COUNT(*) FROM plugin_settings WHERE plugin_name = ? AND key = ?",
        ('test_plugin', 'key')
    )
    count = cur.fetchone()[0]
    conn.close()

    assert count == 1
