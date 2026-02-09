"""
File-based Backup Manager for SciDK.

Creates zip archives of all important application files:
- SQLite databases (settings, path index, etc.)
- Environment configuration (.env)
- Any other critical state files

Much simpler and more reliable than trying to export/import individual settings.
"""

import os
import shutil
import sqlite3
import zipfile
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid


class BackupManager:
    """Manages complete file-based backups of SciDK configuration and data."""

    BACKUP_VERSION = "1.0"

    def __init__(self, backup_dir: str = "backups", alert_manager=None):
        """
        Initialize BackupManager.

        Args:
            backup_dir: Directory to store backup files (default: 'backups/')
            alert_manager: Optional AlertManager instance for notifications
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.alert_manager = alert_manager

    def create_backup(
        self,
        reason: str = 'manual',
        created_by: str = 'system',
        notes: str = '',
        include_data: bool = False
    ) -> Dict[str, Any]:
        """
        Create a complete backup as a zip file.

        Args:
            reason: Reason for backup ('manual', 'auto', 'pre_import')
            created_by: Username or 'system'
            notes: Optional notes
            include_data: If True, also backup data files (can be large)

        Returns:
            Dict with backup_id, filename, size, timestamp
        """
        backup_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)
        timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')

        filename = f"scidk-backup-{timestamp_str}-{backup_id[:8]}.zip"
        backup_path = self.backup_dir / filename

        # Create metadata
        metadata = {
            'version': self.BACKUP_VERSION,
            'backup_id': backup_id,
            'timestamp': timestamp.isoformat(),
            'reason': reason,
            'created_by': created_by,
            'notes': notes,
            'include_data': include_data,
            'files': []
        }

        # Files to backup
        files_to_backup = [
            ('scidk_settings.db', 'Settings database'),
            ('scidk_path_index.db', 'Path index database'),
            ('.env', 'Environment configuration (optional)'),
        ]

        if include_data:
            files_to_backup.extend([
                ('data/files.db', 'Data files database (optional)'),
                ('data/files_20250917.db', 'Legacy data files (optional)'),
            ])

        # Create zip archive
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add each file
                for file_path, description in files_to_backup:
                    if os.path.exists(file_path):
                        # For SQLite databases, use backup API for consistency
                        if file_path.endswith('.db'):
                            temp_db = self._create_db_snapshot(file_path)
                            if temp_db:
                                zipf.write(temp_db, file_path)
                                os.unlink(temp_db)
                                metadata['files'].append({
                                    'path': file_path,
                                    'description': description,
                                    'size': os.path.getsize(file_path)
                                })
                        else:
                            # Regular file
                            zipf.write(file_path, file_path)
                            metadata['files'].append({
                                'path': file_path,
                                'description': description,
                                'size': os.path.getsize(file_path)
                            })

                # Add metadata as JSON
                zipf.writestr('backup_metadata.json', json.dumps(metadata, indent=2))

            backup_size = backup_path.stat().st_size

            return {
                'success': True,
                'backup_id': backup_id,
                'filename': filename,
                'path': str(backup_path),
                'size': backup_size,
                'size_human': self._human_size(backup_size),
                'timestamp': timestamp.isoformat(),
                'files_backed_up': len(metadata['files'])
            }

        except Exception as e:
            # Trigger backup_failed alert
            if self.alert_manager:
                try:
                    self.alert_manager.check_alerts('backup_failed', {
                        'error': str(e),
                        'timestamp': timestamp.isoformat(),
                        'reason': reason,
                        'value': 1  # Failed
                    })
                except Exception as alert_error:
                    print(f"Failed to trigger backup_failed alert: {alert_error}")

            return {
                'success': False,
                'error': str(e)
            }

    def restore_backup(self, backup_file: str, create_backup_first: bool = True) -> Dict[str, Any]:
        """
        Restore from a backup zip file.

        Args:
            backup_file: Path to backup zip file (filename or full path)
            create_backup_first: If True, creates a backup before restoring

        Returns:
            Dict with success status and details
        """
        # Find the backup file
        if not os.path.isabs(backup_file):
            backup_path = self.backup_dir / backup_file
        else:
            backup_path = Path(backup_file)

        if not backup_path.exists():
            return {
                'success': False,
                'error': f'Backup file not found: {backup_path}'
            }

        try:
            # Create a backup before restoring
            pre_restore_backup = None
            if create_backup_first:
                result = self.create_backup(reason='pre_restore', notes='Before restoring from backup')
                if result['success']:
                    pre_restore_backup = result['backup_id']

            # Extract and read metadata
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                # Read metadata
                metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
                metadata = json.loads(metadata_str)

                # Validate version
                if metadata.get('version') != self.BACKUP_VERSION:
                    return {
                        'success': False,
                        'error': f"Backup version mismatch: {metadata.get('version')} (expected {self.BACKUP_VERSION})"
                    }

                # Extract all files
                restored_files = []
                for file_info in metadata['files']:
                    file_path = file_info['path']

                    # Create backup directory if needed
                    target_path = Path(file_path)
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Extract file
                    zipf.extract(file_path, '.')
                    restored_files.append(file_path)

            return {
                'success': True,
                'backup_id': metadata['backup_id'],
                'pre_restore_backup': pre_restore_backup,
                'files_restored': len(restored_files),
                'restored_files': restored_files,
                'original_timestamp': metadata['timestamp']
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def list_backups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List available backups.

        Args:
            limit: Maximum number of backups to return

        Returns:
            List of backup info dicts
        """
        backups = []

        try:
            # Find all backup zip files
            backup_files = sorted(
                self.backup_dir.glob('scidk-backup-*.zip'),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:limit]

            for backup_path in backup_files:
                try:
                    # Try to read metadata from zip
                    with zipfile.ZipFile(backup_path, 'r') as zipf:
                        if 'backup_metadata.json' in zipf.namelist():
                            metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
                            metadata = json.loads(metadata_str)

                            backups.append({
                                'filename': backup_path.name,
                                'path': str(backup_path),
                                'size': backup_path.stat().st_size,
                                'size_human': self._human_size(backup_path.stat().st_size),
                                'backup_id': metadata.get('backup_id'),
                                'timestamp': metadata.get('timestamp'),
                                'reason': metadata.get('reason'),
                                'created_by': metadata.get('created_by'),
                                'notes': metadata.get('notes', ''),
                                'files_count': len(metadata.get('files', []))
                            })
                        else:
                            # Legacy backup without metadata
                            backups.append({
                                'filename': backup_path.name,
                                'path': str(backup_path),
                                'size': backup_path.stat().st_size,
                                'size_human': self._human_size(backup_path.stat().st_size),
                                'backup_id': None,
                                'timestamp': datetime.fromtimestamp(
                                    backup_path.stat().st_mtime, tz=timezone.utc
                                ).isoformat(),
                                'reason': 'unknown',
                                'created_by': 'unknown',
                                'notes': '',
                                'files_count': 0
                            })
                except Exception:
                    # Skip corrupted backups
                    continue

        except Exception:
            pass

        return backups

    def delete_backup(self, backup_file: str) -> bool:
        """
        Delete a backup file.

        Args:
            backup_file: Filename or path to backup file

        Returns:
            True if deleted, False otherwise
        """
        try:
            if not os.path.isabs(backup_file):
                backup_path = self.backup_dir / backup_file
            else:
                backup_path = Path(backup_file)

            if backup_path.exists():
                backup_path.unlink()
                return True
            return False
        except Exception:
            return False

    def _create_db_snapshot(self, db_path: str) -> Optional[str]:
        """
        Create a consistent snapshot of a SQLite database.

        Uses SQLite's backup API for consistency.

        Args:
            db_path: Path to source database

        Returns:
            Path to temporary snapshot file, or None on error
        """
        try:
            # Create temporary file
            fd, temp_path = tempfile.mkstemp(suffix='.db')
            os.close(fd)

            # Use SQLite backup API
            source = sqlite3.connect(db_path)
            dest = sqlite3.connect(temp_path)

            with dest:
                source.backup(dest)

            source.close()
            dest.close()

            return temp_path
        except Exception:
            return None

    def _human_size(self, size_bytes: int) -> str:
        """Convert bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"


def get_backup_manager(backup_dir: str = "backups") -> BackupManager:
    """Get or create a BackupManager instance."""
    return BackupManager(backup_dir)
