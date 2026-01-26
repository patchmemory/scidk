"""
Blueprint for Background task management API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os

from ..helpers import get_neo4j_params as _get_neo4j_params, build_commit_rows, commit_to_neo4j, get_or_build_scan_index
from ...app import commit_to_neo4j_batched

bp = Blueprint('tasks', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']


@bp.post('/tasks')
def api_tasks_create():
    """Create a background task. Supports type=scan and type=commit."""
    data = request.get_json(force=True, silent=True) or {}
    ttype = (data.get('type') or 'scan').strip().lower()
    import time, hashlib, threading
    started = time.time()

    # Enforce max concurrent tasks (running)
    try:
        max_tasks = int(os.environ.get('SCIDK_MAX_BG_TASKS', '2'))
    except Exception:
        max_tasks = 2
    running = sum(1 for t in current_app.extensions['scidk'].get('tasks', {}).values() if t.get('status') == 'running')
    if running >= max_tasks:
        return jsonify({'error': 'too many tasks running', 'code': 'max_tasks', 'max': max_tasks}), 429

    if ttype == 'scan':
        provider_id = (data.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (data.get('root_id') or ('/' if provider_id != 'rclone' else 'remote:')).strip()
        path = data.get('path') or (root_id if provider_id != 'local_fs' else os.getcwd())
        recursive = bool(data.get('recursive', True))
        # Normalize rclone path to full remote target if needed
        if provider_id == 'rclone':
            try:
                from ...core.path_utils import parse_remote_path, join_remote_path
                info = parse_remote_path(path or '')
                if not bool(info.get('is_remote')):
                    path = join_remote_path(root_id, (path or '').lstrip('/'))
            except Exception:
                pass
        tid_src = f"scan|{provider_id}|{path}|{started}"
        task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]
        task = {
            'id': task_id,
            'type': 'scan',
            'status': 'running',
            'path': str(path),
            'recursive': bool(recursive),
            'started': started,
            'ended': None,
            'total': 0,
            'processed': 0,
            'progress': 0.0,
            'scan_id': None,
            'error': None,
            'cancel_requested': False,
            'selection': data.get('selection') or {},
        }
        current_app.extensions['scidk'].setdefault('tasks', {})[task_id] = task
        app = current_app._get_current_object()

        def _worker():
            with app.app_context():
                try:
                    import hashlib as _h
                    from ...core import path_index_sqlite as pix
                    scans = current_app.extensions['scidk'].setdefault('scans', {})
                    # Pre snapshot for in-memory dataset delta
                    before = set(ds.get('checksum') for ds in current_app.extensions['scidk']['graph'].list_datasets())
                    started_ts = time.time()
                    scan_id = _h.sha1(f"{path}|{started_ts}".encode()).hexdigest()[:12]
                    file_count = 0
                    folder_count = 0
                    ingested = 0
                    folders_meta = []

                    if provider_id in ('local_fs', 'mounted_fs'):
                        base = Path(path)
                        # Estimate total: Python traversal
                        files_list = [p for p in _get_ext()['fs']._iter_files_python(base, recursive=recursive)]
                        task['total'] = len(files_list)
                        # Build rows like api_scan, apply selection rules when provided
                        sel = (task.get('selection') or {})
                        rules = sel.get('rules') or []
                        use_ignore = bool(sel.get('use_ignore', True))
                        allow_override_ignores = bool(sel.get('allow_override_ignores', True))
                        from fnmatch import fnmatch as _fn
                        def _norm_rules(rules_list):
                            out = []
                            for i, r in enumerate(rules_list or []):
                                act = (r.get('action') or '').lower(); pth=(r.get('path') or '').rstrip('/');
                                if not act or not pth: continue
                                rec = bool(r.get('recursive', False)); nt=r.get('node_type'); depth=pth.count('/');
                                out.append({'action':act,'path':pth,'recursive':rec,'node_type':nt,'depth':depth,'order_index':i})
                            out.sort(key=lambda x:(x['depth'], x['order_index']), reverse=True)
                            return out
                        _rules = _norm_rules(rules)
                        def _decide(rel_path: str, ignored: bool):
                            if ignored and not allow_override_ignores: return (False, 'ignored_by_scidkignore')
                            for r in _rules:
                                rp = r['path']
                                if r['recursive']:
                                    if rel_path == rp or rel_path.startswith(rp + '/'):
                                        return ((r['action']=='include'), r['action']+'_by_rule')
                                else:
                                    if rel_path == rp:
                                        return ((r['action']=='include'), r['action']+'_by_rule')
                            if ignored: return (False, 'ignored_by_scidkignore')
                            return (True, 'inherited')
                        ignore_patterns = []
                        if use_ignore:
                            try:
                                ign = base / '.scidkignore'
                                if ign.exists():
                                    for line in ign.read_text(encoding='utf-8').splitlines():
                                        s = line.strip();
                                        if s and not s.startswith('#'): ignore_patterns.append(s)
                            except Exception:
                                ignore_patterns = []
                        items_files = []
                        items_dirs = set()
                        if recursive:
                            for p in base.rglob('*'):
                                if task.get('cancel_requested'):
                                    task['status'] = 'canceled'; task['ended'] = time.time(); return
                                try:
                                    if p.is_dir():
                                        items_dirs.add(p)
                                    else:
                                        # selection filter on files
                                        try:
                                            rel = p.resolve().relative_to(base.resolve()).as_posix()
                                        except Exception:
                                            rel = str(p)
                                        ignored = any(_fn(rel, pat) for pat in ignore_patterns)
                                        ok, _ = _decide(rel, ignored)
                                        if ok:
                                            items_files.append(p)
                                        parent = p.parent
                                        while parent and parent != parent.parent and str(parent).startswith(str(base)):
                                            items_dirs.add(parent)
                                            if parent == base:
                                                break
                                            parent = parent.parent
                                except Exception:
                                    continue
                            items_dirs.add(base)
                        else:
                            try:
                                for p in base.iterdir():
                                    if p.is_dir(): items_dirs.add(p)
                                    else:
                                        rel = p.name
                                        ignored = any(_fn(rel, pat) for pat in ignore_patterns)
                                        ok, _ = _decide(rel, ignored)
                                        if ok: items_files.append(p)
                            except Exception:
                                pass
                            items_dirs.add(base)
                        # Map to rows
                        def _row_from_local(pth: Path, typ: str) -> tuple:
                            full = str(pth.resolve())
                            parent = str(pth.parent.resolve()) if pth != pth.parent else ''
                            name = pth.name or full
                            depth = 0 if pth == base else max(0, len(str(pth.resolve()).rstrip('/').split('/')) - len(str(base.resolve()).rstrip('/').split('/')))
                            size = 0; mtime = None; ext = ''; mime = None
                            if typ == 'file':
                                try:
                                    st = pth.stat(); size = int(st.st_size); mtime = float(st.st_mtime)
                                except Exception:
                                    size = 0; mtime = None
                                ext = pth.suffix.lower()
                            remote = f"local:{os.uname().nodename}" if provider_id == 'local_fs' else f"mounted:{root_id}"
                            return (full, parent, name, depth, typ, size, mtime, ext, mime, None, None, remote, scan_id, None)
                        rows = []
                        for d in sorted(items_dirs, key=lambda x: str(x)):
                            rows.append(_row_from_local(d, 'folder'))
                        for fpath in items_files:
                            rows.append(_row_from_local(fpath, 'file'))
                        # dedupe
                        try:
                            seen = set(); uniq = []
                            for r in rows:
                                key = (r[0], r[4])
                                if key in seen: continue
                                seen.add(key); uniq.append(r)
                            rows = uniq
                        except Exception:
                            pass
                        ingested = pix.batch_insert_files(rows)
                        # In-memory datasets and progress
                        processed = 0
                        for fpath in items_files:
                            if task.get('cancel_requested'):
                                task['status'] = 'canceled'; task['ended'] = time.time(); return
                            try:
                                ds = _get_ext()['fs'].create_dataset_node(fpath)
                                current_app.extensions['scidk']['graph'].upsert_dataset(ds)
                            except Exception:
                                pass
                            processed += 1; task['processed'] = processed
                            if task['total']:
                                task['progress'] = processed / task['total']
                        file_count = len(items_files)
                        # Folders meta
                        for d in items_dirs:
                            try:
                                parent = str(d.parent.resolve()) if d != d.parent else ''
                                folders_meta.append({'path': str(d.resolve()), 'name': d.name, 'parent': parent, 'parent_name': Path(parent).name if parent else ''})
                            except Exception:
                                continue
                        folder_count = len(items_dirs)

                    elif provider_id == 'rclone':
                        provs = current_app.extensions['scidk'].get('providers')
                        prov = provs.get('rclone') if provs else None
                        if not prov:
                            raise RuntimeError('rclone provider not available')
                        # Prefer fast_list for recursive unless specified
                        fast_list = True if recursive else False
                        try:
                            items = prov.list_files(path, recursive=recursive, fast_list=fast_list)  # type: ignore[attr-defined]
                        except Exception as ee:
                            raise RuntimeError(str(ee))
                        # Selection for remote: apply only to files using full remote path
                        sel = (task.get('selection') or {})
                        rules = sel.get('rules') or []
                        def _norm_rules(rules_list):
                            out = []
                            for i, r in enumerate(rules_list or []):
                                act = (r.get('action') or '').lower(); pth=(r.get('path') or '').rstrip('/');
                                if not act or not pth: continue
                                rec = bool(r.get('recursive', False)); nt=r.get('node_type'); depth=pth.count('/');
                                out.append({'action':act,'path':pth,'recursive':rec,'node_type':nt,'depth':depth,'order_index':i})
                            out.sort(key=lambda x:(x['depth'], x['order_index']), reverse=True)
                            return out
                        _rules = _norm_rules(rules)
                        def _decide(full_remote: str):
                            for r in _rules:
                                rp = r['path']
                                if r['recursive']:
                                    if full_remote == rp or full_remote.startswith(rp + '/'):
                                        return (r['action']=='include')
                                else:
                                    if full_remote == rp:
                                        return (r['action']=='include')
                            return True
                        rows = []
                        seen_rows = set()
                        seen_folders = set()
                        def _add_folder(full_path: str, name: str, parent: str):
                            nonlocal folders_meta
                            if full_path in seen_folders: return
                            seen_folders.add(full_path)
                            try:
                                from ...core.path_utils import parse_remote_path
                                info_par = parse_remote_path(parent)
                                if info_par.get('is_remote'):
                                    parts = info_par.get('parts') or []
                                    parent_name = (info_par.get('remote_name') or '') if not parts else parts[-1]
                                else:
                                    parent_name = Path(parent).name if parent else ''
                            except Exception:
                                parent_name = ''
                            folders_meta.append({'path': full_path, 'name': name, 'parent': parent, 'parent_name': parent_name})
                        from ...core.path_utils import join_remote_path, parent_remote_path
                        for it in (items or []):
                            name = it.get('Name') or it.get('Path') or ''
                            if it.get('IsDir'):
                                if name:
                                    full = join_remote_path(path, name)
                                    parent = parent_remote_path(full)
                                    _add_folder(full, name, parent)
                                # rclone folder row
                                rrow = pix.map_rclone_item_to_row(it, path, scan_id)
                                key = (rrow[0], rrow[4])
                                if key not in seen_rows:
                                    seen_rows.add(key)
                                    rows.append(rrow)
                                continue
                            # rclone file row (apply selection)
                            full_remote = join_remote_path(path, name)
                            if _decide(full_remote):
                                rrow = pix.map_rclone_item_to_row(it, path, scan_id)
                                key = (rrow[0], rrow[4])
                                if key not in seen_rows:
                                    seen_rows.add(key)
                                    rows.append(rrow)
                                # In-memory dataset for file
                                try:
                                    size = int(it.get('Size') or 0)
                                    ds = _get_ext()['fs'].create_dataset_remote(full_remote, size_bytes=size, modified_ts=0.0, mime=None)
                                    current_app.extensions['scidk']['graph'].upsert_dataset(ds)
                                except Exception:
                                    pass
                                file_count += 1
                                task['processed'] = file_count
                            if recursive and name:
                                parts = [p for p in (name.split('/') if isinstance(name, str) else []) if p]
                                cur = ''
                                for i in range(len(parts)-1):
                                    cur = parts[i] if i == 0 else (cur + '/' + parts[i])
                                    full = join_remote_path(path, cur)
                                    parent = parent_remote_path(full)
                                    _add_folder(full, parts[i], parent)
                        folder_count = len(seen_folders)
                        ingested = pix.batch_insert_files(rows)
                    else:
                        raise RuntimeError(f"provider {provider_id} not supported for background scan")

                    # Build scan record
                    ended = time.time()
                    after = set(ds.get('checksum') for ds in current_app.extensions['scidk']['graph'].list_datasets())
                    new_checksums = sorted(list(after - before))
                    by_ext = {}
                    ext_map = {ds.get('checksum'): ds.get('extension') or '' for ds in current_app.extensions['scidk']['graph'].list_datasets()}
                    for ch in new_checksums:
                        ext = ext_map.get(ch, ''); by_ext[ext] = by_ext.get(ext, 0) + 1
                    # Host/provider tagging
                    host_type = provider_id
                    host_id = None
                    try:
                        if provider_id == 'rclone':
                            host_id = f"rclone:{(root_id or '').rstrip(':')}"
                        elif provider_id == 'local_fs':
                            import socket as _sock
                            host_id = f"local:{_sock.gethostname()}"
                        elif provider_id == 'mounted_fs':
                            host_id = f"mounted:{root_id}"
                    except Exception:
                        host_id = f"{provider_id}:{root_id}" if root_id else provider_id
                    scan = {
                        'id': scan_id,
                        'path': str(path),
                        'recursive': bool(recursive),
                        'started': started_ts,
                        'ended': ended,
                        'duration_sec': ended - started_ts,
                        'file_count': int(file_count),
                        'folder_count': int(folder_count),
                        'checksums': new_checksums,
                        'folders': folders_meta,
                        'by_ext': by_ext,
                        'source': getattr(_get_ext()['fs'], 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
                        'errors': [],
                        'committed': False,
                        'committed_at': None,
                        'provider_id': provider_id,
                        'host_type': host_type,
                        'host_id': host_id,
                        'root_id': root_id,
                        'root_label': Path(root_id).name if root_id else None,
                        'scan_source': f"provider:{provider_id}",
                        'ingested_rows': int(ingested),
                        'config_json': {
                            'interpreters': {
                                'effective_enabled': sorted(list(current_app.extensions['scidk'].get('interpreters', {}).get('effective_enabled', []))),
                                'source': current_app.extensions['scidk'].get('interpreters', {}).get('source', 'default'),
                            }
                        },
                    }
                    scans[scan_id] = scan
                    # Persist scan summary to SQLite (best-effort)
                    try:
                        from ...core import path_index_sqlite as pix
                        from ...core import migrations as _migs
                        import json as _json
                        conn = pix.connect()
                        try:
                            _migs.migrate(conn)
                            cur = conn.cursor()
                            cur.execute(
                                "INSERT OR REPLACE INTO scans(id, root, started, completed, status, extra_json) VALUES(?,?,?,?,?,?)",
                                (
                                    scan_id,
                                    str(path),
                                    float(started_ts or 0.0),
                                    float(ended or 0.0),
                                    'completed',
                                    _json.dumps({
                                        'recursive': bool(recursive),
                                        'duration_sec': ended - started_ts,
                                        'file_count': int(file_count),
                                        'by_ext': by_ext,
                                        'source': scan.get('source'),
                                        'checksums': new_checksums,
                                        'committed': False,
                                        'committed_at': None,
                                        'provider_id': provider_id,
                                        'root_id': root_id,
                                        'host_type': host_type,
                                        'host_id': host_id,
                                        'root_label': scan.get('root_label'),
                                        'selection': (task.get('selection') or {}),
                                    })
                                )
                            )
                            conn.commit()
                        finally:
                            try:
                                conn.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Also persist normalized selection rules for this scan (best-effort)
                    try:
                        from ...core import path_index_sqlite as pix
                        from ...core import migrations as _migs
                        conn = pix.connect()
                        try:
                            _migs.migrate(conn)
                            cur = conn.cursor()
                            cur.execute("DELETE FROM scan_selection_rules WHERE scan_id = ?", (scan_id,))
                            sel = task.get('selection') or {}
                            rules = sel.get('rules') or []
                            for i, r in enumerate(rules):
                                act = (r.get('action') or '').lower(); pth = (r.get('path') or '').strip(); rec = 1 if r.get('recursive') else 0; ntyp = r.get('node_type')
                                cur.execute("INSERT INTO scan_selection_rules(scan_id, action, path, recursive, node_type, order_index) VALUES(?,?,?,?,?,?)", (scan_id, act, pth, rec, ntyp, i))
                            conn.commit()
                        finally:
                            try: conn.close()
                            except Exception: pass
                    except Exception:
                        pass
                    # Telemetry and directories
                    current_app.extensions['scidk'].setdefault('telemetry', {})['last_scan'] = {
                        'path': str(path), 'recursive': bool(recursive), 'scanned': int(file_count),
                        'started': started_ts, 'ended': ended, 'duration_sec': ended - started_ts,
                        'source': scan['source'], 'provider_id': provider_id, 'root_id': root_id,
                    }
                    dirs = current_app.extensions['scidk'].setdefault('directories', {})
                    drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': [], 'source': scan['source'], 'provider_id': provider_id, 'root_id': root_id, 'root_label': scan.get('root_label')})
                    drec.update({'recursive': bool(recursive), 'scanned': int(file_count), 'last_scanned': ended, 'source': scan['source'], 'provider_id': provider_id, 'root_id': root_id, 'root_label': scan.get('root_label')})
                    drec.setdefault('scan_ids', []).append(scan_id)

                    # Complete task
                    task['ended'] = ended
                    task['status'] = 'completed'
                    task['scan_id'] = scan_id
                    task['progress'] = 1.0
                except Exception as e:
                    import time as _t
                    task['ended'] = _t.time()
                    task['status'] = 'error'
                    task['error'] = str(e)
        threading.Thread(target=_worker, daemon=True).start()
        return jsonify({'task_id': task_id, 'status': 'running'}), 202

    elif ttype == 'commit':
        scan_id = (data.get('scan_id') or '').strip()
        scans = current_app.extensions['scidk'].setdefault('scans', {})
        s = scans.get(scan_id)
        if not s:
            return jsonify({'error': 'scan not found'}), 404
        checksums = s.get('checksums') or []
        total = len(checksums)
        tid_src = f"commit|{scan_id}|{started}"
        task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]
        task = {
            'id': task_id,
            'type': 'commit',
            'status': 'running',
            'scan_id': scan_id,
            'path': s.get('path'),
            'started': started,
            'ended': None,
            # include one extra step for the Neo4j write phase so progress doesn't hit 100% before completion
            'total': total + 1,
            'processed': 0,
            'progress': 0.0,
            'neo4j_attempted': False,
            'neo4j_written': 0,
            'neo4j_error': None,
            'error': None,
            'cancel_requested': False,
        }
        current_app.extensions['scidk'].setdefault('tasks', {})[task_id] = task
        app = current_app._get_current_object()

        def _worker_commit():
            with app.app_context():
                try:
                    if task.get('cancel_requested'):
                        task['status'] = 'canceled'
                        task['ended'] = time.time()
                        return
                    g = current_app.extensions['scidk']['graph']
                    # In-memory commit first (idempotent)
                    g.commit_scan(s)
                    s['committed'] = True
                    s['committed_at'] = time.time()
                    # Persist commit status to SQLite (best-effort)
                    try:
                        from ...core import path_index_sqlite as pix
                        import json as _json
                        conn = pix.connect()
                        try:
                            cur = conn.cursor()
                            # fetch existing extra_json to merge
                            cur.execute("SELECT extra_json FROM scans WHERE id = ?", (s.get('id'),))
                            row = cur.fetchone()
                            extra_obj = {}
                            try:
                                if row and row[0]:
                                    extra_obj = _json.loads(row[0])
                            except Exception:
                                extra_obj = {}
                            extra_obj['committed'] = True
                            extra_obj['committed_at'] = s.get('committed_at')
                            cur.execute(
                                "UPDATE scans SET status = ?, extra_json = ? WHERE id = ?",
                                ('committed', _json.dumps(extra_obj), s.get('id'))
                            )
                            conn.commit()
                        finally:
                            try:
                                conn.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Build rows once using shared builder when index mode is enabled
                    use_index = (os.environ.get('SCIDK_COMMIT_FROM_INDEX') or '').strip().lower() in ('1','true','yes','y','on')
                    if use_index:
                        from ...core.commit_rows_from_index import build_rows_for_scan_from_index
                        rows, folder_rows = build_rows_for_scan_from_index(scan_id, s, include_hierarchy=True)
                    else:
                        ds_map = getattr(g, 'datasets', {})
                        rows, folder_rows = build_commit_rows(s, ds_map)
                    # Update progress for the file-processing phase
                    task['processed'] = total
                    if total:
                        task['progress'] = total / (task.get('total') or (total + 1))
                    # Allow cancel before Neo4j step
                    if task.get('cancel_requested'):
                        task['status'] = 'canceled'
                        task['ended'] = time.time()
                        return
                    # Neo4j write if configured via helper
                    uri, user, pwd, database, auth_mode = _get_neo4j_params()
                    def _on_prog(e, p):
                        try:
                            current_app.logger.info(f"neo4j {e}: {p}")
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
                            on_progress=_on_prog
                        )
                    if result['attempted']:
                        task['neo4j_attempted'] = True
                    if result['error']:
                        task['neo4j_error'] = result['error']
                    task['neo4j_written'] = int(result.get('written_files', 0)) + int(result.get('written_folders', 0))
                    # Include DB verification results if available
                    if 'db_verified' in result:
                        task['neo4j_db_verified'] = bool(result.get('db_verified'))
                        task['neo4j_db_files'] = int(result.get('db_files') or 0)
                        task['neo4j_db_folders'] = int(result.get('db_folders') or 0)
                        if task['neo4j_attempted'] and not task['neo4j_db_verified'] and not task.get('neo4j_error'):
                            task['neo4j_error'] = 'Post-commit verification found 0 SCANNED_IN edges for this scan. Check Neo4j credentials/database or permissions.'
                    # Done
                    # mark final step (Neo4j write) as processed so progress reaches 100% only at the end
                    task['processed'] = task.get('total') or task.get('processed')
                    task['ended'] = time.time()
                    task['status'] = 'completed'
                    task['progress'] = 1.0
                except Exception as e:
                    task['ended'] = time.time()
                    task['status'] = 'error'
                    task['error'] = str(e)
        threading.Thread(target=_worker_commit, daemon=True).start()
        return jsonify({'task_id': task_id, 'status': 'running'}), 202

    else:
        return jsonify({"error": "unsupported task type"}), 400

@bp.get('/tasks')
def api_tasks_list():
        # Prefer persisted tasks when state.backend=sqlite; merge with in-memory running tasks
        items = []
        if current_app.config.get('state.backend') == 'sqlite':
            try:
                from ...core import path_index_sqlite as pix
                from ...core import migrations as _migs
                import json as _json
                conn = pix.connect()
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    cur.execute("SELECT id, type, status, created, updated, payload FROM background_tasks ORDER BY coalesce(updated, created) DESC LIMIT 500")
                    for (tid, ttype, status, created, updated, payload) in cur.fetchall() or []:
                        try:
                            payload_obj = _json.loads(payload) if payload else {}
                        except Exception:
                            payload_obj = {}
                        items.append({
                            'id': tid,
                            'type': ttype,
                            'status': status,
                            'started': created,
                            'ended': updated if status in ('completed','error','canceled') else None,
                            'progress': payload_obj.get('progress'),
                            'processed': payload_obj.get('processed'),
                            'total': payload_obj.get('total'),
                            'error': payload_obj.get('error'),
                        })
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
        # Merge/augment with in-memory tasks (these represent current session/running tasks)
        try:
            mem_tasks = list(_get_ext().get('tasks', {}).values())
        except Exception:
            mem_tasks = []
        # Overwrite same-id entries with in-memory (more up-to-date)
        by_id = {t.get('id'): t for t in items if t.get('id')}
        for t in mem_tasks:
            if t.get('id'):
                by_id[t['id']] = t
            else:
                # anonymous tasks unlikely; append
                items.append(t)
        items = list(by_id.values()) if by_id else items
        # sort newest first
        items.sort(key=lambda t: t.get('ended') or t.get('started') or 0, reverse=True)
        return jsonify(items), 200


@bp.get('/tasks/<task_id>')
def api_tasks_detail(task_id):
        task = _get_ext().get('tasks', {}).get(task_id)
        if not task:
            return jsonify({"error": "not found"}), 404
        return jsonify(task), 200


@bp.post('/tasks/<task_id>/cancel')
def api_tasks_cancel(task_id):
        tasks = _get_ext().setdefault('tasks', {})
        task = tasks.get(task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        # only running tasks can be canceled
        if task.get('status') != 'running':
            return jsonify({'status': task.get('status'), 'message': 'task not running'}), 400
        task['cancel_requested'] = True
        return jsonify({'status': 'canceling'}), 202


