"""Read-only browser over an external scan index (SCIDK_EXTERNAL_INDEX_DB).

The file is only ever opened with sqlite3 URI ``mode=ro`` (``immutable=1`` as a retry when the
WAL needs a -shm it cannot get). Nothing here initializes, migrates, indexes or writes it, and it
is never attached as the application's own files DB. GET only; a named session is required.
"""
import json
import os
import re
import sqlite3
import threading
import time
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


# Names and folders that are filesystem/OS noise. Hidden unless ?system=1.
NOISE_DIRS = ('.TemporaryItems', '.snapshot', '.Spotlight-V100', '.fseventsd', '@eaDir', '$RECYCLE.BIN',
              'System Volume Information')
NOISE_PREFIXES = ('.Trash',)  # .Trash, .Trashes, .Trash-1000
SEARCH_BUDGET_S = 1.0
COMPLETE = ('complete', 'completed', 'committed')
SERIES_MIN = 3
_SERIES = re.compile(r'^(.*?)(\d+)((?:\.[A-Za-z][A-Za-z0-9]*)*)$')


def _flag(name):
    return (request.args.get(name) or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _name_noise_sql():
    """Clause on the files.name column (children of the folder being listed)."""
    marks = ','.join('?' * len(NOISE_DIRS))
    prefixes = ' AND '.join("substr(name,1,%d)!=?" % len(x) for x in NOISE_PREFIXES)
    return ("substr(name,1,2)!='._' AND name!='.DS_Store' AND " + prefixes + " AND name NOT IN (" + marks + ")",
            list(NOISE_PREFIXES) + list(NOISE_DIRS))


def _path_noise_sql(column):
    """Clause on a path column: no component is noise (…/.snapshot/…, …/._x, …/.Trash-1000/…)."""
    parts, args = [], []
    wrapped = "('/'||%s||'/')" % column
    for piece in ('/._', '/.DS_Store/') + tuple('/' + x for x in NOISE_PREFIXES) + tuple('/%s/' % d for d in NOISE_DIRS):
        parts.append('instr(%s,?)=0' % wrapped)
        args.append(piece)
    return ' AND '.join(parts), args


def is_noise_name(name):
    return name.startswith('._') or name == '.DS_Store' or name in NOISE_DIRS or name.startswith(NOISE_PREFIXES)


def series_key(name):
    """'x_C1_17.tif' -> 'x_C1_*.tif'; None unless the name ends in a number (before its extension)."""
    m = _SERIES.match(name or '')
    return (m.group(1) + '*' + m.group(3)) if m and m.group(1) else None


def _classify(root):
    """(host, share, is_full_root) from a scan root: /net/<host>/data/<share>, /mnt/server/<host>/<share>/…,
    /data0/core/<share>, remote:path (the remote name), else the last path segment.
    is_full_root: nothing below the share directory itself."""
    root = root or ''
    if ':' in root.split('/')[0]:
        remote, tail = root.split(':', 1)
        return remote, remote, not tail.strip('/')
    parts = [p for p in root.split('/') if p]
    if len(parts) >= 3 and parts[0] == 'net':
        rest = [p for p in parts[2:] if p != 'data']
        return parts[1], (rest[0] if rest else parts[1]), len(rest) <= 1
    if len(parts) >= 4 and parts[:2] == ['mnt', 'server']:
        return parts[2], parts[3], len(parts) == 4
    if len(parts) >= 3 and parts[1] == 'core':
        return parts[0], parts[2], len(parts) == 3
    return '', (parts[-1] if parts else root), True


def _label(root):
    return _classify(root)[:2]


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


def _group_shares(out):
    """One total per share: the latest complete full-root scan is the primary; every other scan of the
    share (other mount, subfolder, older, unfinished) is listed under it and never added to the total."""
    by_share = {}
    for s in out:
        if s['files'] == 0:
            continue
        by_share.setdefault(s['share'], []).append(s)
    shares = []
    for share, scans in by_share.items():
        def newest(s):
            return s['completed_ts'] or s['started_ts'] or 0
        full = [s for s in scans if s['complete'] and s['is_full_root']]
        pool = full or [s for s in scans if s['complete']]
        primary = None
        if pool:
            primary = max(pool, key=lambda s: (-s['depth'] if not full else 0, newest(s)))
        older = sorted((s for s in scans if s is not primary), key=lambda s: -newest(s))
        for s in scans:
            s['role'] = 'primary' if s is primary else 'older'
        shares.append({'share': share, 'host': (primary or scans[0])['host'],
                       'primary_id': primary['id'] if primary else None,
                       'primary_is_full_root': bool(full),
                       'files': primary['files'] if primary else None, 'bytes': primary['bytes'] if primary else None,
                       'date': primary['date'] if primary else None,
                       'older_ids': [s['id'] for s in older]})
    shares.sort(key=lambda x: -(x['files'] or 0))
    return shares


def scan_summaries(conn):
    """(scans, shares) exactly as GET /scans returns them. Read-only; shared with the Locations list."""
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
        host, share, is_full_root = _classify(row['root'])
        files = p.get('files_scanned', extra.get('file_count'))
        size = p.get('bytes_scanned', extra.get('total_bytes', extra.get('total_size')))
        stamp = _iso(row['completed'] or row['started'])
        out.append({'id': row['id'], 'root': row['root'], 'host': host, 'share': share, 'status': row['status'],
                    'started': _iso(row['started']), 'completed': _iso(row['completed']),
                    'date': stamp[:10] if stamp else None, 'is_full_root': is_full_root,
                    'complete': (row['status'] or '').lower() in COMPLETE, 'depth': len([x for x in (row['root'] or '').split('/') if x]),
                    'started_ts': row['started'], 'completed_ts': row['completed'],
                    'files': _int(files), 'bytes': _int(size), 'dirs': _int(p.get('dirs_scanned'))})
    shares = _group_shares(out)
    for s in out:
        s.pop('started_ts'), s.pop('completed_ts'), s.pop('depth')
    return out, shares


@bp.get('/scans')
@_guard
def scans(conn):
    out, shares, _ = _scan_snapshot(conn)
    return {'status': 'success', 'read_only': True, 'scans': out, 'shares': shares}


_LOCAL_PROVIDERS = ('', 'local', 'local_fs', 'localfs', 'file')


def local_access(root, extra=None):
    """True only when this scan root is demonstrably reachable by the local file browser on this machine.

    Purely local and conservative: an absolute path that is a readable directory *here*, and a scan whose recorded
    provider (when it records one) is local. No host is contacted, and a remote path is never matched to a local mount
    by name or alias: an SSH/remote scan that merely shares a path string stays Indexed unless it records a local
    provider."""
    root = root or ''
    if not root.startswith('/') or ':' in root.split('/', 1)[0]:
        return False
    provider = ''
    if isinstance(extra, dict):
        provider = str(extra.get('provider_id') or extra.get('provider') or '').strip().lower()
    if provider not in _LOCAL_PROVIDERS:
        return False
    try:
        return os.path.isdir(root) and os.access(root, os.R_OK | os.X_OK)
    except OSError:
        return False


_SNAP = {}   # (index path, file signature) -> (loaded at, (scans, shares, extras))


def _scan_snapshot(conn):
    """Scan summaries plus each scan's extra_json, cached like the candidate list (index signature, CAT_TTL_S)."""
    path = (os.environ.get('SCIDK_EXTERNAL_INDEX_DB') or '').strip()
    key = (os.path.abspath(path), _signature(path)) if path else None
    with _CAT_LOCK:
        hit = _SNAP.get(key) if key else None
        if hit and time.monotonic() - hit[0] < CAT_TTL_S:
            return hit[1]
    out, shares = scan_summaries(conn)
    extras = {}
    for row in conn.execute('SELECT id, extra_json FROM scans'):
        try:
            extra = json.loads(row['extra_json']) if row['extra_json'] else {}
        except ValueError:
            extra = {}
        extras[row['id']] = extra if isinstance(extra, dict) else {}
    value = (out, shares, extras)
    if key:
        with _CAT_LOCK:
            _SNAP.clear()
            _SNAP[key] = (time.monotonic(), value)
    return value


def scan_locations(conn, shortcuts=()):
    """Scanned locations for the Browse sidebar: one per scan with files, newest share primary first.

    Each is ``{scan_id, host, share, root, label, files, bytes, date, access, role}`` with access ``mounted`` (the
    root is a readable local folder), else ``indexed`` (scan-index browsing only). ``shortcuts`` are scan ids a user
    kept as shortcuts: any that no longer resolve to scan evidence come back as ``unavailable``."""
    out, shares, extras = _scan_snapshot(conn)
    by_id = {s['id']: s for s in out}
    primary = {sh['primary_id'] for sh in shares if sh.get('primary_id')}
    listed = []
    for s in out:
        if not s['files'] or not s['complete']:
            continue
        listed.append({'scan_id': s['id'], 'host': s['host'], 'share': s['share'], 'root': s['root'],
                       'label': ('%s · %s' % (s['host'], s['share'])) if s['host'] and s['host'] != s['share'] else s['share'],
                       'files': s['files'], 'bytes': s['bytes'], 'date': s['date'], 'role': 'primary' if s['id'] in primary else 'other',
                       'access': 'mounted' if local_access(s['root'], extras.get(s['id'])) else 'indexed'})
    listed.sort(key=lambda x: (x['role'] != 'primary', (x['label'] or '').casefold(), x['root'] or ''))
    missing = [{'scan_id': i, 'access': 'unavailable', 'label': 'Unavailable', 'root': None}
               for i in shortcuts if i and i not in by_id]
    return listed, missing


@bp.get('/locations')
@_guard
def locations(conn):
    wanted = [x.strip() for x in (request.args.get('shortcuts') or '').split(',') if x.strip()]
    listed, missing = scan_locations(conn, wanted)
    return {'status': 'success', 'read_only': True, 'locations': listed, 'unavailable': missing}


def _scan_root(conn, scan_id):
    row = conn.execute('SELECT root FROM scans WHERE id=?', (scan_id,)).fetchone() if scan_id else None
    return row['root'] if row else None


def _entry(r):
    return {'path': r['path'], 'name': r['name'], 'type': r['type'], 'size': r['size'],
            'modified': r['modified_time'], 'extension': r['file_extension'],
            'series': series_key(r['name']) if r['type'] != 'folder' else None}


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
    noise, noise_args = ('1=1', []) if _flag('system') else _name_noise_sql()
    # INDEXED BY keeps SQLite on the per-folder index instead of walking the whole scan.
    rows = conn.execute(
        'SELECT path, name, type, size, modified_time, file_extension FROM files INDEXED BY idx_files_scan_parent '
        'WHERE scan_id=? AND parent_path=? AND ' + noise + ' ORDER BY type, name LIMIT ? OFFSET ?',
        [scan_id, path] + noise_args + [PAGE + 1, offset]).fetchall()
    return {'status': 'success', 'read_only': True, 'scan_id': scan_id, 'root': root, 'path': path,
            'entries': [_entry(r) for r in rows[:PAGE]], 'offset': offset, 'has_more': len(rows) > PAGE,
            'next_offset': offset + PAGE}


def _like(text, prefix):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return escaped + '%' if prefix else '%' + escaped + '%'


def _timed(conn, sql, args, deadline, limit):
    """Rows of a query, stopping at the deadline. Returns (rows, capped)."""
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
    rows = []
    try:
        for r in conn.execute(sql, args):
            rows.append(r)
            if len(rows) >= limit:
                break
        return rows, False
    except sqlite3.OperationalError as error:
        if 'interrupt' in str(error).lower():
            return rows, True
        raise
    finally:
        conn.set_progress_handler(None, 0)


@bp.get('/search')
@_guard
def search(conn):
    """Name search inside the current folder (index range) or its subtree (path-prefix index), 200 per page,
    1 s budget. Never walks anything outside the given folder."""
    scan_id = (request.args.get('scan_id') or '').strip()
    root = _scan_root(conn, scan_id)
    if root is None:
        return {'status': 'error', 'error': 'Unknown scan.'}, 404
    q = (request.args.get('q') or '').strip()
    if not q:
        return {'status': 'error', 'error': 'Enter a name to search for.'}, 400
    path = (request.args.get('path') or root).rstrip('/') or '/'
    prefix = (request.args.get('mode') or 'prefix') != 'contains'
    subtree = (request.args.get('scope') or 'folder') == 'subtree'
    cursor = request.args.get('cursor') or ''
    pattern = _like(q, prefix)
    show_system = _flag('system')
    deadline = time.monotonic() + SEARCH_BUDGET_S
    cols = 'path, name, type, size, modified_time, file_extension'
    name_noise, name_args = ('1=1', []) if show_system else _name_noise_sql()
    rows, capped = [], False
    if not subtree:
        after = cursor
        rows, capped = _timed(
            conn, 'SELECT ' + cols + ' FROM files INDEXED BY idx_files_scan_parent_name WHERE scan_id=? AND parent_path=? '
            "AND name>? AND name LIKE ? ESCAPE '\\' AND " + name_noise + ' ORDER BY name LIMIT ?',
            [scan_id, path, after, pattern] + name_args + [PAGE + 1], deadline, PAGE + 1)
        next_cursor = rows[PAGE - 1]['name'] if len(rows) > PAGE else None
    else:
        lo, hi = (path if path.endswith('/') else path + '/'), None
        hi = lo[:-1] + '0'
        path_noise, path_args = ('1=1', []) if show_system else _path_noise_sql('path')
        phase, _, last = cursor.partition(':') if cursor else ('folder', '', '')
        phase = phase if phase in ('folder', 'file') else 'folder'
        for kind in (['folder', 'file'] if phase == 'folder' else ['file']):
            start = last if kind == phase else ''
            got, capped = _timed(
                conn, 'SELECT ' + cols + ' FROM files INDEXED BY idx_files_path_prefix WHERE scan_id=? AND type=? '
                "AND path>? AND path>=? AND path<? AND name LIKE ? ESCAPE '\\' AND " + name_noise + ' AND ' + path_noise +
                ' LIMIT ?', [scan_id, kind, start, lo, hi, pattern] + name_args + path_args + [PAGE + 1 - len(rows)],
                deadline, PAGE + 1 - len(rows))
            rows.extend(got)
            if capped or len(rows) > PAGE:
                break
        next_cursor = None
        if len(rows) > PAGE:
            tail = rows[PAGE - 1]
            next_cursor = '%s:%s' % ('folder' if tail['type'] == 'folder' else 'file', tail['path'])
    entries = [_entry(r) for r in rows[:PAGE]]
    if capped:
        next_cursor = None
    return {'status': 'success', 'read_only': True, 'scan_id': scan_id, 'path': path, 'query': q,
            'scope': 'subtree' if subtree else 'folder', 'mode': 'prefix' if prefix else 'contains',
            'entries': entries, 'has_more': next_cursor is not None, 'next_cursor': next_cursor, 'capped': capped,
            'message': ('Search stopped after %g s — narrow the search (open a subfolder, or use more of the name).'
                        % SEARCH_BUDGET_S) if capped else None}


COUNT_PROBE = 5000  # object_members rows read at most, per dataset, to fill a missing file count
CATALOG_PAGE = 50   # default page size of the paginated Dataset lists
CATALOG_PAGE_MAX = 200


def _display_name(root_path):
    return (root_path or '').rstrip('/').rsplit('/', 1)[-1] or (root_path or '')


def scan_provenance(conn):
    """{scan_id: scan root, host, share, date} from `scans` (a small table), read-only."""
    out = {}
    for r in conn.execute('SELECT id, root, started, completed FROM scans'):
        host, share, _ = _classify(r['root'])
        stamp = _iso(r['completed'] or r['started'])
        out[r['id']] = {'scan_root': r['root'], 'host': host, 'share': share, 'scan_date': stamp[:10] if stamp else None}
    return out


_CAT_LOCK = threading.Lock()
_CAT = {}          # (index path, workspace flag, file signature) -> (loaded at, CandidateSet); at most two kept
CAT_TTL_S = 120    # a cached candidate list is never older than this, whatever the file signature says


def _signature(path):
    """Size and mtime of the index file and its WAL side file: changes whenever the scanner writes."""
    out = []
    for p in (path, path + '-wal'):
        try:
            st = os.stat(p)
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def candidate_set(workspace=False):
    """The sorted candidate list for the whole index, read once through the read-only opener and then reused.

    The cache is refreshed when the index file or its WAL changes, or after CAT_TTL_S. A refresh is one read of
    `data_objects` and `scans`; nothing is written. Raises IndexUnavailable when no index can be opened."""
    from ...services.dataset_catalog import CandidateSet
    path = (os.environ.get('SCIDK_EXTERNAL_INDEX_DB') or '').strip()
    key = (os.path.abspath(path) if path else '', bool(workspace), _signature(path) if path else None)
    with _CAT_LOCK:
        hit = _CAT.get(key)
        if hit and time.monotonic() - hit[0] < CAT_TTL_S:
            return hit[1]
        conn = _open()
        try:
            prov = scan_provenance(conn)
            rows = candidate_tuples(conn, workspace=workspace)
        finally:
            conn.close()
        found = CandidateSet(rows, prov, candidate_entry)
        _CAT[key] = (time.monotonic(), found)
        while len(_CAT) > 2:
            _CAT.pop(min(_CAT, key=lambda k: _CAT[k][0]))
        return found


def candidate_tuples(conn, scan_id='', system=False, workspace=False):
    """Like candidate_rows, but as plain tuples in CANDIDATE_FIELDS order (compact enough for ~10^6 rows)."""
    where, args = ['1=1'], []
    if scan_id:
        where.append('o.scan_id=?')
        args.append(scan_id)
    if not system:
        clause, extra = _path_noise_sql('o.root_path')
        where.append(clause)
        args += extra
    if not workspace:
        where.append("NOT (o.pattern_name LIKE '%workspace%' AND o.confidence<=0.5)")
    return [tuple(r) for r in conn.execute(
        'SELECT o.id, o.scan_id, o.pattern_name, o.root_path, o.file_count, o.total_bytes, o.confidence, o.status '
        'FROM data_objects o WHERE ' + ' AND '.join(where), args)]


def candidate_rows(conn, scan_id='', system=False, workspace=False):
    """Every recognized Dataset in the index as lean dicts (no row cap, no sorting here).

    Read-only: one SELECT over `data_objects`, keeping only the lean columns. Callers filter, sort globally and
    page; nothing is truncated before sorting. Counts come from the stored row."""
    where, args = ['1=1'], []
    if scan_id:
        where.append('o.scan_id=?')
        args.append(scan_id)
    if not system:
        clause, extra = _path_noise_sql('o.root_path')
        where.append(clause)
        args += extra
    if not workspace:
        where.append("NOT (o.pattern_name LIKE '%workspace%' AND o.confidence<=0.5)")
    cursor = conn.execute(
        'SELECT o.id, o.scan_id, o.pattern_name, o.root_path, o.file_count, o.total_bytes, o.confidence, o.status '
        'FROM data_objects o WHERE ' + ' AND '.join(where), args)
    return [{'id': r[0], 'scan_id': r[1], 'pattern_name': r[2], 'root_path': r[3], 'file_count': r[4],
             'total_bytes': r[5], 'confidence': r[6], 'status': r[7]} for r in cursor]


def candidate_entry(row, prov):
    """One candidate as the API returns it: the observed row plus its scan provenance."""
    p = prov.get(row['scan_id']) or {}
    return {'id': row['id'], 'scan_id': row['scan_id'], 'name': _display_name(row['root_path']),
            'pattern_name': row['pattern_name'], 'root_path': row['root_path'], 'file_count': row['file_count'],
            'total_bytes': row['total_bytes'], 'confidence': row['confidence'], 'status': row['status'],
            'scan_root': p.get('scan_root'), 'host': p.get('host'), 'share': p.get('share'),
            'scan_date': p.get('scan_date')}


def read_candidate(conn, scan_id, root_path):
    """The observed row for one (scan_id, root_path), or None. Read-only point lookup."""
    row = conn.execute(
        'SELECT id, scan_id, pattern_name, root_path, file_count, total_bytes, confidence, status FROM data_objects '
        'WHERE scan_id=? AND root_path=? LIMIT 1', (scan_id, root_path)).fetchone()
    if row is None:
        return None
    return candidate_entry({'id': row[0], 'scan_id': row[1], 'pattern_name': row[2], 'root_path': row[3],
                            'file_count': row[4], 'total_bytes': row[5], 'confidence': row[6], 'status': row[7]},
                           scan_provenance(conn))


def page_args(args=None):
    args = args if args is not None else request.args
    try:
        limit = max(1, min(CATALOG_PAGE_MAX, int(args.get('limit') or CATALOG_PAGE)))
    except (TypeError, ValueError):
        limit = CATALOG_PAGE
    try:
        offset = max(0, int(args.get('offset') or 0))
    except (TypeError, ValueError):
        offset = 0
    return limit, offset


@bp.get('/datasets/all')
@_guard
def datasets_all(conn):
    """Recognized Datasets across every scan, globally alphabetical by display name, paged.

    Read-only references keyed by (scan_id, root_path). Nothing is truncated before sorting: every candidate is read,
    sorted by (name, root, scan) and only then sliced by ?limit= (default 50, max 200) and ?offset=. Optional ?q=
    matches the name, root, profile, host, share and scan root. Provenance is joined from `scans`."""
    from ...services import dataset_catalog as dc
    limit, offset = page_args()
    q = (request.args.get('q') or '').strip()
    scan_id = (request.args.get('scan_id') or '').strip()
    if not scan_id and not _flag('system'):
        found = candidate_set(workspace=_flag('workspace'))
        idx = found.match(q)
        chunk = [found.entry(i) for i in idx[offset:offset + limit]]
        total = len(idx)
    else:
        prov = scan_provenance(conn)
        rows = [candidate_entry(r, prov) for r in candidate_rows(conn, scan_id=scan_id, system=_flag('system'), workspace=_flag('workspace'))]
        rows = [d for d in rows if dc.matches(q, d.get('name'), d.get('root_path'), d.get('pattern_name'), d.get('host'),
                                              d.get('share'), d.get('scan_root'))]
        rows.sort(key=dc.sort_key)
        chunk, total = rows[offset:offset + limit], len(rows)
    more = offset + limit < total
    return {'status': 'success', 'read_only': True, 'total': total, 'offset': offset, 'limit': limit,
            'has_more': more, 'next_offset': offset + limit if more else None, 'datasets': chunk}


@bp.get('/datasets')
@_guard
def datasets(conn):
    scan_id = (request.args.get('scan_id') or '').strip()
    root = _scan_root(conn, scan_id)
    if root is None:
        return {'status': 'error', 'error': 'Unknown scan.'}, 404
    path = (request.args.get('path') or root).rstrip('/') or '/'
    # This folder or anything beneath it; never a bare prefix (/huang must not match /huangw). One ordered range
    # over idx_do_root (no OR, no sort) so the 200-row page stops early; the substr check drops names such as
    # "<path>.old" that sort inside the range.
    prefix = path if path.endswith('/') else path + '/'
    where = ['scan_id=?', 'root_path>=?', 'root_path<?', '(root_path=? OR substr(root_path,1,?)=?)']
    args = [scan_id, path, prefix[:-1] + '0', path, len(prefix), prefix]
    if not _flag('system'):
        clause, extra = _path_noise_sql('root_path')
        where.append(clause)
        args += extra
    if not _flag('workspace'):
        where.append("NOT (pattern_name LIKE '%workspace%' AND confidence<=0.5)")
    rows = conn.execute(
        'SELECT id, pattern_name, root_path, file_count, total_bytes, confidence, status FROM data_objects INDEXED BY idx_do_root WHERE ' +
        ' AND '.join(where) + ' ORDER BY root_path LIMIT ?', args + [PAGE + 1]).fetchall()
    out = []
    for r in rows[:PAGE]:
        count, pending, capped = r['file_count'], False, False
        if count is None:
            # object_members is indexed by object_id; read at most COUNT_PROBE of one dataset's members.
            n = conn.execute('SELECT COUNT(*) FROM (SELECT 1 FROM object_members WHERE object_id=? LIMIT ?)',
                             (r['id'], COUNT_PROBE + 1)).fetchone()[0]
            if n:
                count, capped = min(n, COUNT_PROBE), n > COUNT_PROBE
            else:
                pending = True
        out.append({'id': r['id'], 'pattern_name': r['pattern_name'], 'root_path': r['root_path'], 'file_count': count,
                    'file_count_is_minimum': capped, 'count_pending': pending, 'total_bytes': r['total_bytes'],
                    'confidence': r['confidence'], 'status': r['status']})
    return {'status': 'success', 'read_only': True, 'scan_id': scan_id, 'path': path, 'has_more': len(rows) > PAGE,
            'datasets': out}
