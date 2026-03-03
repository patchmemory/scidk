"""
Blueprint for Neo4j integration API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os
import time

from ..helpers import get_neo4j_params, build_commit_rows, commit_to_neo4j, get_or_build_scan_index
from ..helpers import commit_to_neo4j_batched
bp = Blueprint('neo4j', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

@bp.get('/scans/<scan_id>/commit_preview')
def api_scan_commit_preview(scan_id):
        """Dev-only: preview rows/folders the app would commit for this scan (index mode builder)."""
        scans = _get_ext().setdefault('scans', {})
        s = scans.get(scan_id)
        if not s:
            # Try to load minimal scan from SQLite to allow preview
            try:
                from ...core import path_index_sqlite as pix
                from ...core import migrations as _migs
                import json as _json
                conn = pix.connect()
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    cur.execute("SELECT id, root, started, completed, status, extra_json FROM scans WHERE id = ?", (scan_id,))
                    row = cur.fetchone()
                    if row:
                        sid, root, started, completed, status, extra = row
                        ex = {}
                        try:
                            if extra:
                                ex = _json.loads(extra)
                        except Exception:
                            ex = {}
                        s = {'id': sid, 'path': root, 'started': started, 'ended': completed}
                        scans[scan_id] = s
                    else:
                        return jsonify({"error": "scan not found"}), 404
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                return jsonify({"error": "scan not found"}), 404
        try:
            from ...core.commit_rows_from_index import build_rows_for_scan_from_index
            rows, folder_rows = build_rows_for_scan_from_index(scan_id, s, include_hierarchy=True)
            return jsonify({
                'scan_id': scan_id,
                'base': s.get('path'),
                'counts': {'files': len(rows), 'folders': len(folder_rows)},
                'sample_files': [{"path": r.get("path"), "folder": r.get("folder")} for r in (rows[:20] if rows else [])],
                'sample_folders': [{"path": r.get("path"), "parent": r.get("parent")} for r in (folder_rows[:20] if folder_rows else [])]
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@bp.post('/scans/<scan_id>/commit')
def api_scan_commit(scan_id):
        scans = _get_ext().setdefault('scans', {})
        s = scans.get(scan_id)
        if not s:
            return jsonify({"status": "error", "error": "scan not found"}), 404
        try:
            use_index = (os.environ.get('SCIDK_COMMIT_FROM_INDEX') or '').strip().lower() in ('1','true','yes','y','on')
            g = _get_ext()['graph']
            if use_index:
                # Build rows directly from SQLite index for this scan using shared builder
                from ...core.commit_rows_from_index import build_rows_for_scan_from_index
                rows, folder_rows = build_rows_for_scan_from_index(scan_id, s, include_hierarchy=True)
                # Debug: first 10 mappings from index
                try:
                    current_app.logger.debug({
                        "event": "index_mapping_debug",
                        "sample_files": [{"path": r.get("path"), "folder": r.get("folder")} for r in (rows[:10] if rows else [])],
                        "sample_folders": [{"path": r.get("path"), "parent": r.get("parent")} for r in (folder_rows[:10] if folder_rows else [])]
                    })
                except Exception:
                    pass
                # For compatibility with schema endpoint, still add a Scan node to in-memory graph
                try:
                    g.commit_scan(s)
                except Exception:
                    pass
                # Totals for reporting
                total = len([r for r in rows if r.get('path')])
                present = total  # index-driven commit considers all indexed files as present
                missing = 0
                s['committed'] = True
                import time as _t
                s['committed_at'] = _t.time()
            else:
                # Legacy in-memory path
                checksums = s.get('checksums') or []
                total = len(checksums)
                # How many of these files are present in the current graph
                present = sum(1 for ch in checksums if ch in getattr(g, 'datasets', {}))
                missing = total - present
                # Commit into graph (idempotent add of Scan + edges)
                g.commit_scan(s)
                ds_map = getattr(g, 'datasets', {})
                rows, folder_rows = build_commit_rows(s, ds_map)
            import time as _t
            s['committed'] = True
            s['committed_at'] = _t.time()

            # Attempt Neo4j write if configuration is present (do not rely solely on connected flag)
            neo_state = _get_ext().get('neo4j_state', {})
            neo_attempted = False
            neo_written = 0
            neo_error = None
            db_verified = None
            db_files = 0
            db_folders = 0
            uri, user, pwd, database, auth_mode = get_neo4j_params()
            if uri and ((auth_mode == 'none') or (user and pwd)):
                neo_attempted = True
                try:
                    # If committing from index, use the rows built above from SQLite; otherwise build from legacy datasets
                    if use_index:
                        def _prog(ev, payload):
                            try:
                                current_app.logger.info(f"neo4j {ev}: {payload}")
                            except Exception:
                                pass
                        if current_app.config.get('TESTING'):
                            result = commit_to_neo4j(rows, folder_rows, s, (uri, user, pwd, database, auth_mode))
                        else:
                            result = commit_to_neo4j_batched(
                                rows=rows,
                                folder_rows=folder_rows,
                                scan=s,
                                neo4j_params=(uri, user, pwd, database, auth_mode),
                                file_batch_size=int(os.environ.get('SCIDK_NEO4J_FILE_BATCH') or 5000),
                                folder_batch_size=int(os.environ.get('SCIDK_NEO4J_FOLDER_BATCH') or 5000),
                                max_retries=2,
                                on_progress=_prog,
                            )
                    else:
                        ds_map = getattr(g, 'datasets', {})
                        rows, folder_rows = build_commit_rows(s, ds_map)
                        result = commit_to_neo4j_batched(
                            rows=rows,
                            folder_rows=folder_rows,
                            scan=s,
                            neo4j_params=(uri, user, pwd, database, auth_mode),
                            file_batch_size=int(os.environ.get('SCIDK_NEO4J_FILE_BATCH') or 5000),
                            folder_batch_size=int(os.environ.get('SCIDK_NEO4J_FOLDER_BATCH') or 5000),
                            max_retries=2,
                            on_progress=_neo4j_progress_default,
                        )
                    neo_written = int(result.get('written_files', 0)) + int(result.get('written_folders', 0))
                    # Capture DB verification if provided
                    if 'db_verified' in result:
                        db_verified = bool(result.get('db_verified'))
                        db_files = int(result.get('db_files') or 0)
                        db_folders = int(result.get('db_folders') or 0)
                    if result.get('error'):
                        raise Exception(result['error'])
                    # Update state on success
                    neo_state['connected'] = True
                    neo_state['last_error'] = None
                except Exception as ne:
                    neo_error = str(ne)
                    neo_state['connected'] = False
                    neo_state['last_error'] = neo_error
                # Note: even on Neo4j error we still return 200 for in-memory commit but include error details

            # In our in-memory model, linked_edges_added ~= present (File→Scan per matched dataset)
            payload = {
                "status": "ok",
                "committed": True,
                "scan_id": scan_id,
                "files_in_scan": total,
                "matched_in_graph": present,
                "missing_from_graph": max(0, missing),
                "linked_edges_added": present,
                "neo4j_attempted": neo_attempted,
                "neo4j_written_files": neo_written,
                "commit_mode": ("index" if use_index else "legacy"),
                # DB verification results (if commit attempted)
                "neo4j_db_verified": db_verified,
                "neo4j_db_files": db_files,
                "neo4j_db_folders": db_folders,
            }
            # Diagnostics about commit path and row counts
            if use_index:
                try:
                    payload["neo4j_rows_files"] = len(rows)
                    payload["neo4j_rows_folders"] = len(folder_rows)
                except Exception:
                    pass
            if neo_error:
                payload["neo4j_error"] = neo_error
            # Add user-facing warnings
            if total == 0:
                payload["warning"] = "This scan has 0 files; nothing was linked."
            elif present == 0:
                payload["warning"] = "None of the scanned files are currently present in the graph; verify you scanned in this session or refresh."
            # Neo4j-specific warning when verification fails but no explicit error was raised
            if neo_attempted and (db_verified is not None) and (not db_verified) and (not neo_error):
                payload["neo4j_warning"] = (
                    "Neo4j post-commit verification found 0 SCANNED_IN edges for this scan. "
                    "Verify: URI, credentials or set NEO4J_AUTH=none for no-auth, and database name. "
                    "Also ensure the scan has files present in this session's graph."
                )
            try:
                from ...services.metrics import inc_counter
                # Consider files written as "rows" proxy for MVP
                inc_counter(current_app, 'rows_ingested_total', int(payload.get('neo4j_written_files') or 0))
            except Exception:
                pass
            return jsonify(payload), 200
        except Exception as e:
            return jsonify({"status": "error", "error": "commit failed", "error_detail": str(e)}), 500


@bp.get('/settings/neo4j')
def api_settings_neo4j_get():
    cfg = _get_ext().get('neo4j_config', {})
    state = _get_ext().get('neo4j_state', {})
    # Do not return password
    out = {
        'uri': cfg.get('uri') or '',
        'user': cfg.get('user') or '',
        'database': cfg.get('database') or '',
        'connected': bool(state.get('connected')),
        'last_error': state.get('last_error'),
    }
    return jsonify(out), 200

@bp.post('/settings/neo4j')
def api_settings_neo4j_set():
        data = request.get_json(force=True, silent=True) or {}
        cfg = _get_ext().setdefault('neo4j_config', {})

        # Accept free text fields for uri, user, database
        for k in ['uri','user','database']:
            v = data.get(k)
            if v is not None:
                v = v.strip()
                cfg[k] = v if v else None

        # Password handling: only update if non-empty provided, unless clear_password=true
        if data.get('clear_password') is True:
            cfg['password'] = None
        else:
            if 'password' in data:
                v = data.get('password')
                if isinstance(v, str) and v.strip():
                    cfg['password'] = v.strip()
                # else: ignore empty password to avoid wiping stored secret

        # Persist to database for survival across restarts
        try:
            from ...core.settings import set_setting
            # Store as JSON (excluding password for security - handle separately)
            persisted_config = {
                'uri': cfg.get('uri'),
                'user': cfg.get('user'),
                'database': cfg.get('database')
            }
            set_setting('neo4j_config', json.dumps(persisted_config))

            # Store password separately (could be encrypted in future)
            if cfg.get('password'):
                set_setting('neo4j_password', cfg['password'])
            elif data.get('clear_password'):
                set_setting('neo4j_password', '')
        except Exception as e:
            current_app.logger.warning(f"Failed to persist Neo4j settings: {e}")

        # Reset state error on change
        st = _get_ext().setdefault('neo4j_state', {})
        st['last_error'] = None
        return jsonify({'status':'ok'}), 200


@bp.post('/settings/neo4j/connect')
def api_settings_neo4j_connect():
        uri, user, pwd, database, auth_mode = get_neo4j_params()
        st = _get_ext().setdefault('neo4j_state', {})
        st['connected'] = False
        st['last_error'] = None
        if not uri:
            st['last_error'] = 'Missing uri'
            return jsonify({'connected': False, 'error': st['last_error']}), 400
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception as e:
            st['last_error'] = f'neo4j driver not installed: {e}'
            return jsonify({'connected': False, 'error': st['last_error']}), 501
        # Respect auth-failure backoff
        import time as _t
        now = _t.time()
        next_after = float(st.get('next_connect_after') or 0)
        if next_after and now < next_after:
            st['last_error'] = f"backoff active; retry after {int(next_after-now)}s"
            return jsonify({'connected': False, 'error': st['last_error']}), 429
        try:
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                with driver.session(database=database) as sess:
                    rec = sess.run('RETURN 1 AS ok').single()
                    ok = bool(rec and rec.get('ok') == 1)
            finally:
                try:
                    if driver is not None:
                        driver.close()
                except Exception:
                    pass
            st['connected'] = ok
            # On success, clear backoff
            if ok:
                st['next_connect_after'] = 0
                st['last_error'] = None
            return jsonify({'connected': ok}), 200 if ok else 502
        except Exception as e:
            msg = str(e)
            st['last_error'] = msg
            st['connected'] = False
            # Apply backoff on auth errors
            try:
                emsg = msg.lower()
                if ('unauthorized' in emsg) or ('authentication' in emsg):
                    prev = float(st.get('next_connect_after') or 0)
                    base = 20.0
                    delay = base
                    if prev and now < prev:
                        rem = prev - now
                        delay = min(max(base*2, rem*2), 120.0)
                    st['next_connect_after'] = now + delay
            except Exception:
                pass
            return jsonify({'connected': False, 'error': st['last_error']}), 502


@bp.post('/settings/neo4j/disconnect')
def api_settings_neo4j_disconnect():
        st = _get_ext().setdefault('neo4j_state', {})
        st['connected'] = False
        return jsonify({'connected': False}), 200


# ========== Neo4j Connection Profiles ==========

@bp.get('/settings/neo4j/profiles')
def api_neo4j_profiles_list():
    """List all saved Neo4j connection profiles."""
    try:
        from ...core.settings import get_settings_by_prefix
        profiles_data = get_settings_by_prefix('neo4j_profile_')

        profiles = []
        seen_names = set()

        for key, value in profiles_data.items():
            # Keys are like: neo4j_profile_Local_Dev, neo4j_profile_Production
            name = key.replace('neo4j_profile_', '').replace('_', ' ')
            if name in seen_names:
                continue
            seen_names.add(name)

            try:
                profile = json.loads(value)
                profiles.append({
                    'name': name,
                    'uri': profile.get('uri', ''),
                    'user': profile.get('user', ''),
                    'database': profile.get('database', ''),
                    'role': profile.get('role', 'primary'),
                    # Don't return password in list
                })
            except Exception:
                continue

        return jsonify({'status': 'ok', 'profiles': profiles}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.post('/settings/neo4j/profiles')
def api_neo4j_profile_save():
    """Save a Neo4j connection profile with role."""
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        role = data.get('role', 'primary').strip().lower()

        if not name:
            return jsonify({'status': 'error', 'error': 'Profile name is required'}), 400

        # Validate role
        valid_roles = ['primary', 'labels_source', 'readonly', 'ingestion_target']
        if role not in valid_roles:
            return jsonify({'status': 'error', 'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}), 400

        # Store profile data
        from ...core.settings import set_setting
        profile_data = {
            'uri': data.get('uri', ''),
            'user': data.get('user', ''),
            'database': data.get('database', ''),
            'role': role
        }

        # Use underscores in key to make it a valid setting key
        profile_key = f'neo4j_profile_{name.replace(" ", "_")}'
        set_setting(profile_key, json.dumps(profile_data))

        # Store password separately if provided
        if data.get('password'):
            password_key = f'neo4j_profile_password_{name.replace(" ", "_")}'
            set_setting(password_key, data['password'])

        # If this is a primary profile, immediately update app.extensions so it takes effect
        if role == 'primary':
            try:
                from ...core.settings import get_setting
                cfg = _get_ext().setdefault('neo4j_config', {})
                cfg['uri'] = profile_data.get('uri')
                cfg['user'] = profile_data.get('user')
                cfg['database'] = profile_data.get('database')
                if data.get('password'):
                    cfg['password'] = data['password']
                current_app.logger.info(f"Updated runtime Neo4j config from saved primary profile '{name}'")
            except Exception as e:
                current_app.logger.warning(f"Failed to update runtime config after saving primary profile: {e}")

        return jsonify({'status': 'ok', 'name': name, 'role': role}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.delete('/settings/neo4j/profiles/<name>')
def api_neo4j_profile_delete(name):
    """Delete a Neo4j connection profile."""
    try:
        from ...core.settings import set_setting

        # Delete profile data
        profile_key = f'neo4j_profile_{name.replace(" ", "_")}'
        set_setting(profile_key, '')

        # Delete password
        password_key = f'neo4j_profile_password_{name.replace(" ", "_")}'
        set_setting(password_key, '')

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.get('/settings/neo4j/profiles/<name>')
def api_neo4j_profile_get(name):
    """Get a specific Neo4j connection profile (including password for loading)."""
    try:
        from ...core.settings import get_setting

        profile_key = f'neo4j_profile_{name.replace(" ", "_")}'
        profile_json = get_setting(profile_key)

        if not profile_json:
            return jsonify({'status': 'error', 'error': 'Profile not found'}), 404

        profile = json.loads(profile_json)

        # Load password separately
        password_key = f'neo4j_profile_password_{name.replace(" ", "_")}'
        password = get_setting(password_key)
        if password:
            profile['password'] = password

        profile['name'] = name
        return jsonify({'status': 'ok', 'profile': profile}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.get('/settings/neo4j/profiles/by-role/<role>')
def api_neo4j_profile_by_role(role):
    """Get the active profile for a specific role."""
    try:
        from ...core.settings import get_setting

        # Get active profile name for this role
        active_key = f'neo4j_active_role_{role}'
        active_name = get_setting(active_key)

        if not active_name:
            return jsonify({'status': 'ok', 'profile': None, 'message': f'No active profile for role: {role}'}), 200

        # Load the profile
        profile_key = f'neo4j_profile_{active_name.replace(" ", "_")}'
        profile_json = get_setting(profile_key)

        if not profile_json:
            return jsonify({'status': 'error', 'error': 'Active profile not found'}), 404

        profile = json.loads(profile_json)

        # Load password
        password_key = f'neo4j_profile_password_{active_name.replace(" ", "_")}'
        password = get_setting(password_key)
        if password:
            profile['password'] = password

        profile['name'] = active_name
        return jsonify({'status': 'ok', 'profile': profile}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.put('/settings/neo4j/profiles/<name>/activate')
def api_neo4j_profile_activate(name):
    """Activate a profile for its assigned role."""
    try:
        from ...core.settings import get_setting, set_setting

        # Load profile to get its role
        profile_key = f'neo4j_profile_{name.replace(" ", "_")}'
        profile_json = get_setting(profile_key)

        if not profile_json:
            return jsonify({'status': 'error', 'error': 'Profile not found'}), 404

        profile = json.loads(profile_json)
        role = profile.get('role', 'primary')

        # Set this profile as active for its role
        active_key = f'neo4j_active_role_{role}'
        set_setting(active_key, name)

        # Apply to current connection config if it's the primary role
        if role == 'primary':
            # Load password
            password_key = f'neo4j_profile_password_{name.replace(" ", "_")}'
            password = get_setting(password_key)

            # Apply to active config
            cfg = _get_ext().setdefault('neo4j_config', {})
            cfg['uri'] = profile.get('uri')
            cfg['user'] = profile.get('user')
            cfg['database'] = profile.get('database')
            if password:
                cfg['password'] = password

        return jsonify({'status': 'ok', 'role': role, 'message': f'Profile {name} activated for role: {role}'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


