"""Plugin settings management.

Provides functionality for plugins to define and store configuration settings.
Settings can be encrypted (for sensitive data like API keys) and are stored in the database.
"""

import json
import sqlite3
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """Get path to settings database."""
    return os.environ.get('SCIDK_DB_PATH', os.path.join(os.getcwd(), 'scidk.db'))


def _encrypt_value(value: str) -> str:
    """Encrypt a sensitive value.

    TODO: Implement proper encryption. For now, this is a placeholder.
    In production, use cryptography library with a proper key management system.

    Args:
        value: Plain text value to encrypt

    Returns:
        Encrypted value (currently just base64 encoded as placeholder)
    """
    import base64
    return base64.b64encode(value.encode()).decode()


def _decrypt_value(encrypted: str) -> str:
    """Decrypt a sensitive value.

    TODO: Implement proper decryption matching _encrypt_value.

    Args:
        encrypted: Encrypted value

    Returns:
        Plain text value
    """
    import base64
    return base64.b64decode(encrypted.encode()).decode()


def get_plugin_setting(plugin_name: str, key: str, default: Any = None) -> Any:
    """Get a plugin setting value.

    Args:
        plugin_name: Name of the plugin
        key: Setting key
        default: Default value if not found

    Returns:
        Setting value (automatically decrypted if encrypted), or default if not found
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT value, encrypted FROM plugin_settings WHERE plugin_name = ? AND key = ?",
            (plugin_name, key)
        )
        row = cur.fetchone()
        conn.close()

        if row is None:
            return default

        value, encrypted = row
        if encrypted:
            value = _decrypt_value(value)

        # Try to parse as JSON for complex types
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    except Exception as e:
        logger.error(f"Error getting plugin setting {plugin_name}.{key}: {e}")
        return default


def set_plugin_setting(plugin_name: str, key: str, value: Any, encrypted: bool = False):
    """Set a plugin setting value.

    Args:
        plugin_name: Name of the plugin
        key: Setting key
        value: Setting value (will be JSON serialized)
        encrypted: Whether to encrypt the value (for sensitive data)
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)

        # Serialize value to JSON
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)

        # Encrypt if needed
        if encrypted and value_str:
            value_str = _encrypt_value(value_str)

        from datetime import timezone
        now = datetime.now(tz=timezone.utc).timestamp()

        conn.execute(
            """
            INSERT OR REPLACE INTO plugin_settings
            (plugin_name, key, value, encrypted, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (plugin_name, key, value_str, 1 if encrypted else 0, now)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Error setting plugin setting {plugin_name}.{key}: {e}")
        raise


def get_all_plugin_settings(plugin_name: str, include_encrypted: bool = True) -> Dict[str, Any]:
    """Get all settings for a plugin.

    Args:
        plugin_name: Name of the plugin
        include_encrypted: Whether to include (decrypted) encrypted settings

    Returns:
        Dict mapping setting keys to values
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT key, value, encrypted FROM plugin_settings WHERE plugin_name = ?",
            (plugin_name,)
        )

        settings = {}
        for key, value, encrypted in cur.fetchall():
            if not include_encrypted and encrypted:
                continue

            if encrypted:
                value = _decrypt_value(value)

            # Try to parse as JSON
            try:
                settings[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                settings[key] = value

        conn.close()
        return settings

    except Exception as e:
        logger.error(f"Error getting plugin settings for {plugin_name}: {e}")
        return {}


def delete_plugin_setting(plugin_name: str, key: str):
    """Delete a plugin setting.

    Args:
        plugin_name: Name of the plugin
        key: Setting key
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "DELETE FROM plugin_settings WHERE plugin_name = ? AND key = ?",
            (plugin_name, key)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Error deleting plugin setting {plugin_name}.{key}: {e}")
        raise


def delete_all_plugin_settings(plugin_name: str):
    """Delete all settings for a plugin.

    Args:
        plugin_name: Name of the plugin
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "DELETE FROM plugin_settings WHERE plugin_name = ?",
            (plugin_name,)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Error deleting plugin settings for {plugin_name}: {e}")
        raise


def validate_settings_against_schema(settings: Dict[str, Any], schema: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate plugin settings against a schema.

    Args:
        settings: Settings dict to validate
        schema: Schema dict defining expected settings

    Returns:
        Tuple of (is_valid, list of error messages)

    Schema format:
        {
            'api_key': {
                'type': 'password',  # text, password, number, boolean, select
                'required': True,
                'description': 'API key for service'
            },
            'endpoint_url': {
                'type': 'text',
                'default': 'https://api.example.com',
                'required': False
            }
        }
    """
    errors = []

    # Check required fields
    for key, field_schema in schema.items():
        if field_schema.get('required', False):
            if key not in settings or settings[key] is None or settings[key] == '':
                errors.append(f"Required field '{key}' is missing")

    # Check field types
    for key, value in settings.items():
        if key not in schema:
            continue

        field_type = schema[key].get('type', 'text')

        if field_type == 'number':
            try:
                float(value)
            except (ValueError, TypeError):
                errors.append(f"Field '{key}' must be a number")

        elif field_type == 'boolean':
            if not isinstance(value, bool) and value not in ['true', 'false', '0', '1']:
                errors.append(f"Field '{key}' must be a boolean")

    return len(errors) == 0, errors


def apply_schema_defaults(settings: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Apply default values from schema to settings.

    Args:
        settings: Current settings dict
        schema: Schema dict with default values

    Returns:
        Settings dict with defaults applied
    """
    result = settings.copy()

    for key, field_schema in schema.items():
        if key not in result and 'default' in field_schema:
            result[key] = field_schema['default']

    return result
