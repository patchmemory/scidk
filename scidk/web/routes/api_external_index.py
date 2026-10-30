"""Read-only browser over an external scan index (SCIDK_EXTERNAL_INDEX_DB).

The file is only ever opened with sqlite3 URI ``mode=ro`` (``immutable=1`` as a retry when the
WAL needs a -shm it cannot get). Nothing here initializes, migrates, indexes or writes it, and it
is never attached as the application's own files DB. GET only; a named session is required.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Blueprint, jsonify, request

bp = Blueprint('external_index', __name__, url_prefix='/api/external-index')
PAGE = 200


class IndexUnavailable(Exception):
    pass


def _open():
    path = (os.environ.get('SCIDK_EXTERNAL_INDEX_DB') or '').strip()
    if not path:
        raise IndexUnavailable('No external index is configured (SCIDK_EXTERNAL_INDEX_DB is not set).')
    if not os.path.isfile(path):
        raise IndexUnavailable('The external index file was not found.')
    base = 'file:' + quote(os.path.abspath(path))
    last = None
    for query in ('?mode=ro', '?mode=ro&immutable=1'):
        conn = None
        try:
            conn = sqlite3.connect(base + query, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA query_only=ON')
            conn.execute('SELECT 1 FROM scans LIMIT 1').fetchall()
            return conn
        except sqlite3.Error as error:
            last = error
            if conn is not None:
                conn.close()
    raise IndexUnavailable('The external index could not be opened read-only (%s).' % type(last).__name__)


def _guard(handler):
    def wrapper():
        from ..named_session import named_session
        try:
            named_session()
        except Exception:
            return jsonify(status='unavailable', error='Sign in with a named account to browse the index.'), 403, {'Cache-Control': 'no-store'}
        try:
            conn = _open()
        except IndexUnavailable as error:
            return jsonify(status='unavailable', error=str(error)), 503, {'Cache-Control': 'no-store'}
        try:
            result = handler(conn)
            if isinstance(result, tuple):
                return jsonify(result[0]), result[1], {'Cache-Control': 'no-store'}
            return jsonify(result), 200, {'Cache-Control': 'no-store'}
        except sqlite3.Error as error:
            return jsonify(status='unavailable', error='The external index query failed (%s).' % type(error).__name__), 503, {'Cache-Control': 'no-store'}
        finally:
            conn.close()
    wrapper.__name__ = handler.__name__
    return wrapper


def _label(root):
    """(host, share) from a scan root: /net/<host>/data/<share>, /mnt/server/<host>/<share>/…,
    /data0/core/<share>, remote:path (the remote name), else the last path segment."""
    root = root or ''
    if ':' in root.split('/')[0]:
        remote = root.split(':', 1)[0]
        return remote, remote
    parts = [p for p in root.split('/') if p]
    if len(parts) >= 3 and parts[0] == 'net':
        rest = [p for p in parts[2:] if p != 'data']
        return parts[1], (rest[0] if rest else parts[1])
    if len(parts) >= 4 and parts[:2] == ['mnt', 'server']:
        return parts[2], parts[3]
    if len(parts) >= 3 and parts[1] == 'core':
        return parts[0], parts[2]
    return '', (parts[-1] if parts else root)


def _iso(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat(timespec='seconds')
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@bp.get('/scans')
@_guard
def scans(conn):
    progress = {}
    for row in conn.execute("SELECT scan_id, metric, value FROM scan_progress "
                            "WHERE metric IN ('files_scanned','bytes_scanned','dirs_scanned')"):
        progress.setdefault(row['scan_id'], {})[row['metric']] = row['value']
    out = []
    for row in conn.execute('SELECT id, root, status, started, completed, extra_json FROM scans ORDER BY started DESC'):
        try:
            extra = json.loads(row['extra_json']) if row['extra_json'] else {}
        except ValueError:
            extra = {}
        extra = extra if isinstance(extra, dict) else {}
        p = progress.get(row['id'], {})
        host, share = _label(row['root'])
        files = p.get('files_scanned', extra.get('file_count'))
        size = p.get('bytes_scanned', extra.get('total_bytes', extra.get('total_size')))
        out.append({'id': row['id'], 'root': row['root'], 'host': host, 'share': share, 'status': row['status'],
                    'started': _iso(row['started']), 'completed': _iso(row['completed']),
                    'files': _int(files), 'bytes': _int(size), 'dirs': _int(p.get('dirs_scanned'))})
    return {'status': 'success', 'read_only': True, 'scans': out}


def _scan_root(conn, scan_id):
    row = conn.execute('SELECT root FROM scans WHERE id=?', (scan_id,)).fetchone() if scan_id else None
    return row['root'] if row else None


@bp.get('/browse')
@_guard
def browse(conn):
    scan_id = (request.args.get('scan_id') or '').strip()
    root = _scan_root(conn, scan_id)
    if root is None:
        return {'status': 'error', 'error': 'Unknown scan.'}, 404
    path = request.args.get('path') or root
    offset = _int(request.args.get('offset')) or 0
    if offset < 0:
        return {'status': 'error', 'error': 'Invalid offset.'}, 400
    # INDEXED BY keeps SQLite on the per-folder index instead of walking the whole scan.
    rows = conn.execute(
        'SELECT path, name, type, size, modified_time, file_extension FROM files INDEXED BY idx_files_scan_parent '
        'WHERE scan_id=? AND parent_path=? ORDER BY type, name LIMIT ? OFFSET ?',
        (scan_id, path, PAGE + 1, offset)).fetchall()
    entries = [{'path': r['path'], 'name': r['name'], 'type': r['type'], 'size': r['size'],
                'modified': r['modified_time'], 'extension': r['file_extension']} for r in rows[:PAGE]]
    return {'status': 'success', 'read_only': True, 'scan_id': scan_id, 'root': root, 'path': path,
            'entries': entries, 'offset': offset, 'has_more': len(rows) > PAGE, 'next_offset': offset + PAGE}


@bp.get('/datasets')
@_guard
def datasets(conn):
    scan_id = (request.args.get('scan_id') or '').strip()
    root = _scan_root(conn, scan_id)
    if root is None:
        return {'status': 'error', 'error': 'Unknown scan.'}, 404
    path = (request.args.get('path') or root).rstrip('/') or '/'
    # This folder or anything beneath it; never a bare prefix (/huang must not match /huangw).
    escaped = path.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    rows = conn.execute(
        "SELECT id, pattern_name, root_path, file_count, total_bytes, confidence, status FROM data_objects "
        "WHERE scan_id=? AND (root_path=? OR root_path LIKE ? || '/%' ESCAPE '\\') ORDER BY root_path LIMIT ?",
        (scan_id, path, escaped, PAGE + 1)).fetchall()
    return {'status': 'success', 'read_only': True, 'scan_id': scan_id, 'path': path, 'has_more': len(rows) > PAGE,
            'datasets': [{'id': r['id'], 'pattern_name': r['pattern_name'], 'root_path': r['root_path'],
                          'file_count': r['file_count'], 'total_bytes': r['total_bytes'],
                          'confidence': r['confidence'], 'status': r['status']} for r in rows[:PAGE]]}
