"""Plugin Instance Manager for user-created plugin instances.

Manages plugin instances (user configurations) stored in SQLite. Each instance
is based on a template and contains user-specific configuration.

Example:
    Instance: "iLab Equipment 2024"
    - Template: "table_loader"
    - Config: {file_path: "/data/equipment.xlsx", table_name: "ilab_equipment_2024"}
    - Status: active
    - Last run: 2 hours ago
"""

import sqlite3
import json
import logging
import time
import uuid
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PluginInstanceManager:
    """Manages user-created plugin instances stored in SQLite."""

    def __init__(self, db_path: str = 'scidk_settings.db'):
        """Initialize the plugin instance manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
        logger.info(f"Plugin instance manager initialized (db: {db_path})")

    def _init_db(self):
        """Initialize database schema for plugin instances."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

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
                updated_at REAL NOT NULL
            )
        ''')

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_instance(self, template_id: str, name: str, config: dict) -> str:
        """Create a new plugin instance.

        Args:
            template_id: ID of the template to instantiate
            name: User-friendly name for the instance
            config: Instance configuration (JSON-serializable dict)

        Returns:
            str: The created instance ID

        Raises:
            ValueError: If instance with same name already exists
        """
        # Check for duplicate name
        existing = self.get_instance_by_name(name)
        if existing:
            raise ValueError(f"Instance with name '{name}' already exists")

        instance_id = str(uuid.uuid4())
        now = time.time()

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO plugin_instances
            (id, name, template_id, config, enabled, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, 'pending', ?, ?)
        ''', (instance_id, name, template_id, json.dumps(config), now, now))

        conn.commit()
        conn.close()

        logger.info(f"Created plugin instance: {instance_id} ({name}) using template {template_id}")
        return instance_id

    def get_instance(self, instance_id: str) -> Optional[dict]:
        """Get a plugin instance by ID.

        Args:
            instance_id: The instance ID

        Returns:
            dict: Instance data, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM plugin_instances WHERE id = ?', (instance_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_dict(row)
        return None

    def get_instance_by_name(self, name: str) -> Optional[dict]:
        """Get a plugin instance by name.

        Args:
            name: The instance name

        Returns:
            dict: Instance data, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM plugin_instances WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_dict(row)
        return None

    def list_instances(self, template_id: Optional[str] = None, enabled_only: bool = False) -> List[dict]:
        """List all plugin instances, optionally filtered.

        Args:
            template_id: Optional template ID filter
            enabled_only: If True, only return enabled instances

        Returns:
            List of instance dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM plugin_instances WHERE 1=1'
        params = []

        if template_id:
            query += ' AND template_id = ?'
            params.append(template_id)

        if enabled_only:
            query += ' AND enabled = 1'

        query += ' ORDER BY created_at DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def update_instance(self, instance_id: str, name: Optional[str] = None,
                       config: Optional[dict] = None, enabled: Optional[bool] = None) -> bool:
        """Update a plugin instance.

        Args:
            instance_id: The instance ID
            name: Optional new name
            config: Optional new config
            enabled: Optional new enabled status

        Returns:
            bool: True if updated, False if not found
        """
        instance = self.get_instance(instance_id)
        if not instance:
            return False

        updates = []
        params = []

        if name is not None:
            updates.append('name = ?')
            params.append(name)

        if config is not None:
            updates.append('config = ?')
            params.append(json.dumps(config))

        if enabled is not None:
            updates.append('enabled = ?')
            params.append(1 if enabled else 0)
            updates.append('status = ?')
            params.append('active' if enabled else 'inactive')

        if not updates:
            return True  # Nothing to update

        updates.append('updated_at = ?')
        params.append(time.time())

        params.append(instance_id)

        conn = self._get_connection()
        cursor = conn.cursor()

        query = f"UPDATE plugin_instances SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)

        conn.commit()
        conn.close()

        logger.info(f"Updated plugin instance: {instance_id}")
        return True

    def delete_instance(self, instance_id: str) -> bool:
        """Delete a plugin instance.

        Args:
            instance_id: The instance ID

        Returns:
            bool: True if deleted, False if not found
        """
        instance = self.get_instance(instance_id)
        if not instance:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM plugin_instances WHERE id = ?', (instance_id,))

        conn.commit()
        conn.close()

        logger.info(f"Deleted plugin instance: {instance_id} ({instance['name']})")
        return True

    def record_execution(self, instance_id: str, result: dict, status: str = 'active') -> bool:
        """Record the result of an instance execution.

        Args:
            instance_id: The instance ID
            result: Execution result (JSON-serializable dict)
            status: New status ('active', 'error', etc.)

        Returns:
            bool: True if recorded, False if instance not found
        """
        instance = self.get_instance(instance_id)
        if not instance:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE plugin_instances
            SET last_run = ?, last_result = ?, status = ?, updated_at = ?
            WHERE id = ?
        ''', (time.time(), json.dumps(result), status, time.time(), instance_id))

        conn.commit()
        conn.close()

        logger.info(f"Recorded execution for instance: {instance_id} (status: {status})")
        return True

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a dict.

        Args:
            row: SQLite row object

        Returns:
            dict: Instance data with parsed JSON fields
        """
        result = {
            'id': row['id'],
            'name': row['name'],
            'template_id': row['template_id'],
            'config': json.loads(row['config']) if row['config'] else {},
            'enabled': bool(row['enabled']),
            'status': row['status'],
            'last_run': row['last_run'],
            'last_result': json.loads(row['last_result']) if row['last_result'] else None,
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }

        # Add new columns if they exist
        try:
            result['published_label'] = row['published_label']
            result['graph_config'] = json.loads(row['graph_config']) if row['graph_config'] else None
        except (KeyError, IndexError):
            # Columns don't exist yet (pre-migration)
            result['published_label'] = None
            result['graph_config'] = None

        return result

    def get_stats(self) -> dict:
        """Get statistics about plugin instances.

        Returns:
            dict: Statistics including counts by status, template, etc.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Total count
        cursor.execute('SELECT COUNT(*) as total FROM plugin_instances')
        total = cursor.fetchone()['total']

        # Count by status
        cursor.execute('SELECT status, COUNT(*) as count FROM plugin_instances GROUP BY status')
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}

        # Count by template
        cursor.execute('SELECT template_id, COUNT(*) as count FROM plugin_instances GROUP BY template_id')
        by_template = {row['template_id']: row['count'] for row in cursor.fetchall()}

        conn.close()

        return {
            'total': total,
            'by_status': by_status,
            'by_template': by_template
        }

    def publish_label_schema(self, instance_id: str, label_config: dict, app=None) -> bool:
        """Publish plugin instance schema as a Label.

        Args:
            instance_id: Plugin instance ID
            label_config: {
                "label_name": "LabEquipment",
                "primary_key": "serial_number",
                "property_mapping": {...},  # Optional, auto-generated if missing
                "sync_strategy": "on_demand"
            }
            app: Flask app instance (optional, for LabelService)

        Returns:
            bool: True if published successfully
        """
        instance = self.get_instance(instance_id)
        if not instance:
            logger.error(f"Instance {instance_id} not found")
            return False

        label_name = label_config.get('label_name')
        if not label_name:
            logger.error("Label name is required")
            return False

        primary_key = label_config.get('primary_key', 'id')
        sync_strategy = label_config.get('sync_strategy', 'on_demand')
        property_mapping = label_config.get('property_mapping', {})

        # Auto-generate property schema from SQLite table if not provided
        if not property_mapping:
            config = instance['config']
            table_name = config.get('table_name')
            if table_name:
                property_mapping = self._infer_table_schema(table_name)

        # Convert property_mapping dict to properties list for label service
        properties = []
        for prop_name, prop_info in property_mapping.items():
            properties.append({
                'name': prop_name,
                'type': prop_info.get('type', 'string'),
                'required': prop_info.get('required', False)
            })

        # Create or update label definition
        label_def = {
            'name': label_name,
            'properties': properties,
            'relationships': [],  # No relationships initially
            'source_type': 'plugin_instance',
            'source_id': instance_id,
            'sync_config': {
                'primary_key': primary_key,
                'sync_strategy': sync_strategy,
                'auto_sync': False,
                'last_sync_at': None,
                'last_sync_count': 0
            }
        }

        try:
            # Use LabelService to save label
            if app:
                from ..services.label_service import LabelService
                label_service = LabelService(app)
                label_service.save_label(label_def)
            else:
                # Fallback: direct database save using the same database
                conn = self._get_connection()
                cursor = conn.cursor()

                props_json = json.dumps(properties)
                sync_config_json = json.dumps(label_def['sync_config'])
                now = time.time()

                # Check if label exists
                cursor.execute('SELECT name FROM label_definitions WHERE name = ?', (label_name,))
                exists = cursor.fetchone()

                if exists:
                    cursor.execute('''
                        UPDATE label_definitions
                        SET properties = ?, source_type = ?, source_id = ?,
                            sync_config = ?, updated_at = ?
                        WHERE name = ?
                    ''', (props_json, 'plugin_instance', instance_id, sync_config_json, now, label_name))
                else:
                    cursor.execute('''
                        INSERT INTO label_definitions
                        (name, properties, relationships, source_type, source_id, sync_config, created_at, updated_at)
                        VALUES (?, ?, '[]', ?, ?, ?, ?, ?)
                    ''', (label_name, props_json, 'plugin_instance', instance_id, sync_config_json, now, now))

                conn.commit()
                conn.close()

            # Update instance with published label
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE plugin_instances
                SET published_label = ?, graph_config = ?, updated_at = ?
                WHERE id = ?
            ''', (label_name, json.dumps(label_config), time.time(), instance_id))
            conn.commit()
            conn.close()

            logger.info(f"Published label '{label_name}' from instance {instance_id}")
            return True

        except Exception as e:
            logger.error(f"Error publishing label: {e}", exc_info=True)
            return False

    def _infer_table_schema(self, table_name: str) -> dict:
        """Infer property schema from SQLite table structure.

        Args:
            table_name: SQLite table name

        Returns:
            dict: Property mapping {column_name: {type, required}}
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()

            property_mapping = {}
            for col in columns:
                col_name = col[1] if isinstance(col, tuple) else col['name']
                col_type = (col[2] if isinstance(col, tuple) else col['type']).lower()
                not_null = col[3] if isinstance(col, tuple) else col['notnull']

                # Map SQLite types to schema types
                if 'int' in col_type:
                    prop_type = 'integer'
                elif 'real' in col_type or 'float' in col_type or 'double' in col_type:
                    prop_type = 'number'
                elif 'bool' in col_type:
                    prop_type = 'boolean'
                else:
                    prop_type = 'string'

                property_mapping[col_name] = {
                    'type': prop_type,
                    'required': bool(not_null)
                }

            return property_mapping

        except Exception as e:
            logger.error(f"Error inferring schema for table {table_name}: {e}")
            return {}
        finally:
            conn.close()
