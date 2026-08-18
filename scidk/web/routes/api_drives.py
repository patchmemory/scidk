"""Blueprint for the Drives API — the Add Drive drawer's backend (Task group G).

A *drive* is a place SciDK can read files from: a local directory, or an rclone
remote. Providers (``scidk/core/providers.py``) discover what the host happens
to offer at startup; this table is the editable half — what the operator has
deliberately added, persisted so it survives a restart without anyone editing
``rclone.conf`` or ``SCIDK_LOCAL_FILES_BASE`` by hand.

Storage is the ``drives`` table in ``files.db``, created in
``path_index_sqlite.init_db`` (never in ``migrations.py`` — that module runs
against every test database and none of them has a ``files`` table).

Reachability is probed, not assumed, and cached for
:data:`_CONNECTED_TTL_SECONDS` — ``/api/servers`` reported a hardcoded
``connected: true`` for years, which made a dead remote and a live one look
identical in the sidebar.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from ..decorators import require_role

bp = Blueprint('drives', __name__, url_prefix='/api')

#: Reading the drive list is an ordinary page load; changing it runs subprocesses
#: and touches host configuration, so writes are admin-only. Spelled out rather
#: than relying on a hierarchy: require_role is a flat membership test, so
#: 'admin' has to be listed explicitly wherever users are allowed too.
_READ_ROLES = ('admin', 'user')

#: A probe costs a subprocess and up to a few seconds of timeout. Every sidebar
#: render asks for every drive, so the answer is cached for this long.
_CONNECTED_TTL_SECONDS = 30.0

#: Timeouts for the two rclone probes. The list probe runs behind a page load,
#: so it is the tighter of the two; the explicit "Test" button can afford more.
_PROBE_TIMEOUT = 3
_TEST_TIMEOUT = 5

#: browse-local caps its listing here. A directory with 100k entries is not
#: something a path picker should try to render.
_BROWSE_LIMIT = 200

#: rclone identifiers and config keys are interpolated into an argv list. No
#: shell is involved, so there is no quoting hazard, but a value starting with
#: '-' would be read by rclone as a flag. Anchored character classes make that
#: unrepresentable rather than escaped.
_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
_PARAM_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')


# ── storage ────────────────────────────────────────────────────────────────

def _conn():
    from ...core import path_index_sqlite as pix
    conn = pix.connect()
    pix.init_db(conn)
    return conn


def _row_to_drive(row) -> Dict[str, Any]:
    did, dtype, label, path, name, remote_type, created_at = row
    out: Dict[str, Any] = {
        'id': did,
        'type': dtype,
        'label': label or name or path or did,
        'created_at': created_at,
    }
    if dtype == 'local_fs':
        out['path'] = path
    else:
        out['name'] = name
        out['remote_type'] = remote_type
    return out


def _load_drives() -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = _conn()
        rows = conn.execute(
            "SELECT id, type, label, path, name, remote_type, created_at FROM drives ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [_row_to_drive(r) for r in rows]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ── reachability ───────────────────────────────────────────────────────────

def _rclone_exe() -> Optional[str]:
    return shutil.which('rclone')


def _probe_local(path: str) -> bool:
    return bool(path) and os.access(path, os.R_OK)


def _probe_rclone(name: str, timeout: int = _PROBE_TIMEOUT) -> subprocess.CompletedProcess | None:
    """``rclone lsjson <name>: --max-depth 0``, or None if rclone is absent.

    Returns the completed process so callers that want stderr can have it. A
    timeout is reported as a returncode of 124, matching the shell convention,
    rather than raising into a 500.
    """
    exe = _rclone_exe()
    if not exe:
        return None
    try:
        return subprocess.run(
            [exe, 'lsjson', f'{name}:', '--max-depth', '0'],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args=[], returncode=124, stdout='', stderr='timed out')
    except OSError as e:
        return subprocess.CompletedProcess(args=[], returncode=127, stdout='', stderr=str(e))


def _cache() -> Dict[str, Any]:
    return current_app.extensions['scidk'].setdefault('drive_connectivity', {})


def check_connected(drive: Dict[str, Any]) -> bool:
    """Whether this drive is reachable right now, cached for 30 seconds.

    Shared with ``/api/servers`` (J1) so the two surfaces cannot disagree about
    whether a remote is up.
    """
    key = drive.get('id') or f"{drive.get('type')}:{drive.get('path') or drive.get('name')}"
    cache = _cache()
    hit = cache.get(key)
    now = time.time()
    if hit and (now - hit[0]) < _CONNECTED_TTL_SECONDS:
        return hit[1]

    dtype = drive.get('type')
    if dtype == 'local_fs':
        ok = _probe_local(drive.get('path') or '')
    elif dtype == 'rclone':
        proc = _probe_rclone(drive.get('name') or '')
        ok = bool(proc and proc.returncode == 0)
    else:
        ok = False

    cache[key] = (now, ok)
    return ok


def invalidate_connectivity_cache(drive_id: Optional[str] = None) -> None:
    """Drop cached reachability, for one drive or all of them.

    Called after a write so the sidebar does not spend 30 seconds insisting a
    just-added drive is unreachable.
    """
    cache = _cache()
    if drive_id is None:
        cache.clear()
    else:
        cache.pop(drive_id, None)


# ── G1 — list ──────────────────────────────────────────────────────────────

@bp.get('/drives')
@require_role(*_READ_ROLES)
def api_drives_list():
    """Every configured drive, with a probed ``connected`` flag."""
    try:
        drives = _load_drives()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    for d in drives:
        d['connected'] = check_connected(d)
    return jsonify({'drives': drives}), 200


# ── G2 — add ───────────────────────────────────────────────────────────────

def _insert_drive(drive_id: str, dtype: str, label: str, path: str = '',
                  name: str = '', remote_type: str = ''):
    conn = None
    try:
        conn = _conn()
        existing = conn.execute("SELECT 1 FROM drives WHERE id = ?", (drive_id,)).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO drives(id, type, label, path, name, remote_type, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (drive_id, dtype, label, path or None, name or None, remote_type or None, time.time()),
        )
        conn.commit()
        return True
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _rclone_remote_exists(name: str) -> bool:
    exe = _rclone_exe()
    if not exe:
        return False
    try:
        proc = subprocess.run([exe, 'config', 'show', name],
                              capture_output=True, text=True, timeout=_PROBE_TIMEOUT, check=False)
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _rclone_config_create(name: str, remote_type: str, params: Dict[str, Any]):
    """``rclone config create`` for a remote whose credentials we were given.

    Returns ``(ok, stderr)``. Keys and the remote name are validated by the
    caller; values are passed through as ``key=value`` argv elements, never a
    shell string.
    """
    exe = _rclone_exe()
    if not exe:
        return False, 'rclone is not installed on the server'
    argv = [exe, 'config', 'create', name, remote_type, '--non-interactive']
    for key, value in params.items():
        if value is None or value == '':
            continue
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        argv.append(f'{key}={value}')
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        return False, 'rclone config create timed out'
    except OSError as e:
        return False, str(e)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or '').strip() or f'rclone exited {proc.returncode}'
    return True, ''


@bp.post('/drives')
@require_role('admin')
def api_drives_create():
    body = request.get_json(silent=True) or {}
    dtype = str(body.get('type') or '').strip()

    if dtype == 'local_fs':
        path = str(body.get('path') or '').strip()
        if not path:
            return jsonify({'error': 'path is required'}), 400
        resolved = str(Path(path).expanduser())
        if not os.path.isdir(resolved):
            return jsonify({'error': f'not a directory: {resolved}'}), 400
        if not os.access(resolved, os.R_OK):
            return jsonify({'error': f'not readable: {resolved}'}), 403
        label = str(body.get('label') or '').strip() or Path(resolved).name or resolved
        # Keyed on the path, not the label: two drives pointing at the same
        # directory are the same drive however they are named.
        drive_id = f'local:{resolved}'
        if not _insert_drive(drive_id, 'local_fs', label, path=resolved):
            return jsonify({'error': 'drive already exists', 'id': drive_id}), 409
        invalidate_connectivity_cache(drive_id)
        return jsonify({'status': 'ok', 'id': drive_id}), 201

    if dtype == 'rclone':
        name = str(body.get('name') or '').strip()
        remote_type = str(body.get('remote_type') or '').strip()
        if not _NAME_RE.match(name):
            return jsonify({'error': 'name must be alphanumeric, starting with a letter or digit'}), 400
        params = body.get('params') or {}
        if not isinstance(params, dict):
            return jsonify({'error': 'params must be an object'}), 400
        # Drop empties before deciding which path we are on: the drawer sends
        # every field of the chosen backend, blank ones included, so a form the
        # user left empty must not read as "create a remote with no settings".
        params = {k: v for k, v in params.items() if v not in (None, '', False)}

        drive_id = f'rclone:{name}'
        if params:
            if not _NAME_RE.match(remote_type):
                return jsonify({'error': 'remote_type is required to create a remote'}), 400
            bad = [k for k in params if not _PARAM_KEY_RE.match(str(k))]
            if bad:
                return jsonify({'error': f'invalid parameter name(s): {", ".join(sorted(bad))}'}), 400
            ok, err = _rclone_config_create(name, remote_type, params)
            if not ok:
                return jsonify({'error': f'rclone config create failed: {err}'}), 500
        else:
            # No credentials given, so the remote has to exist already —
            # typically an OAuth backend the operator set up with `rclone config`.
            if not _rclone_remote_exists(name):
                return jsonify({
                    'error': f'no rclone remote named "{name}". Create it with '
                             f'`rclone config`, or supply params to create it here.'
                }), 400
            if not remote_type:
                remote_type = ''

        if not _insert_drive(drive_id, 'rclone', str(body.get('label') or '').strip() or name,
                             name=name, remote_type=remote_type):
            return jsonify({'error': 'drive already exists', 'id': drive_id}), 409
        invalidate_connectivity_cache(drive_id)
        return jsonify({'status': 'ok', 'id': drive_id}), 201

    return jsonify({'error': "type must be 'local_fs' or 'rclone'"}), 400


# ── G3 — remove ────────────────────────────────────────────────────────────

@bp.delete('/drives/<path:drive_id>')
@require_role('admin')
def api_drives_delete(drive_id):
    conn = None
    try:
        conn = _conn()
        row = conn.execute("SELECT type, name FROM drives WHERE id = ?", (drive_id,)).fetchone()
        if not row:
            return jsonify({'error': 'drive not found'}), 404
        dtype, name = row
        conn.execute("DELETE FROM drives WHERE id = ?", (drive_id,))
        conn.commit()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    invalidate_connectivity_cache(drive_id)

    out: Dict[str, Any] = {'status': 'ok'}
    # Forgetting a drive and destroying its rclone credentials are different
    # acts, so the destructive one is opt-in per request.
    if dtype == 'rclone' and (request.args.get('delete_remote') or '').lower() in ('1', 'true', 'yes'):
        exe = _rclone_exe()
        if not exe:
            out['remote_deleted'] = False
            out['remote_error'] = 'rclone is not installed on the server'
        else:
            try:
                proc = subprocess.run([exe, 'config', 'delete', name or ''],
                                      capture_output=True, text=True, timeout=_PROBE_TIMEOUT, check=False)
                out['remote_deleted'] = (proc.returncode == 0)
                if proc.returncode != 0:
                    out['remote_error'] = (proc.stderr or '').strip()
            except (subprocess.TimeoutExpired, OSError) as e:
                out['remote_deleted'] = False
                out['remote_error'] = str(e)
    return jsonify(out), 200


# ── G4 — enumerate the host filesystem ─────────────────────────────────────

@bp.get('/drives/browse-local')
@require_role('admin')
def api_drives_browse_local():
    """Directories under ``path``, so the drawer can offer a path picker.

    Admin-only: it enumerates the host filesystem outside any provider root,
    which is exactly the information a provider root exists to bound.
    """
    raw = (request.args.get('path') or '/').strip() or '/'
    show_files = (request.args.get('show_files') or '').lower() in ('1', 'true', 'yes')
    p = Path(raw).expanduser()

    if not p.exists():
        return jsonify({'error': 'Path not found', 'path': str(p), 'entries': []}), 404
    if not p.is_dir():
        return jsonify({'error': 'Not a directory', 'path': str(p), 'entries': []}), 400

    entries: List[Dict[str, Any]] = []
    try:
        for child in sorted(p.iterdir(), key=lambda c: c.name.lower()):
            if child.name.startswith('.'):
                continue
            try:
                is_dir = child.is_dir()
            except OSError:
                # A broken symlink or a mount the process cannot stat. Skipping
                # it beats failing the whole listing.
                continue
            if not is_dir and not show_files:
                continue
            entries.append({
                'name': child.name,
                'path': str(child),
                'type': 'dir' if is_dir else 'file',
                'readable': os.access(child, os.R_OK),
            })
            if len(entries) >= _BROWSE_LIMIT:
                break
    except PermissionError:
        return jsonify({'error': 'Permission denied', 'path': str(p), 'entries': []}), 403
    except OSError as e:
        return jsonify({'error': str(e), 'path': str(p), 'entries': []}), 500

    out = {'path': str(p), 'entries': entries}
    if len(entries) >= _BROWSE_LIMIT:
        out['truncated'] = True
    return jsonify(out), 200


# ── G5 — test a connection ─────────────────────────────────────────────────

@bp.get('/drives/test')
@require_role('admin')
def api_drives_test():
    name = (request.args.get('name') or '').strip()
    path = (request.args.get('path') or '').strip()

    if path:
        resolved = str(Path(path).expanduser())
        if not os.path.isdir(resolved):
            return jsonify({'status': 'error', 'error': f'not a directory: {resolved}'}), 404
        if not os.access(resolved, os.R_OK):
            return jsonify({'status': 'error', 'error': f'not readable: {resolved}'}), 403
        return jsonify({'status': 'ok', 'message': f'Readable — {resolved}'}), 200

    if not name:
        return jsonify({'status': 'error', 'error': 'name or path is required'}), 400
    if not _NAME_RE.match(name):
        return jsonify({'status': 'error', 'error': 'invalid remote name'}), 400

    proc = _probe_rclone(name, timeout=_TEST_TIMEOUT)
    if proc is None:
        return jsonify({'status': 'error', 'error': 'rclone is not installed on the server'}), 400
    if proc.returncode != 0:
        detail = (proc.stderr or '').strip().splitlines()
        return jsonify({
            'status': 'error',
            'error': detail[-1] if detail else f'rclone exited {proc.returncode}',
        }), 400

    # lsjson prints a JSON array; its length is the item count at the root.
    count = None
    try:
        import json as _json
        parsed = _json.loads(proc.stdout or '[]')
        if isinstance(parsed, list):
            count = len(parsed)
    except Exception:
        count = None
    message = f'Connected — {count} item(s) at root' if count is not None else 'Connected'
    return jsonify({'status': 'ok', 'message': message}), 200


# ── G6 — rclone OAuth ──────────────────────────────────────────────────────

#: Backends whose credentials come from an OAuth handshake rather than a form.
OAUTH_BACKENDS = ('dropbox', 'drive', 'onedrive', 'box', 'pcloud', 'yandex')

_OAUTH_INSTRUCTIONS = (
    'OAuth remotes cannot be authorized from the server. rclone runs the '
    'callback listener on the machine that starts the handshake (localhost:53682), '
    'so a browser on your workstation cannot complete a flow started here.\n\n'
    'Run this in a terminal on the SciDK host:\n'
    '    rclone config create {name} {type}\n\n'
    'Then add it here without params — the drawer will import the existing remote.'
)


@bp.post('/drives/rclone/oauth')
@require_role('admin')
def api_drives_rclone_oauth():
    """Not implemented, deliberately, with the working alternative spelled out.

    ``rclone authorize`` binds its callback listener to loopback on whichever
    machine runs it. Started from this process, that is the server, so the
    operator's browser has nowhere to redirect to. Rather than ship a flow that
    only works when SciDK happens to run on the operator's own desktop, this
    reports the one procedure that always works. Once the remote exists,
    ``POST /api/drives`` with no params imports it (G2's third case).
    """
    body = request.get_json(silent=True) or {}
    remote_type = str(body.get('type') or '').strip() or '<type>'
    name = str(body.get('name') or '').strip() or remote_type
    return jsonify({
        'status': 'error',
        'error': _OAUTH_INSTRUCTIONS.format(name=name, type=remote_type),
        'manual_command': f'rclone config create {name} {remote_type}',
    }), 501


@bp.get('/drives/rclone/oauth/status')
@require_role('admin')
def api_drives_rclone_oauth_status():
    """Whether an rclone remote of this name exists yet.

    The poll half of the manual flow: the operator runs ``rclone config`` in a
    terminal, and the drawer watches for the remote to appear.
    """
    name = (request.args.get('name') or '').strip()
    if not _NAME_RE.match(name):
        return jsonify({'status': 'error', 'error': 'invalid remote name'}), 400
    if not _rclone_exe():
        return jsonify({'status': 'error', 'error': 'rclone is not installed on the server'}), 400
    if _rclone_remote_exists(name):
        return jsonify({'status': 'ok', 'remote': name}), 200
    return jsonify({'status': 'pending'}), 200
