"""
Blueprint for Interpreter configuration API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os

from ..decorators import require_role

bp = Blueprint('interpreters', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

@bp.get('/interpreters')
def api_interpreters():
        # Unified listing: registry metadata + toggle/usage/metrics + effective view override
        reg = _get_ext()['registry']
        # Build mapping ext -> interpreter ids
        ext_map = {}
        for ext, interps in reg.by_extension.items():
            ext_map[ext] = [getattr(i, 'id', 'unknown') for i in interps]
        items = []
        for iid, interp in reg.by_id.items():
            globs = sorted([ext for ext, ids in ext_map.items() if iid in ids])
            it = {
                'id': iid,
                'name': getattr(interp, 'name', iid),
                'version': getattr(interp, 'version', '0.0.1'),
                'globs': globs,
                'default_enabled': bool(getattr(interp, 'default_enabled', getattr(reg, 'default_enabled', True))),
                'cost': getattr(interp, 'cost', None),
                'extensions': globs,
                'enabled': True,
                'runtime': getattr(interp, 'runtime', 'python'),
                'last_used': getattr(reg, 'get_last_used', lambda _x: None)(iid),
                'success_rate': getattr(reg, 'get_success_rate', lambda _x: 0.0)(iid),
            }
            try:
                it['enabled'] = reg._is_enabled(iid)
            except Exception:
                pass
            items.append(it)
        # Optional effective view from app extensions (e.g., CLI/env overridden)
        view = (request.args.get('view') or '').strip().lower()
        if view == 'effective':
            interp_state = _get_ext().get('interpreters', {})
            eff = set(interp_state.get('effective_enabled') or [])
            src = interp_state.get('source') or 'default'
            for it in items:
                it['enabled'] = (it['id'] in eff)
                it['source'] = src
        return jsonify(items), 200


@bp.get('/interpreters/effective_debug')
def api_interpreters_effective_debug():
        istate = current_app.extensions.get('scidk', {}).get('interpreters', {})
        eff = sorted(list(istate.get('effective_enabled') or []))
        src = istate.get('source') or 'default'
        unknown_env = istate.get('unknown_env') or {}
        reg = _get_ext()['registry']
        all_ids = sorted(list(reg.by_id.keys()))
        default_enabled = []
        for iid in all_ids:
            try:
                if bool(getattr(reg.by_id[iid], 'default_enabled', True)):
                    default_enabled.append(iid)
            except Exception:
                pass
        loaded = []
        try:
            settings = _get_ext().get('settings')
            if settings is not None and src != 'cli':
                loaded = sorted(list(settings.load_enabled_interpreters() or []))
        except Exception:
            loaded = []
        en_raw = [s.strip() for s in (os.environ.get('SCIDK_ENABLE_INTERPRETERS') or '').split(',') if s.strip()]
        dis_raw = [s.strip() for s in (os.environ.get('SCIDK_DISABLE_INTERPRETERS') or '').split(',') if s.strip()]
        en_norm = [s.lower() for s in en_raw]
        dis_norm = [s.lower() for s in dis_raw]
        return jsonify({
            'source': src,
            'effective_enabled': eff,
            'default_enabled': sorted(default_enabled),
            'loaded_settings': loaded,
            'env': {
                'enable_raw': en_raw,
                'disable_raw': dis_raw,
                'enable_norm': en_norm,
                'disable_norm': dis_norm,
                'unknown': unknown_env,
            }
        }), 200


@bp.post('/interpreters/<interpreter_id>/toggle')
def api_interpreters_toggle(interpreter_id):
        reg = _get_ext()['registry']
        data = request.get_json(force=True, silent=True) or {}
        enabled = bool(data.get('enabled', True))
        if enabled:
            reg.enable_interpreter(interpreter_id)
        else:
            reg.disable_interpreter(interpreter_id)
        # Persist if settings available
        try:
            settings = _get_ext().get('settings')
            if settings is not None:
                settings.save_enabled_interpreters(reg.enabled_interpreters)
        except Exception:
            pass
        # Refresh effective interpreter view so /api/interpreters?view=effective reflects the change immediately
        try:
            istate = _get_ext().setdefault('interpreters', {})
            eff = set(istate.get('effective_enabled') or [])
            # If snapshot missing/empty, rebuild from current registry state
            if not eff:
                eff = set([iid for iid in reg.by_id.keys() if reg._is_enabled(iid)])
            if enabled:
                eff.add(interpreter_id)
            else:
                eff.discard(interpreter_id)
            istate['effective_enabled'] = eff
        except Exception:
            pass
        return jsonify({'status': 'updated', 'enabled': enabled}), 200


@bp.route('/settings/rclone-interpret', methods=['GET', 'POST'])
def api_settings_rclone_interpret():
        if request.method == 'GET':
            # Load current settings
            try:
                from ...core import path_index_sqlite as pix
                from ...core import migrations as _migs
                conn = pix.connect()
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    suggest_row = cur.execute("SELECT value FROM settings WHERE key = ?", ('rclone.interpret.suggest_mount_threshold',)).fetchone()
                    batch_row = cur.execute("SELECT value FROM settings WHERE key = ?", ('rclone.interpret.max_files_per_batch',)).fetchone()
                    suggest = int(suggest_row[0]) if suggest_row else 400
                    max_batch = int(batch_row[0]) if batch_row else 1000
                finally:
                    conn.close()
                return jsonify({'suggest_mount_threshold': suggest, 'max_files_per_batch': max_batch}), 200
            except Exception as e:
                return jsonify({'suggest_mount_threshold': 400, 'max_files_per_batch': 1000}), 200

        # POST: Save settings
        data = request.get_json(force=True, silent=True) or {}
        try:
            suggest = int(data.get('suggest_mount_threshold')) if data.get('suggest_mount_threshold') not in (None, '') else None
        except Exception:
            suggest = None
        try:
            max_batch = int(data.get('max_files_per_batch')) if data.get('max_files_per_batch') not in (None, '') else None
        except Exception:
            max_batch = None
        # Validate and clamp
        if suggest is not None:
            suggest = max(0, int(suggest))
        if max_batch is not None:
            max_batch = min(max(100, int(max_batch)), 2000)
        # Persist best-effort
        try:
            from ...core import path_index_sqlite as pix
            from ...core import migrations as _migs
            conn = pix.connect()
            try:
                _migs.migrate(conn)
                cur = conn.cursor()
                if suggest is not None:
                    cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", ('rclone.interpret.suggest_mount_threshold', str(suggest)))
                if max_batch is not None:
                    cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", ('rclone.interpret.max_files_per_batch', str(max_batch)))
                conn.commit()
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception:
            pass
        # Update in-memory config
        if suggest is not None:
            current_app.config['rclone.interpret.suggest_mount_threshold'] = int(suggest)
        if max_batch is not None:
            current_app.config['rclone.interpret.max_files_per_batch'] = int(max_batch)
        return jsonify({'ok': True, 'suggest_mount_threshold': int(current_app.config.get('rclone.interpret.suggest_mount_threshold', 400)), 'max_files_per_batch': int(current_app.config.get('rclone.interpret.max_files_per_batch', 1000))}), 200

    # Settings APIs for Neo4j configuration


# ── Interpret tab (H3, H4) ────────────────────────────────────────────────
#
# Both routes work on caller-supplied index paths. `files.path` is the key:
# remote scans store `remote:rel/path`, local scans a resolved absolute path,
# and the browser gets those strings from /api/browse or /api/scans/<id>/browse,
# so it can hand them straight back.

#: Bounds a request the drawer builds from a selection. A user can tick a whole
#: directory; they cannot usefully read the status of ten thousand files.
_MAX_STATUS_PATHS = 500


def _requested_paths():
    """Paths from ``paths[]=`` (the drawer's spelling) or ``paths=``."""
    values = request.args.getlist('paths[]') or request.args.getlist('paths')
    seen, out = set(), []
    for v in values:
        v = (v or '').strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _interpreter_meta(interpreter_id):
    """(name, version) for a registry id, falling back to the id itself."""
    reg = _get_ext().get('registry')
    interp = getattr(reg, 'by_id', {}).get(interpreter_id) if reg else None
    return (
        getattr(interp, 'name', interpreter_id) or interpreter_id,
        getattr(interp, 'version', None),
    )


def _expected_interpreter(extension):
    """Which interpreter *should* handle this extension, per the scanner's table."""
    from ...core.scanner_formats import KNOWN_INTERPRETERS
    return KNOWN_INTERPRETERS.get((extension or '').lower())


@bp.get('/interpreters/status')
def api_interpreters_status():
    """Which interpreters have run over each of these paths, and which have not.

    One batched query over ``files`` — ``idx_files_path`` covers it — joined
    against the extension table so a file that *should* have been interpreted
    but never was is reported as missing rather than omitted.

    A path the index has never seen is reported under ``unknown_paths`` rather
    than silently dropped: "no interpreter ran" and "this file was never
    scanned" are different problems.
    """
    paths = _requested_paths()
    if not paths:
        return jsonify({'error': 'paths[] is required', 'interpreters': []}), 400
    if len(paths) > _MAX_STATUS_PATHS:
        return jsonify({
            'error': f'too many paths ({len(paths)}); the maximum is {_MAX_STATUS_PATHS}',
            'interpreters': [],
        }), 400

    from ...core import path_index_sqlite as pix

    conn = None
    try:
        conn = pix.connect()
        pix.init_db(conn)
        placeholders = ','.join('?' for _ in paths)
        rows = conn.execute(
            "SELECT path, name, file_extension, interpreted_as, interpreted_at, interpreter_version "
            f"FROM files WHERE path IN ({placeholders})",
            paths,
        ).fetchall()
    except Exception as e:
        return jsonify({'error': str(e), 'interpreters': []}), 500
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # A path can appear once per scan. The most recent interpretation is the
    # answer, so collapse to the row with the latest interpreted_at, preferring
    # any interpreted row over an uninterpreted one.
    best = {}
    for path, name, extension, interpreted_as, interpreted_at, version in rows:
        current = best.get(path)
        if current is None or (interpreted_at or 0) > (current.get('interpreted_at') or 0):
            best[path] = {
                'name': name or path.rsplit('/', 1)[-1],
                'extension': extension,
                'interpreted_as': interpreted_as,
                'interpreted_at': interpreted_at,
                'version': version,
            }

    # Group by interpreter: the one that ran, or the one that should have.
    by_interpreter = {}
    for path in paths:
        row = best.get(path)
        if row is None:
            continue
        ran = row['interpreted_as']
        expected = _expected_interpreter(row['extension'])
        for interpreter_id in {i for i in (ran, expected) if i}:
            entry = by_interpreter.setdefault(interpreter_id, {})
            ok = (interpreter_id == ran) and bool(row['interpreted_at'])
            entry[row['name']] = {
                'path': path,
                'status': 'ok' if ok else 'missing',
                'interpreted_at': row['interpreted_at'] if ok else None,
            }

    out = []
    for interpreter_id in sorted(by_interpreter):
        name, version = _interpreter_meta(interpreter_id)
        files = by_interpreter[interpreter_id]
        # The version actually recorded on a run beats the registry's current
        # one — it is what produced the output on screen.
        recorded = next((best[f['path']]['version'] for f in files.values()
                         if f['status'] == 'ok' and best.get(f['path'], {}).get('version')), None)
        out.append({
            'id': interpreter_id,
            'name': name,
            'version': recorded or version,
            'files': files,
        })

    unknown = [p for p in paths if p not in best]
    body = {'interpreters': out}
    if unknown:
        body['unknown_paths'] = unknown
    return jsonify(body), 200


@bp.post('/interpreters/run')
@require_role('admin')
def api_interpreters_run():
    """Run interpreters over an explicit list of paths, in the background.

    Body: ``{"paths": [...], "interpreter": "fcs_interpreter", "mode": "missing_only"|"all"}``

    ``mode`` maps onto the dispatcher's ``force``: ``missing_only`` leaves
    already-enriched files alone (its default), ``all`` re-runs them.

    Returns a task id in the same registry ``/api/tasks`` uses, so the page
    polls it exactly like a scan.
    """
    import hashlib
    import threading
    import time

    body = request.get_json(silent=True) or {}
    paths = [str(p).strip() for p in (body.get('paths') or []) if str(p).strip()]
    if not paths:
        return jsonify({'error': 'paths is required'}), 400
    if len(paths) > _MAX_STATUS_PATHS:
        return jsonify({'error': f'too many paths ({len(paths)}); the maximum is {_MAX_STATUS_PATHS}'}), 400

    mode = (body.get('mode') or 'missing_only').strip().lower()
    if mode not in ('missing_only', 'all'):
        return jsonify({'error': "mode must be 'missing_only' or 'all'"}), 400

    interpreter = (body.get('interpreter') or '').strip() or None
    if interpreter:
        from ...interpreters.registry import get_interpreter_by_id, list_interpreter_ids
        if get_interpreter_by_id(interpreter) is None:
            # An unknown id matches no row and would report a clean zero, which
            # reads exactly like "nothing left to interpret".
            return jsonify({
                'error': f'unknown interpreter: {interpreter}',
                'known_interpreters': list_interpreter_ids(),
            }), 400

    started = time.time()
    task_id = hashlib.sha1(f'interpret|{interpreter}|{len(paths)}|{started}'.encode()).hexdigest()[:12]
    task = {
        'id': task_id,
        'type': 'interpret',
        'status': 'running',
        'path': paths[0] if len(paths) == 1 else f'{len(paths)} files',
        'started': started,
        'ended': None,
        'total': len(paths),
        'processed': 0,
        'progress': 0.0,
        'error': None,
        'cancel_requested': False,
        'status_message': 'Running interpreters...',
    }
    _get_ext().setdefault('tasks', {})[task_id] = task
    app = current_app._get_current_object()

    def _worker():
        with app.app_context():
            try:
                from ...services.enrichment_service import run_enrichment
                result = run_enrichment(
                    interpreter_id=interpreter,
                    limit=len(paths),
                    paths=paths,
                    force=(mode == 'all'),
                )
                task['result'] = result
                task['processed'] = result.get('files_enriched', len(paths))
                task['progress'] = 1.0
                task['status'] = 'completed'
                if result.get('errors'):
                    task['error'] = '; '.join(result['errors'][:5])
            except Exception as e:
                task['status'] = 'error'
                task['error'] = f'{type(e).__name__}: {e}'
            finally:
                task['ended'] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({'status': 'accepted', 'task_id': task_id}), 202
