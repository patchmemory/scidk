"""Tests for plugin label publishing functionality."""

import pytest
import sqlite3
import json
import tempfile
import os
from scidk.core.plugin_instance_manager import PluginInstanceManager
from scidk.services.label_service import LabelService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing with migrations."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # Create connection and apply migrations including label_definitions with new columns
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    # Create label_definitions table with all columns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS label_definitions (
            name TEXT PRIMARY KEY,
            properties TEXT,
            relationships TEXT,
            created_at REAL,
            updated_at REAL,
            source_type TEXT DEFAULT 'manual',
            source_id TEXT,
            sync_config TEXT
        )
    ''')

    # Create plugin_instances table with new columns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plugin_instances (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            template_id TEXT NOT NULL,
            config TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            status TEXT,
            last_run REAL,
            last_result TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            published_label TEXT,
            graph_config TEXT
        )
    ''')

    conn.commit()
    conn.close()

    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def instance_manager(temp_db):
    """Create a plugin instance manager with temporary database."""
    return PluginInstanceManager(db_path=temp_db)


@pytest.fixture
def sample_table(temp_db):
    """Create a sample table for testing schema inference."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE test_equipment (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            count INTEGER,
            active BOOLEAN,
            price REAL
        )
    ''')

    # Insert some test data
    cursor.execute('''
        INSERT INTO test_equipment (name, serial_number, count, active, price)
        VALUES ('Microscope', 'SN001', 5, 1, 1500.50)
    ''')

    conn.commit()
    conn.close()
    return 'test_equipment'


class TestSchemaInference:
    """Test schema inference from SQLite tables."""

    def test_infer_table_schema(self, instance_manager, sample_table):
        """Test inferring schema from a SQLite table."""
        schema = instance_manager._infer_table_schema(sample_table)

        # Check that all columns are present
        assert 'id' in schema
        assert 'name' in schema
        assert 'serial_number' in schema
        assert 'count' in schema
        assert 'active' in schema
        assert 'price' in schema

        # Check types are correctly mapped
        assert schema['id']['type'] == 'integer'
        assert schema['name']['type'] == 'string'
        assert schema['serial_number']['type'] == 'string'
        assert schema['count']['type'] == 'integer'
        assert schema['active']['type'] == 'boolean'
        assert schema['price']['type'] == 'number'

        # Check required fields
        # Note: PRIMARY KEY doesn't set notnull=1 in SQLite PRAGMA, so id won't be required
        # but explicitly NOT NULL columns will be
        assert schema['name']['required'] is True
        assert schema['serial_number']['required'] is True
        assert schema['count']['required'] is False

    def test_infer_nonexistent_table(self, instance_manager):
        """Test inferring schema from a non-existent table returns empty dict."""
        schema = instance_manager._infer_table_schema('nonexistent_table')
        assert schema == {}


class TestLabelPublishing:
    """Test publishing labels from plugin instances."""

    def test_publish_label_with_explicit_schema(self, instance_manager):
        """Test publishing a label with explicit property mapping."""
        # Create a plugin instance
        instance_id = instance_manager.create_instance(
            template_id='table_loader',
            name='Test Equipment Loader',
            config={'table_name': 'test_equipment', 'file_path': '/test.csv'}
        )

        # Publish label with explicit schema
        label_config = {
            'label_name': 'TestEquipment',
            'primary_key': 'serial_number',
            'property_mapping': {
                'id': {'type': 'integer', 'required': True},
                'name': {'type': 'string', 'required': True},
                'serial_number': {'type': 'string', 'required': True}
            },
            'sync_strategy': 'on_demand'
        }

        success = instance_manager.publish_label_schema(instance_id, label_config)
        assert success is True

        # Verify instance was updated
        instance = instance_manager.get_instance(instance_id)
        assert instance['published_label'] == 'TestEquipment'
        assert instance['graph_config'] is not None
        assert instance['graph_config']['label_name'] == 'TestEquipment'

    def test_publish_label_with_auto_schema(self, instance_manager, sample_table):
        """Test publishing a label with auto-generated schema."""
        # Create a plugin instance
        instance_id = instance_manager.create_instance(
            template_id='table_loader',
            name='Test Equipment Loader',
            config={'table_name': sample_table, 'file_path': '/test.csv'}
        )

        # Publish label without explicit schema (should auto-generate)
        label_config = {
            'label_name': 'AutoEquipment',
            'primary_key': 'id'
        }

        success = instance_manager.publish_label_schema(instance_id, label_config)
        assert success is True

        # Verify instance was updated
        instance = instance_manager.get_instance(instance_id)
        assert instance['published_label'] == 'AutoEquipment'

    def test_publish_label_invalid_instance(self, instance_manager):
        """Test publishing label for non-existent instance fails."""
        label_config = {
            'label_name': 'TestLabel',
            'primary_key': 'id'
        }

        success = instance_manager.publish_label_schema('invalid-id', label_config)
        assert success is False

    def test_publish_label_missing_name(self, instance_manager):
        """Test publishing label without name fails."""
        instance_id = instance_manager.create_instance(
            template_id='table_loader',
            name='Test Loader',
            config={'table_name': 'test', 'file_path': '/test.csv'}
        )

        label_config = {
            'primary_key': 'id'
            # Missing label_name
        }

        success = instance_manager.publish_label_schema(instance_id, label_config)
        assert success is False

    def test_publish_label_updates_existing(self, instance_manager, sample_table):
        """Test publishing label updates existing label definition."""
        instance_id = instance_manager.create_instance(
            template_id='table_loader',
            name='Test Equipment Loader',
            config={'table_name': sample_table, 'file_path': '/test.csv'}
        )

        # First publish
        label_config1 = {
            'label_name': 'Equipment',
            'primary_key': 'id',
            'property_mapping': {
                'id': {'type': 'integer', 'required': True},
                'name': {'type': 'string', 'required': True}
            }
        }

        success1 = instance_manager.publish_label_schema(instance_id, label_config1)
        assert success1 is True

        # Second publish with updated schema
        label_config2 = {
            'label_name': 'Equipment',
            'primary_key': 'serial_number',  # Different primary key
            'property_mapping': {
                'id': {'type': 'integer', 'required': True},
                'name': {'type': 'string', 'required': True},
                'serial_number': {'type': 'string', 'required': True}  # New property
            }
        }

        success2 = instance_manager.publish_label_schema(instance_id, label_config2)
        assert success2 is True


class TestPluginInstanceColumns:
    """Test new columns in plugin_instances table."""

    def test_new_columns_in_instance_dict(self, instance_manager):
        """Test that new columns are included in instance dict."""
        instance_id = instance_manager.create_instance(
            template_id='table_loader',
            name='Test Instance',
            config={'table_name': 'test', 'file_path': '/test.csv'}
        )

        instance = instance_manager.get_instance(instance_id)

        # New columns should be present (may be None)
        assert 'published_label' in instance
        assert 'graph_config' in instance

    def test_published_label_persists(self, instance_manager):
        """Test that published_label is persisted correctly."""
        instance_id = instance_manager.create_instance(
            template_id='table_loader',
            name='Test Instance',
            config={'table_name': 'test', 'file_path': '/test.csv'}
        )

        label_config = {
            'label_name': 'TestLabel',
            'primary_key': 'id',
            'property_mapping': {
                'id': {'type': 'integer', 'required': True}
            }
        }

        instance_manager.publish_label_schema(instance_id, label_config)

        # Retrieve instance again
        instance = instance_manager.get_instance(instance_id)
        assert instance['published_label'] == 'TestLabel'
        assert instance['graph_config']['label_name'] == 'TestLabel'
