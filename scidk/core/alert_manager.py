"""
Alert and notification management system for SciDK.

Manages alert definitions, triggers notifications (email), and tracks alert history.
"""

import sqlite3
import json
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from cryptography.fernet import Fernet


class AlertManager:
    """Manages alert definitions and triggers notifications."""

    def __init__(self, db_path: str, encryption_key: Optional[str] = None):
        """
        Initialize AlertManager.

        Args:
            db_path: Path to settings database
            encryption_key: Fernet key for SMTP password encryption (base64-encoded)
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.db.row_factory = sqlite3.Row

        # Initialize encryption for SMTP passwords
        if encryption_key:
            self.cipher = Fernet(encryption_key.encode())
        else:
            self.cipher = Fernet(Fernet.generate_key())

        self.init_tables()
        self.bootstrap_default_alerts()

    def init_tables(self):
        """Create alert-related tables if they don't exist."""
        # Alert definitions
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                condition_type TEXT NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'email',
                recipients TEXT,
                threshold REAL,
                enabled INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                created_by TEXT
            )
            """
        )

        # Alert history
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                triggered_at REAL NOT NULL,
                condition_details TEXT,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                FOREIGN KEY (alert_id) REFERENCES alerts(id)
            )
            """
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_alert_history_alert ON alert_history(alert_id);")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_alert_history_triggered ON alert_history(triggered_at DESC);")

        # SMTP configuration (singleton)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS smtp_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                host TEXT,
                port INTEGER DEFAULT 587,
                username TEXT,
                password_encrypted TEXT,
                from_address TEXT,
                use_tls INTEGER DEFAULT 1,
                enabled INTEGER DEFAULT 0
            )
            """
        )

        self.db.commit()

    def bootstrap_default_alerts(self):
        """Create default alert definitions if they don't exist."""
        defaults = [
            {
                'name': 'Import Failed',
                'condition_type': 'import_failed',
                'action_type': 'email',
                'recipients': [],
                'threshold': None,
                'description': 'Triggered when a file import or scan operation fails'
            },
            {
                'name': 'High Discrepancies',
                'condition_type': 'high_discrepancies',
                'action_type': 'email',
                'recipients': [],
                'threshold': 50.0,
                'description': 'Triggered when reconciliation finds more than 50 discrepancies'
            },
            {
                'name': 'Backup Failed',
                'condition_type': 'backup_failed',
                'action_type': 'email',
                'recipients': [],
                'threshold': None,
                'description': 'Triggered when a scheduled backup operation fails'
            },
            {
                'name': 'Neo4j Connection Lost',
                'condition_type': 'neo4j_down',
                'action_type': 'email',
                'recipients': [],
                'threshold': None,
                'description': 'Triggered when Neo4j database connection is lost'
            },
            {
                'name': 'Disk Space Critical',
                'condition_type': 'disk_critical',
                'action_type': 'email',
                'recipients': [],
                'threshold': 95.0,
                'description': 'Triggered when disk usage exceeds 95%'
            },
        ]

        for alert_def in defaults:
            # Check if alert with this condition_type already exists
            cur = self.db.execute(
                "SELECT id FROM alerts WHERE condition_type = ?",
                (alert_def['condition_type'],)
            )
            existing = cur.fetchone()

            if not existing:
                alert_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc).timestamp()
                recipients_json = json.dumps(alert_def['recipients'])

                self.db.execute(
                    """
                    INSERT INTO alerts (id, name, condition_type, action_type, recipients, threshold, enabled, created_at, updated_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 'system')
                    """,
                    (alert_id, alert_def['name'], alert_def['condition_type'], alert_def['action_type'],
                     recipients_json, alert_def['threshold'], now, now)
                )

        self.db.commit()

    def list_alerts(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all alert definitions."""
        query = "SELECT * FROM alerts"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"

        cur = self.db.execute(query)
        rows = cur.fetchall()

        alerts = []
        for row in rows:
            alerts.append({
                'id': row['id'],
                'name': row['name'],
                'condition_type': row['condition_type'],
                'action_type': row['action_type'],
                'recipients': json.loads(row['recipients']) if row['recipients'] else [],
                'threshold': row['threshold'],
                'enabled': bool(row['enabled']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'created_by': row['created_by']
            })

        return alerts

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get alert by ID."""
        cur = self.db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        row = cur.fetchone()

        if not row:
            return None

        return {
            'id': row['id'],
            'name': row['name'],
            'condition_type': row['condition_type'],
            'action_type': row['action_type'],
            'recipients': json.loads(row['recipients']) if row['recipients'] else [],
            'threshold': row['threshold'],
            'enabled': bool(row['enabled']),
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'created_by': row['created_by']
        }

    def create_alert(self, name: str, condition_type: str, action_type: str,
                     recipients: List[str], threshold: Optional[float] = None,
                     created_by: str = 'system') -> str:
        """Create new alert definition."""
        alert_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).timestamp()
        recipients_json = json.dumps(recipients)

        self.db.execute(
            """
            INSERT INTO alerts (id, name, condition_type, action_type, recipients, threshold, enabled, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (alert_id, name, condition_type, action_type, recipients_json, threshold, now, now, created_by)
        )
        self.db.commit()

        return alert_id

    def update_alert(self, alert_id: str, **kwargs) -> bool:
        """Update alert definition."""
        allowed_fields = ['name', 'action_type', 'recipients', 'threshold', 'enabled']
        updates = []
        params = []

        for field in allowed_fields:
            if field in kwargs:
                if field == 'recipients':
                    updates.append(f"{field} = ?")
                    params.append(json.dumps(kwargs[field]))
                elif field == 'enabled':
                    updates.append(f"{field} = ?")
                    params.append(1 if kwargs[field] else 0)
                else:
                    updates.append(f"{field} = ?")
                    params.append(kwargs[field])

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).timestamp())
        params.append(alert_id)

        query = f"UPDATE alerts SET {', '.join(updates)} WHERE id = ?"
        cursor = self.db.execute(query, params)
        self.db.commit()

        return cursor.rowcount > 0

    def delete_alert(self, alert_id: str) -> bool:
        """Delete alert definition."""
        cursor = self.db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def check_alerts(self, condition_type: str, details: Dict[str, Any]) -> List[str]:
        """
        Check if any alerts match this condition and trigger them.

        Args:
            condition_type: Type of condition (e.g., 'import_failed')
            details: Context about the condition (e.g., error message, counts)

        Returns:
            List of alert IDs that were triggered
        """
        alerts = self.list_alerts(enabled_only=True)
        triggered = []

        for alert in alerts:
            if alert['condition_type'] != condition_type:
                continue

            # Check threshold if applicable
            if alert.get('threshold') is not None:
                value = details.get('value')
                if value is None or value < alert['threshold']:
                    continue

            # Check if recipients are configured
            if not alert.get('recipients'):
                continue

            # Trigger alert
            success, error_msg = self._trigger_alert(alert, details)
            self._log_alert_history(alert['id'], details, success, error_msg)

            if success:
                triggered.append(alert['id'])

        return triggered

    def _trigger_alert(self, alert: Dict[str, Any], details: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Send notification for this alert.

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        action_type = alert['action_type']

        if action_type == 'email':
            return self._send_email_alert(alert, details)
        elif action_type == 'webhook':
            return self._send_webhook_alert(alert, details)
        elif action_type == 'log':
            return self._log_alert(alert, details)
        else:
            return False, f"Unknown action type: {action_type}"

    def _send_email_alert(self, alert: Dict[str, Any], details: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Send email notification."""
        smtp_config = self.get_smtp_config()
        if not smtp_config or not smtp_config.get('enabled'):
            return False, "SMTP not configured or disabled"

        recipients = alert.get('recipients', [])
        if not recipients:
            return False, "No recipients configured"

        # Compose email
        subject = f"SciDK Alert: {alert['name']}"
        body = self._format_email_body(alert, details)

        msg = MIMEMultipart()
        msg['From'] = smtp_config['from_address']
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        try:
            with smtplib.SMTP(smtp_config['host'], smtp_config['port'], timeout=10) as server:
                if smtp_config.get('use_tls'):
                    server.starttls()
                if smtp_config.get('username') and smtp_config.get('password_encrypted'):
                    password = self._decrypt_password(smtp_config['password_encrypted'])
                    server.login(smtp_config['username'], password)
                server.send_message(msg)
            return True, None
        except Exception as e:
            error_msg = f"Failed to send email: {str(e)}"
            print(error_msg)
            return False, error_msg

    def _format_email_body(self, alert: Dict[str, Any], details: Dict[str, Any]) -> str:
        """Format email body with alert details."""
        is_test = details.get('test', False)
        test_banner = '<div style="background: #ffc107; color: #000; padding: 0.75rem; margin-bottom: 1rem; border-radius: 4px;"><strong>⚠️ TEST ALERT</strong> - This is a test notification</div>' if is_test else ''

        details_html = '<ul>'
        for k, v in details.items():
            if k != 'test':  # Skip the test flag in details
                details_html += f'<li><strong>{k}:</strong> {v}</li>'
        details_html += '</ul>'

        return f"""
        <html>
        <body style="font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; color: #333;">
        {test_banner}
        <h2 style="color: #d32f2f;">Alert: {alert['name']}</h2>
        <p><strong>Condition:</strong> {alert['condition_type']}</p>
        <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

        <h3>Details:</h3>
        {details_html}

        <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">
        <p style="color: #666; font-size: 0.9em;">
        Generated by SciDK Alert System<br>
        <a href="http://localhost:5000/settings/alerts">Configure Alerts</a>
        </p>
        </body>
        </html>
        """

    def _send_webhook_alert(self, alert: Dict[str, Any], details: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Send webhook notification (placeholder for future implementation)."""
        # TODO: Implement webhook notifications
        return False, "Webhook notifications not yet implemented"

    def _log_alert(self, alert: Dict[str, Any], details: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Log alert to system logs."""
        log_msg = f"ALERT: {alert['name']} - {alert['condition_type']} - {json.dumps(details)}"
        print(log_msg)
        return True, None

    def _log_alert_history(self, alert_id: str, details: Dict[str, Any], success: bool, error_message: Optional[str] = None):
        """Log alert trigger to history."""
        now = datetime.now(timezone.utc).timestamp()
        condition_details_json = json.dumps(details)

        self.db.execute(
            """
            INSERT INTO alert_history (alert_id, triggered_at, condition_details, success, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert_id, now, condition_details_json, 1 if success else 0, error_message)
        )
        self.db.commit()

    def test_alert(self, alert_id: str) -> tuple[bool, Optional[str]]:
        """
        Send test notification for this alert.

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        alert = self.get_alert(alert_id)
        if not alert:
            return False, "Alert not found"

        test_details = {
            'test': True,
            'message': 'This is a test alert from SciDK',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        success, error_msg = self._trigger_alert(alert, test_details)
        self._log_alert_history(alert['id'], test_details, success, error_msg)

        return success, error_msg

    def get_alert_history(self, alert_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get alert trigger history.

        Args:
            alert_id: Optional alert ID to filter by
            limit: Maximum number of entries to return

        Returns:
            List of alert history entries
        """
        if alert_id:
            query = "SELECT * FROM alert_history WHERE alert_id = ? ORDER BY triggered_at DESC LIMIT ?"
            params = (alert_id, limit)
        else:
            query = "SELECT * FROM alert_history ORDER BY triggered_at DESC LIMIT ?"
            params = (limit,)

        cur = self.db.execute(query, params)
        rows = cur.fetchall()

        history = []
        for row in rows:
            history.append({
                'id': row['id'],
                'alert_id': row['alert_id'],
                'triggered_at': row['triggered_at'],
                'triggered_at_iso': datetime.fromtimestamp(row['triggered_at'], tz=timezone.utc).isoformat(),
                'condition_details': json.loads(row['condition_details']) if row['condition_details'] else {},
                'success': bool(row['success']),
                'error_message': row['error_message']
            })

        return history

    # SMTP Configuration methods

    def get_smtp_config(self) -> Optional[Dict[str, Any]]:
        """Get SMTP configuration (password redacted)."""
        cur = self.db.execute("SELECT * FROM smtp_config WHERE id = 1")
        row = cur.fetchone()

        if not row:
            return None

        return {
            'host': row['host'],
            'port': row['port'],
            'username': row['username'],
            'password_encrypted': row['password_encrypted'],  # Don't expose this directly
            'from_address': row['from_address'],
            'use_tls': bool(row['use_tls']),
            'enabled': bool(row['enabled'])
        }

    def get_smtp_config_safe(self) -> Optional[Dict[str, Any]]:
        """Get SMTP configuration with password redacted (safe for API responses)."""
        config = self.get_smtp_config()
        if config:
            config['password'] = '••••••••' if config.get('password_encrypted') else ''
            del config['password_encrypted']
        return config

    def update_smtp_config(self, host: str, port: int, username: str, password: Optional[str],
                           from_address: str, use_tls: bool = True, enabled: bool = True) -> bool:
        """Update SMTP configuration."""
        # Encrypt password if provided
        password_encrypted = None
        if password:
            password_encrypted = self._encrypt_password(password)

        # Check if config exists
        cur = self.db.execute("SELECT id FROM smtp_config WHERE id = 1")
        exists = cur.fetchone()

        if exists:
            # Update existing
            if password:
                # Update with new password
                self.db.execute(
                    """
                    UPDATE smtp_config
                    SET host = ?, port = ?, username = ?, password_encrypted = ?, from_address = ?, use_tls = ?, enabled = ?
                    WHERE id = 1
                    """,
                    (host, port, username, password_encrypted, from_address, 1 if use_tls else 0, 1 if enabled else 0)
                )
            else:
                # Keep existing password
                self.db.execute(
                    """
                    UPDATE smtp_config
                    SET host = ?, port = ?, username = ?, from_address = ?, use_tls = ?, enabled = ?
                    WHERE id = 1
                    """,
                    (host, port, username, from_address, 1 if use_tls else 0, 1 if enabled else 0)
                )
        else:
            # Insert new
            self.db.execute(
                """
                INSERT INTO smtp_config (id, host, port, username, password_encrypted, from_address, use_tls, enabled)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (host, port, username, password_encrypted, from_address, 1 if use_tls else 0, 1 if enabled else 0)
            )

        self.db.commit()
        return True

    def test_smtp_config(self, test_recipient: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Test SMTP configuration by sending a test email.

        Args:
            test_recipient: Email address to send test to. If None, uses from_address

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        smtp_config = self.get_smtp_config()
        if not smtp_config or not smtp_config.get('enabled'):
            return False, "SMTP not configured or disabled"

        recipient = test_recipient or smtp_config['from_address']
        subject = "SciDK SMTP Test"
        body = f"""
        <html>
        <body style="font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #4caf50;">✓ SMTP Configuration Test</h2>
        <p>This is a test email from SciDK to verify your SMTP configuration.</p>
        <p><strong>Time:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        <p><strong>SMTP Host:</strong> {smtp_config['host']}:{smtp_config['port']}</p>
        <p><strong>From Address:</strong> {smtp_config['from_address']}</p>
        <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">
        <p style="color: #666; font-size: 0.9em;">
        If you received this email, your SMTP configuration is working correctly.
        </p>
        </body>
        </html>
        """

        msg = MIMEMultipart()
        msg['From'] = smtp_config['from_address']
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        try:
            with smtplib.SMTP(smtp_config['host'], smtp_config['port'], timeout=10) as server:
                if smtp_config.get('use_tls'):
                    server.starttls()
                if smtp_config.get('username') and smtp_config.get('password_encrypted'):
                    password = self._decrypt_password(smtp_config['password_encrypted'])
                    server.login(smtp_config['username'], password)
                server.send_message(msg)
            return True, None
        except Exception as e:
            error_msg = f"SMTP test failed: {str(e)}"
            print(error_msg)
            return False, error_msg

    def _encrypt_password(self, password: str) -> str:
        """Encrypt password using Fernet."""
        return self.cipher.encrypt(password.encode()).decode()

    def _decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt password using Fernet."""
        return self.cipher.decrypt(encrypted_password.encode()).decode()


def get_encryption_key() -> str:
    """Get or generate encryption key for alert manager."""
    import os
    key = os.environ.get('SCIDK_ENCRYPTION_KEY')
    if not key:
        # Generate and store key (in production, this should be persisted securely)
        key = Fernet.generate_key().decode()
    return key
