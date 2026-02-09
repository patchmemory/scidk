"""
Tests for alert management functionality.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from scidk.core.alert_manager import AlertManager


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
def alert_manager(temp_db):
    """Create an AlertManager instance for testing."""
    return AlertManager(temp_db)


def test_alert_manager_init(alert_manager):
    """Test AlertManager initialization."""
    assert alert_manager is not None
    assert alert_manager.db_path is not None

    # Check that default alerts were created
    alerts = alert_manager.list_alerts()
    assert len(alerts) == 5  # 5 default alerts

    # Verify default alert types
    condition_types = [a['condition_type'] for a in alerts]
    assert 'import_failed' in condition_types
    assert 'high_discrepancies' in condition_types
    assert 'backup_failed' in condition_types
    assert 'neo4j_down' in condition_types
    assert 'disk_critical' in condition_types


def test_create_alert(alert_manager):
    """Test creating a new alert."""
    alert_id = alert_manager.create_alert(
        name='Test Alert',
        condition_type='test_condition',
        action_type='email',
        recipients=['test@example.com'],
        threshold=100.0,
        created_by='test_user'
    )

    assert alert_id is not None
    assert len(alert_id) > 0

    # Verify alert was created
    alert = alert_manager.get_alert(alert_id)
    assert alert is not None
    assert alert['name'] == 'Test Alert'
    assert alert['condition_type'] == 'test_condition'
    assert alert['action_type'] == 'email'
    assert alert['recipients'] == ['test@example.com']
    assert alert['threshold'] == 100.0
    assert alert['enabled'] is True


def test_list_alerts(alert_manager):
    """Test listing alerts."""
    # Should have default alerts
    all_alerts = alert_manager.list_alerts()
    assert len(all_alerts) >= 5

    # Create and enable a custom alert
    alert_id = alert_manager.create_alert(
        name='Enabled Alert',
        condition_type='test',
        action_type='email',
        recipients=['test@example.com']
    )

    # Create and disable another alert
    alert_id2 = alert_manager.create_alert(
        name='Disabled Alert',
        condition_type='test2',
        action_type='email',
        recipients=['test@example.com']
    )
    alert_manager.update_alert(alert_id2, enabled=False)

    # Test enabled_only filter
    enabled_alerts = alert_manager.list_alerts(enabled_only=True)
    alert_names = [a['name'] for a in enabled_alerts]
    assert 'Enabled Alert' in alert_names
    assert 'Disabled Alert' not in alert_names


def test_update_alert(alert_manager):
    """Test updating an alert."""
    # Create alert
    alert_id = alert_manager.create_alert(
        name='Original Name',
        condition_type='test',
        action_type='email',
        recipients=['old@example.com']
    )

    # Update alert
    success = alert_manager.update_alert(
        alert_id,
        name='Updated Name',
        recipients=['new@example.com'],
        threshold=50.0,
        enabled=False
    )

    assert success is True

    # Verify updates
    alert = alert_manager.get_alert(alert_id)
    assert alert['name'] == 'Updated Name'
    assert alert['recipients'] == ['new@example.com']
    assert alert['threshold'] == 50.0
    assert alert['enabled'] is False


def test_delete_alert(alert_manager):
    """Test deleting an alert."""
    # Create alert
    alert_id = alert_manager.create_alert(
        name='To Delete',
        condition_type='test',
        action_type='email',
        recipients=['test@example.com']
    )

    # Verify it exists
    assert alert_manager.get_alert(alert_id) is not None

    # Delete it
    success = alert_manager.delete_alert(alert_id)
    assert success is True

    # Verify it's gone
    assert alert_manager.get_alert(alert_id) is None

    # Try deleting non-existent alert
    success = alert_manager.delete_alert('nonexistent')
    assert success is False


def test_check_alerts_with_threshold(alert_manager):
    """Test checking alerts with threshold conditions."""
    # Create alert with threshold
    alert_id = alert_manager.create_alert(
        name='Threshold Alert',
        condition_type='test_metric',
        action_type='log',  # Use log for testing
        recipients=['test@example.com'],  # Need recipients even for log action
        threshold=50.0
    )

    # Value below threshold should not trigger
    triggered = alert_manager.check_alerts('test_metric', {'value': 30.0})
    assert len(triggered) == 0

    # Value at threshold should trigger
    triggered = alert_manager.check_alerts('test_metric', {'value': 50.0})
    assert len(triggered) == 1
    assert triggered[0] == alert_id

    # Value above threshold should trigger
    triggered = alert_manager.check_alerts('test_metric', {'value': 70.0})
    assert len(triggered) == 1
    assert triggered[0] == alert_id


def test_check_alerts_without_recipients(alert_manager):
    """Test that alerts without recipients don't trigger."""
    # Create alert without recipients
    alert_id = alert_manager.create_alert(
        name='No Recipients',
        condition_type='test',
        action_type='email',
        recipients=[]
    )

    # Should not trigger without recipients
    triggered = alert_manager.check_alerts('test', {'value': 1})
    assert len(triggered) == 0


def test_check_alerts_disabled(alert_manager):
    """Test that disabled alerts don't trigger."""
    # Create and disable alert
    alert_id = alert_manager.create_alert(
        name='Disabled Alert',
        condition_type='test',
        action_type='log',
        recipients=['test@example.com']
    )
    alert_manager.update_alert(alert_id, enabled=False)

    # Should not trigger when disabled
    triggered = alert_manager.check_alerts('test', {'value': 1})
    assert len(triggered) == 0


@patch('smtplib.SMTP')
def test_send_email_alert(mock_smtp, alert_manager):
    """Test sending email alerts."""
    # Configure SMTP
    alert_manager.update_smtp_config(
        host='smtp.test.com',
        port=587,
        username='test@test.com',
        password='test123',
        from_address='noreply@test.com',
        use_tls=True,
        enabled=True
    )

    # Create alert with recipients
    alert_id = alert_manager.create_alert(
        name='Email Test',
        condition_type='test_email',
        action_type='email',
        recipients=['recipient@test.com']
    )

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Trigger alert
    triggered = alert_manager.check_alerts('test_email', {
        'message': 'Test alert',
        'value': 1
    })

    assert len(triggered) == 1
    assert triggered[0] == alert_id

    # Verify SMTP was called
    mock_smtp.assert_called_once()
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once()
    mock_server.send_message.assert_called_once()


def test_alert_history(alert_manager):
    """Test alert history logging."""
    # Create alert
    alert_id = alert_manager.create_alert(
        name='History Test',
        condition_type='test_history',
        action_type='log',
        recipients=['test@example.com']
    )

    # Trigger alert multiple times
    alert_manager.check_alerts('test_history', {'value': 1, 'message': 'First'})
    alert_manager.check_alerts('test_history', {'value': 2, 'message': 'Second'})
    alert_manager.check_alerts('test_history', {'value': 3, 'message': 'Third'})

    # Get history
    history = alert_manager.get_alert_history(alert_id=alert_id)
    assert len(history) == 3

    # Verify history entries (most recent first)
    assert history[0]['condition_details']['message'] == 'Third'
    assert history[1]['condition_details']['message'] == 'Second'
    assert history[2]['condition_details']['message'] == 'First'

    # Get all history
    all_history = alert_manager.get_alert_history()
    assert len(all_history) >= 3


@patch('smtplib.SMTP')
def test_test_alert(mock_smtp, alert_manager):
    """Test the test_alert functionality."""
    # Configure SMTP
    alert_manager.update_smtp_config(
        host='smtp.test.com',
        port=587,
        username='test@test.com',
        password='test123',
        from_address='noreply@test.com',
        use_tls=True,
        enabled=True
    )

    # Create alert
    alert_id = alert_manager.create_alert(
        name='Test Alert',
        condition_type='test',
        action_type='email',
        recipients=['test@example.com']
    )

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Send test alert
    success, error_msg = alert_manager.test_alert(alert_id)
    assert success is True
    assert error_msg is None

    # Verify SMTP was called
    mock_smtp.assert_called_once()
    mock_server.send_message.assert_called_once()

    # Verify history was logged
    history = alert_manager.get_alert_history(alert_id=alert_id)
    assert len(history) == 1
    assert history[0]['condition_details']['test'] is True


def test_smtp_config(alert_manager):
    """Test SMTP configuration management."""
    # Update SMTP config
    alert_manager.update_smtp_config(
        host='smtp.gmail.com',
        port=587,
        username='user@gmail.com',
        password='app_password',
        from_address='noreply@example.com',
        use_tls=True,
        enabled=True
    )

    # Get config (safe version)
    config = alert_manager.get_smtp_config_safe()
    assert config is not None
    assert config['host'] == 'smtp.gmail.com'
    assert config['port'] == 587
    assert config['username'] == 'user@gmail.com'
    assert config['password'] == '••••••••'  # Redacted
    assert config['from_address'] == 'noreply@example.com'
    assert config['use_tls'] is True
    assert config['enabled'] is True

    # Update without changing password
    alert_manager.update_smtp_config(
        host='smtp.test.com',
        port=25,
        username='new@test.com',
        password=None,  # Don't change password
        from_address='noreply@test.com',
        use_tls=False,
        enabled=True
    )

    config = alert_manager.get_smtp_config_safe()
    assert config['host'] == 'smtp.test.com'
    assert config['port'] == 25
    assert config['password'] == '••••••••'  # Still has password


@patch('smtplib.SMTP')
def test_test_smtp_config(mock_smtp, alert_manager):
    """Test SMTP configuration testing."""
    # Configure SMTP
    alert_manager.update_smtp_config(
        host='smtp.test.com',
        port=587,
        username='test@test.com',
        password='test123',
        from_address='noreply@test.com',
        use_tls=True,
        enabled=True
    )

    # Mock SMTP server
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server

    # Test SMTP config
    success, error_msg = alert_manager.test_smtp_config()
    assert success is True
    assert error_msg is None

    # Verify SMTP was called
    mock_smtp.assert_called_once()
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once()
    mock_server.send_message.assert_called_once()


def test_log_action_type(alert_manager):
    """Test alert with log action type."""
    # Create log alert
    alert_id = alert_manager.create_alert(
        name='Log Alert',
        condition_type='test_log',
        action_type='log',
        recipients=['test@example.com']
    )

    # Trigger alert
    triggered = alert_manager.check_alerts('test_log', {
        'message': 'Test log message',
        'value': 1
    })

    assert len(triggered) == 1
    assert triggered[0] == alert_id

    # Verify history
    history = alert_manager.get_alert_history(alert_id=alert_id)
    assert len(history) == 1
    assert history[0]['success'] is True
