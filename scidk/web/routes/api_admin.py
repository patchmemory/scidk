"""
Blueprint for Health/metrics/logs API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os
import time

from ..helpers import get_neo4j_params, build_commit_rows, commit_to_neo4j, get_or_build_scan_index
from ..decorators import require_admin
bp = Blueprint('admin', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

@bp.get('/health/graph')
def api_health_graph():
        """Basic health for graph backend. In-memory is always OK; if Neo4j settings/env are provided, try a connection."""
        backend = os.environ.get('SCIDK_GRAPH_BACKEND', 'in_memory').lower() or 'in_memory'
        info = {
            'backend': backend,
            'in_memory_ok': True,
            'neo4j': {
                'configured': False,
                'connectable': False,
                'error': None,
            }
        }
        uri, user, pwd, database, auth_mode = get_neo4j_params()
        if uri:
            info['neo4j']['configured'] = True
            try:
                from neo4j import GraphDatabase  # type: ignore
            except Exception as e:
                info['neo4j']['error'] = f"neo4j driver not installed: {e}"
                return jsonify(info), 200
            # Respect auth-failure backoff
            st = _get_ext().setdefault('neo4j_state', {})
            import time as _t
            now = _t.time()
            next_after = float(st.get('next_connect_after') or 0)
            if next_after and now < next_after:
                info['neo4j']['error'] = f"backoff active; retry after {int(next_after-now)}s"
                return jsonify(info), 200
            try:
                driver = None
                try:
                    driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                    with driver.session(database=database) as sess:
                        rec = sess.run("RETURN 1 AS ok").single()
                        if rec and rec.get('ok') == 1:
                            info['neo4j']['connectable'] = True
                finally:
                    try:
                        if driver is not None:
                            driver.close()
                    except Exception:
                        pass
            except Exception as e:
                info['neo4j']['error'] = str(e)
        return jsonify(info), 200


@bp.get('/health')
def api_health():
        """Overall health focusing on SQLite availability and WAL mode."""
        from ...core import path_index_sqlite as pix
        from ...core import migrations as _migs
        info = {
            'sqlite': {
                'path': None,
                'exists': False,
                'journal_mode': None,
                'wal_mode': None,
                'schema_version': None,
                'select1': False,
                'error': None,
            }
        }
        try:
            dbp = pix._db_path()
            info['sqlite']['path'] = str(dbp)
            conn = pix.connect()
            try:
                # Ensure schema and capture version
                try:
                    v = _migs.migrate(conn)
                    info['sqlite']['schema_version'] = int(v)
                except Exception:
                    try:
                        row_ver = conn.execute('SELECT version FROM schema_migrations LIMIT 1').fetchone()
                        if row_ver and row_ver[0] is not None:
                            info['sqlite']['schema_version'] = int(row_ver[0])
                    except Exception:
                        pass
                mode = (conn.execute('PRAGMA journal_mode;').fetchone() or [''])[0]
                if isinstance(mode, str):
                    jm = mode.lower()
                    info['sqlite']['journal_mode'] = jm
                    info['sqlite']['wal_mode'] = jm
                row = conn.execute('SELECT 1').fetchone()
                info['sqlite']['select1'] = bool(row and row[0] == 1)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            # After connecting, the DB file should exist on disk
            try:
                from pathlib import Path as _P
                info['sqlite']['exists'] = _P(info['sqlite']['path']).exists()
            except Exception:
                pass
        except Exception as e:
            info['sqlite']['error'] = str(e)
        # Always return 200 so UIs can render details; clients can decide on status
        return jsonify(info), 200


@bp.get('/health/comprehensive')
def api_health_comprehensive():
    """
    Comprehensive system health check dashboard.

    Returns health status for all system components: Flask, SQLite, Neo4j,
    interpreters, disk, memory, and CPU usage.

    Note: Available to all users (authentication handled by middleware).
    System health information is not sensitive and useful for all users.

    Returns:
        JSON with overall status and individual component health metrics
    """
    import psutil
    from ...core import path_index_sqlite as pix

    components = {}
    start_time_key = 'START_TIME'

    # Flask/Application health
    try:
        uptime = int(time.time() - current_app.config.get(start_time_key, time.time()))
        memory_mb = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
        components['flask'] = {
            'status': 'ok',
            'uptime_seconds': uptime,
            'memory_mb': memory_mb
        }
    except Exception as e:
        components['flask'] = {
            'status': 'error',
            'error': str(e)
        }

    # SQLite health (reuse existing logic)
    try:
        conn = pix.connect()
        try:
            dbp = pix._db_path()
            mode = (conn.execute('PRAGMA journal_mode;').fetchone() or [''])[0]

            # Get database size
            size_bytes = 0
            try:
                from pathlib import Path as _P
                db_path = _P(str(dbp))
                if db_path.exists():
                    size_bytes = db_path.stat().st_size
            except Exception:
                pass

            # Get row count from scans table
            row_count = 0
            try:
                result = conn.execute('SELECT COUNT(*) FROM scans').fetchone()
                row_count = result[0] if result else 0
            except Exception:
                pass

            components['sqlite'] = {
                'status': 'ok',
                'path': str(dbp),
                'size_mb': round(size_bytes / 1024 / 1024, 2),
                'journal_mode': mode.lower() if isinstance(mode, str) else 'unknown',
                'row_count': row_count
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as e:
        components['sqlite'] = {
            'status': 'error',
            'error': str(e)
        }

    # Neo4j health (reuse existing logic)
    try:
        uri, user, pwd, database, auth_mode = get_neo4j_params()
        if uri:
            neo4j_start = time.time()
            try:
                from neo4j import GraphDatabase
                driver = None
                try:
                    driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                    with driver.session(database=database) as sess:
                        result = sess.run("MATCH (n) RETURN count(n) AS count")
                        rec = result.single()
                        node_count = rec['count'] if rec else 0
                        response_ms = round((time.time() - neo4j_start) * 1000)
                        components['neo4j'] = {
                            'status': 'connected',
                            'response_time_ms': response_ms,
                            'node_count': node_count
                        }
                finally:
                    if driver:
                        driver.close()
            except Exception as e:
                components['neo4j'] = {
                    'status': 'unavailable',
                    'error': str(e)
                }
        else:
            components['neo4j'] = {
                'status': 'not_configured'
            }
    except Exception as e:
        components['neo4j'] = {
            'status': 'error',
            'error': str(e)
        }

    # Interpreters health
    try:
        ext = _get_ext()
        reg = ext.get('registry')
        if reg and hasattr(reg, 'by_id'):
            # Get interpreter state
            interp_state = ext.get('interpreters', {})
            eff = set(interp_state.get('effective_enabled') or [])

            total = len(reg.by_id)
            enabled = len(eff) if eff else total  # If no override, assume all enabled

            components['interpreters'] = {
                'status': 'ok',
                'enabled_count': enabled,
                'total_count': total
            }
        else:
            components['interpreters'] = {
                'status': 'ok',
                'enabled_count': 0,
                'total_count': 0
            }
    except Exception as e:
        components['interpreters'] = {
            'status': 'error',
            'error': str(e)
        }

    # Disk health
    try:
        disk = psutil.disk_usage('/')
        disk_percent = round(disk.percent, 1)
        components['disk'] = {
            'status': 'critical' if disk_percent > 95 else 'warning' if disk_percent > 85 else 'good',
            'free_gb': round(disk.free / 1024**3, 1),
            'total_gb': round(disk.total / 1024**3, 1),
            'percent_used': disk_percent
        }
    except Exception as e:
        components['disk'] = {
            'status': 'error',
            'error': str(e)
        }

    # Memory health
    try:
        mem = psutil.virtual_memory()
        mem_percent = round(mem.percent, 1)
        components['memory'] = {
            'status': 'critical' if mem_percent > 90 else 'high' if mem_percent > 75 else 'normal',
            'used_mb': round(mem.used / 1024 / 1024),
            'total_mb': round(mem.total / 1024 / 1024),
            'percent_used': mem_percent
        }
    except Exception as e:
        components['memory'] = {
            'status': 'error',
            'error': str(e)
        }

    # CPU health
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        components['cpu'] = {
            'status': 'high' if cpu_percent > 80 else 'normal' if cpu_percent > 20 else 'low',
            'load_percent': round(cpu_percent, 1)
        }
    except Exception as e:
        components['cpu'] = {
            'status': 'error',
            'error': str(e)
        }

    # Calculate overall status
    statuses = []
    for comp in components.values():
        status = comp.get('status', 'unknown')
        if status == 'error' or status == 'critical':
            statuses.append('critical')
        elif status == 'warning' or status == 'high':
            statuses.append('warning')
        elif status == 'unavailable' or status == 'not_configured':
            # Don't count unavailable/not_configured as critical
            pass
        else:
            statuses.append('healthy')

    overall = 'critical' if 'critical' in statuses else 'warning' if 'warning' in statuses else 'healthy'

    return jsonify({
        'status': overall,
        'timestamp': time.time(),
        'components': components
    }), 200


@bp.get('/metrics')
def api_metrics():
        try:
            from ...services.metrics import collect_metrics
            m = collect_metrics(current_app)
            return jsonify(m), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@bp.get('/logs')
def api_logs():
        """
        Browse operational logs with pagination and filters.
        Query params: limit, offset, level, since_ts
        Privacy: No sensitive file paths or user data exposed.
        """
        try:
            from ...core import path_index_sqlite as pix
            limit = min(int(request.args.get('limit', 100)), 1000)
            offset = int(request.args.get('offset', 0))
            level = request.args.get('level', '').strip().upper() or None
            since_ts = request.args.get('since_ts', '').strip() or None

            conn = pix.connect()
            try:
                cur = conn.cursor()
                # Build query with filters
                conditions = []
                params = []
                if level:
                    conditions.append("level = ?")
                    params.append(level)
                if since_ts:
                    try:
                        ts_val = float(since_ts)
                        conditions.append("ts >= ?")
                        params.append(ts_val)
                    except Exception:
                        pass

                where_clause = ""
                if conditions:
                    where_clause = " WHERE " + " AND ".join(conditions)

                # Get total count
                count_query = f"SELECT COUNT(*) FROM logs{where_clause}"
                cur.execute(count_query, params)
                row = cur.fetchone()
                total = row[0] if row else 0

                # Get logs (most recent first)
                query = f"""
                    SELECT ts, level, message, context
                    FROM logs{where_clause}
                    ORDER BY ts DESC
                    LIMIT ? OFFSET ?
                """
                cur.execute(query, params + [limit, offset])
                rows = cur.fetchall()

                logs = []
                for row in rows:
                    logs.append({
                        'ts': row[0],
                        'level': row[1],
                        'message': row[2],
                        'context': row[3]
                    })

                return jsonify({
                    'logs': logs,
                    'total': total,
                    'limit': limit,
                    'offset': offset
                }), 200
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Rclone interpretation settings (GET/POST)


@bp.post('/admin/cleanup-test-scans')
def api_admin_cleanup_test_scans():
    """Remove test scans from the database (scans with /tmp/ or /nonexistent/ paths).

    This endpoint cleans up scans created during testing that accumulate over time.
    Removes scans from both SQLite (when state.backend=sqlite) and in-memory registry.

    Returns:
        JSON with counts of deleted scans and related records
    """
    try:
        from ...core import path_index_sqlite as pix

        conn = pix.connect()
        try:
            cur = conn.cursor()

            # Find test scan IDs (paths containing /tmp/ or /nonexistent/)
            cur.execute("""
                SELECT id FROM scans
                WHERE root LIKE '%/tmp/%'
                   OR root LIKE '%nonexistent%'
                   OR root LIKE '%scidk-e2e%'
            """)
            test_scan_ids = [row[0] for row in cur.fetchall()]

            if not test_scan_ids:
                return jsonify({
                    'deleted_scans': 0,
                    'deleted_scan_items': 0,
                    'deleted_scan_progress': 0,
                    'message': 'No test scans found'
                }), 200

            # Delete related records first (foreign keys)
            placeholders = ','.join(['?' for _ in test_scan_ids])

            # Delete scan_items
            cur.execute(f"DELETE FROM scan_items WHERE scan_id IN ({placeholders})", test_scan_ids)
            deleted_items = cur.rowcount

            # Delete scan_progress
            cur.execute(f"DELETE FROM scan_progress WHERE scan_id IN ({placeholders})", test_scan_ids)
            deleted_progress = cur.rowcount

            # Delete scan_selection_rules (if exists)
            try:
                cur.execute(f"DELETE FROM scan_selection_rules WHERE scan_id IN ({placeholders})", test_scan_ids)
            except Exception:
                pass  # Table might not exist in older schemas

            # Delete scans
            cur.execute(f"DELETE FROM scans WHERE id IN ({placeholders})", test_scan_ids)
            deleted_scans = cur.rowcount

            conn.commit()

            # Also clear from in-memory registry
            ext = _get_ext()
            scans_registry = ext.get('scans', {})
            for scan_id in list(scans_registry.keys()):
                scan = scans_registry.get(scan_id)
                if scan:
                    path = scan.get('path', '')
                    if ('/tmp/' in path or 'nonexistent' in path or 'scidk-e2e' in path):
                        del scans_registry[scan_id]

            return jsonify({
                'deleted_scans': deleted_scans,
                'deleted_scan_items': deleted_items,
                'deleted_scan_progress': deleted_progress,
                'scan_ids': test_scan_ids[:10] + (['...'] if len(test_scan_ids) > 10 else []),
                'total_test_scans_found': len(test_scan_ids),
                'message': f'Successfully deleted {deleted_scans} test scans'
            }), 200

        finally:
            try:
                conn.close()
            except Exception:
                pass

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/admin/cleanup-test-labels')
def api_admin_cleanup_test_labels():
    """Remove test labels from the database (labels with test prefixes like E2E*, Test*, etc).

    This endpoint cleans up labels created during testing that accumulate over time.

    Returns:
        JSON with counts of deleted labels
    """
    try:
        from ...core import path_index_sqlite as pix

        # Test label patterns to delete
        test_patterns = [
            'E2E%',  # E2E test labels
            'Test%',  # TestLabel, TestNode, etc
            'Person%',  # From arrows test
            'Company%',  # From arrows test
            'Project%',  # Multiple test uses
            'Export%',  # ExportProject, ExportTask
            'Layout%',  # LayoutTestLabel
            'Roundtrip%',  # RoundtripAuthor, RoundtripBook
            'Label%',  # Label1, Label2, Label3
            'AllTypes%',  # AllTypes
            'File%',  # File from relationship tests
            'Directory%',  # Directory from relationship tests
            'User%',  # User from relationship tests
            'Update%',  # UpdateTest
            'Delete%',  # DeleteTest
            'Bad%',  # BadLabel
            'Node%',  # TestNode, OtherNode, NodeA, NodeB
        ]

        conn = pix.connect()
        try:
            cur = conn.cursor()

            # Check if label_definitions table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='label_definitions'")
            if not cur.fetchone():
                return jsonify({
                    'deleted_labels': 0,
                    'message': 'Label definitions table does not exist'
                }), 200

            # Collect label names that match test patterns
            deleted_labels = []
            total_deleted = 0

            for pattern in test_patterns:
                cur.execute("SELECT name FROM label_definitions WHERE name LIKE ?", (pattern,))
                matching_labels = [row[0] for row in cur.fetchall()]
                deleted_labels.extend(matching_labels)

                # Delete matching labels
                cur.execute("DELETE FROM label_definitions WHERE name LIKE ?", (pattern,))
                total_deleted += cur.rowcount

            conn.commit()

            return jsonify({
                'deleted_labels': total_deleted,
                'label_names': deleted_labels[:10] + (['...'] if len(deleted_labels) > 10 else []),
                'total_test_labels_found': len(deleted_labels),
                'message': f'Successfully deleted {total_deleted} test labels'
            }), 200

        finally:
            try:
                conn.close()
            except Exception:
                pass

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/admin/cleanup-test-endpoints')
def api_admin_cleanup_test_endpoints():
    """Remove test API endpoints from the database (endpoints with test prefixes).

    This endpoint cleans up API endpoints created during testing that accumulate over time.

    Returns:
        JSON with counts of deleted endpoints
    """
    try:
        import sqlite3

        # Test endpoint patterns to delete
        test_patterns = [
            'Test%',  # Test Users API, etc
            'E2E%',  # E2E test endpoints
            'Secure%',  # Secure API from auth tests
            'Updated%',  # Updated API from update tests
            'Bearer%',  # Bearer API from auth tests
            'API%Key%',  # API Key API from auth tests
            '%JSONPath%',  # JSONPath API tests
            'Original%',  # Original API from edit tests
            'Delete%',  # Delete Me API from delete tests
            'Cancel%',  # Cancel Test API from cancel tests
        ]

        # Use settings DB (where API endpoints are stored, not path_index)
        settings_db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        conn = sqlite3.connect(settings_db)
        conn.execute('PRAGMA journal_mode=WAL')
        try:
            cur = conn.cursor()

            # Check if api_endpoints table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_endpoints'")
            if not cur.fetchone():
                return jsonify({
                    'deleted_endpoints': 0,
                    'message': 'API endpoints table does not exist'
                }), 200

            # Collect endpoint names that match test patterns
            deleted_endpoints = []
            total_deleted = 0

            for pattern in test_patterns:
                cur.execute("SELECT name FROM api_endpoints WHERE name LIKE ?", (pattern,))
                matching_endpoints = [row[0] for row in cur.fetchall()]
                deleted_endpoints.extend(matching_endpoints)

                # Delete matching endpoints
                cur.execute("DELETE FROM api_endpoints WHERE name LIKE ?", (pattern,))
                total_deleted += cur.rowcount

            conn.commit()

            return jsonify({
                'deleted_endpoints': total_deleted,
                'endpoint_names': deleted_endpoints[:10] + (['...'] if len(deleted_endpoints) > 10 else []),
                'total_test_endpoints_found': len(deleted_endpoints),
                'message': f'Successfully deleted {total_deleted} test endpoints'
            }), 200

        finally:
            try:
                conn.close()
            except Exception:
                pass

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Backup Management API Endpoints

@bp.get('/backups')
@require_admin
def api_backups_list():
    """
    List all backups with metadata.

    Admin-only endpoint that returns backup history with verification status.

    Returns:
        JSON list of backups with metadata
    """
    try:
        from ...core.backup_manager import get_backup_manager

        backup_manager = get_backup_manager()
        backups = backup_manager.list_backups(limit=100)

        # Add verification status from metadata
        for backup in backups:
            try:
                import zipfile
                backup_path = Path(backup['path'])
                if backup_path.exists():
                    with zipfile.ZipFile(backup_path, 'r') as zipf:
                        if 'backup_metadata.json' in zipf.namelist():
                            metadata_str = zipf.read('backup_metadata.json').decode('utf-8')
                            metadata = json.loads(metadata_str)
                            verification = metadata.get('verification', {})
                            backup['verified'] = verification.get('verified', False)
                            backup['verification_error'] = verification.get('error')
                            backup['verification_timestamp'] = verification.get('timestamp')
            except Exception:
                # If we can't read verification status, mark as unknown
                backup['verified'] = None

        # Get scheduler info if available
        scheduler_info = {}
        try:
            ext = _get_ext()
            backup_scheduler = ext.get('backup_scheduler')
            if backup_scheduler and backup_scheduler.is_running():
                scheduler_info = {
                    'enabled': True,
                    'next_backup': backup_scheduler.get_next_backup_time(),
                    'schedule_hour': backup_scheduler.schedule_hour,
                    'schedule_minute': backup_scheduler.schedule_minute,
                    'retention_days': backup_scheduler.retention_days
                }
            else:
                scheduler_info = {'enabled': False}
        except Exception:
            scheduler_info = {'enabled': False}

        return jsonify({
            'backups': backups,
            'scheduler': scheduler_info
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/backups')
@require_admin
def api_backups_create():
    """
    Trigger manual backup creation.

    Admin-only endpoint to create a backup on demand.

    Request body (JSON, optional):
        - reason: Reason for backup (default: 'manual')
        - notes: Optional notes
        - include_data: Include data files (default: false)
        - verify: Verify backup after creation (default: true)

    Returns:
        JSON with backup details and verification status
    """
    try:
        from ...core.backup_manager import get_backup_manager
        from flask import g

        data = request.get_json() or {}
        reason = data.get('reason', 'manual')
        notes = data.get('notes', '')
        include_data = data.get('include_data', False)
        verify = data.get('verify', True)

        # Get username from auth context if available
        created_by = getattr(g, 'scidk_username', 'admin')

        backup_manager = get_backup_manager()
        result = backup_manager.create_backup(
            reason=reason,
            created_by=created_by,
            notes=notes,
            include_data=include_data
        )

        if not result['success']:
            return jsonify(result), 500

        # Verify backup if requested
        verification_result = None
        if verify:
            try:
                ext = _get_ext()
                backup_scheduler = ext.get('backup_scheduler')
                if backup_scheduler:
                    verification_result = backup_scheduler.verify_backup(result['filename'])
                    result['verification'] = verification_result
            except Exception as e:
                result['verification_error'] = str(e)

        return jsonify(result), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/backups/<backup_id>/restore')
@require_admin
def api_backups_restore(backup_id):
    """
    Restore from a backup.

    Admin-only endpoint to restore application state from a backup file.

    Path parameter:
        backup_id: Backup filename or ID

    Request body (JSON, optional):
        - create_backup_first: Create backup before restoring (default: true)

    Returns:
        JSON with restore results
    """
    try:
        from ...core.backup_manager import get_backup_manager

        data = request.get_json() or {}
        create_backup_first = data.get('create_backup_first', True)

        backup_manager = get_backup_manager()

        # Try to find backup by ID or filename
        backups = backup_manager.list_backups(limit=1000)
        backup_file = None

        for backup in backups:
            if backup.get('backup_id') == backup_id or backup.get('filename') == backup_id:
                backup_file = backup['filename']
                break

        if not backup_file:
            return jsonify({'error': f'Backup not found: {backup_id}'}), 404

        result = backup_manager.restore_backup(
            backup_file=backup_file,
            create_backup_first=create_backup_first
        )

        if not result['success']:
            return jsonify(result), 500

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.delete('/backups/<backup_id>')
@require_admin
def api_backups_delete(backup_id):
    """
    Delete a backup file.

    Admin-only endpoint to permanently delete a backup.

    Path parameter:
        backup_id: Backup filename or ID

    Returns:
        JSON with deletion result
    """
    try:
        from ...core.backup_manager import get_backup_manager

        backup_manager = get_backup_manager()

        # Try to find backup by ID or filename
        backups = backup_manager.list_backups(limit=1000)
        backup_file = None

        for backup in backups:
            if backup.get('backup_id') == backup_id or backup.get('filename') == backup_id:
                backup_file = backup['filename']
                break

        if not backup_file:
            return jsonify({'error': f'Backup not found: {backup_id}'}), 404

        success = backup_manager.delete_backup(backup_file)

        if success:
            return jsonify({
                'success': True,
                'message': f'Backup deleted: {backup_file}'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete backup'
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/backups/verify/<backup_id>')
@require_admin
def api_backups_verify(backup_id):
    """
    Verify a backup's integrity.

    Admin-only endpoint to verify a backup without restoring it.

    Path parameter:
        backup_id: Backup filename or ID

    Returns:
        JSON with verification results
    """
    try:
        from ...core.backup_manager import get_backup_manager

        ext = _get_ext()
        backup_scheduler = ext.get('backup_scheduler')

        if not backup_scheduler:
            return jsonify({'error': 'Backup scheduler not available'}), 503

        backup_manager = get_backup_manager()

        # Try to find backup by ID or filename
        backups = backup_manager.list_backups(limit=1000)
        backup_file = None

        for backup in backups:
            if backup.get('backup_id') == backup_id or backup.get('filename') == backup_id:
                backup_file = backup['filename']
                break

        if not backup_file:
            return jsonify({'error': f'Backup not found: {backup_id}'}), 404

        result = backup_scheduler.verify_backup(backup_file)

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/backups/cleanup')
@require_admin
def api_backups_cleanup():
    """
    Manually trigger cleanup of old backups.

    Admin-only endpoint to delete backups older than retention policy.

    Returns:
        JSON with cleanup results
    """
    try:
        ext = _get_ext()
        backup_scheduler = ext.get('backup_scheduler')

        if not backup_scheduler:
            return jsonify({'error': 'Backup scheduler not available'}), 503

        result = backup_scheduler.cleanup_old_backups()

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.get('/backups/settings')
@require_admin
def api_backups_settings_get():
    """
    Get current backup schedule and retention settings.

    Admin-only endpoint to retrieve backup configuration.

    Returns:
        JSON with current settings
    """
    try:
        ext = _get_ext()
        backup_scheduler = ext.get('backup_scheduler')

        if not backup_scheduler:
            return jsonify({'error': 'Backup scheduler not available'}), 503

        settings = backup_scheduler.get_settings()

        return jsonify(settings), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.post('/backups/settings')
@require_admin
def api_backups_settings_update():
    """
    Update backup schedule and retention settings.

    Admin-only endpoint to configure automated backups.

    Request body (JSON):
        - schedule_enabled: Enable/disable automated backups (boolean)
        - schedule_hour: Hour to run daily backup (0-23)
        - schedule_minute: Minute to run daily backup (0-59)
        - retention_days: Days to keep backups before cleanup
        - verify_backups: Enable/disable backup verification (boolean)

    Returns:
        JSON with updated settings
    """
    try:
        ext = _get_ext()
        backup_scheduler = ext.get('backup_scheduler')

        if not backup_scheduler:
            return jsonify({'error': 'Backup scheduler not available'}), 503

        data = request.get_json() or {}

        # Validate settings
        if 'schedule_hour' in data:
            try:
                hour = int(data['schedule_hour'])
                if hour < 0 or hour > 23:
                    return jsonify({'error': 'schedule_hour must be between 0 and 23'}), 400
            except ValueError:
                return jsonify({'error': 'schedule_hour must be an integer'}), 400

        if 'schedule_minute' in data:
            try:
                minute = int(data['schedule_minute'])
                if minute < 0 or minute > 59:
                    return jsonify({'error': 'schedule_minute must be between 0 and 59'}), 400
            except ValueError:
                return jsonify({'error': 'schedule_minute must be an integer'}), 400

        if 'retention_days' in data:
            try:
                days = int(data['retention_days'])
                if days < 1:
                    return jsonify({'error': 'retention_days must be at least 1'}), 400
            except ValueError:
                return jsonify({'error': 'retention_days must be an integer'}), 400

        # Update settings
        success = backup_scheduler.update_settings(data)

        if success:
            updated_settings = backup_scheduler.get_settings()
            return jsonify(updated_settings), 200
        else:
            return jsonify({'error': 'Failed to update settings'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
