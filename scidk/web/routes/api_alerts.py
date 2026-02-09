"""
Blueprint for Alerts API routes.

Provides REST endpoints for:
- Alert definitions CRUD
- Alert testing
- Alert history
- SMTP configuration
"""
from flask import Blueprint, jsonify, request, current_app
from ..decorators import require_admin

bp = Blueprint('alerts', __name__, url_prefix='/api')


def _get_alert_manager():
    """Get or create AlertManager instance."""
    from ...core.alert_manager import AlertManager, get_encryption_key

    if 'alert_manager' not in current_app.extensions.get('scidk', {}):
        if 'scidk' not in current_app.extensions:
            current_app.extensions['scidk'] = {}

        # Get settings DB path
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        encryption_key = get_encryption_key()

        current_app.extensions['scidk']['alert_manager'] = AlertManager(
            db_path=settings_db,
            encryption_key=encryption_key
        )

    return current_app.extensions['scidk']['alert_manager']


@bp.route('/settings/alerts', methods=['GET'])
@require_admin
def list_alerts():
    """
    Get all alert definitions.

    Returns:
    {
        "status": "success",
        "alerts": [...]
    }
    """
    try:
        manager = _get_alert_manager()
        enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
        alerts = manager.list_alerts(enabled_only=enabled_only)

        return jsonify({
            'status': 'success',
            'alerts': alerts
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/alerts/<alert_id>', methods=['GET'])
@require_admin
def get_alert(alert_id):
    """
    Get a specific alert by ID.

    Returns:
    {
        "status": "success",
        "alert": {...}
    }
    """
    try:
        manager = _get_alert_manager()
        alert = manager.get_alert(alert_id)

        if not alert:
            return jsonify({
                'status': 'error',
                'error': f'Alert "{alert_id}" not found'
            }), 404

        return jsonify({
            'status': 'success',
            'alert': alert
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/alerts', methods=['POST'])
@require_admin
def create_alert():
    """
    Create new alert definition.

    Request body:
    {
        "name": "My Alert",
        "condition_type": "import_failed",
        "action_type": "email",
        "recipients": ["user@example.com"],
        "threshold": 50.0
    }

    Returns:
    {
        "status": "success",
        "alert_id": "uuid"
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required = ['name', 'condition_type', 'action_type']
        for field in required:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'error': f'Missing required field: {field}'
                }), 400

        manager = _get_alert_manager()
        alert_id = manager.create_alert(
            name=data['name'],
            condition_type=data['condition_type'],
            action_type=data['action_type'],
            recipients=data.get('recipients', []),
            threshold=data.get('threshold'),
            created_by=data.get('created_by', 'system')
        )

        return jsonify({
            'status': 'success',
            'alert_id': alert_id
        }), 201
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/alerts/<alert_id>', methods=['PUT'])
@require_admin
def update_alert(alert_id):
    """
    Update alert definition.

    Request body:
    {
        "name": "Updated Name",
        "recipients": ["new@example.com"],
        "threshold": 100.0,
        "enabled": true
    }

    Returns:
    {
        "status": "success"
    }
    """
    try:
        data = request.get_json()
        manager = _get_alert_manager()

        # Check if alert exists
        alert = manager.get_alert(alert_id)
        if not alert:
            return jsonify({
                'status': 'error',
                'error': f'Alert "{alert_id}" not found'
            }), 404

        # Update alert
        success = manager.update_alert(alert_id, **data)

        if success:
            return jsonify({
                'status': 'success'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'error': 'No fields to update'
            }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/alerts/<alert_id>', methods=['DELETE'])
@require_admin
def delete_alert(alert_id):
    """
    Delete alert definition.

    Returns:
    {
        "status": "success"
    }
    """
    try:
        manager = _get_alert_manager()
        success = manager.delete_alert(alert_id)

        if success:
            return jsonify({
                'status': 'success'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'error': f'Alert "{alert_id}" not found'
            }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/alerts/<alert_id>/test', methods=['POST'])
@require_admin
def test_alert(alert_id):
    """
    Send test notification for this alert.

    Returns:
    {
        "status": "success",
        "message": "Test alert sent successfully"
    }
    """
    try:
        manager = _get_alert_manager()
        success, error_msg = manager.test_alert(alert_id)

        if success:
            return jsonify({
                'status': 'success',
                'message': 'Test alert sent successfully'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'error': error_msg or 'Failed to send test alert'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/alerts/history', methods=['GET'])
@require_admin
def get_alert_history():
    """
    Get alert trigger history.

    Query params:
    - alert_id: Optional, filter by specific alert
    - limit: Optional, max entries to return (default: 100)

    Returns:
    {
        "status": "success",
        "history": [...]
    }
    """
    try:
        manager = _get_alert_manager()
        alert_id = request.args.get('alert_id')
        limit = int(request.args.get('limit', 100))

        history = manager.get_alert_history(alert_id=alert_id, limit=limit)

        return jsonify({
            'status': 'success',
            'history': history
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# SMTP Configuration endpoints

@bp.route('/settings/smtp', methods=['GET'])
@require_admin
def get_smtp_config():
    """
    Get SMTP configuration (password redacted).

    Returns:
    {
        "status": "success",
        "smtp": {
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "user@example.com",
            "password": "••••••••",
            "from_address": "noreply@example.com",
            "use_tls": true,
            "enabled": true
        }
    }
    """
    try:
        manager = _get_alert_manager()
        smtp_config = manager.get_smtp_config_safe()

        return jsonify({
            'status': 'success',
            'smtp': smtp_config or {}
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/smtp', methods=['POST'])
@require_admin
def update_smtp_config():
    """
    Update SMTP configuration.

    Request body:
    {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "user@example.com",
        "password": "app_password",
        "from_address": "noreply@example.com",
        "use_tls": true,
        "enabled": true
    }

    Returns:
    {
        "status": "success"
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required = ['host', 'port', 'from_address']
        for field in required:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'error': f'Missing required field: {field}'
                }), 400

        manager = _get_alert_manager()
        manager.update_smtp_config(
            host=data['host'],
            port=int(data['port']),
            username=data.get('username', ''),
            password=data.get('password'),  # Can be None to keep existing
            from_address=data['from_address'],
            use_tls=data.get('use_tls', True),
            enabled=data.get('enabled', True)
        )

        return jsonify({
            'status': 'success'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@bp.route('/settings/smtp/test', methods=['POST'])
@require_admin
def test_smtp():
    """
    Send test email to verify SMTP configuration.

    Request body (optional):
    {
        "recipient": "test@example.com"
    }

    Returns:
    {
        "status": "success",
        "message": "Test email sent successfully"
    }
    """
    try:
        data = request.get_json() or {}
        recipient = data.get('recipient')

        manager = _get_alert_manager()
        success, error_msg = manager.test_smtp_config(test_recipient=recipient)

        if success:
            return jsonify({
                'status': 'success',
                'message': 'Test email sent successfully'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'error': error_msg or 'Failed to send test email'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
