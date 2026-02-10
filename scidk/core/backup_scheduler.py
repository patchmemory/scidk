"""
Automated backup scheduler for SciDK.

Manages scheduled backups, verification, and retention policies.
"""

import os
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .backup_manager import BackupManager


class BackupScheduler:
    """Manages automated backup scheduling, verification, and retention."""

    def __init__(
        self,
        backup_manager: BackupManager,
        settings_db_path: str = 'scidk_settings.db',
        alert_manager=None
    ):
        """
        Initialize BackupScheduler.

        Loads schedule and retention settings from database.

        Args:
            backup_manager: BackupManager instance
            settings_db_path: Path to settings database
            alert_manager: Optional AlertManager for notifications
        """
        self.backup_manager = backup_manager
        self.settings_db_path = settings_db_path
        self.alert_manager = alert_manager
        self.scheduler = BackgroundScheduler()
        self._running = False

        # Load settings from database (with defaults)
        self.reload_settings()

    def reload_settings(self):
        """Reload schedule and retention settings from database."""
        import sqlite3

        defaults = {
            'schedule_enabled': True,
            'schedule_hour': 2,
            'schedule_minute': 0,
            'retention_days': 30,
            'verify_backups': True
        }

        try:
            db = sqlite3.connect(self.settings_db_path)
            db.execute('PRAGMA journal_mode=WAL;')

            # Ensure settings table exists
            db.execute('''
                CREATE TABLE IF NOT EXISTS backup_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Load each setting
            for key, default_value in defaults.items():
                cur = db.execute('SELECT value FROM backup_settings WHERE key = ?', (key,))
                row = cur.fetchone()
                if row and row[0] is not None:
                    # Parse value based on type
                    if isinstance(default_value, bool):
                        value = row[0].lower() in ('true', '1', 'yes')
                    elif isinstance(default_value, int):
                        value = int(row[0])
                    else:
                        value = row[0]
                    setattr(self, key, value)
                else:
                    # Use default and save it
                    setattr(self, key, default_value)
                    db.execute(
                        'INSERT OR IGNORE INTO backup_settings (key, value) VALUES (?, ?)',
                        (key, str(default_value))
                    )

            db.commit()
            db.close()
        except Exception:
            # If database fails, use defaults
            for key, default_value in defaults.items():
                setattr(self, key, default_value)

    def start(self):
        """Start the backup scheduler."""
        if self._running:
            return

        # Schedule daily backup
        self.scheduler.add_job(
            self._run_scheduled_backup,
            CronTrigger(hour=self.schedule_hour, minute=self.schedule_minute),
            id='daily_backup',
            replace_existing=True,
            name='Daily Backup'
        )

        self.scheduler.start()
        self._running = True

    def stop(self):
        """Stop the backup scheduler."""
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def _run_scheduled_backup(self):
        """Execute the scheduled backup workflow."""
        try:
            # Create backup
            result = self.backup_manager.create_backup(
                reason='auto',
                created_by='system',
                notes='Automated daily backup'
            )

            if not result['success']:
                # Trigger backup_failed alert
                if self.alert_manager:
                    self.alert_manager.check_alerts('backup_failed', {
                        'error': result.get('error', 'Unknown error'),
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'reason': 'auto',
                        'value': 1
                    })
                return

            backup_id = result['backup_id']

            # Verify backup if enabled
            verification_result = None
            if self.verify_backups:
                verification_result = self.verify_backup(result['filename'])

                # Update backup metadata with verification status
                if verification_result and 'verified' in verification_result:
                    self._update_backup_verification(
                        result['filename'],
                        verification_result['verified'],
                        verification_result.get('error')
                    )

            # Cleanup old backups
            self.cleanup_old_backups()

            # Trigger backup_completed alert if available
            if self.alert_manager:
                try:
                    self.alert_manager.check_alerts('backup_completed', {
                        'backup_id': backup_id,
                        'size': result.get('size', 0),
                        'verified': verification_result.get('verified', False) if verification_result else False,
                        'timestamp': result.get('timestamp'),
                        'value': 1
                    })
                except Exception:
                    # Alert might not be configured
                    pass

        except Exception as e:
            # Log error and trigger alert
            if self.alert_manager:
                try:
                    self.alert_manager.check_alerts('backup_failed', {
                        'error': str(e),
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'reason': 'auto',
                        'value': 1
                    })
                except Exception:
                    pass

    def verify_backup(self, backup_file: str) -> Dict[str, Any]:
        """
        Verify a backup by attempting to read and validate its contents.

        Args:
            backup_file: Backup filename or path

        Returns:
            Dict with verification results
        """
        try:
            # Find the backup file
            if not os.path.isabs(backup_file):
                backup_path = self.backup_manager.backup_dir / backup_file
            else:
                backup_path = Path(backup_file)

            if not backup_path.exists():
                return {
                    'verified': False,
                    'error': f'Backup file not found: {backup_path}'
                }

            # Verify zip integrity
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                # Test zip file integrity
                bad_file = zipf.testzip()
                if bad_file:
                    return {
                        'verified': False,
                        'error': f'Corrupted file in backup: {bad_file}'
                    }

                # Verify metadata exists and is valid JSON
                if 'backup_metadata.json' not in zipf.namelist():
                    return {
                        'verified': False,
                        'error': 'Missing backup_metadata.json'
                    }

                metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
                import json
                metadata = json.loads(metadata_str)

                # Verify expected fields
                required_fields = ['version', 'backup_id', 'timestamp', 'files']
                for field in required_fields:
                    if field not in metadata:
                        return {
                            'verified': False,
                            'error': f'Missing required field: {field}'
                        }

                # Verify all listed files exist in zip
                for file_info in metadata['files']:
                    file_path = file_info['path']
                    if file_path not in zipf.namelist():
                        return {
                            'verified': False,
                            'error': f'Missing file in backup: {file_path}'
                        }

            return {
                'verified': True,
                'backup_id': metadata['backup_id'],
                'files_count': len(metadata['files']),
                'timestamp': metadata['timestamp']
            }

        except zipfile.BadZipFile:
            return {
                'verified': False,
                'error': 'Invalid or corrupted zip file'
            }
        except json.JSONDecodeError:
            return {
                'verified': False,
                'error': 'Invalid JSON in metadata'
            }
        except Exception as e:
            return {
                'verified': False,
                'error': str(e)
            }

    def cleanup_old_backups(self) -> Dict[str, Any]:
        """
        Delete backups older than retention_days.

        Returns:
            Dict with cleanup results
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            deleted_count = 0
            freed_bytes = 0

            # Get all backups
            backups = self.backup_manager.list_backups(limit=1000)

            for backup in backups:
                # Parse timestamp
                try:
                    backup_time = datetime.fromisoformat(backup['timestamp'])
                    if backup_time < cutoff_date:
                        # Delete old backup
                        if self.backup_manager.delete_backup(backup['filename']):
                            deleted_count += 1
                            freed_bytes += backup['size']
                except Exception:
                    # Skip backups with invalid timestamps
                    continue

            return {
                'success': True,
                'deleted_count': deleted_count,
                'freed_bytes': freed_bytes,
                'freed_human': self._human_size(freed_bytes),
                'retention_days': self.retention_days
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _update_backup_verification(self, backup_file: str, verified: bool, error: Optional[str] = None):
        """
        Update backup metadata with verification status.

        Args:
            backup_file: Backup filename
            verified: Whether backup was verified successfully
            error: Optional error message
        """
        try:
            import json

            if not os.path.isabs(backup_file):
                backup_path = self.backup_manager.backup_dir / backup_file
            else:
                backup_path = Path(backup_file)

            if not backup_path.exists():
                return

            # Read existing backup
            temp_dir = tempfile.mkdtemp()
            temp_zip = Path(temp_dir) / 'temp.zip'

            # Extract and update metadata
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
                metadata = json.loads(metadata_str)

                # Add verification info
                metadata['verification'] = {
                    'verified': verified,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'error': error
                }

                # Create new zip with updated metadata
                with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as new_zipf:
                    # Copy all files except metadata
                    for item in zipf.namelist():
                        if item != 'backup_metadata.json':
                            data = zipf.read(item)
                            new_zipf.writestr(item, data)

                    # Write updated metadata
                    new_zipf.writestr('backup_metadata.json', json.dumps(metadata, indent=2))

            # Replace original with updated version
            temp_zip.replace(backup_path)

            # Cleanup temp directory
            import shutil
            shutil.rmtree(temp_dir)

        except Exception:
            # Don't fail if we can't update metadata
            pass

    def _human_size(self, size_bytes: int) -> str:
        """Convert bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def get_next_backup_time(self) -> Optional[str]:
        """Get the next scheduled backup time as ISO string."""
        if not self._running:
            return None

        try:
            job = self.scheduler.get_job('daily_backup')
            if job and job.next_run_time:
                return job.next_run_time.isoformat()
        except Exception:
            pass

        return None

    def update_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Update backup settings and reschedule if needed.

        Args:
            settings: Dict of settings to update (schedule_hour, schedule_minute, retention_days, etc.)

        Returns:
            True if settings were updated successfully
        """
        import sqlite3

        try:
            db = sqlite3.connect(self.settings_db_path)
            db.execute('PRAGMA journal_mode=WAL;')

            # Update database
            for key, value in settings.items():
                db.execute(
                    'INSERT OR REPLACE INTO backup_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
                    (key, str(value))
                )

            db.commit()
            db.close()

            # Reload settings into memory
            self.reload_settings()

            # Reschedule if scheduler is running
            if self._running:
                # Remove existing job
                try:
                    self.scheduler.remove_job('daily_backup')
                except Exception:
                    pass

                # Re-add job with new schedule
                if self.schedule_enabled:
                    self.scheduler.add_job(
                        self._run_scheduled_backup,
                        CronTrigger(hour=self.schedule_hour, minute=self.schedule_minute),
                        id='daily_backup',
                        replace_existing=True,
                        name='Daily Backup'
                    )

            return True
        except Exception:
            return False

    def get_settings(self) -> Dict[str, Any]:
        """Get current backup settings."""
        return {
            'schedule_enabled': self.schedule_enabled,
            'schedule_hour': self.schedule_hour,
            'schedule_minute': self.schedule_minute,
            'retention_days': self.retention_days,
            'verify_backups': self.verify_backups
        }


def get_backup_scheduler(
    backup_manager: BackupManager,
    settings_db_path: str = 'scidk_settings.db',
    alert_manager=None
) -> BackupScheduler:
    """
    Get or create a BackupScheduler instance.

    Args:
        backup_manager: BackupManager instance
        settings_db_path: Path to settings database
        alert_manager: Optional AlertManager for notifications

    Returns:
        BackupScheduler instance
    """
    return BackupScheduler(
        backup_manager=backup_manager,
        settings_db_path=settings_db_path,
        alert_manager=alert_manager
    )
