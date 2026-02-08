"""Tests for authentication manager and API endpoints."""
import pytest
import tempfile
import os
from scidk.core.auth import AuthManager, get_auth_manager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def auth_manager(temp_db):
    """Create an AuthManager instance with temp database."""
    return AuthManager(db_path=temp_db)


class TestAuthManager:
    """Tests for AuthManager class."""

    def test_init_creates_tables(self, auth_manager):
        """Test that initialization creates required tables."""
        # Check that tables exist by querying them
        cursor = auth_manager.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('auth_config', 'auth_sessions', 'auth_failed_attempts')"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert 'auth_config' in tables
        assert 'auth_sessions' in tables
        assert 'auth_failed_attempts' in tables

    def test_is_enabled_default_false(self, auth_manager):
        """Test that authentication is disabled by default."""
        assert auth_manager.is_enabled() is False

    def test_get_config_default(self, auth_manager):
        """Test getting default config."""
        config = auth_manager.get_config()
        assert config['enabled'] is False
        assert config['username'] is None
        assert config['has_password'] is False

    def test_set_config_enable_auth(self, auth_manager):
        """Test enabling authentication with username and password."""
        success = auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='testpass123'
        )
        assert success is True

        # Verify config was saved
        config = auth_manager.get_config()
        assert config['enabled'] is True
        assert config['username'] == 'testuser'
        assert config['has_password'] is True

        # Verify auth is enabled
        assert auth_manager.is_enabled() is True

    def test_set_config_requires_username_and_password(self, auth_manager):
        """Test that enabling auth requires username and password."""
        # Missing username
        success = auth_manager.set_config(
            enabled=True,
            username=None,
            password='testpass123'
        )
        assert success is False

        # Missing password
        success = auth_manager.set_config(
            enabled=True,
            username='testuser',
            password=None
        )
        assert success is False

    def test_verify_credentials_success(self, auth_manager):
        """Test successful credential verification."""
        # Set up auth
        auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='testpass123'
        )

        # Verify correct credentials
        assert auth_manager.verify_credentials('testuser', 'testpass123') is True

    def test_verify_credentials_wrong_password(self, auth_manager):
        """Test credential verification with wrong password."""
        # Set up auth
        auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='testpass123'
        )

        # Verify wrong password
        assert auth_manager.verify_credentials('testuser', 'wrongpass') is False

    def test_verify_credentials_wrong_username(self, auth_manager):
        """Test credential verification with wrong username."""
        # Set up auth
        auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='testpass123'
        )

        # Verify wrong username
        assert auth_manager.verify_credentials('wronguser', 'testpass123') is False

    def test_verify_credentials_when_disabled(self, auth_manager):
        """Test that credentials don't verify when auth is disabled."""
        # Set up auth but disabled
        auth_manager.set_config(
            enabled=False,
            username='testuser',
            password='testpass123'
        )

        # Should fail even with correct credentials
        assert auth_manager.verify_credentials('testuser', 'testpass123') is False

    def test_create_session(self, auth_manager):
        """Test creating a session."""
        token = auth_manager.create_session('testuser', duration_hours=1)

        assert token is not None
        assert len(token) > 0

    def test_verify_session_success(self, auth_manager):
        """Test verifying a valid session."""
        # Create session
        token = auth_manager.create_session('testuser', duration_hours=1)

        # Verify session
        username = auth_manager.verify_session(token)
        assert username == 'testuser'

    def test_verify_session_invalid_token(self, auth_manager):
        """Test verifying an invalid session token."""
        username = auth_manager.verify_session('invalid_token_123')
        assert username is None

    def test_verify_session_empty_token(self, auth_manager):
        """Test verifying empty token."""
        username = auth_manager.verify_session('')
        assert username is None

    def test_delete_session(self, auth_manager):
        """Test deleting a session."""
        # Create session
        token = auth_manager.create_session('testuser', duration_hours=1)

        # Verify it exists
        assert auth_manager.verify_session(token) == 'testuser'

        # Delete session
        success = auth_manager.delete_session(token)
        assert success is True

        # Verify it's gone
        assert auth_manager.verify_session(token) is None

    def test_log_failed_attempt(self, auth_manager):
        """Test logging failed login attempts."""
        # Log a failed attempt
        auth_manager.log_failed_attempt('testuser', '127.0.0.1')

        # Get failed attempts
        attempts = auth_manager.get_failed_attempts(limit=10)
        assert len(attempts) == 1
        assert attempts[0]['username'] == 'testuser'
        assert attempts[0]['ip_address'] == '127.0.0.1'

    def test_update_password(self, auth_manager):
        """Test updating password while keeping username."""
        # Set initial auth
        auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='oldpass123'
        )

        # Verify old password works
        assert auth_manager.verify_credentials('testuser', 'oldpass123') is True

        # Update password
        auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='newpass456'
        )

        # Verify old password doesn't work
        assert auth_manager.verify_credentials('testuser', 'oldpass123') is False

        # Verify new password works
        assert auth_manager.verify_credentials('testuser', 'newpass456') is True

    def test_disable_auth(self, auth_manager):
        """Test disabling authentication."""
        # Enable auth first
        auth_manager.set_config(
            enabled=True,
            username='testuser',
            password='testpass123'
        )
        assert auth_manager.is_enabled() is True

        # Disable auth
        auth_manager.set_config(enabled=False)
        assert auth_manager.is_enabled() is False

    def test_get_auth_manager_factory(self, temp_db):
        """Test factory function."""
        manager = get_auth_manager(db_path=temp_db)
        assert isinstance(manager, AuthManager)
        assert manager.is_enabled() is False


@pytest.mark.integration
class TestAuthAPIEndpoints:
    """Integration tests for auth API endpoints."""

    @pytest.fixture
    def app(self, temp_db, monkeypatch):
        """Create Flask app for testing."""
        from scidk.app import create_app

        # Set environment variables for testing
        monkeypatch.setenv('PYTEST_CURRENT_TEST', '1')
        monkeypatch.setenv('SCIDK_SETTINGS_DB', temp_db)
        monkeypatch.setenv('PYTEST_TEST_AUTH', '1')  # Enable auth checking in tests

        app = create_app()
        app.config['TESTING'] = True
        app.config['SCIDK_SETTINGS_DB'] = temp_db
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    def test_auth_status_disabled_by_default(self, client):
        """Test /api/auth/status when auth is disabled."""
        response = client.get('/api/auth/status')
        assert response.status_code == 200

        data = response.get_json()
        assert data['authenticated'] is True  # Always authenticated when disabled
        assert data['auth_enabled'] is False

    def test_login_when_auth_disabled(self, client):
        """Test login endpoint when auth is disabled."""
        response = client.post('/api/auth/login', json={
            'username': 'test',
            'password': 'test'
        })
        assert response.status_code == 503  # Service unavailable

        data = response.get_json()
        assert data['success'] is False
        assert 'not enabled' in data['error'].lower()

    def test_full_auth_flow(self, client, temp_db):
        """Test complete authentication flow."""
        # Enable auth
        auth = get_auth_manager(temp_db)
        auth.set_config(enabled=True, username='testuser', password='testpass123')

        # Test status before login
        response = client.get('/api/auth/status')
        data = response.get_json()
        assert data['authenticated'] is False
        assert data['auth_enabled'] is True

        # Test login with wrong credentials
        response = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'wrongpass'
        })
        assert response.status_code == 401

        # Test login with correct credentials
        response = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'testpass123'
        })
        assert response.status_code == 200

        data = response.get_json()
        assert data['success'] is True
        assert data['username'] == 'testuser'
        assert 'token' in data

        # Test status after login (with cookie from response)
        token = data['token']
        response = client.get(
            '/api/auth/status',
            headers={'Authorization': f'Bearer {token}'}
        )
        data = response.get_json()
        assert data['authenticated'] is True
        assert data['username'] == 'testuser'

        # Test logout
        response = client.post(
            '/api/auth/logout',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 200

        # Test status after logout
        response = client.get(
            '/api/auth/status',
            headers={'Authorization': f'Bearer {token}'}
        )
        data = response.get_json()
        assert data['authenticated'] is False
