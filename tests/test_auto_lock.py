"""Tests for auto-lock functionality."""

import pytest
import time
import sqlite3
from scidk.core.auth import AuthManager


@pytest.fixture
def auth_manager(tmp_path):
    """Create a temporary AuthManager for testing."""
    db_path = tmp_path / 'test_auth.db'
    manager = AuthManager(db_path=str(db_path))

    # Create a test user
    user_id = manager.create_user('testuser', 'testpass123', role='admin', created_by='system')
    assert user_id is not None

    yield manager

    manager.close()


def test_session_lock_columns_migration(tmp_path):
    """Test that lock columns are added to auth_sessions table."""
    db_path = tmp_path / 'test_migration.db'

    # Create database without lock columns (simulate old schema)
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute(
        """
        CREATE TABLE auth_sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            last_activity REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    # Initialize AuthManager - should trigger migration
    manager = AuthManager(db_path=str(db_path))

    # Check that lock columns exist
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("PRAGMA table_info(auth_sessions)")
    columns = [row[1] for row in cur.fetchall()]
    conn.close()

    assert 'locked' in columns, "locked column should be added by migration"
    assert 'locked_at' in columns, "locked_at column should be added by migration"

    manager.close()


def test_lock_session(auth_manager):
    """Test locking a session."""
    # Create a session
    token = auth_manager.create_user_session(1, 'testuser', duration_hours=24)
    assert token

    # Session should not be locked initially
    assert not auth_manager.is_session_locked(token)

    # Lock the session
    result = auth_manager.lock_session(token)
    assert result is True

    # Session should now be locked
    assert auth_manager.is_session_locked(token)


def test_unlock_session(auth_manager):
    """Test unlocking a locked session."""
    # Create and lock a session
    token = auth_manager.create_user_session(1, 'testuser', duration_hours=24)
    auth_manager.lock_session(token)
    assert auth_manager.is_session_locked(token)

    # Unlock with correct password
    result = auth_manager.unlock_session(token, 'testpass123')
    assert result is True

    # Session should be unlocked
    assert not auth_manager.is_session_locked(token)


def test_unlock_session_wrong_password(auth_manager):
    """Test that unlock fails with wrong password."""
    # Create and lock a session
    token = auth_manager.create_user_session(1, 'testuser', duration_hours=24)
    auth_manager.lock_session(token)

    # Try to unlock with wrong password
    result = auth_manager.unlock_session(token, 'wrongpassword')
    assert result is False

    # Session should still be locked
    assert auth_manager.is_session_locked(token)


def test_get_session_lock_info(auth_manager):
    """Test retrieving session lock information."""
    # Create a session
    token = auth_manager.create_user_session(1, 'testuser', duration_hours=24)

    # Get lock info before locking
    lock_info = auth_manager.get_session_lock_info(token)
    assert lock_info is not None
    assert lock_info['username'] == 'testuser'
    assert lock_info['locked'] is False
    assert lock_info['locked_at'] is None

    # Lock the session
    auth_manager.lock_session(token)

    # Get lock info after locking
    lock_info = auth_manager.get_session_lock_info(token)
    assert lock_info is not None
    assert lock_info['username'] == 'testuser'
    assert lock_info['locked'] is True
    assert lock_info['locked_at'] is not None
    assert isinstance(lock_info['locked_at'], float)
    assert lock_info['locked_at'] <= time.time()


def test_lock_nonexistent_session(auth_manager):
    """Test locking a session that doesn't exist."""
    result = auth_manager.lock_session('invalid_token_123')
    # Should succeed but have no effect (UPDATE with no matching row)
    assert result is True


def test_unlock_nonlocked_session(auth_manager):
    """Test unlocking a session that isn't locked."""
    # Create a session
    token = auth_manager.create_user_session(1, 'testuser', duration_hours=24)

    # Try to unlock (session not locked)
    result = auth_manager.unlock_session(token, 'testpass123')
    assert result is False  # Should fail because session is not locked


def test_audit_log_on_unlock(auth_manager):
    """Test that successful unlock is logged in audit trail."""
    # Create and lock a session
    token = auth_manager.create_user_session(1, 'testuser', duration_hours=24)
    auth_manager.lock_session(token)

    # Unlock session
    auth_manager.unlock_session(token, 'testpass123')

    # Check audit log
    audit_log = auth_manager.get_audit_log(limit=10)
    assert len(audit_log) > 0

    # Find the unlock event
    unlock_events = [entry for entry in audit_log if entry['action'] == 'session_unlocked']
    assert len(unlock_events) > 0
    assert unlock_events[0]['username'] == 'testuser'


@pytest.mark.parametrize('timeout_minutes,expected_enabled', [
    (5, True),
    (10, True),
    (60, True),
    (120, True),
])
def test_auto_lock_settings_valid(tmp_path, timeout_minutes, expected_enabled):
    """Test saving valid auto-lock settings."""
    db_path = tmp_path / 'test_settings.db'
    conn = sqlite3.connect(str(db_path))

    # Create settings table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )
        """
    )

    # Save settings
    now = time.time()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ('auto_lock_enabled', 'true', now)
    )
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        ('auto_lock_timeout_minutes', str(timeout_minutes), now)
    )
    conn.commit()

    # Read back settings
    cur = conn.execute("SELECT key, value FROM settings")
    settings_dict = {row[0]: row[1] for row in cur.fetchall()}

    assert settings_dict['auto_lock_enabled'] == 'true'
    assert int(settings_dict['auto_lock_timeout_minutes']) == timeout_minutes

    conn.close()
