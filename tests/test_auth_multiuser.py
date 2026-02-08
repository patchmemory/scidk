"""
Unit tests for multi-user authentication and RBAC features.

Tests cover:
- Multi-user CRUD operations
- Role-based access control
- Audit logging
- Migration from single-user to multi-user
- Session management with user roles
"""
import os
import tempfile
import pytest
from scidk.core.auth import AuthManager
from scidk.app import create_app


class TestMultiUserAuth:
    """Test multi-user authentication features."""

    @pytest.fixture
    def auth(self):
        """Create a fresh AuthManager for each test."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        auth_manager = AuthManager(db_path=db_path)
        yield auth_manager

        auth_manager.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_create_user(self, auth):
        """Test creating a new user."""
        user_id = auth.create_user('testuser', 'password123', role='user', created_by='admin')
        assert user_id is not None
        assert user_id > 0

        # Verify user was created
        user = auth.get_user(user_id)
        assert user is not None
        assert user['username'] == 'testuser'
        assert user['role'] == 'user'
        assert user['enabled'] is True

    def test_create_user_duplicate_username(self, auth):
        """Test that duplicate usernames are rejected."""
        auth.create_user('testuser', 'password123', role='user')

        # Try to create another user with same username
        user_id = auth.create_user('testuser', 'password456', role='user')
        assert user_id is None

    def test_create_user_invalid_role(self, auth):
        """Test that invalid roles are rejected."""
        user_id = auth.create_user('testuser', 'password123', role='superadmin')
        assert user_id is None

    def test_get_user_by_username(self, auth):
        """Test retrieving user by username."""
        user_id = auth.create_user('testuser', 'password123', role='user')

        user = auth.get_user_by_username('testuser')
        assert user is not None
        assert user['id'] == user_id
        assert user['username'] == 'testuser'

    def test_list_users(self, auth):
        """Test listing all users."""
        auth.create_user('admin', 'pass123', role='admin')
        auth.create_user('user1', 'pass456', role='user')
        auth.create_user('user2', 'pass789', role='user')

        users = auth.list_users()
        assert len(users) == 3

        usernames = [u['username'] for u in users]
        assert 'admin' in usernames
        assert 'user1' in usernames
        assert 'user2' in usernames

    def test_list_users_exclude_disabled(self, auth):
        """Test that disabled users are excluded by default."""
        user1_id = auth.create_user('user1', 'pass123', role='user')
        auth.create_user('user2', 'pass456', role='user')

        # Disable user1
        auth.update_user(user1_id, enabled=False)

        # List users (exclude disabled)
        users = auth.list_users(include_disabled=False)
        assert len(users) == 1
        assert users[0]['username'] == 'user2'

        # List all users (include disabled)
        all_users = auth.list_users(include_disabled=True)
        assert len(all_users) == 2

    def test_update_user_password(self, auth):
        """Test updating user password."""
        user_id = auth.create_user('testuser', 'oldpassword', role='user')

        # Update password
        success = auth.update_user(user_id, password='newpassword')
        assert success is True

        # Verify old password doesn't work
        user = auth.verify_user_credentials('testuser', 'oldpassword')
        assert user is None

        # Verify new password works
        user = auth.verify_user_credentials('testuser', 'newpassword')
        assert user is not None

    def test_update_user_role(self, auth):
        """Test updating user role."""
        user_id = auth.create_user('testuser', 'password123', role='user')

        # Promote to admin
        success = auth.update_user(user_id, role='admin')
        assert success is True

        user = auth.get_user(user_id)
        assert user['role'] == 'admin'

    def test_update_user_enable_disable(self, auth):
        """Test enabling and disabling users."""
        user_id = auth.create_user('testuser', 'password123', role='user')

        # Disable user
        success = auth.update_user(user_id, enabled=False)
        assert success is True

        user = auth.get_user(user_id)
        assert user['enabled'] is False

        # Verify disabled user can't log in
        creds = auth.verify_user_credentials('testuser', 'password123')
        assert creds is None

        # Re-enable user
        success = auth.update_user(user_id, enabled=True)
        assert success is True

        creds = auth.verify_user_credentials('testuser', 'password123')
        assert creds is not None

    def test_delete_user(self, auth):
        """Test deleting a user."""
        user_id = auth.create_user('testuser', 'password123', role='user')

        # Delete user
        success = auth.delete_user(user_id)
        assert success is True

        # Verify user is gone
        user = auth.get_user(user_id)
        assert user is None

    def test_cannot_delete_last_admin(self, auth):
        """Test that the last admin cannot be deleted."""
        admin_id = auth.create_user('admin', 'password123', role='admin')

        # Try to delete the last admin
        success = auth.delete_user(admin_id)
        assert success is False

        # Verify admin still exists
        user = auth.get_user(admin_id)
        assert user is not None

    def test_can_delete_admin_if_others_exist(self, auth):
        """Test that an admin can be deleted if others exist."""
        admin1_id = auth.create_user('admin1', 'password123', role='admin')
        admin2_id = auth.create_user('admin2', 'password456', role='admin')

        # Delete admin1 (should succeed since admin2 exists)
        success = auth.delete_user(admin1_id)
        assert success is True

        # Verify admin2 still exists
        user = auth.get_user(admin2_id)
        assert user is not None

    def test_verify_user_credentials(self, auth):
        """Test verifying user credentials."""
        auth.create_user('testuser', 'password123', role='user')

        # Valid credentials
        user = auth.verify_user_credentials('testuser', 'password123')
        assert user is not None
        assert user['username'] == 'testuser'
        assert user['role'] == 'user'

        # Invalid password
        user = auth.verify_user_credentials('testuser', 'wrongpassword')
        assert user is None

        # Invalid username
        user = auth.verify_user_credentials('nonexistent', 'password123')
        assert user is None

    def test_create_user_session(self, auth):
        """Test creating a user session."""
        user_id = auth.create_user('testuser', 'password123', role='user')

        token = auth.create_user_session(user_id, 'testuser', duration_hours=24)
        assert token is not None
        assert len(token) > 20

    def test_get_session_user(self, auth):
        """Test retrieving user from session token."""
        user_id = auth.create_user('testuser', 'password123', role='user')
        token = auth.create_user_session(user_id, 'testuser', duration_hours=24)

        # Get session user
        session_user = auth.get_session_user(token)
        assert session_user is not None
        assert session_user['username'] == 'testuser'
        assert session_user['role'] == 'user'
        assert session_user['id'] == user_id

    def test_session_invalid_token(self, auth):
        """Test that invalid tokens return None."""
        session_user = auth.get_session_user('invalid_token_123')
        assert session_user is None

    def test_delete_user_sessions(self, auth):
        """Test deleting all sessions for a user."""
        user_id = auth.create_user('testuser', 'password123', role='user')
        token = auth.create_user_session(user_id, 'testuser', duration_hours=24)

        # Verify session exists
        session_user = auth.get_session_user(token)
        assert session_user is not None

        # Delete all sessions for user
        success = auth.delete_user_sessions(user_id)
        assert success is True

        # Verify session is gone
        session_user = auth.get_session_user(token)
        assert session_user is None

    def test_count_admin_users(self, auth):
        """Test counting admin users."""
        assert auth.count_admin_users() == 0

        auth.create_user('admin1', 'pass123', role='admin')
        assert auth.count_admin_users() == 1

        auth.create_user('admin2', 'pass456', role='admin')
        assert auth.count_admin_users() == 2

        auth.create_user('user1', 'pass789', role='user')
        assert auth.count_admin_users() == 2

    def test_audit_log(self, auth):
        """Test audit logging."""
        auth.log_audit('admin', 'test_action', 'Test details', '127.0.0.1')

        entries = auth.get_audit_log(limit=10)
        assert len(entries) == 1
        assert entries[0]['username'] == 'admin'
        assert entries[0]['action'] == 'test_action'
        assert entries[0]['details'] == 'Test details'
        assert entries[0]['ip_address'] == '127.0.0.1'

    def test_audit_log_filter_by_username(self, auth):
        """Test filtering audit log by username."""
        auth.log_audit('admin', 'action1', 'Details 1', '127.0.0.1')
        auth.log_audit('user1', 'action2', 'Details 2', '127.0.0.1')
        auth.log_audit('admin', 'action3', 'Details 3', '127.0.0.1')

        # Get all entries
        all_entries = auth.get_audit_log()
        assert len(all_entries) == 3

        # Filter by username
        admin_entries = auth.get_audit_log(username='admin')
        assert len(admin_entries) == 2
        assert all(e['username'] == 'admin' for e in admin_entries)

    def test_is_enabled_with_users(self, auth):
        """Test that auth is enabled when users exist."""
        # No users yet
        assert auth.is_enabled() is False

        # Create user
        auth.create_user('admin', 'password123', role='admin')
        assert auth.is_enabled() is True

    def test_migration_from_single_user(self):
        """Test migration from single-user auth_config to multi-user."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        try:
            # Create legacy single-user auth
            import sqlite3
            import bcrypt
            db = sqlite3.connect(db_path)
            db.execute('''
                CREATE TABLE IF NOT EXISTS auth_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER DEFAULT 0,
                    username TEXT,
                    password_hash TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            ''')

            password_hash = bcrypt.hashpw(b'oldpassword', bcrypt.gensalt()).decode('utf-8')
            db.execute(
                'INSERT INTO auth_config (id, enabled, username, password_hash, created_at, updated_at) VALUES (1, 1, ?, ?, 1234567890, 1234567890)',
                ('oldadmin', password_hash)
            )
            db.commit()
            db.close()

            # Initialize AuthManager (should trigger migration)
            auth = AuthManager(db_path=db_path)

            # Verify user was migrated
            users = auth.list_users()
            assert len(users) == 1
            assert users[0]['username'] == 'oldadmin'
            assert users[0]['role'] == 'admin'

            # Verify migrated user can log in
            user = auth.verify_user_credentials('oldadmin', 'oldpassword')
            assert user is not None

            auth.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestRBACDecorator:
    """Test role-based access control decorator."""

    @pytest.fixture
    def app(self):
        """Create Flask app for testing RBAC."""
        # Create temporary database for testing
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            test_db_path = f.name

        # Set test database path
        os.environ['PYTEST_TEST_AUTH'] = '1'

        app = create_app()
        app.config['TESTING'] = True
        app.config['SCIDK_SETTINGS_DB'] = test_db_path

        yield app

        # Cleanup
        os.environ.pop('PYTEST_TEST_AUTH', None)
        if os.path.exists(test_db_path):
            os.unlink(test_db_path)

    @pytest.fixture
    def auth(self, app):
        """Get AuthManager instance."""
        db_path = app.config['SCIDK_SETTINGS_DB']
        from scidk.core.auth import get_auth_manager
        return get_auth_manager(db_path=db_path)

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    def test_require_admin_decorator_allows_admin(self, client, auth):
        """Test that @require_admin allows admin users."""
        # Create admin user
        user_id = auth.create_user('admin', 'password123', role='admin')
        token = auth.create_user_session(user_id, 'admin')

        # Make request with admin token
        response = client.get('/api/users', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200

    def test_require_admin_decorator_blocks_user(self, client, auth):
        """Test that @require_admin blocks regular users."""
        # Create regular user
        user_id = auth.create_user('user', 'password123', role='user')
        token = auth.create_user_session(user_id, 'user')

        # Make request with user token
        response = client.get('/api/users', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 403
        data = response.get_json()
        assert 'error' in data
        assert 'permission' in data['error'].lower()

    def test_require_admin_decorator_blocks_unauthenticated(self, client):
        """Test that @require_admin blocks unauthenticated requests."""
        response = client.get('/api/users')
        assert response.status_code == 401

    def test_user_management_endpoints_require_admin(self, client, auth):
        """Test that all user management endpoints require admin role."""
        # Create regular user
        user_id = auth.create_user('user', 'password123', role='user')
        token = auth.create_user_session(user_id, 'user')
        headers = {'Authorization': f'Bearer {token}'}

        # All these should return 403
        assert client.get('/api/users', headers=headers).status_code == 403
        assert client.get('/api/users/1', headers=headers).status_code == 403
        assert client.post('/api/users', json={'username': 'test', 'password': 'test'}, headers=headers).status_code == 403
        assert client.put('/api/users/1', json={'enabled': False}, headers=headers).status_code == 403
        assert client.delete('/api/users/1', headers=headers).status_code == 403

    def test_audit_log_endpoint_requires_admin(self, client, auth):
        """Test that audit log endpoint requires admin role."""
        # Create regular user
        user_id = auth.create_user('user', 'password123', role='user')
        token = auth.create_user_session(user_id, 'user')
        headers = {'Authorization': f'Bearer {token}'}

        response = client.get('/api/audit-log', headers=headers)
        assert response.status_code == 403
