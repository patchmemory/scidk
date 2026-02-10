"""
Tests for Alerts API routes (/api/settings/alerts).
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def admin_client(client):
    """Create a client with admin privileges."""
    with patch('scidk.web.decorators.require_admin', lambda f: f):
        yield client


def test_list_alerts_empty(admin_client):
    """Test listing alerts when none exist."""
    resp = admin_client.get('/api/settings/alerts')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert 'alerts' in data
    assert isinstance(data['alerts'], list)


def test_create_alert(admin_client):
    """Test creating a new alert."""
    alert_data = {
        'name': 'Test Alert',
        'condition_type': 'threshold',
        'threshold': 100,
        'action_type': 'email',
        'recipients': ['test@example.com'],
        'enabled': True
    }

    resp = admin_client.post('/api/settings/alerts', json=alert_data)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['status'] == 'success'
    assert 'alert_id' in data


def test_create_alert_missing_name(admin_client):
    """Test creating alert without required name."""
    alert_data = {
        'condition_type': 'threshold',
        'action_type': 'email'
    }

    resp = admin_client.post('/api/settings/alerts', json=alert_data)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['status'] == 'error'


def test_get_alert(admin_client):
    """Test getting a specific alert."""
    # First create an alert
    alert_data = {
        'name': 'Get Test',
        'condition_type': 'threshold',
        'action_type': 'log'
    }
    create_resp = admin_client.post('/api/settings/alerts', json=alert_data)
    alert_id = create_resp.get_json()['alert_id']

    # Now get it
    resp = admin_client.get(f'/api/settings/alerts/{alert_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert data['alert']['name'] == 'Get Test'


def test_get_alert_not_found(admin_client):
    """Test getting a non-existent alert."""
    resp = admin_client.get('/api/settings/alerts/nonexistent-id')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['status'] == 'error'


def test_update_alert(admin_client):
    """Test updating an existing alert."""
    # Create alert
    alert_data = {
        'name': 'Original Name',
        'condition_type': 'threshold',
        'action_type': 'log'
    }
    create_resp = admin_client.post('/api/settings/alerts', json=alert_data)
    alert_id = create_resp.get_json()['alert_id']

    # Update it
    update_data = {'name': 'Updated Name', 'enabled': False}
    resp = admin_client.put(f'/api/settings/alerts/{alert_id}', json=update_data)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'

    # Verify update
    get_resp = admin_client.get(f'/api/settings/alerts/{alert_id}')
    alert = get_resp.get_json()['alert']
    assert alert['name'] == 'Updated Name'
    assert alert['enabled'] is False


def test_delete_alert(admin_client):
    """Test deleting an alert."""
    # Create alert
    alert_data = {
        'name': 'To Delete',
        'condition_type': 'threshold',
        'action_type': 'log'
    }
    create_resp = admin_client.post('/api/settings/alerts', json=alert_data)
    alert_id = create_resp.get_json()['alert_id']

    # Delete it
    resp = admin_client.delete(f'/api/settings/alerts/{alert_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'

    # Verify it's gone
    get_resp = admin_client.get(f'/api/settings/alerts/{alert_id}')
    assert get_resp.status_code == 404


@patch('smtplib.SMTP')
def test_test_alert(mock_smtp, admin_client):
    """Test the alert testing functionality."""
    # Configure SMTP first
    smtp_config = {
        'host': 'smtp.test.com',
        'port': 587,
        'username': 'test@test.com',
        'password': 'test123',
        'from_address': 'noreply@test.com',
        'use_tls': True,
        'enabled': True,
        'recipients': ['admin@test.com']
    }
    admin_client.post('/api/settings/smtp', json=smtp_config)

    # Create an email alert
    alert_data = {
        'name': 'Test Email Alert',
        'condition_type': 'test',
        'action_type': 'email',
        'recipients': ['recipient@test.com']
    }
    create_resp = admin_client.post('/api/settings/alerts', json=alert_data)
    alert_id = create_resp.get_json()['alert_id']

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Test the alert
    resp = admin_client.post(f'/api/settings/alerts/{alert_id}/test')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'


def test_alert_history(admin_client):
    """Test getting alert history."""
    # Create and trigger an alert
    alert_data = {
        'name': 'History Test',
        'condition_type': 'threshold',
        'threshold': 50,
        'action_type': 'log',
        'enabled': True
    }
    create_resp = admin_client.post('/api/settings/alerts', json=alert_data)
    alert_id = create_resp.get_json()['alert_id']

    # Get history (all alerts)
    resp = admin_client.get('/api/settings/alerts/history')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert 'history' in data
    assert isinstance(data['history'], list)

    # Get history for specific alert
    resp2 = admin_client.get(f'/api/settings/alerts/history?alert_id={alert_id}')
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2['status'] == 'success'


def test_smtp_config_get(admin_client):
    """Test getting SMTP configuration."""
    resp = admin_client.get('/api/settings/smtp')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert 'smtp' in data


def test_smtp_config_update(admin_client):
    """Test updating SMTP configuration."""
    smtp_config = {
        'host': 'smtp.gmail.com',
        'port': 587,
        'username': 'user@gmail.com',
        'password': 'app_password',
        'from_address': 'noreply@example.com',
        'use_tls': True,
        'enabled': True,
        'recipients': ['admin@example.com']
    }

    resp = admin_client.post('/api/settings/smtp', json=smtp_config)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'

    # Verify config was saved (password should be redacted)
    get_resp = admin_client.get('/api/settings/smtp')
    smtp_data = get_resp.get_json()['smtp']
    assert smtp_data['host'] == 'smtp.gmail.com'
    assert smtp_data['password'] == '••••••••'  # Redacted


@patch('scidk.core.alert_manager.smtplib.SMTP')
def test_smtp_test(mock_smtp, admin_client):
    """Test SMTP connection testing."""
    # Configure SMTP
    smtp_config = {
        'host': 'smtp.test.com',
        'port': 587,
        'username': 'test@test.com',
        'password': 'test123',
        'from_address': 'noreply@test.com',
        'use_tls': True,
        'enabled': True,
        'recipients': ['admin@test.com']
    }
    admin_client.post('/api/settings/smtp', json=smtp_config)

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Test connection with recipient
    resp = admin_client.post('/api/settings/smtp/test', json={'recipient': 'test@example.com'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
