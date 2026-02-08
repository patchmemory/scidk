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
        """Create auth_config and sessions tables if they don't exist."""
        # Auth configuration table (single row expected)
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

        # Active sessions table
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                last_activity REAL NOT NULL
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

        self.db.commit()

    def is_enabled(self) -> bool:
        """Check if authentication is currently enabled.

        Returns:
            bool: True if auth is enabled, False otherwise
        """
        try:
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
