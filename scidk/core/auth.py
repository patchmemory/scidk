"""Authentication and session management for SciDK.

This module provides basic username/password authentication with secure password
hashing (bcrypt) and session management. Sessions are stored in SQLite and can
persist across page reloads.

Security features:
- bcrypt password hashing with automatic salt generation
- Session tokens using secrets.token_urlsafe()
- Failed login attempt logging
- Configurable session expiration
"""

import sqlite3
import secrets
import bcrypt
import time
from typing import Optional, Dict, Any
from pathlib import Path


class AuthManager:
    """Manage authentication config, password verification, and sessions."""

    def __init__(self, db_path: str = 'scidk_settings.db'):
        """Initialize AuthManager with SQLite database.

        Args:
            db_path: Path to settings database (default: scidk_settings.db)
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.init_tables()

    def init_tables(self):
        """Create auth_config, users, sessions, and audit tables if they don't exist."""
        # Auth configuration table (single row, legacy - kept for backward compatibility)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER DEFAULT 0,
                username TEXT,
                password_hash TEXT,
                created_at REAL,
                updated_at REAL
            )
            """
        )

        # Multi-user table (new primary user storage)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                enabled INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                created_by TEXT,
                last_login REAL
            )
            """
        )

        # Active sessions table (updated with user_id)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                user_id INTEGER,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                last_activity REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES auth_users(id) ON DELETE CASCADE
            )
            """
        )

        # Failed login attempts log (for security monitoring)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_failed_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                timestamp REAL NOT NULL,
                ip_address TEXT
            )
            """
        )

        # Audit log for user actions
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT
            )
            """
        )

        self.db.commit()

        # Auto-migrate from single-user to multi-user on first run
        self._migrate_to_multi_user()

    def _migrate_to_multi_user(self):
        """Migrate from single-user auth_config to multi-user auth_users table.

        If auth_config has a user configured but auth_users is empty,
        migrate the user to auth_users as an admin.
        """
        try:
            # Check if migration is needed
            cur = self.db.execute("SELECT COUNT(*) FROM auth_users")
            user_count = cur.fetchone()[0]

            if user_count > 0:
                # Already migrated
                return

            # Check if there's a user in auth_config
            cur = self.db.execute(
                "SELECT enabled, username, password_hash FROM auth_config WHERE id = 1"
            )
            row = cur.fetchone()

            if not row or not row[1] or not row[2]:
                # No user to migrate
                return

            enabled, username, password_hash = row
            now = time.time()

            # Migrate user to auth_users as admin
            self.db.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, enabled, created_at, updated_at, created_by)
                VALUES (?, ?, 'admin', ?, ?, ?, 'system')
                """,
                (username, password_hash, int(enabled), now, now)
            )
            self.db.commit()

            print(f"Migrated user '{username}' from auth_config to auth_users as admin")
        except Exception as e:
            print(f"Migration warning: {e}")

    def is_enabled(self) -> bool:
        """Check if authentication is currently enabled.

        Returns:
            bool: True if auth is enabled, False otherwise
        """
        try:
            # Check if there are any enabled users in auth_users (multi-user mode)
            cur = self.db.execute("SELECT COUNT(*) FROM auth_users WHERE enabled = 1")
            user_count = cur.fetchone()[0]
            if user_count > 0:
                return True

            # Fall back to auth_config for backward compatibility
            cur = self.db.execute("SELECT enabled FROM auth_config WHERE id = 1")
            row = cur.fetchone()
            return bool(row and row[0]) if row else False
        except Exception:
            return False

    def get_config(self) -> Dict[str, Any]:
        """Get current auth configuration (without password hash).

        Returns:
            dict: {'enabled': bool, 'username': str or None, 'has_password': bool}
        """
        try:
            cur = self.db.execute(
                "SELECT enabled, username, password_hash FROM auth_config WHERE id = 1"
            )
            row = cur.fetchone()
            if row:
                return {
                    'enabled': bool(row[0]),
                    'username': row[1],
                    'has_password': bool(row[2]),
                }
            return {'enabled': False, 'username': None, 'has_password': False}
        except Exception:
            return {'enabled': False, 'username': None, 'has_password': False}

    def set_config(self, enabled: bool, username: Optional[str] = None,
                   password: Optional[str] = None) -> bool:
        """Save authentication configuration.

        Args:
            enabled: Whether to enable authentication
            username: Username (required if enabled=True and changing)
            password: Plain-text password (will be hashed; optional if keeping existing)

        Returns:
            bool: True if successful, False on error
        """
        try:
            now = time.time()

            # Get existing config
            cur = self.db.execute("SELECT username, password_hash FROM auth_config WHERE id = 1")
            existing = cur.fetchone()

            # Determine final username and password_hash
            final_username = username if username is not None else (existing[0] if existing else None)

            if password is not None:
                # Hash new password
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            else:
                # Keep existing hash
                password_hash = existing[1] if existing else None

            # Validate: if enabling, must have username and password
            if enabled and (not final_username or not password_hash):
                return False

            if existing:
                # Update existing row
                self.db.execute(
                    """
                    UPDATE auth_config
                    SET enabled = ?, username = ?, password_hash = ?, updated_at = ?
                    WHERE id = 1
                    """,
                    (int(enabled), final_username, password_hash, now)
                )
            else:
                # Insert new row
                self.db.execute(
                    """
                    INSERT INTO auth_config (id, enabled, username, password_hash, created_at, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?)
                    """,
                    (int(enabled), final_username, password_hash, now, now)
                )

            self.db.commit()
            return True
        except Exception as e:
            print(f"AuthManager.set_config error: {e}")
            return False

    def verify_credentials(self, username: str, password: str) -> bool:
        """Verify username and password against stored credentials.

        Args:
            username: Username to check
            password: Plain-text password to verify

        Returns:
            bool: True if credentials are valid, False otherwise
        """
        try:
            cur = self.db.execute(
                "SELECT password_hash FROM auth_config WHERE id = 1 AND enabled = 1 AND username = ?"
            , (username,))
            row = cur.fetchone()

            if not row or not row[0]:
                return False

            stored_hash = row[0].encode('utf-8')
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        except Exception as e:
            print(f"AuthManager.verify_credentials error: {e}")
            return False

    def create_session(self, username: str, duration_hours: int = 24) -> str:
        """Create a new session token for the given username.

        Args:
            username: Username to create session for
            duration_hours: Session validity duration (default: 24 hours)

        Returns:
            str: Session token (URL-safe random string)
        """
        token = secrets.token_urlsafe(32)
        now = time.time()
        expires_at = now + (duration_hours * 3600)

        try:
            self.db.execute(
                """
                INSERT INTO auth_sessions (token, username, created_at, expires_at, last_activity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token, username, now, expires_at, now)
            )
            self.db.commit()
            return token
        except Exception as e:
            print(f"AuthManager.create_session error: {e}")
            return ""

    def verify_session(self, token: str, update_activity: bool = True) -> Optional[str]:
        """Verify session token and return username if valid.

        Args:
            token: Session token to verify
            update_activity: Whether to update last_activity timestamp

        Returns:
            str or None: Username if session is valid, None otherwise
        """
        if not token:
            return None

        try:
            now = time.time()
            cur = self.db.execute(
                """
                SELECT username, expires_at FROM auth_sessions
                WHERE token = ? AND expires_at > ?
                """,
                (token, now)
            )
            row = cur.fetchone()

            if not row:
                return None

            username = row[0]

            # Update last activity timestamp
            if update_activity:
                self.db.execute(
                    "UPDATE auth_sessions SET last_activity = ? WHERE token = ?",
                    (now, token)
                )
                self.db.commit()

            return username
        except Exception as e:
            print(f"AuthManager.verify_session error: {e}")
            return None

    def delete_session(self, token: str) -> bool:
        """Delete a session (logout).

        Args:
            token: Session token to delete

        Returns:
            bool: True if successful, False on error
        """
        try:
            self.db.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            self.db.commit()
            return True
        except Exception:
            return False

    def cleanup_expired_sessions(self):
        """Remove all expired sessions from the database."""
        try:
            now = time.time()
            self.db.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
            self.db.commit()
        except Exception as e:
            print(f"AuthManager.cleanup_expired_sessions error: {e}")

    def log_failed_attempt(self, username: str, ip_address: Optional[str] = None):
        """Log a failed login attempt for security monitoring.

        Args:
            username: Username that was attempted
            ip_address: IP address of the request (optional)
        """
        try:
            now = time.time()
            self.db.execute(
                "INSERT INTO auth_failed_attempts (username, timestamp, ip_address) VALUES (?, ?, ?)",
                (username, now, ip_address)
            )
            self.db.commit()
        except Exception as e:
            print(f"AuthManager.log_failed_attempt error: {e}")

    def get_failed_attempts(self, since_timestamp: Optional[float] = None, limit: int = 100) -> list:
        """Get recent failed login attempts.

        Args:
            since_timestamp: Only return attempts after this timestamp (optional)
            limit: Maximum number of attempts to return

        Returns:
            list: List of dicts with keys: id, username, timestamp, ip_address
        """
        try:
            if since_timestamp:
                cur = self.db.execute(
                    """
                    SELECT id, username, timestamp, ip_address
                    FROM auth_failed_attempts
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (since_timestamp, limit)
                )
            else:
                cur = self.db.execute(
                    """
                    SELECT id, username, timestamp, ip_address
                    FROM auth_failed_attempts
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                )

            rows = cur.fetchall()
            return [
                {
                    'id': row[0],
                    'username': row[1],
                    'timestamp': row[2],
                    'ip_address': row[3],
                }
                for row in rows
            ]
        except Exception:
            return []

    # ========== Multi-User Management Methods ==========

    def list_users(self, include_disabled: bool = False) -> list:
        """Get list of all users.

        Args:
            include_disabled: Whether to include disabled users

        Returns:
            list: List of user dicts (without password hashes)
        """
        try:
            if include_disabled:
                cur = self.db.execute(
                    """
                    SELECT id, username, role, enabled, created_at, updated_at, created_by, last_login
                    FROM auth_users
                    ORDER BY created_at DESC
                    """
                )
            else:
                cur = self.db.execute(
                    """
                    SELECT id, username, role, enabled, created_at, updated_at, created_by, last_login
                    FROM auth_users
                    WHERE enabled = 1
                    ORDER BY created_at DESC
                    """
                )

            rows = cur.fetchall()
            return [
                {
                    'id': row[0],
                    'username': row[1],
                    'role': row[2],
                    'enabled': bool(row[3]),
                    'created_at': row[4],
                    'updated_at': row[5],
                    'created_by': row[6],
                    'last_login': row[7],
                }
                for row in rows
            ]
        except Exception as e:
            print(f"AuthManager.list_users error: {e}")
            return []

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID.

        Args:
            user_id: User ID

        Returns:
            dict or None: User dict (without password hash) if found
        """
        try:
            cur = self.db.execute(
                """
                SELECT id, username, role, enabled, created_at, updated_at, created_by, last_login
                FROM auth_users
                WHERE id = ?
                """,
                (user_id,)
            )
            row = cur.fetchone()
            if not row:
                return None

            return {
                'id': row[0],
                'username': row[1],
                'role': row[2],
                'enabled': bool(row[3]),
                'created_at': row[4],
                'updated_at': row[5],
                'created_by': row[6],
                'last_login': row[7],
            }
        except Exception as e:
            print(f"AuthManager.get_user error: {e}")
            return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username.

        Args:
            username: Username

        Returns:
            dict or None: User dict (without password hash) if found
        """
        try:
            cur = self.db.execute(
                """
                SELECT id, username, role, enabled, created_at, updated_at, created_by, last_login
                FROM auth_users
                WHERE username = ?
                """,
                (username,)
            )
            row = cur.fetchone()
            if not row:
                return None

            return {
                'id': row[0],
                'username': row[1],
                'role': row[2],
                'enabled': bool(row[3]),
                'created_at': row[4],
                'updated_at': row[5],
                'created_by': row[6],
                'last_login': row[7],
            }
        except Exception as e:
            print(f"AuthManager.get_user_by_username error: {e}")
            return None

    def create_user(self, username: str, password: str, role: str = 'user',
                    created_by: Optional[str] = None) -> Optional[int]:
        """Create a new user.

        Args:
            username: Username (must be unique)
            password: Plain-text password (will be hashed)
            role: User role ('admin' or 'user')
            created_by: Username of creator (for audit trail)

        Returns:
            int or None: User ID if successful, None on error
        """
        try:
            if role not in ('admin', 'user'):
                return None

            # Hash password
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            now = time.time()
            cur = self.db.execute(
                """
                INSERT INTO auth_users (username, password_hash, role, enabled, created_at, updated_at, created_by)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                """,
                (username, password_hash, role, now, now, created_by)
            )
            self.db.commit()

            return cur.lastrowid
        except Exception as e:
            print(f"AuthManager.create_user error: {e}")
            return None

    def update_user(self, user_id: int, username: Optional[str] = None,
                    password: Optional[str] = None, role: Optional[str] = None,
                    enabled: Optional[bool] = None) -> bool:
        """Update user properties.

        Args:
            user_id: User ID
            username: New username (optional)
            password: New plain-text password (will be hashed, optional)
            role: New role (optional)
            enabled: New enabled status (optional)

        Returns:
            bool: True if successful, False on error
        """
        try:
            # Build dynamic update query
            updates = []
            params = []

            if username is not None:
                updates.append("username = ?")
                params.append(username)

            if password is not None:
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                updates.append("password_hash = ?")
                params.append(password_hash)

            if role is not None:
                if role not in ('admin', 'user'):
                    return False
                updates.append("role = ?")
                params.append(role)

            if enabled is not None:
                updates.append("enabled = ?")
                params.append(int(enabled))

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = ?")
            params.append(time.time())
            params.append(user_id)

            query = f"UPDATE auth_users SET {', '.join(updates)} WHERE id = ?"
            self.db.execute(query, params)
            self.db.commit()

            return True
        except Exception as e:
            print(f"AuthManager.update_user error: {e}")
            return False

    def delete_user(self, user_id: int) -> bool:
        """Delete a user (and all their sessions).

        Args:
            user_id: User ID

        Returns:
            bool: True if successful, False on error
        """
        try:
            # Safety check: don't delete the last admin
            user = self.get_user(user_id)
            if user and user['role'] == 'admin':
                admin_count = self.count_admin_users()
                if admin_count <= 1:
                    print("Cannot delete last admin user")
                    return False

            # Delete user (CASCADE will delete sessions)
            self.db.execute("DELETE FROM auth_users WHERE id = ?", (user_id,))
            self.db.commit()

            return True
        except Exception as e:
            print(f"AuthManager.delete_user error: {e}")
            return False

    def delete_user_sessions(self, user_id: int) -> bool:
        """Delete all sessions for a user (force logout).

        Args:
            user_id: User ID

        Returns:
            bool: True if successful, False on error
        """
        try:
            self.db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            self.db.commit()
            return True
        except Exception as e:
            print(f"AuthManager.delete_user_sessions error: {e}")
            return False

    def count_admin_users(self) -> int:
        """Count the number of admin users.

        Returns:
            int: Number of admin users
        """
        try:
            cur = self.db.execute("SELECT COUNT(*) FROM auth_users WHERE role = 'admin' AND enabled = 1")
            return cur.fetchone()[0]
        except Exception:
            return 0

    # ========== Session Management (Updated for Multi-User) ==========

    def verify_user_credentials(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verify username and password against auth_users table.

        Args:
            username: Username to check
            password: Plain-text password to verify

        Returns:
            dict or None: User dict if credentials are valid, None otherwise
        """
        try:
            cur = self.db.execute(
                """
                SELECT id, username, password_hash, role, enabled
                FROM auth_users
                WHERE username = ?
                """,
                (username,)
            )
            row = cur.fetchone()

            if not row:
                return None

            user_id, username, password_hash, role, enabled = row

            if not enabled:
                return None

            # Verify password
            if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                return None

            # Update last_login
            self.db.execute(
                "UPDATE auth_users SET last_login = ? WHERE id = ?",
                (time.time(), user_id)
            )
            self.db.commit()

            return {
                'id': user_id,
                'username': username,
                'role': role,
                'enabled': bool(enabled),
            }
        except Exception as e:
            print(f"AuthManager.verify_user_credentials error: {e}")
            return None

    def create_user_session(self, user_id: int, username: str, duration_hours: int = 24) -> str:
        """Create a new session token for the given user.

        Args:
            user_id: User ID
            username: Username
            duration_hours: Session validity duration (default: 24 hours)

        Returns:
            str: Session token (URL-safe random string)
        """
        token = secrets.token_urlsafe(32)
        now = time.time()
        expires_at = now + (duration_hours * 3600)

        try:
            self.db.execute(
                """
                INSERT INTO auth_sessions (token, username, user_id, created_at, expires_at, last_activity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, username, user_id, now, expires_at, now)
            )
            self.db.commit()
            return token
        except Exception as e:
            print(f"AuthManager.create_user_session error: {e}")
            return ""

    def get_session_user(self, token: str, update_activity: bool = True) -> Optional[Dict[str, Any]]:
        """Get user info from session token.

        Args:
            token: Session token to verify
            update_activity: Whether to update last_activity timestamp

        Returns:
            dict or None: User dict if session is valid, None otherwise
        """
        if not token:
            return None

        try:
            now = time.time()
            cur = self.db.execute(
                """
                SELECT s.username, s.user_id, u.role, u.enabled
                FROM auth_sessions s
                JOIN auth_users u ON s.user_id = u.id
                WHERE s.token = ? AND s.expires_at > ?
                """,
                (token, now)
            )
            row = cur.fetchone()

            if not row:
                return None

            username, user_id, role, enabled = row

            if not enabled:
                return None

            # Update last activity timestamp
            if update_activity:
                self.db.execute(
                    "UPDATE auth_sessions SET last_activity = ? WHERE token = ?",
                    (now, token)
                )
                self.db.commit()

            return {
                'id': user_id,
                'username': username,
                'role': role,
                'enabled': bool(enabled),
            }
        except Exception as e:
            print(f"AuthManager.get_session_user error: {e}")
            return None

    # ========== Audit Logging ==========

    def log_audit(self, username: str, action: str, details: Optional[str] = None,
                  ip_address: Optional[str] = None):
        """Log an audit event.

        Args:
            username: Username performing the action
            action: Action description (e.g., 'user_created', 'user_deleted', 'login')
            details: Additional details (optional, can be JSON string)
            ip_address: IP address of the request (optional)
        """
        try:
            now = time.time()
            self.db.execute(
                """
                INSERT INTO auth_audit_log (timestamp, username, action, details, ip_address)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, username, action, details, ip_address)
            )
            self.db.commit()
        except Exception as e:
            print(f"AuthManager.log_audit error: {e}")

    def get_audit_log(self, since_timestamp: Optional[float] = None,
                      username: Optional[str] = None, limit: int = 100) -> list:
        """Get audit log entries.

        Args:
            since_timestamp: Only return entries after this timestamp (optional)
            username: Filter by username (optional)
            limit: Maximum number of entries to return

        Returns:
            list: List of dicts with keys: id, timestamp, username, action, details, ip_address
        """
        try:
            query = "SELECT id, timestamp, username, action, details, ip_address FROM auth_audit_log WHERE 1=1"
            params = []

            if since_timestamp:
                query += " AND timestamp > ?"
                params.append(since_timestamp)

            if username:
                query += " AND username = ?"
                params.append(username)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cur = self.db.execute(query, params)
            rows = cur.fetchall()

            return [
                {
                    'id': row[0],
                    'timestamp': row[1],
                    'username': row[2],
                    'action': row[3],
                    'details': row[4],
                    'ip_address': row[5],
                }
                for row in rows
            ]
        except Exception as e:
            print(f"AuthManager.get_audit_log error: {e}")
            return []

    def close(self):
        """Close database connection."""
        try:
            self.db.close()
        except Exception:
            pass


def get_auth_manager(db_path: str = 'scidk_settings.db') -> AuthManager:
    """Factory function to get AuthManager instance.

    Args:
        db_path: Path to settings database

    Returns:
        AuthManager: Configured auth manager instance
    """
    return AuthManager(db_path=db_path)
