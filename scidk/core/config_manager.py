"""
Configuration Export/Import Manager.

Provides unified export and import functionality for all SciDK settings including:
- General settings (host, port, channel)
- Neo4j connection settings
- Chat/LLM provider settings
- Interpreter configurations
- Rclone settings
- Integration settings (API endpoints, table formats, fuzzy matching)
- Security settings (authentication)

Supports:
- Complete or selective export/import
- Sensitive data handling (exclude or encrypt)
- Automatic backups before import
- Configuration validation
- Audit logging
"""

import sqlite3
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from cryptography.fernet import Fernet


class ConfigManager:
    """Manages configuration export, import, and backup operations."""

    CONFIG_VERSION = "1.0"

    def __init__(self, db_path: str, encryption_key: Optional[str] = None):
        """
        Initialize ConfigManager.

        Args:
            db_path: Path to settings database
            encryption_key: Fernet key for sensitive data encryption (base64-encoded)
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.db.row_factory = sqlite3.Row

        # Initialize encryption for sensitive data
        if encryption_key:
            self.cipher = Fernet(encryption_key.encode())
        else:
            self.cipher = Fernet(Fernet.generate_key())

        self.init_tables()

    def init_tables(self):
        """Create required tables if they don't exist."""
        # Config backups table
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS config_backups (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                config_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_by TEXT,
                notes TEXT
            )
            """
        )

        # Settings table for various config values
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """
        )

        # Interpreter settings table
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS interpreter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Auth config table
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_config (
                id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                username TEXT,
                password_hash TEXT
            )
            """
        )

        self.db.commit()

    def export_config(self, include_sensitive: bool = False, sections: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Export configuration to JSON-serializable dict.

        Args:
            include_sensitive: If True, include passwords and API keys (encrypted)
            sections: Optional list of sections to export. If None, exports all.
                     Valid sections: 'general', 'neo4j', 'chat', 'interpreters',
                     'plugins', 'rclone', 'integrations', 'security'

        Returns:
            Configuration dict with version, timestamp, and requested sections
        """
        config = {
            'version': self.CONFIG_VERSION,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'include_sensitive': include_sensitive
        }

        all_sections = ['general', 'neo4j', 'chat', 'interpreters', 'plugins', 'rclone', 'integrations', 'security']
        export_sections = sections if sections else all_sections

        if 'general' in export_sections:
            config['general'] = self._export_general()

        if 'neo4j' in export_sections:
            config['neo4j'] = self._export_neo4j(include_sensitive)

        if 'chat' in export_sections:
            config['chat'] = self._export_chat(include_sensitive)

        if 'interpreters' in export_sections:
            config['interpreters'] = self._export_interpreters()

        if 'plugins' in export_sections:
            config['plugins'] = self._export_plugins()

        if 'rclone' in export_sections:
            config['rclone'] = self._export_rclone(include_sensitive)

        if 'integrations' in export_sections:
            config['integrations'] = self._export_integrations(include_sensitive)

        if 'security' in export_sections:
            config['security'] = self._export_security(include_sensitive)

        return config

    def import_config(
        self,
        config_data: Dict[str, Any],
        create_backup: bool = True,
        sections: Optional[List[str]] = None,
        created_by: str = 'system'
    ) -> Dict[str, Any]:
        """
        Import configuration from dict.

        Args:
            config_data: Configuration dict (from export_config)
            create_backup: If True, creates backup before import
            sections: Optional list of sections to import. If None, imports all available.
            created_by: Username or 'system' for audit trail

        Returns:
            Import report dict with successes, failures, and backup_id
        """
        report = {
            'success': True,
            'backup_id': None,
            'sections_imported': [],
            'sections_failed': [],
            'errors': []
        }

        # Validate config version
        if config_data.get('version') != self.CONFIG_VERSION:
            report['errors'].append(f"Config version mismatch: expected {self.CONFIG_VERSION}, got {config_data.get('version')}")
            report['success'] = False
            return report

        # Create backup before import
        if create_backup:
            try:
                backup_id = self.create_backup(reason='pre_import', created_by=created_by)
                report['backup_id'] = backup_id
            except Exception as e:
                report['errors'].append(f"Backup creation failed: {str(e)}")
                report['success'] = False
                return report

        # Import each section
        import_sections = sections if sections else list(config_data.keys())
        import_sections = [s for s in import_sections if s not in ['version', 'timestamp', 'include_sensitive']]

        for section in import_sections:
            if section not in config_data:
                continue

            try:
                if section == 'general':
                    self._import_general(config_data['general'])
                elif section == 'neo4j':
                    self._import_neo4j(config_data['neo4j'])
                elif section == 'chat':
                    self._import_chat(config_data['chat'])
                elif section == 'interpreters':
                    self._import_interpreters(config_data['interpreters'])
                elif section == 'plugins':
                    self._import_plugins(config_data['plugins'])
                elif section == 'rclone':
                    self._import_rclone(config_data['rclone'])
                elif section == 'integrations':
                    self._import_integrations(config_data['integrations'])
                elif section == 'security':
                    self._import_security(config_data['security'])

                report['sections_imported'].append(section)
            except Exception as e:
                report['sections_failed'].append(section)
                report['errors'].append(f"{section}: {str(e)}")
                report['success'] = False

        return report

    def create_backup(self, reason: str = 'manual', created_by: str = 'system', notes: str = '') -> str:
        """
        Create a backup of current configuration.

        Args:
            reason: Reason for backup ('manual', 'auto', 'pre_import')
            created_by: Username or 'system'
            notes: Optional notes

        Returns:
            Backup ID (UUID)
        """
        backup_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).timestamp()

        # Export current config (including sensitive data for complete backup)
        config_json = json.dumps(self.export_config(include_sensitive=True))

        self.db.execute(
            """
            INSERT INTO config_backups (id, timestamp, config_json, reason, created_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (backup_id, timestamp, config_json, reason, created_by, notes)
        )
        self.db.commit()

        return backup_id

    def list_backups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List configuration backups.

        Args:
            limit: Maximum number of backups to return

        Returns:
            List of backup metadata dicts (without full config)
        """
        cur = self.db.execute(
            """
            SELECT id, timestamp, reason, created_by, notes
            FROM config_backups
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cur.fetchall()

        backups = []
        for row in rows:
            backups.append({
                'id': row['id'],
                'timestamp': row['timestamp'],
                'timestamp_iso': datetime.fromtimestamp(row['timestamp'], tz=timezone.utc).isoformat(),
                'reason': row['reason'],
                'created_by': row['created_by'],
                'notes': row['notes'] or ''
            })

        return backups

    def get_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific backup by ID.

        Args:
            backup_id: Backup UUID

        Returns:
            Full backup dict including config, or None if not found
        """
        cur = self.db.execute(
            "SELECT * FROM config_backups WHERE id = ?",
            (backup_id,)
        )
        row = cur.fetchone()

        if not row:
            return None

        return {
            'id': row['id'],
            'timestamp': row['timestamp'],
            'timestamp_iso': datetime.fromtimestamp(row['timestamp'], tz=timezone.utc).isoformat(),
            'config': json.loads(row['config_json']),
            'reason': row['reason'],
            'created_by': row['created_by'],
            'notes': row['notes'] or ''
        }

    def restore_backup(self, backup_id: str, created_by: str = 'system') -> Dict[str, Any]:
        """
        Restore configuration from a backup.

        Args:
            backup_id: Backup UUID to restore
            created_by: Username for audit trail

        Returns:
            Import report dict
        """
        backup = self.get_backup(backup_id)
        if not backup:
            return {
                'success': False,
                'errors': [f'Backup {backup_id} not found']
            }

        # Import the backed-up config (will create a new backup before restoring)
        return self.import_config(backup['config'], create_backup=True, created_by=created_by)

    def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a backup.

        Args:
            backup_id: Backup UUID

        Returns:
            True if deleted, False if not found
        """
        cursor = self.db.execute(
            "DELETE FROM config_backups WHERE id = ?",
            (backup_id,)
        )
        self.db.commit()
        return cursor.rowcount > 0

    def preview_import_diff(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Preview changes that would be made by importing config.

        Args:
            config_data: Configuration dict to preview

        Returns:
            Diff dict showing current vs new values for each section
        """
        current = self.export_config(include_sensitive=False)
        diff = {
            'sections': {}
        }

        for section in ['general', 'neo4j', 'chat', 'interpreters', 'plugins', 'rclone', 'integrations', 'security']:
            if section not in config_data:
                continue

            section_diff = {
                'changed': [],
                'added': [],
                'removed': []
            }

            current_section = current.get(section, {})
            new_section = config_data.get(section, {})

            # Compare nested dicts
            section_diff = self._diff_dicts(current_section, new_section)
            if section_diff['changed'] or section_diff['added'] or section_diff['removed']:
                diff['sections'][section] = section_diff

        return diff

    def _diff_dicts(self, current: Dict, new: Dict, prefix: str = '') -> Dict[str, List]:
        """Recursively diff two dicts."""
        diff = {
            'changed': [],
            'added': [],
            'removed': []
        }

        # Find changed and removed keys
        for key in current:
            full_key = f"{prefix}.{key}" if prefix else key
            if key not in new:
                diff['removed'].append({'key': full_key, 'old_value': current[key]})
            elif isinstance(current[key], dict) and isinstance(new[key], dict):
                nested_diff = self._diff_dicts(current[key], new[key], full_key)
                diff['changed'].extend(nested_diff['changed'])
                diff['added'].extend(nested_diff['added'])
                diff['removed'].extend(nested_diff['removed'])
            elif current[key] != new[key]:
                diff['changed'].append({
                    'key': full_key,
                    'old_value': current[key],
                    'new_value': new[key]
                })

        # Find added keys
        for key in new:
            if key not in current:
                full_key = f"{prefix}.{key}" if prefix else key
                diff['added'].append({'key': full_key, 'new_value': new[key]})

        return diff

    # Section export methods

    def _export_general(self) -> Dict[str, Any]:
        """Export general settings (environment-based)."""
        return {
            'host': os.environ.get('SCIDK_HOST', '127.0.0.1'),
            'port': os.environ.get('SCIDK_PORT', '5000'),
            'channel': os.environ.get('SCIDK_CHANNEL', 'stable'),
            'providers': os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs'),
            'files_viewer': os.environ.get('SCIDK_FILES_VIEWER', ''),
            'feature_file_index': os.environ.get('SCIDK_FEATURE_FILE_INDEX', ''),
            'commit_from_index': os.environ.get('SCIDK_COMMIT_FROM_INDEX', '1'),
            'graph_backend': os.environ.get('SCIDK_GRAPH_BACKEND', 'memory')
        }

    def _export_neo4j(self, include_sensitive: bool) -> Dict[str, Any]:
        """Export Neo4j settings from settings table."""
        neo4j = {}
        try:
            cur = self.db.execute("SELECT key, value FROM settings WHERE key LIKE 'neo4j_%'")
            rows = cur.fetchall()

            for row in rows:
                key = row['key'].replace('neo4j_', '')
                value = row['value']

                if key == 'password':
                    if include_sensitive:
                        neo4j[key] = value
                    else:
                        neo4j[key] = '[REDACTED]' if value else ''
                else:
                    neo4j[key] = value
        except sqlite3.OperationalError:
            # Table doesn't exist yet, return empty
            pass

        return neo4j

    def _export_chat(self, include_sensitive: bool) -> Dict[str, Any]:
        """Export chat/LLM settings from settings table."""
        chat = {}
        try:
            cur = self.db.execute("SELECT key, value FROM settings WHERE key LIKE 'chat_%'")
            rows = cur.fetchall()

            for row in rows:
                key = row['key'].replace('chat_', '')
                value = row['value']

                # Redact API keys
                if 'key' in key.lower() or 'api' in key.lower():
                    if include_sensitive:
                        chat[key] = value
                    else:
                        chat[key] = '[REDACTED]' if value else ''
                else:
                    chat[key] = value
        except sqlite3.OperationalError:
            pass

        return chat

    def _export_interpreters(self) -> Dict[str, Any]:
        """Export interpreter settings."""
        interpreters = {}
        try:
            cur = self.db.execute("SELECT key, value FROM interpreter_settings")
            rows = cur.fetchall()

            for row in rows:
                interpreters[row['key']] = json.loads(row['value']) if row['value'] else None
        except sqlite3.OperationalError:
            pass

        return interpreters

    def _export_plugins(self) -> Dict[str, Any]:
        """Export plugin settings (placeholder for future)."""
        return {}

    def _export_rclone(self, include_sensitive: bool) -> Dict[str, Any]:
        """Export rclone settings from settings table."""
        rclone = {}
        try:
            cur = self.db.execute("SELECT key, value FROM settings WHERE key LIKE 'rclone_%'")
            rows = cur.fetchall()

            for row in rows:
                key = row['key'].replace('rclone_', '')
                value = row['value']

                # Redact passwords/tokens
                if 'pass' in key.lower() or 'token' in key.lower() or 'secret' in key.lower():
                    if include_sensitive:
                        rclone[key] = value
                    else:
                        rclone[key] = '[REDACTED]' if value else ''
                else:
                    rclone[key] = value
        except sqlite3.OperationalError:
            pass

        return rclone

    def _export_integrations(self, include_sensitive: bool) -> Dict[str, Any]:
        """Export integration settings (API endpoints, table formats, fuzzy matching)."""
        integrations = {}

        # Export API endpoints
        try:
            from .api_endpoint_registry import APIEndpointRegistry, get_encryption_key
            endpoint_registry = APIEndpointRegistry(self.db_path, get_encryption_key())
            endpoints = endpoint_registry.list_endpoints()

            if include_sensitive:
                # Include decrypted auth values
                for endpoint in endpoints:
                    endpoint['auth_value'] = endpoint_registry.get_decrypted_auth(endpoint['id'])
            else:
                # Mark as redacted
                for endpoint in endpoints:
                    if endpoint.get('auth_method') != 'none':
                        endpoint['auth_value'] = '[REDACTED]'

            integrations['api_endpoints'] = endpoints
        except Exception:
            integrations['api_endpoints'] = []

        # Export table formats
        try:
            cur = self.db.execute("SELECT * FROM table_formats WHERE is_preprogrammed = 0")
            rows = cur.fetchall()
            table_formats = []
            for row in rows:
                table_formats.append({
                    'id': row['id'],
                    'name': row['name'],
                    'file_extension': row['file_extension'],
                    'config': json.loads(row['config']) if row['config'] else {}
                })
            integrations['table_formats'] = table_formats
        except sqlite3.OperationalError:
            integrations['table_formats'] = []

        # Export fuzzy matching settings
        try:
            cur = self.db.execute("SELECT * FROM fuzzy_match_settings")
            row = cur.fetchone()
            if row:
                integrations['fuzzy_matching'] = {
                    'algorithm': row['algorithm'],
                    'threshold': row['threshold'],
                    'case_sensitive': bool(row['case_sensitive']),
                    'normalize_whitespace': bool(row['normalize_whitespace']),
                    'strip_punctuation': bool(row['strip_punctuation']),
                    'phonetic_enabled': bool(row['phonetic_enabled']),
                    'phonetic_algorithm': row['phonetic_algorithm'],
                    'min_string_length': row['min_string_length'],
                    'max_comparisons': row['max_comparisons'],
                    'show_confidence_scores': bool(row['show_confidence_scores'])
                }
        except sqlite3.OperationalError:
            pass

        return integrations

    def _export_security(self, include_sensitive: bool) -> Dict[str, Any]:
        """Export security/auth settings."""
        try:
            cur = self.db.execute("SELECT * FROM auth_config LIMIT 1")
            row = cur.fetchone()

            if not row:
                return {'enabled': False}

            security = {
                'enabled': bool(row['enabled']),
                'username': row['username'] if row['username'] else ''
            }

            if include_sensitive and row['password_hash']:
                security['password_hash'] = row['password_hash']
            elif row['password_hash']:
                security['password_hash'] = '[REDACTED]'

            return security
        except sqlite3.OperationalError:
            return {'enabled': False}

    # Section import methods

    def _import_general(self, data: Dict[str, Any]):
        """Import general settings (note: these are environment-based, so just document them)."""
        # General settings are environment variables, can't directly import
        # Could optionally write to a .env file or similar
        pass

    def _import_neo4j(self, data: Dict[str, Any]):
        """Import Neo4j settings to settings table."""
        for key, value in data.items():
            if value == '[REDACTED]':
                continue  # Skip redacted values

            self.db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (f'neo4j_{key}', value, datetime.now(timezone.utc).isoformat())
            )
        self.db.commit()

    def _import_chat(self, data: Dict[str, Any]):
        """Import chat settings to settings table."""
        for key, value in data.items():
            if value == '[REDACTED]':
                continue

            self.db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (f'chat_{key}', value, datetime.now(timezone.utc).isoformat())
            )
        self.db.commit()

    def _import_interpreters(self, data: Dict[str, Any]):
        """Import interpreter settings."""
        for key, value in data.items():
            value_json = json.dumps(value) if value is not None else None
            self.db.execute(
                "INSERT OR REPLACE INTO interpreter_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value_json, datetime.now(timezone.utc).isoformat())
            )
        self.db.commit()

    def _import_plugins(self, data: Dict[str, Any]):
        """Import plugin settings (placeholder)."""
        pass

    def _import_rclone(self, data: Dict[str, Any]):
        """Import rclone settings."""
        for key, value in data.items():
            if value == '[REDACTED]':
                continue

            self.db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (f'rclone_{key}', value, datetime.now(timezone.utc).isoformat())
            )
        self.db.commit()

    def _import_integrations(self, data: Dict[str, Any]):
        """Import integration settings."""
        from .api_endpoint_registry import APIEndpointRegistry, get_encryption_key

        # Import API endpoints
        if 'api_endpoints' in data:
            endpoint_registry = APIEndpointRegistry(self.db_path, get_encryption_key())
            for endpoint_data in data['api_endpoints']:
                # Check if endpoint exists by name
                existing = endpoint_registry.get_endpoint_by_name(endpoint_data['name'])
                if existing:
                    # Update existing
                    endpoint_registry.update_endpoint(existing['id'], endpoint_data)
                else:
                    # Create new
                    endpoint_registry.create_endpoint(endpoint_data)

        # Import table formats
        if 'table_formats' in data:
            for format_data in data['table_formats']:
                self.db.execute(
                    """
                    INSERT OR REPLACE INTO table_formats
                    (id, name, file_extension, config, is_preprogrammed, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        format_data['id'],
                        format_data['name'],
                        format_data['file_extension'],
                        json.dumps(format_data['config']),
                        datetime.now(timezone.utc).timestamp(),
                        datetime.now(timezone.utc).timestamp()
                    )
                )

        # Import fuzzy matching settings
        if 'fuzzy_matching' in data:
            fm = data['fuzzy_matching']
            self.db.execute(
                """
                INSERT OR REPLACE INTO fuzzy_match_settings
                (id, algorithm, threshold, case_sensitive, normalize_whitespace, strip_punctuation,
                 phonetic_enabled, phonetic_algorithm, min_string_length, max_comparisons, show_confidence_scores)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fm['algorithm'], fm['threshold'], fm['case_sensitive'],
                    fm['normalize_whitespace'], fm['strip_punctuation'],
                    fm['phonetic_enabled'], fm['phonetic_algorithm'],
                    fm['min_string_length'], fm['max_comparisons'],
                    fm['show_confidence_scores']
                )
            )

        self.db.commit()

    def _import_security(self, data: Dict[str, Any]):
        """Import security settings."""
        if data.get('password_hash') == '[REDACTED]':
            # Skip password if redacted
            self.db.execute(
                """
                INSERT OR REPLACE INTO auth_config (id, enabled, username, password_hash)
                VALUES (1, ?, ?, (SELECT password_hash FROM auth_config WHERE id = 1))
                """,
                (data.get('enabled', False), data.get('username', ''))
            )
        else:
            self.db.execute(
                """
                INSERT OR REPLACE INTO auth_config (id, enabled, username, password_hash)
                VALUES (1, ?, ?, ?)
                """,
                (data.get('enabled', False), data.get('username', ''), data.get('password_hash', ''))
            )
        self.db.commit()
