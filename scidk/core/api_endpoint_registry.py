"""
API Endpoint Registry for Links integration.

Manages persistent storage of API endpoint configurations for use in Links wizard.
Supports authentication, field mappings, and test connections.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from cryptography.fernet import Fernet
import os


class APIEndpointRegistry:
    """
    Registry for API endpoint configurations.

    Stores endpoint metadata including:
    - URL and authentication
    - JSONPath extraction rules
    - Field mappings to Label properties
    - Encrypted auth tokens
    """

    def __init__(self, db_path: str, encryption_key: Optional[str] = None):
        """
        Initialize registry with SQLite database.

        Args:
            db_path: Path to settings database
            encryption_key: Fernet key for auth token encryption (base64-encoded)
                          If None, generates a new key (only for development!)
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.db.row_factory = sqlite3.Row

        # Initialize encryption
        if encryption_key:
            self.cipher = Fernet(encryption_key.encode())
        else:
            # Generate ephemeral key (WARNING: not persistent across restarts)
            self.cipher = Fernet(Fernet.generate_key())

        self.init_tables()

    def init_tables(self):
        """Create tables if they don't exist."""
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS api_endpoints (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                auth_method TEXT NOT NULL DEFAULT 'none',
                auth_value_encrypted TEXT,
                json_path TEXT,
                target_label TEXT,
                field_mappings TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.db.commit()

    def create_endpoint(self, endpoint_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new API endpoint configuration.

        Args:
            endpoint_data: Dict with keys:
                - name: Endpoint name (required)
                - url: API URL (required)
                - auth_method: "none", "bearer", or "api_key" (default: "none")
                - auth_value: Auth token/key (optional, encrypted at rest)
                - json_path: JSONPath for extracting data (optional)
                - target_label: Target Label name (optional)
                - field_mappings: Dict {api_field: label_property} (optional)

        Returns:
            Created endpoint dict with id

        Raises:
            ValueError: If required fields missing or endpoint name exists
        """
        # Validation
        if not endpoint_data.get('name'):
            raise ValueError("Endpoint name is required")
        if not endpoint_data.get('url'):
            raise ValueError("Endpoint URL is required")

        # Check for duplicate name
        existing = self.get_endpoint_by_name(endpoint_data['name'])
        if existing:
            raise ValueError(f"Endpoint with name '{endpoint_data['name']}' already exists")

        endpoint_id = str(uuid.uuid4())
        now = datetime.utcnow().timestamp()

        # Encrypt auth value if present
        auth_value = endpoint_data.get('auth_value', '')
        auth_value_encrypted = None
        if auth_value:
            auth_value_encrypted = self.cipher.encrypt(auth_value.encode()).decode()

        # Serialize field mappings
        field_mappings_json = json.dumps(endpoint_data.get('field_mappings', {}))

        self.db.execute(
            """
            INSERT INTO api_endpoints
            (id, name, url, auth_method, auth_value_encrypted, json_path,
             target_label, field_mappings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                endpoint_id,
                endpoint_data['name'],
                endpoint_data['url'],
                endpoint_data.get('auth_method', 'none'),
                auth_value_encrypted,
                endpoint_data.get('json_path', ''),
                endpoint_data.get('target_label', ''),
                field_mappings_json,
                now,
                now
            )
        )
        self.db.commit()

        return self.get_endpoint(endpoint_id)

    def get_endpoint(self, endpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Get endpoint by ID.

        Args:
            endpoint_id: Endpoint UUID

        Returns:
            Endpoint dict (without decrypted auth_value) or None
        """
        cur = self.db.execute(
            "SELECT * FROM api_endpoints WHERE id = ?",
            (endpoint_id,)
        )
        row = cur.fetchone()
        if not row:
            return None

        return self._row_to_dict(row, include_auth=False)

    def get_endpoint_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get endpoint by name."""
        cur = self.db.execute(
            "SELECT * FROM api_endpoints WHERE name = ?",
            (name,)
        )
        row = cur.fetchone()
        if not row:
            return None

        return self._row_to_dict(row, include_auth=False)

    def list_endpoints(self) -> List[Dict[str, Any]]:
        """
        List all endpoints.

        Returns:
            List of endpoint dicts (without decrypted auth values)
        """
        cur = self.db.execute(
            "SELECT * FROM api_endpoints ORDER BY name"
        )
        rows = cur.fetchall()
        return [self._row_to_dict(row, include_auth=False) for row in rows]

    def update_endpoint(self, endpoint_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing endpoint.

        Args:
            endpoint_id: Endpoint UUID
            updates: Dict with fields to update

        Returns:
            Updated endpoint dict

        Raises:
            ValueError: If endpoint not found or name conflict
        """
        endpoint = self.get_endpoint(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint {endpoint_id} not found")

        # Check for name conflict if renaming
        if 'name' in updates and updates['name'] != endpoint['name']:
            existing = self.get_endpoint_by_name(updates['name'])
            if existing and existing['id'] != endpoint_id:
                raise ValueError(f"Endpoint with name '{updates['name']}' already exists")

        # Build update query dynamically
        set_clauses = []
        values = []

        if 'name' in updates:
            set_clauses.append("name = ?")
            values.append(updates['name'])

        if 'url' in updates:
            set_clauses.append("url = ?")
            values.append(updates['url'])

        if 'auth_method' in updates:
            set_clauses.append("auth_method = ?")
            values.append(updates['auth_method'])

        if 'auth_value' in updates:
            if updates['auth_value']:
                auth_encrypted = self.cipher.encrypt(updates['auth_value'].encode()).decode()
                set_clauses.append("auth_value_encrypted = ?")
                values.append(auth_encrypted)
            else:
                set_clauses.append("auth_value_encrypted = NULL")

        if 'json_path' in updates:
            set_clauses.append("json_path = ?")
            values.append(updates.get('json_path', ''))

        if 'target_label' in updates:
            set_clauses.append("target_label = ?")
            values.append(updates.get('target_label', ''))

        if 'field_mappings' in updates:
            set_clauses.append("field_mappings = ?")
            values.append(json.dumps(updates['field_mappings']))

        if not set_clauses:
            return endpoint

        set_clauses.append("updated_at = ?")
        values.append(datetime.utcnow().timestamp())

        values.append(endpoint_id)

        query = f"UPDATE api_endpoints SET {', '.join(set_clauses)} WHERE id = ?"
        self.db.execute(query, values)
        self.db.commit()

        return self.get_endpoint(endpoint_id)

    def delete_endpoint(self, endpoint_id: str) -> bool:
        """
        Delete an endpoint.

        Args:
            endpoint_id: Endpoint UUID

        Returns:
            True if deleted, False if not found
        """
        cursor = self.db.execute(
            "DELETE FROM api_endpoints WHERE id = ?",
            (endpoint_id,)
        )
        self.db.commit()
        return cursor.rowcount > 0

    def get_decrypted_auth(self, endpoint_id: str) -> Optional[str]:
        """
        Get decrypted auth value for an endpoint.

        Args:
            endpoint_id: Endpoint UUID

        Returns:
            Decrypted auth value or None
        """
        cur = self.db.execute(
            "SELECT auth_value_encrypted FROM api_endpoints WHERE id = ?",
            (endpoint_id,)
        )
        row = cur.fetchone()
        if not row or not row['auth_value_encrypted']:
            return None

        try:
            return self.cipher.decrypt(row['auth_value_encrypted'].encode()).decode()
        except Exception:
            return None

    def _row_to_dict(self, row: sqlite3.Row, include_auth: bool = False) -> Dict[str, Any]:
        """Convert SQLite row to dict."""
        data = {
            'id': row['id'],
            'name': row['name'],
            'url': row['url'],
            'auth_method': row['auth_method'],
            'json_path': row['json_path'] or '',
            'target_label': row['target_label'] or '',
            'field_mappings': json.loads(row['field_mappings']) if row['field_mappings'] else {},
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }

        if include_auth and row['auth_value_encrypted']:
            try:
                data['auth_value'] = self.cipher.decrypt(row['auth_value_encrypted'].encode()).decode()
            except Exception:
                data['auth_value'] = None

        return data


def get_encryption_key() -> str:
    """
    Get encryption key from environment or generate one.

    For production, set SCIDK_API_ENCRYPTION_KEY environment variable.
    For development, a key is generated (but not persisted!).

    Returns:
        Base64-encoded Fernet key
    """
    key = os.environ.get('SCIDK_API_ENCRYPTION_KEY')
    if key:
        return key

    # Development: generate ephemeral key
    # WARNING: This means auth tokens won't survive app restarts
    return Fernet.generate_key().decode()
