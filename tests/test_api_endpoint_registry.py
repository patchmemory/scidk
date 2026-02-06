"""
Tests for API Endpoint Registry.

Tests CRUD operations, encryption, and validation.
"""
import pytest
import tempfile
import os
from scidk.core.api_endpoint_registry import APIEndpointRegistry, get_encryption_key
from cryptography.fernet import Fernet


@pytest.fixture
def registry():
    """Create a temporary registry for testing."""
    # Use temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    # Generate test encryption key
    encryption_key = Fernet.generate_key().decode()

    reg = APIEndpointRegistry(db_path=db_path, encryption_key=encryption_key)

    yield reg

    # Cleanup
    reg.db.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_create_endpoint(registry):
    """Test creating a new API endpoint."""
    endpoint_data = {
        'name': 'Test API',
        'url': 'https://api.example.com/users',
        'auth_method': 'bearer',
        'auth_value': 'secret_token_123',
        'json_path': '$.data[*]',
        'target_label': 'User',
        'field_mappings': {
            'email': 'email',
            'full_name': 'name'
        }
    }

    endpoint = registry.create_endpoint(endpoint_data)

    assert endpoint['id'] is not None
    assert endpoint['name'] == 'Test API'
    assert endpoint['url'] == 'https://api.example.com/users'
    assert endpoint['auth_method'] == 'bearer'
    assert endpoint['json_path'] == '$.data[*]'
    assert endpoint['target_label'] == 'User'
    assert endpoint['field_mappings'] == {'email': 'email', 'full_name': 'name'}
    assert 'auth_value' not in endpoint  # Should not be included by default


def test_create_endpoint_validation(registry):
    """Test endpoint creation validation."""
    # Missing name
    with pytest.raises(ValueError, match="Endpoint name is required"):
        registry.create_endpoint({'url': 'https://example.com'})

    # Missing URL
    with pytest.raises(ValueError, match="Endpoint URL is required"):
        registry.create_endpoint({'name': 'Test'})


def test_create_duplicate_name(registry):
    """Test that duplicate names are rejected."""
    data = {
        'name': 'Duplicate Test',
        'url': 'https://api.example.com/users'
    }

    # First creation should succeed
    registry.create_endpoint(data)

    # Second creation with same name should fail
    with pytest.raises(ValueError, match="already exists"):
        registry.create_endpoint(data)


def test_get_endpoint(registry):
    """Test retrieving an endpoint by ID."""
    data = {
        'name': 'Get Test',
        'url': 'https://api.example.com/data'
    }

    created = registry.create_endpoint(data)
    endpoint_id = created['id']

    retrieved = registry.get_endpoint(endpoint_id)

    assert retrieved is not None
    assert retrieved['id'] == endpoint_id
    assert retrieved['name'] == 'Get Test'


def test_get_nonexistent_endpoint(registry):
    """Test getting a nonexistent endpoint returns None."""
    result = registry.get_endpoint('nonexistent-id')
    assert result is None


def test_get_endpoint_by_name(registry):
    """Test retrieving an endpoint by name."""
    data = {
        'name': 'Name Search Test',
        'url': 'https://api.example.com/search'
    }

    created = registry.create_endpoint(data)
    retrieved = registry.get_endpoint_by_name('Name Search Test')

    assert retrieved is not None
    assert retrieved['id'] == created['id']
    assert retrieved['name'] == 'Name Search Test'


def test_list_endpoints(registry):
    """Test listing all endpoints."""
    # Create multiple endpoints
    registry.create_endpoint({'name': 'API 1', 'url': 'https://example.com/1'})
    registry.create_endpoint({'name': 'API 2', 'url': 'https://example.com/2'})
    registry.create_endpoint({'name': 'API 3', 'url': 'https://example.com/3'})

    endpoints = registry.list_endpoints()

    assert len(endpoints) == 3
    names = [e['name'] for e in endpoints]
    assert 'API 1' in names
    assert 'API 2' in names
    assert 'API 3' in names


def test_list_endpoints_empty(registry):
    """Test listing endpoints when none exist."""
    endpoints = registry.list_endpoints()
    assert endpoints == []


def test_update_endpoint(registry):
    """Test updating an endpoint."""
    data = {
        'name': 'Original Name',
        'url': 'https://example.com/original',
        'auth_method': 'none'
    }

    created = registry.create_endpoint(data)
    endpoint_id = created['id']

    # Update
    updates = {
        'name': 'Updated Name',
        'url': 'https://example.com/updated',
        'auth_method': 'bearer',
        'auth_value': 'new_token',
        'target_label': 'UpdatedLabel'
    }

    updated = registry.update_endpoint(endpoint_id, updates)

    assert updated['name'] == 'Updated Name'
    assert updated['url'] == 'https://example.com/updated'
    assert updated['auth_method'] == 'bearer'
    assert updated['target_label'] == 'UpdatedLabel'


def test_update_nonexistent_endpoint(registry):
    """Test updating a nonexistent endpoint raises error."""
    with pytest.raises(ValueError, match="not found"):
        registry.update_endpoint('nonexistent-id', {'name': 'Test'})


def test_update_endpoint_name_conflict(registry):
    """Test that renaming to an existing name is rejected."""
    registry.create_endpoint({'name': 'Endpoint 1', 'url': 'https://example.com/1'})
    created2 = registry.create_endpoint({'name': 'Endpoint 2', 'url': 'https://example.com/2'})

    # Try to rename Endpoint 2 to Endpoint 1
    with pytest.raises(ValueError, match="already exists"):
        registry.update_endpoint(created2['id'], {'name': 'Endpoint 1'})


def test_delete_endpoint(registry):
    """Test deleting an endpoint."""
    data = {
        'name': 'Delete Test',
        'url': 'https://example.com/delete'
    }

    created = registry.create_endpoint(data)
    endpoint_id = created['id']

    # Verify it exists
    assert registry.get_endpoint(endpoint_id) is not None

    # Delete
    result = registry.delete_endpoint(endpoint_id)
    assert result is True

    # Verify it's gone
    assert registry.get_endpoint(endpoint_id) is None


def test_delete_nonexistent_endpoint(registry):
    """Test deleting a nonexistent endpoint returns False."""
    result = registry.delete_endpoint('nonexistent-id')
    assert result is False


def test_auth_value_encryption(registry):
    """Test that auth values are encrypted at rest."""
    data = {
        'name': 'Encryption Test',
        'url': 'https://example.com/secure',
        'auth_method': 'bearer',
        'auth_value': 'super_secret_token'
    }

    endpoint = registry.create_endpoint(data)
    endpoint_id = endpoint['id']

    # Get decrypted auth value
    decrypted = registry.get_decrypted_auth(endpoint_id)
    assert decrypted == 'super_secret_token'

    # Verify it's encrypted in the database
    cursor = registry.db.execute(
        "SELECT auth_value_encrypted FROM api_endpoints WHERE id = ?",
        (endpoint_id,)
    )
    row = cursor.fetchone()
    encrypted_value = row[0]

    # Encrypted value should be different from original
    assert encrypted_value != 'super_secret_token'
    assert len(encrypted_value) > len('super_secret_token')


def test_auth_value_optional(registry):
    """Test that auth value is optional."""
    data = {
        'name': 'No Auth Test',
        'url': 'https://example.com/public',
        'auth_method': 'none'
    }

    endpoint = registry.create_endpoint(data)
    assert endpoint['auth_method'] == 'none'

    # Getting auth for endpoint with no auth should return None
    decrypted = registry.get_decrypted_auth(endpoint['id'])
    assert decrypted is None


def test_field_mappings_serialization(registry):
    """Test that field mappings are correctly serialized/deserialized."""
    data = {
        'name': 'Mappings Test',
        'url': 'https://example.com/api',
        'field_mappings': {
            'api_field_1': 'label_prop_1',
            'api_field_2': 'label_prop_2',
            'nested.field': 'flat_field'
        }
    }

    endpoint = registry.create_endpoint(data)
    retrieved = registry.get_endpoint(endpoint['id'])

    assert retrieved['field_mappings'] == data['field_mappings']
    assert isinstance(retrieved['field_mappings'], dict)


def test_default_values(registry):
    """Test that optional fields have sensible defaults."""
    data = {
        'name': 'Minimal Test',
        'url': 'https://example.com/minimal'
    }

    endpoint = registry.create_endpoint(data)

    assert endpoint['auth_method'] == 'none'
    assert endpoint['json_path'] == ''
    assert endpoint['target_label'] == ''
    assert endpoint['field_mappings'] == {}


def test_get_encryption_key_from_env(monkeypatch):
    """Test getting encryption key from environment variable."""
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv('SCIDK_API_ENCRYPTION_KEY', test_key)

    key = get_encryption_key()
    assert key == test_key


def test_get_encryption_key_generates_ephemeral(monkeypatch):
    """Test that encryption key is generated when not in environment."""
    monkeypatch.delenv('SCIDK_API_ENCRYPTION_KEY', raising=False)

    key = get_encryption_key()
    assert key is not None
    assert len(key) > 0

    # Verify it's a valid Fernet key
    Fernet(key.encode())  # Should not raise
