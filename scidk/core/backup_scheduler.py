"""
Automated backup scheduler for SciDK.

Manages scheduled backups, verification, and retention policies.
"""

import logging
import os
import tempfile
import threading
import zipfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .backup_manager import BackupManager

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Manages automated backup scheduling, verification, and retention."""

    def __init__(
        self,
        backup_manager: BackupManager,
        settings_db_path: str = 'scidk_settings.db',
        alert_manager=None,
        app_scheduler=None
    ):
        """
        Initialize BackupScheduler.

        Loads schedule and retention settings from database.

        Args:
            backup_manager: BackupManager instance
            settings_db_path: Path to settings database
            alert_manager: Optional AlertManager for notifications
            app_scheduler: Optional AppScheduler whose BackgroundScheduler this
                instance should register its jobs into. create_app() injects the
                process-wide one so backup jobs and other features' jobs share a
                single scheduler. When omitted, a private BackgroundScheduler is
                created — this keeps direct construction (tests, scripts) fully
                self-contained.
        """
        self.backup_manager = backup_manager
        self.settings_db_path = settings_db_path
        self.alert_manager = alert_manager
        self.app_scheduler = app_scheduler
        self.scheduler = (
            app_scheduler.scheduler if app_scheduler is not None
            else BackgroundScheduler()
        )
        self._running = False
        self._owner_pid: Optional[int] = None

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

    def start(self, concept_driver=None):
        """
        Start the backup scheduler.

        Args:
            concept_driver: Optional Neo4j driver for Concept Graph (for weight decay)
        """
        if self._running:
            return

        # Store concept_driver for weight decay job
        self.concept_driver = concept_driver

        # Schedule daily backup
        self.scheduler.add_job(
            self._run_scheduled_backup,
            CronTrigger(hour=self.schedule_hour, minute=self.schedule_minute),
            id='daily_backup',
            replace_existing=True,
            name='Daily Backup'
        )

        # Schedule nightly weight decay at 03:00 (if concept graph is available).
        # NOTE: no timezone is stated here, so this fires at 03:00 in whatever
        # timezone the scheduler was built with — system-local for a private
        # BackgroundScheduler. Left as-is to keep existing deployments firing at
        # the same wall-clock time they do today; new jobs registered through
        # AppScheduler.add_job() state their timezone explicitly.
        if concept_driver is not None:
            self.scheduler.add_job(
                self._run_weight_decay,
                CronTrigger(hour=3, minute=0),
                id='concept_graph_weight_decay',
                replace_existing=True,
                name='Concept Graph Weight Decay'
            )

        if not self.scheduler.running:
            self.scheduler.start()
        self._running = True
        self._owner_pid = os.getpid()

    def stop(self):
        """Stop the backup scheduler.

        When the underlying scheduler is shared (injected AppScheduler), only
        this instance's jobs are removed — shutting the shared scheduler down
        would take other features' jobs with it.
        """
        if not self._running:
            return

        if self.app_scheduler is not None:
            for job_id in ('daily_backup', 'concept_graph_weight_decay'):
                self.app_scheduler.remove_job(job_id)
        else:
            self.scheduler.shutdown(wait=False)

        self._running = False
        self._owner_pid = None

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def is_owner(self) -> bool:
        """True if this process is the one whose timer thread is running.

        False in a gunicorn worker that inherited a started scheduler across
        fork under --preload: the object reports running, but the thread that
        fires jobs stayed in the master.
        """
        return self._owner_pid is not None and self._owner_pid == os.getpid()

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

    def _run_weight_decay(self):
        """Execute the Concept Graph weight decay workflow."""
        try:
            if self.concept_driver is None:
                return

            from ..services.concept_graph_service import apply_weight_decay
            import os

            half_life = int(os.environ.get('SCIDK_CONCEPT_WEIGHT_HALFLIFE_DAYS', '90'))
            result = apply_weight_decay(self.concept_driver, half_life)

            # Log results
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Concept graph weight decay completed: {result}")

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Concept graph weight decay failed: {e}")

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
        """Get the next scheduled backup time as ISO string.

        In a process that does not own the scheduler — every gunicorn worker
        under --preload — the answer is computed from the persisted schedule
        rather than read off the inherited scheduler.

        That is deliberate, not just tidiness. Reading a job acquires
        APScheduler's ``_jobstores_lock``, and gunicorn forks while the master's
        scheduler thread is running: a child can inherit that mutex already held,
        with no thread left to release it. A worker touching it would block
        forever, and this is called from the admin status endpoint. Recomputing
        the trigger touches no shared state.
        """
        if not self._running:
            return None

        if self.is_owner():
            try:
                job = self.scheduler.get_job('daily_backup')
                if job and job.next_run_time:
                    return job.next_run_time.isoformat()
            except Exception:
                pass
            return None

        try:
            trigger = CronTrigger(
                hour=self.schedule_hour, minute=self.schedule_minute
            )
            next_fire = trigger.get_next_fire_time(
                None, datetime.now(trigger.timezone)
            )
            return next_fire.isoformat() if next_fire else None
        except Exception:
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
                if not self.is_owner():
                    # Under gunicorn --preload the live scheduler runs in the
                    # master process; this is an inherited copy in a worker, so
                    # rescheduling here changes nothing that will fire. The new
                    # settings are persisted above and take effect on restart.
                    logger.warning(
                        "Backup schedule updated in the database, but this "
                        f"process (pid={os.getpid()}) does not own the running "
                        f"scheduler (owner pid={self._owner_pid}). The new "
                        "schedule takes effect on restart."
                    )
                    return True

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


_backup_scheduler: Optional[BackupScheduler] = None
_backup_scheduler_lock = threading.Lock()


def get_backup_scheduler(
    backup_manager: BackupManager,
    settings_db_path: str = 'scidk_settings.db',
    alert_manager=None,
    app_scheduler=None
) -> BackupScheduler:
    """
    Get or create this process's BackupScheduler.

    Module-level singleton, matching ``get_canvas_service()``. This used to
    construct a new BackupScheduler — and therefore a new BackgroundScheduler
    with its own jobstore — on every call, so every extra ``create_app()`` in a
    process added another set of jobs firing in parallel. Arguments after the
    first call are ignored rather than silently rebuilding a scheduler that is
    already running; use ``reset_backup_scheduler()`` in tests.

    Args:
        backup_manager: BackupManager instance
        settings_db_path: Path to settings database
        alert_manager: Optional AlertManager for notifications
        app_scheduler: Optional AppScheduler to register jobs into

    Returns:
        BackupScheduler instance
    """
    global _backup_scheduler
    if _backup_scheduler is None:
        with _backup_scheduler_lock:
            if _backup_scheduler is None:
                _backup_scheduler = BackupScheduler(
                    backup_manager=backup_manager,
                    settings_db_path=settings_db_path,
                    alert_manager=alert_manager,
                    app_scheduler=app_scheduler
                )
    return _backup_scheduler


def reset_backup_scheduler():
    """Drop the singleton, stopping it first. For tests only."""
    global _backup_scheduler
    with _backup_scheduler_lock:
        if _backup_scheduler is not None:
            try:
                _backup_scheduler.stop()
            except Exception:
                pass
            _backup_scheduler = None
