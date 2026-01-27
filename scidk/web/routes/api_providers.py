"""
Blueprint for Provider/rclone management API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
from typing import Optional
import json
import os
import subprocess
import shutil
import time

bp = Blueprint('providers', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

def _feature_rclone_mounts() -> bool:
    """Check if rclone mounts feature is enabled."""
    val = (os.environ.get('SCIDK_RCLONE_MOUNTS') or os.environ.get('SCIDK_FEATURE_RCLONE_MOUNTS') or '').strip().lower()
    return val in ('1', 'true', 'yes', 'y', 'on')

@bp.get('/providers')
def api_providers():
    provs = _get_ext()['providers']
    out = []
    for d in provs.list():
        out.append({
            'id': d.id,
            'display_name': d.display_name,
            'capabilities': d.capabilities,
            'auth': d.auth,
        })
    return jsonify(out), 200


@bp.get('/provider_roots')
def api_provider_roots():
    prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
    try:
        provs = _get_ext()['providers']
        prov = provs.get(prov_id)
        if not prov:
            return jsonify({'error': 'provider not available'}), 400
        roots = prov.list_roots()
        return jsonify([{'id': r.id, 'name': r.name, 'path': r.path} for r in roots]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Rclone Mount Manager (feature-flagged)
# These routes are only registered if SCIDK_RCLONE_MOUNTS is enabled

def _mounts_dir() -> Path:
    """Get mounts directory."""
    d = Path(current_app.root_path).parent / 'data' / 'mounts'
    d.mkdir(parents=True, exist_ok=True)
    return d

def _sanitize_name(name: str) -> str:
    """Sanitize mount name for filesystem safety."""
    safe = ''.join([c for c in (name or '') if c.isalnum() or c in ('-', '_')]).strip()
    return safe[:64] if safe else ''

def _listremotes() -> list:
    """List available rclone remotes."""
    try:
        provs = _get_ext()['providers']
        rp = provs.get('rclone') if provs else None
        roots = rp.list_roots() if rp else []
        return [r.id for r in roots]
    except Exception:
        return []

def _rclone_exe() -> Optional[str]:
    """Get path to rclone executable."""
    return shutil.which('rclone')


# Rclone mount routes (check feature flag in handlers)
@bp.get('/rclone/mounts')
def api_rclone_mounts_list():
    mounts_mem = _get_ext().setdefault('rclone_mounts', {})
    rows = []
    try:
        from ..core import path_index_sqlite as pix
        from ..core import migrations as _migs
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute("SELECT id, provider, root, created, status, extra_json FROM provider_mounts WHERE provider='rclone'")
            rows = cur.fetchall() or []
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        rows = []
    out = []
    for (mid, provider, remote, created, status_persisted, extra) in rows:
        try:
            extra_obj = json.loads(extra) if extra else {}
        except Exception:
            extra_obj = {}
        mem = mounts_mem.get(mid) or {}
        proc = mem.get('process')
        alive = (proc is not None) and (proc.poll() is None)
        status = 'running' if alive else ('exited' if proc is not None else (status_persisted or 'unknown'))
        exit_code = None if alive else (proc.returncode if proc is not None else None)
        out.append({
            'id': mid,
            'name': mid,
            'remote': remote,
            'subpath': extra_obj.get('subpath'),
            'path': extra_obj.get('path'),
            'read_only': extra_obj.get('read_only'),
            'started_at': created,
            'status': status,
            'exit_code': exit_code,
            'log_file': extra_obj.get('log_file'),
            'pid': extra_obj.get('pid') or mem.get('pid'),
        })
    return jsonify(out), 200

@bp.post('/rclone/mounts')
def api_rclone_mounts_create():
    if not _rclone_exe():
        return jsonify({'error': 'rclone not installed'}), 400
    try:
        body = request.get_json(silent=True) or {}
        remote = str(body.get('remote') or '').strip()
        subpath = str(body.get('subpath') or '').strip().lstrip('/')
        name = _sanitize_name(str(body.get('name') or ''))
        read_only = bool(body.get('read_only', True))
        if not remote:
            return jsonify({'error': 'remote required'}), 400
        if not remote.endswith(':'):
            remote = remote + ':'
        if not name:
            return jsonify({'error': 'name required'}), 400
        # Safety: restrict mountpoint and validate remote exists
        remotes = _listremotes()
        if remote not in remotes:
            return jsonify({'error': f'remote not configured: {remote}'}), 400
        mdir = _mounts_dir()
        mpath = mdir / name
        try:
            mpath.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return jsonify({'error': f'failed to create mount dir: {e}'}), 500
        target = remote + (subpath if subpath else '')
        log_file = mdir / f"{name}.log"
        # Build rclone command
        args = [
            _rclone_exe(), 'mount', target, str(mpath),
            '--dir-cache-time', '60m',
            '--poll-interval', '30s',
            '--vfs-cache-mode', 'minimal',
            '--log-format', 'DATE,TIME,LEVEL',
            '--log-level', 'INFO',
            '--log-file', str(log_file),
        ]
        if read_only:
            args.append('--read-only')
        # Launch subprocess detached from terminal; logs go to file
        try:
            fnull = open(os.devnull, 'wb')
            proc = subprocess.Popen(args, stdout=fnull, stderr=fnull)
        except Exception as e:
            return jsonify({'error': f'failed to start rclone: {e}'}), 500
        rec = {
            'id': name,
            'name': name,
            'remote': remote,
            'subpath': subpath,
            'path': str(mpath),
            'read_only': bool(read_only),
            'started_at': time.time(),
            'process': proc,
            'pid': proc.pid if proc else None,
            'log_file': str(log_file),
        }
        mounts = _get_ext().setdefault('rclone_mounts', {})
        mounts[name] = rec
        # Persist mount definition to SQLite (best-effort)
        try:
            from ..core import path_index_sqlite as pix
            from ..core import migrations as _migs
            conn = pix.connect()
            try:
                _migs.migrate(conn)
                cur = conn.cursor()
                extra = {
                    'subpath': subpath,
                    'path': str(mpath),
                    'read_only': bool(read_only),
                    'log_file': str(log_file),
                    'pid': rec.get('pid'),
                }
                cur.execute(
                    "INSERT OR REPLACE INTO provider_mounts(id, provider, root, created, status, extra_json) VALUES(?,?,?,?,?,?)",
                    (name, 'rclone', remote, float(rec.get('started_at') or time.time()), 'running', json.dumps(extra))
                )
                conn.commit()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception:
            pass
        return jsonify({'id': name, 'path': str(mpath)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.delete('/rclone/mounts/<mid>')
def api_rclone_mounts_delete(mid):
    mounts = _get_ext().setdefault('rclone_mounts', {})
    m = mounts.get(mid)
    if not m:
        return jsonify({'error': 'not found'}), 404
    proc = m.get('process')
    mpath = m.get('path')
    try:
        if proc and (proc.poll() is None):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        # Best-effort unmount
        try:
            subprocess.run(['fusermount', '-u', mpath], check=False)
        except Exception:
            pass
        try:
            subprocess.run(['umount', mpath], check=False)
        except Exception:
            pass
    except Exception:
        pass
    mounts.pop(mid, None)
    # Remove persisted mount definition (best-effort)
    try:
        from ..core import path_index_sqlite as pix
        from ..core import migrations as _migs
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute("DELETE FROM provider_mounts WHERE id = ?", (mid,))
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass
    return jsonify({'ok': True}), 200

@bp.get('/rclone/mounts/<mid>/logs')
def api_rclone_mounts_logs(mid):
    mounts = _get_ext().setdefault('rclone_mounts', {})
    m = mounts.get(mid)
    if not m:
        return jsonify({'error': 'not found'}), 404
    tail_n = int(request.args.get('tail') or 200)
    path = m.get('log_file')
    lines = []
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            lines = fh.readlines()
    except Exception:
        lines = []
    if tail_n > 0 and len(lines) > tail_n:
        lines = lines[-tail_n:]
    return jsonify({'lines': [ln.rstrip('\n') for ln in lines]}), 200

@bp.get('/rclone/mounts/<mid>/health')
def api_rclone_mounts_health(mid):
    mounts = _get_ext().setdefault('rclone_mounts', {})
    m = mounts.get(mid)
    if not m:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    proc = m.get('process')
    alive = (proc is not None) and (proc.poll() is None)
    path = m.get('path')
    listable = False
    try:
        p = Path(path)
        listable = p.exists() and p.is_dir() and (len(list(p.iterdir())) >= 0)
    except Exception:
        listable = False
    return jsonify({'ok': bool(alive and listable), 'alive': bool(alive), 'listable': bool(listable)}), 200
