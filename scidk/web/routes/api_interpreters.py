"""
Blueprint for Interpreter configuration API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os

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


@bp.post('/settings/rclone-interpret')
def api_settings_rclone_interpret_set():
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

