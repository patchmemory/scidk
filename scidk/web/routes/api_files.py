"""
Blueprint for File/scan/dataset API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import hashlib
import json
import os
import time as _time

from ..helpers import get_neo4j_params, build_commit_rows, commit_to_neo4j, get_or_build_scan_index
bp = Blueprint('files', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

@bp.post('/scan/dry-run')
def api_scan_dry_run():
        from fnmatch import fnmatch
        data = request.get_json(force=True, silent=True) or {}
        path = data.get('path') or os.getcwd()
        include = data.get('include') or []
        exclude = data.get('exclude') or []
        max_depth = data.get('max_depth')
        use_ignore = bool(data.get('use_ignore', True))
        base = Path(path)
        if not base.exists() or not base.is_dir():
            return jsonify({'status':'error','error':'invalid path'}), 400
        # Load .scidkignore patterns (gitignore-like globs, one per line) at root
        ignore_patterns = []
        if use_ignore:
            ign = base / '.scidkignore'
            try:
                if ign.exists():
                    for line in ign.read_text(encoding='utf-8').splitlines():
                        s = line.strip()
                        if not s or s.startswith('#'):
                            continue
                        ignore_patterns.append(s)
            except Exception:
                pass
        files = []
        total_bytes = 0
        base_parts = len(base.resolve().parts)
        try:
            for p in base.rglob('*'):
                try:
                    if p.is_file():
                        rel = p.resolve().relative_to(base.resolve()).as_posix()
                        # skip control file itself
                        if rel == '.scidkignore':
                            continue
                        # depth filter
                        if isinstance(max_depth, int):
                            depth = len(p.resolve().parts) - base_parts
                            if depth > max_depth:
                                continue
                        # ignore patterns
                        ignored = any(fnmatch(rel, pat) for pat in ignore_patterns)
                        if ignored:
                            continue
                        # include/exclude
                        if include:
                            if not any(fnmatch(rel, pat) for pat in include):
                                continue
                        if exclude and any(fnmatch(rel, pat) for pat in exclude):
                            continue
                        files.append(rel)
                        try:
                            total_bytes += int(p.stat().st_size)
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception:
            files = []
            total_bytes = 0
        files.sort()
        return jsonify({
            'status': 'ok',
            'root': str(base.resolve()),
            'total_files': len(files),
            'total_bytes': int(total_bytes),
            'files': files
        })


@bp.post('/scan')
def api_scan():
        data = request.get_json(force=True, silent=True) or {}
        try:
            from ...services.metrics import record_event_time
            record_event_time(current_app, 'scan_started_times')
        except Exception:
            pass
        provider_id = (data.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (data.get('root_id') or '/').strip() or '/'
        path = data.get('path') or (root_id if provider_id != 'local_fs' else os.getcwd())
        recursive = bool(data.get('recursive', True))
        fast_list = bool(data.get('fast_list', False))
        # Prefer fast_list by default for recursive rclone scans if client omitted it
        _client_specified_fast_list = ('fast_list' in data)
        # Delegate to ScansService (refactor): preserve payload and behavior
        try:
            from ...services.scans_service import ScansService
            svc = ScansService(app)
            result = svc.run_scan({
                'provider_id': provider_id,
                'root_id': root_id,
                'path': path,
                'recursive': recursive,
                'fast_list': fast_list,
                'selection': data.get('selection') or {},
            })
            if isinstance(result, dict) and result.get('status') == 'ok':
                # Persist selection, if provided
                try:
                    sel = data.get('selection') or {}
                    if sel and result.get('scan_id'):
                        from ...core import path_index_sqlite as pix
                        from ...core import migrations as _migs
                        import json as _json
                        conn = pix.connect()
                        try:
                            _migs.migrate(conn)
                            cur = conn.cursor()
                            # Update scans.extra_json snapshot
                            try:
                                cur.execute("SELECT extra_json FROM scans WHERE id = ?", (result['scan_id'],))
                                row = cur.fetchone()
                                extra_obj = {}
                                if row and row[0]:
                                    try: extra_obj = _json.loads(row[0])
                                    except Exception: extra_obj = {}
                                extra_obj['selection'] = sel
                                cur.execute("UPDATE scans SET extra_json = ? WHERE id = ?", (_json.dumps(extra_obj), result['scan_id']))
                            except Exception:
                                pass
                            # Replace normalized rules rows
                            try:
                                cur.execute("DELETE FROM scan_selection_rules WHERE scan_id = ?", (result['scan_id'],))
                            except Exception:
                                pass
                            rules = sel.get('rules') or []
                            for i, r in enumerate(rules):
                                act = (r.get('action') or '').lower()
                                pth = (r.get('path') or '').strip()
                                rec = 1 if r.get('recursive') else 0
                                ntyp = r.get('node_type')
                                cur.execute(
                                    "INSERT INTO scan_selection_rules(scan_id, action, path, recursive, node_type, order_index) VALUES(?,?,?,?,?,?)",
                                    (result['scan_id'], act, pth, rec, ntyp, i)
                                )
                            conn.commit()
                        finally:
                            try: conn.close()
                            except Exception: pass
                except Exception:
                    pass
                return jsonify(result), 200
            # Error path with optional http_status
            if isinstance(result, dict) and result.get('status') == 'error':
                code = int(result.get('http_status', 400))
                payload = {'status': 'error', 'error': result.get('error')}
                return jsonify(payload), code
        except Exception:
            # On service failure, fallback to legacy in-place implementation below
            pass
        try:
            import time, hashlib, json
            from ...core import path_index_sqlite as pix
            # Pre-scan snapshot of checksums
            before = set(ds.get('checksum') for ds in _get_ext()['graph'].list_datasets())
            started = time.time()
            # Precompute scan id early for SQLite tagging
            sid_src = f"{path}|{started}"
            scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
            count = 0
            ingested = 0
            folders = []
            files_skipped = 0
            files_hashed = 0
            if provider_id in ('local_fs', 'mounted_fs'):
                # Local/Mounted: enumerate filesystem and ingest into SQLite index
                base = Path(path)
                # Build list of files and folders
                items_files = []
                items_dirs = set()
                # Preserve source detection semantics (ncdu > gdu > python)
                try:
                    probe_ncdu = _get_ext()['fs']._list_files_with_ncdu(base, recursive=recursive)  # type: ignore
                    if probe_ncdu:
                        _get_ext()['fs'].last_scan_source = 'ncdu'
                    else:
                        probe_gdu = _get_ext()['fs']._list_files_with_gdu(base, recursive=recursive)  # type: ignore
                        if probe_gdu:
                            _get_ext()['fs'].last_scan_source = 'gdu'
                        else:
                            _get_ext()['fs'].last_scan_source = 'python'
                except Exception:
                    _get_ext()['fs'].last_scan_source = 'python'
                try:
                    if recursive:
                        for p in base.rglob('*'):
                            try:
                                if p.is_dir():
                                    items_dirs.add(p)
                                else:
                                    items_files.append(p)
                                    # ensure parent chain exists in dirs set
                                    parent = p.parent
                                    while parent and parent != parent.parent and str(parent).startswith(str(base)):
                                        items_dirs.add(parent)
                                        if parent == base:
                                            break
                                        parent = parent.parent
                            except Exception:
                                continue
                        # include base itself as a folder
                        items_dirs.add(base)
                    else:
                        for p in base.iterdir():
                            try:
                                if p.is_dir():
                                    items_dirs.add(p)
                                else:
                                    items_files.append(p)
                            except Exception:
                                continue
                        items_dirs.add(base)
                except Exception:
                    items_files = []
                    items_dirs = set()
                # Map to rows
                from ...core import path_index_sqlite as pix
                rows = []
                files_skipped = 0
                files_hashed = 0
                hash_policy = (os.environ.get('SCIDK_HASH_POLICY') or 'auto').strip().lower()
                def _row_from_local(pth: Path, typ: str) -> tuple:
                    nonlocal files_skipped, files_hashed
                    full = str(pth.resolve())
                    parent = str(pth.parent.resolve()) if pth != pth.parent else ''
                    name = pth.name or full
                    depth = 0 if pth == base else max(0, len(str(pth.resolve()).rstrip('/').split('/')) - len(str(base.resolve()).rstrip('/').split('/')))
                    size = 0
                    mtime = None
                    ext = ''
                    mime = None
                    etag = None
                    ahash = None
                    if typ == 'file':
                        try:
                            st = pth.stat()
                            size = int(st.st_size)
                            mtime = float(st.st_mtime)
                        except Exception:
                            size = 0
                            mtime = None
                        ext = pth.suffix.lower()
                        # Skip logic: reuse previous hash if unchanged (size + mtime)
                        try:
                            prev = pix.get_latest_file_meta(full)
                        except Exception:
                            prev = None
                        if prev is not None and prev[0] == size and prev[1] == mtime and (prev[2] or '') != '':
                            ahash = prev[2]
                            files_skipped += 1
                        else:
                            # Compute content hash with policy
                            try:
                                ahash = pix.compute_content_hash(full, hash_policy)
                            except Exception:
                                ahash = None
                            files_hashed += 1
                    remote = f"local:{os.uname().nodename}" if provider_id == 'local_fs' else f"mounted:{root_id}"
                    return (full, parent, name, depth, typ, size, mtime, ext, mime, etag, ahash, remote, scan_id, None)
                # Insert folder rows first for structure consistency
                for d in sorted(items_dirs, key=lambda x: str(x)):
                    rows.append(_row_from_local(d, 'folder'))
                # Then files
                for fpath in items_files:
                    rows.append(_row_from_local(fpath, 'file'))
                ingested = pix.batch_insert_files(rows)
                # Also create in-memory datasets (keep legacy behavior)
                count = 0
                for fpath in items_files:
                    try:
                        ds = _get_ext()['fs'].create_dataset_node(fpath)
                        _get_ext()['graph'].upsert_dataset(ds)
                        interps = _get_ext()['registry'].select_for_dataset(ds)
                        for interp in interps:
                            try:
                                result = interp.interpret(fpath)
                                payload = {
                                    'status': result.get('status', 'success'),
                                    'data': result.get('data', result),
                                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                                }
                                _get_ext()['graph'].add_interpretation(ds['checksum'], interp.id, payload)
                                # Persist interpretation metadata into SQLite files table for this path
                                try:
                                    from ...core import path_index_sqlite as pix
                                    conn_i = pix.connect(); pix.init_db(conn_i)
                                    try:
                                        cur_i = conn_i.cursor()
                                        import json as _json
                                        # Determine the canonical key used in the index for this file path
                                        key_path = None
                                        try:
                                            # For rclone/remote scans, the index stores canonical remote paths like "remote:rel/path"
                                            # Prefer dataset-provided original path if present
                                            key_path = ds.get('path') or None
                                        except Exception:
                                            key_path = None
                                        if not key_path:
                                            # Fallback to absolute local path for local filesystem scans
                                            key_path = str(fpath.resolve())
                                        cur_i.execute(
                                            "UPDATE files SET interpreted_as = ?, interpretation_json = ? WHERE path = ? AND type = 'file' AND scan_id = ?",
                                            (interp.id, _json.dumps(payload.get('data')), key_path, scan_id)
                                        )
                                        conn_i.commit()
                                    finally:
                                        conn_i.close()
                                except Exception:
                                    pass
                            except Exception as e:
                                err_payload = {
                                    'status': 'error',
                                    'data': {'error': str(e)},
                                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                                }
                                _get_ext()['graph'].add_interpretation(ds['checksum'], interp.id, err_payload)
                                try:
                                    from ...core import path_index_sqlite as pix
                                    conn_i = pix.connect(); pix.init_db(conn_i)
                                    try:
                                        cur_i = conn_i.cursor()
                                        import json as _json
                                        # Determine canonical key as above
                                        key_path = None
                                        try:
                                            key_path = ds.get('path') or None
                                        except Exception:
                                            key_path = None
                                        if not key_path:
                                            key_path = str(fpath.resolve())
                                        cur_i.execute(
                                            "UPDATE files SET interpreted_as = ?, interpretation_json = ? WHERE path = ? AND type = 'file' AND scan_id = ?",
                                            (interp.id, _json.dumps(err_payload.get('data')), key_path, scan_id)
                                        )
                                        conn_i.commit()
                                    finally:
                                        conn_i.close()
                                except Exception:
                                    pass
                        count += 1
                    except Exception:
                        continue
                # Collect folders metadata for scan record
                folders = []
                for d in items_dirs:
                    try:
                        parent = str(d.parent.resolve()) if d != d.parent else ''
                        folders.append({'path': str(d.resolve()), 'name': d.name, 'parent': parent, 'parent_name': Path(parent).name if parent else ''})
                    except Exception:
                        continue
            elif provider_id == 'rclone':
                # Use rclone lsjson to enumerate remote files; ingest into SQLite and create lightweight datasets.
                provs = _get_ext().get('providers')
                prov = provs.get('rclone') if provs else None
                if not prov:
                    raise RuntimeError('rclone provider not available')
                # Normalize relative Rclone paths to full remote targets using root_id
                try:
                    from ...core.path_utils import parse_remote_path, join_remote_path
                    info = parse_remote_path(path or '')
                    is_remote = bool(info.get('is_remote'))
                except Exception:
                    is_remote = False
                if not is_remote:
                    # path is relative or empty; compose with root_id
                    from ...core.path_utils import join_remote_path as _join
                    path = _join(root_id, (path or '').lstrip('/'))
                # If recursive rclone and client did not specify fast_list, enable it for robustness
                if provider_id == 'rclone' and recursive and not _client_specified_fast_list:
                    fast_list = True

                # ALWAYS RECORD THE SCAN BASE FOLDER for rclone scans
                # Ensures the target path appears as a folder node, preventing flattened view
                try:
                    from ...core.path_utils import parse_remote_path, parent_remote_path
                    from ...core import path_index_sqlite as pix

                    info_t = parse_remote_path(path)
                    base_name = (info_t.get('parts')[-1] if info_t.get('parts') else info_t.get('remote_name') or path)
                    base_parent = parent_remote_path(path)

                    # Create synthetic base folder SQLite row and initialize rows with it
                    base_item = {"Name": base_name, "Path": "", "IsDir": True, "Size": 0}
                    rows = [pix.map_rclone_item_to_row(base_item, path, scan_id)]

                    # Compute parent display name for folders list
                    try:
                        info_par = parse_remote_path(base_parent) if base_parent else {}
                        if info_par.get('is_remote'):
                            parts = info_par.get('parts') or []
                            parent_name = (info_par.get('remote_name') or '') if not parts else parts[-1]
                        else:
                            from pathlib import Path as _P
                            parent_name = _P(base_parent).name if base_parent else ''
                    except Exception:
                        parent_name = ''

                    folders.append({
                        'path': path,
                        'name': base_name,
                        'parent': base_parent,
                        'parent_name': parent_name,
                    })
                except Exception:
                    # Non-fatal; initialize to empty rows if base insertion fails
                    rows = []

                try:
                    # In testing mode, allow metadata-only scans for rclone to avoid external binary dependency
                    if current_app.config.get('TESTING') and not recursive:
                        items = []
                    else:
                        items = prov.list_files(path, recursive=recursive, fast_list=fast_list)  # type: ignore[attr-defined]
                except Exception as ee:
                    return jsonify({"status": "error", "error": str(ee)}), 400
                # Map to SQLite rows (files and folders); only files will have size > 0 typically.
                # rows is initialized above with the base folder row; continue accumulating
                # Collect folders set for both non-recursive and recursive scans
                seen_folders = set()
                def _add_folder(full_path: str, name: str, parent: str):
                    if full_path in seen_folders:
                        return
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
                    folders.append({'path': full_path, 'name': name, 'parent': parent, 'parent_name': parent_name})
                for it in (items or []):
                    try:
                        # Track folders for both modes
                        if it.get('IsDir'):
                            rel = it.get('Path') or it.get('Name') or ''
                            if rel:
                                from ...core.path_utils import join_remote_path, parent_remote_path
                                full = join_remote_path(path, rel)
                                parent = parent_remote_path(full)
                                leaf = rel.rsplit('/',1)[-1] if isinstance(rel, str) and '/' in rel else rel
                                # record folder regardless of recursive flag so empty dirs are preserved
                                _add_folder(full, leaf, parent)
                            # Still insert folder rows into SQLite for depth/structure awareness
                            rows.append(pix.map_rclone_item_to_row(it, path, scan_id))
                            continue
                        # File entry
                        rows.append(pix.map_rclone_item_to_row(it, path, scan_id))
                                # Synthesize intermediate folders from file rel paths (even if not recursive)
                        rel = it.get('Path') or it.get('Name') or ''
                        if rel:
                            from ...core.path_utils import join_remote_path, parent_remote_path
                            parts = [p for p in (rel.split('/') if isinstance(rel, str) else []) if p]
                            cur_rel = ''
                            for i in range(len(parts)-1):  # exclude the file itself
                                cur_rel = parts[i] if i == 0 else (cur_rel + '/' + parts[i])
                                full = join_remote_path(path, cur_rel)
                                parent = parent_remote_path(full)
                                _add_folder(full, parts[i], parent)
                                # ensure a folder row exists in SQLite, even if rclone didn't emit it
                                try:
                                    folder_item = {"Name": parts[i], "Path": cur_rel, "IsDir": True, "Size": 0}
                                    rows.append(pix.map_rclone_item_to_row(folder_item, path, scan_id))
                                except Exception:
                                    pass
                        # Create datasets only when backend is not neo4j (to reduce RAM)
                        backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()
                        if backend != 'neo4j':
                            size = int(it.get('Size') or 0)
                            from ...core.path_utils import join_remote_path
                            full = join_remote_path(path, rel)
                            ds = _get_ext()['fs'].create_dataset_remote(full, size_bytes=size, modified_ts=0.0, mime=None)
                            _get_ext()['graph'].upsert_dataset(ds)
                            count += 1
                    except Exception:
                        continue
                # Batch insert into SQLite (10k/txn) always (remove feature flag gating for rclone)
                try:
                    # Deduplicate rows by (path,type) before insert
                    try:
                        seen = set(); uniq = []
                        for r in rows:
                            key = (r[0], r[4])  # path, type
                            if key in seen:
                                continue
                            seen.add(key); uniq.append(r)
                        rows = uniq
                    except Exception:
                        pass
                    ingested = pix.batch_insert_files(rows, batch_size=10000)
                    # Minimal change detection to populate file_history
                    try:
                        _chg = pix.apply_basic_change_history(scan_id, path)
                        _get_ext().setdefault('telemetry', {})['last_change_counts'] = _chg
                    except Exception as __e:
                        _get_ext().setdefault('telemetry', {})['last_change_error'] = str(__e)
                except Exception as _e:
                    # Surface as non-fatal for now; continue app flow but record error
                    _get_ext().setdefault('telemetry', {})['last_sqlite_error'] = str(_e)
            else:
                return jsonify({"status": "error", "error": f"provider {provider_id} not supported for scan"}), 400
            ended = time.time()
            duration = ended - started
            after = set(ds.get('checksum') for ds in _get_ext()['graph'].list_datasets())
            new_checksums = sorted(list(after - before))
            # Build by_ext
            by_ext = {}
            backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()
            if backend == 'neo4j':
                # derive from SQLite for the current scan
                try:
                    from ...core import path_index_sqlite as pix
                    conn = pix.connect(); pix.init_db(conn)
                    cur = conn.cursor()
                    cur.execute("SELECT file_extension FROM files WHERE scan_id = ? AND type='file'", (scan_id,))
                    for (ext,) in cur.fetchall():
                        ext = ext or ''
                        by_ext[ext] = by_ext.get(ext, 0) + 1
                    conn.close()
                except Exception:
                    by_ext = {}
            else:
                ext_map = {}
                for ds in _get_ext()['graph'].list_datasets():
                    ext_map[ds.get('checksum')] = ds.get('extension') or ''
                for ch in new_checksums:
                    ext = ext_map.get(ch, '')
                    by_ext[ext] = by_ext.get(ext, 0) + 1
            # For non-recursive local scans, include immediate subfolders for later commit/merge
            if provider_id in ('local_fs', 'mounted_fs'):
                try:
                    if not recursive:
                        base = Path(path)
                        for child in base.iterdir():
                            if child.is_dir():
                                parent = str(child.parent)
                                folders.append({
                                    'path': str(child.resolve()),
                                    'name': child.name,
                                    'parent': parent,
                                    'parent_name': Path(parent).name if parent else '',
                                })
                except Exception:
                    pass
            # Provider metadata for scan/session records
            provs = _get_ext().get('providers')
            prov = provs.get(provider_id) if provs else None
            root_label = None
            try:
                if prov:
                    root_label = Path(root_id).name or str(root_id)
            except Exception:
                root_label = None
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
                'started': started,
                'ended': ended,
                'duration_sec': duration,
                'file_count': int(count),
                'folder_count': len(folders),
                'checksums': new_checksums,
                'folders': folders,
                'by_ext': by_ext,
                'source': getattr(_get_ext()['fs'], 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
                'errors': [],
                'committed': False,
                'committed_at': None,
                'provider_id': provider_id,
                'host_type': host_type,
                'host_id': host_id,
                'root_id': root_id,
                'root_label': root_label,
                'scan_source': f"provider:{provider_id}",
                'ingested_rows': int(ingested),
                'config_json': {
                    'interpreters': {
                        'effective_enabled': sorted(list(_get_ext().get('interpreters', {}).get('effective_enabled', []))),
                        'source': _get_ext().get('interpreters', {}).get('source', 'default'),
                    }
                },
            }
            scans = _get_ext().setdefault('scans', {})
            scans[scan_id] = scan
            # Persist scan summary to SQLite (best-effort)
            try:
                from ...core import path_index_sqlite as pix
                from ...core import migrations as _migs
                conn = pix.connect()
                import json as _json
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT OR REPLACE INTO scans(id, root, started, completed, status, extra_json) VALUES(?,?,?,?,?,?)",
                        (
                            scan_id,
                            str(path),
                            float(started or 0.0),
                            float(ended or 0.0),
                            'completed',
                            _json.dumps({
                                'recursive': bool(recursive),
                                'duration_sec': duration,
                                'file_count': int(count),
                                'by_ext': by_ext,
                                'source': scan.get('source'),
                                'checksums': new_checksums,
                                'committed': False,
                                'committed_at': None,
                                'provider_id': provider_id,
                                'root_id': root_id,
                                'host_type': host_type,
                                'host_id': host_id,
                                'root_label': root_label,
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
            # Clear cached fs index for this scan so next request rebuilds with fresh data
            try:
                _get_ext().setdefault('scan_fs', {}).pop(scan_id, None)
            except Exception:
                pass
            # Save telemetry on app
            telem = _get_ext().setdefault('telemetry', {})
            telem['last_scan'] = {
                'path': str(path),
                'recursive': bool(recursive),
                'scanned': int(count),
                'started': started,
                'ended': ended,
                'duration_sec': duration,
                'source': getattr(_get_ext()['fs'], 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
                'provider_id': provider_id,
                'root_id': root_id,
                'files_skipped': int(files_skipped),
                'files_hashed': int(files_hashed),
            }
            # Persist telemetry.last_scan to SQLite (best-effort)
            try:
                from ...core import path_index_sqlite as pix
                from ...core import migrations as _migs
                import json as _json
                conn = pix.connect()
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                        ("telemetry.last_scan", _json.dumps(telem.get('last_scan') or {}))
                    )
                    conn.commit()
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
            # Track scanned directories (in-session registry)
            dirs = _get_ext().setdefault('directories', {})
            drec = dirs.setdefault(str(path), {
                'path': str(path),
                'recursive': bool(recursive),
                'scanned': 0,
                'last_scanned': 0,
                'scan_ids': [],
                'source': getattr(_get_ext()['fs'], 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
                'provider_id': provider_id,
                'root_id': root_id,
                'root_label': root_label,
            })
            drec.update({
                'recursive': bool(recursive),
                'scanned': int(count),
                'last_scanned': ended,
                'source': getattr(_get_ext()['fs'], 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
                'provider_id': provider_id,
                'root_id': root_id,
                'root_label': root_label,
            })
            drec.setdefault('scan_ids', []).append(scan_id)
            return jsonify({"status": "ok", "scan_id": scan_id, "scanned": count, "folder_count": len(folders), "ingested_rows": int(ingested), "duration_sec": duration, "path": str(path), "recursive": bool(recursive), "provider_id": provider_id}), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 400


@bp.get('/datasets')
def api_datasets():
        items = _get_ext()['graph'].list_datasets()
        return jsonify(items)


@bp.get('/datasets/<dataset_id>')
def api_dataset(dataset_id):
        item = _get_ext()['graph'].get_dataset(dataset_id)
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)


@bp.post('/interpret')
def api_interpret():
        data = request.get_json(force=True, silent=True) or {}
        dataset_id = data.get('dataset_id')
        interpreter_id = data.get('interpreter_id')
        if not dataset_id:
            return jsonify({"status": "error", "error": "dataset_id required"}), 400
        ds = _get_ext()['graph'].get_dataset(dataset_id)
        if not ds:
            return jsonify({"status": "error", "error": "dataset not found"}), 404
        file_path = Path(ds['path'])
        if interpreter_id:
            interp = _get_ext()['registry'].get_by_id(interpreter_id)
            if not interp:
                return jsonify({"status": "error", "error": "interpreter not found"}), 404
            interps = [interp]
        else:
            interps = _get_ext()['registry'].select_for_dataset(ds)
            if not interps:
                return jsonify({"status": "error", "error": "no interpreters available"}), 400
        results = []
        for interp in interps:
            try:
                _t0 = time.time()
                result = interp.interpret(file_path)
                _t1 = time.time()
                _get_ext()['graph'].add_interpretation(ds['checksum'], interp.id, {
                    'status': result.get('status', 'success'),
                    'data': result.get('data', result),
                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                })
                # Record success
                try:
                    _get_ext()['registry'].record_usage(interp.id, success=True, execution_time_ms=int((_t1 - _t0)*1000))
                except Exception:
                    pass
                results.append({'interpreter_id': interp.id, 'status': 'ok'})
            except Exception as e:
                try:
                    _get_ext()['registry'].record_usage(interp.id, success=False, execution_time_ms=0)
                except Exception:
                    pass
                _get_ext()['graph'].add_interpretation(ds['checksum'], interp.id, {
                    'status': 'error',
                    'data': {'error': str(e)},
                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                })
                results.append({'interpreter_id': interp.id, 'status': 'error', 'error': str(e)})
        return jsonify({"status": "ok", "results": results}), 200


@bp.get('/browse')
def api_browse():
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        path_q = (request.args.get('path') or '').strip()
        _t0 = _time.time()
        try:
            provs = _get_ext()['providers']
            prov = provs.get(prov_id)
            if not prov:
                return jsonify({'error': 'provider not available', 'code': 'provider_not_available'}), 400
            # If path empty, default to root_id
            # Parse rclone browse options
            opts = {}
            if prov_id == 'rclone':
                rec_s = (request.args.get('recursive') or '').strip().lower()
                fast_s = (request.args.get('fast_list') or '').strip().lower()
                depth_s = (request.args.get('max_depth') or '').strip()
                opts['recursive'] = (rec_s in ('1','true','yes','on'))
                opts['fast_list'] = (fast_s in ('1','true','yes','on'))
                try:
                    opts['max_depth'] = int(depth_s) if depth_s else 1
                except Exception:
                    opts['max_depth'] = 1
            listing = prov.list(root_id=root_id, path=path_q or root_id, **opts)
            # Bubble provider-level errors clearly
            if isinstance(listing, dict) and listing.get('error'):
                return jsonify({'error': listing.get('error'), 'code': 'browse_failed'}), 400
            # Augment with provider badge and convenience fields
            for e in listing.get('entries', []):
                e['provider_id'] = prov_id
            try:
                from ...services.metrics import record_latency
                record_latency(current_app, 'browse', _time.time() - _t0)
            except Exception:
                pass
            return jsonify(listing), 200
        except Exception as e:
            try:
                from ...services.metrics import record_latency
                record_latency(current_app, 'browse', _time.time() - _t0)
            except Exception:
                pass
            return jsonify({'error': str(e), 'code': 'browse_exception'}), 500


@bp.get('/directories')
def api_directories():
        # Prefer SQLite-backed aggregation by root when state.backend=sqlite; fallback to in-memory registry
        use_sqlite = (current_app.config.get('state.backend') == 'sqlite')
        if use_sqlite:
            try:
                from ...core import path_index_sqlite as pix
                from ...core import migrations as _migs
                import json as _json
                conn = pix.connect()
                try:
                    _migs.migrate(conn)
                    cur = conn.cursor()
                    cur.execute("SELECT id, root, completed, extra_json FROM scans WHERE root IS NOT NULL AND root <> '' ORDER BY coalesce(completed, 0) DESC LIMIT 2000")
                    rows = cur.fetchall()
                    agg = {}
                    for (sid, root, completed, extra) in rows:
                        if not root:
                            continue
                        rec = agg.get(root) or {'path': root, 'scanned': 0, 'last_scanned': 0, 'scan_ids': [], 'recursive': None}
                        rec['scan_ids'].append(sid)
                        try:
                            if completed and float(completed) > float(rec.get('last_scanned') or 0):
                                rec['last_scanned'] = float(completed)
                        except Exception:
                            pass
                        try:
                            ex = _json.loads(extra) if extra else {}
                            # Best-effort fields
                            if ex:
                                if rec.get('recursive') is None:
                                    rec['recursive'] = bool(ex.get('recursive', False))
                                if 'file_count' in ex:
                                    rec['scanned'] = int(ex.get('file_count') or rec.get('scanned') or 0)
                                if 'source' in ex and not rec.get('source'):
                                    rec['source'] = ex.get('source')
                                if 'provider_id' in ex and not rec.get('provider_id'):
                                    rec['provider_id'] = ex.get('provider_id')
                                if 'root_id' in ex and not rec.get('root_id'):
                                    rec['root_id'] = ex.get('root_id')
                                if 'root_label' in ex and not rec.get('root_label'):
                                    rec['root_label'] = ex.get('root_label')
                        except Exception:
                            pass
                        agg[root] = rec
                    values = list(agg.values())
                    values.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
                    # Fill defaults
                    for v in values:
                        if v.get('recursive') is None:
                            v['recursive'] = False
                    return jsonify(values), 200
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                # fall through to in-memory
                pass
        # Fallback (in-memory)
        dirs = _get_ext().get('directories', {})
        values = list(dirs.values())
        values.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        return jsonify(values), 200

@bp.get('/fs/list')
def api_fs_list():
    """List immediate children within a scanned base directory.
    Query params:
      - base (required): must equal a previously scanned directory path
      - path (optional): if provided, must resolve under base; otherwise list base
    Returns JSON with breadcrumb and items. Prevents path traversal outside base.
    """
    base = (request.args.get('base') or '').strip()
    rel_path = (request.args.get('path') or '').strip()
    if not base:
        return jsonify({"error": "missing base"}), 400
    dirs = _get_ext().get('directories', {})
    if base not in dirs:
        return jsonify({"error": "unknown base (run a scan first)"}), 400
    try:
        base_p = Path(base).resolve()
        cur_p = Path(rel_path).resolve() if rel_path else base_p
        # Ensure cur_p is under base
        try:
            cur_p.relative_to(base_p)
        except Exception:
            cur_p = base_p
        if not cur_p.exists() or not cur_p.is_dir():
            return jsonify({"error": "path not a directory"}), 400
        # Build breadcrumb from base to cur
        breadcrumb = []
        # iterate ancestors from base to cur
        parts = []
        tmp = cur_p
        while True:
            parts.append(tmp)
            if tmp == base_p:
                break
            tmp = tmp.parent
            if tmp == tmp.parent:  # reached filesystem root
                break
        parts.reverse()
        for p in parts:
            try:
                breadcrumb.append({"name": p.name or str(p), "path": str(p)})
            except Exception:
                breadcrumb.append({"name": str(p), "path": str(p)})
        # Precompute scanned dataset paths
        scanned_paths = {}
        for d in _get_ext()['graph'].list_datasets():
            scanned_paths[d.get('path')] = d.get('id')
        # List items
        items = []
        for child in cur_p.iterdir():
            try:
                st = child.stat()
                is_dir = child.is_dir()
                item = {
                    'name': child.name,
                    'path': str(child.resolve()),
                    'is_dir': bool(is_dir),
                    'size_bytes': 0 if is_dir else int(st.st_size),
                    'modified': float(st.st_mtime),
                    'ext': '' if is_dir else child.suffix.lower(),
                    'scanned': False,
                    'dataset_id': None,
                }
                if not is_dir:
                    dsid = scanned_paths.get(str(child.resolve()))
                    if dsid:
                        item['scanned'] = True
                        item['dataset_id'] = dsid
                items.append(item)
            except Exception:
                continue
        # Sort: directories first, then files by name
        items.sort(key=lambda x: (0 if x['is_dir'] else 1, x['name'].lower()))
        return jsonify({
            'base': str(base_p),
            'path': str(cur_p),
            'breadcrumb': breadcrumb,
            'items': items,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.post('/research_objects')
def api_research_objects_create():
    """Create or update a ResearchObject node for a directory path.
    Body JSON: { provider_id, root_id, path, name?, metadata? }
    Links to known files (datasets) under the directory and includes derived folder paths.
    """
    data = request.get_json(silent=True) or {}
    prov_id = (data.get('provider_id') or 'local_fs').strip() or 'local_fs'
    root_id = (data.get('root_id') or '/').strip() or '/'
    sel_path = (data.get('path') or '').strip() or root_id
    name = (data.get('name') or '').strip() or None
    extra_meta = data.get('metadata') or {}
    try:
        base = Path(root_id).resolve()
        target = Path(sel_path).resolve()
        try:
            target.relative_to(base)
        except Exception:
            return jsonify({'error': 'path outside root'}), 400
        if not target.exists() or not target.is_dir():
            return jsonify({'error': 'path not a directory'}), 400
        # Build file checksum list by matching datasets whose path is under target
        g = _get_ext()['graph']
        file_checksums = []
        folder_paths = set()
        for ds in g.list_datasets():
            try:
                p = Path(ds.get('path') or '').resolve()
            except Exception:
                continue
            try:
                p.relative_to(target)
            except Exception:
                continue
            # Under target => include
            file_checksums.append(ds.get('checksum'))
            try:
                folder_paths.add(str(p.parent))
            except Exception:
                pass
        meta = {
            'name': name or (target.name or str(target)),
            'path': str(target),
            'provider_id': prov_id,
            'root_id': root_id,
        }
        # merge extra metadata
        try:
            if isinstance(extra_meta, dict):
                meta.update({k: v for k, v in extra_meta.items() if k not in meta})
        except Exception:
            pass
        ro = g.upsert_research_object(meta, file_checksums, list(folder_paths))
        return jsonify({'status': 'ok', 'research_object': ro, 'file_links': len(file_checksums), 'folder_links': len(folder_paths)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.get('/research_objects')
def api_research_objects_list():
    g = _get_ext()['graph']
    return jsonify(g.list_research_objects()), 200

@bp.get('/research_objects/<ro_id>')
def api_research_objects_get(ro_id):
    g = _get_ext()['graph']
    ro = g.get_research_object(ro_id)
    if not ro:
        return jsonify({'error': 'not found'}), 404
    # expand lightweight links counts
    files = len(g.ro_files.get(ro_id, set()))
    folders = len(g.ro_folders.get(ro_id, set()))
    out = ro.copy()
    out.update({'file_count': files, 'folder_count': folders})
    return jsonify(out), 200

# Selections & Annotations API (SQLite-backed)
@bp.post('/selections')
def api_create_selection():
    from ...core import annotations_sqlite as ann_db
    payload = request.get_json(silent=True) or {}
    sel_id = (payload.get('id') or '').strip()
    name = (payload.get('name') or '').strip() or None
    import time as _t
    ts = _t.time()
    # If id not provided, derive short id from time
    if not sel_id:
        sel_id = hex(int(ts * 1000000))[2:]
    item = ann_db.create_selection(sel_id, name, ts)
    return jsonify(item), 201

@bp.post('/selections/<sel_id>/items')
def api_add_selection_items(sel_id):
    from ...core import annotations_sqlite as ann_db
    payload = request.get_json(silent=True) or {}
    file_ids = payload.get('file_ids') or payload.get('files') or []
    if not isinstance(file_ids, list):
        return jsonify({'error': 'file_ids must be a list'}), 400
    import time as _t
    ts = _t.time()
    count = ann_db.add_selection_items(sel_id, [str(fid) for fid in file_ids], ts)
    return jsonify({'selection_id': sel_id, 'added': int(count)}), 200

@bp.post('/annotations')
def api_create_annotation():
    from ...core import annotations_sqlite as ann_db
    payload = request.get_json(silent=True) or {}
    file_id = (payload.get('file_id') or '').strip()
    if not file_id:
        return jsonify({'error': 'file_id is required'}), 400
    kind = (payload.get('kind') or '').strip() or None
    label = (payload.get('label') or '').strip() or None
    note = payload.get('note')
    if isinstance(note, str):
        note = note
    elif note is None:
        note = None
    else:
        try:
            note = json.dumps(note)
        except Exception:
            note = str(note)
    data_json = payload.get('data_json')
    if not isinstance(data_json, (str, type(None))):
        try:
            data_json = json.dumps(data_json)
        except Exception:
            data_json = None
    import time as _t
    ts = _t.time()
    ann = ann_db.create_annotation(file_id, kind, label, note, data_json, ts)
    return jsonify(ann), 201

@bp.get('/annotations')
def api_get_annotations():
    from ...core import annotations_sqlite as ann_db
    # Optional filters and pagination
    file_id = (request.args.get('file_id') or '').strip() or None
    try:
        limit = int(request.args.get('limit') or 100)
        offset = int(request.args.get('offset') or 0)
    except Exception:
        limit, offset = 100, 0
    items = ann_db.list_annotations(limit=limit, offset=offset, file_id=file_id)
    return jsonify({'items': items, 'count': len(items), 'limit': limit, 'offset': offset}), 200

@bp.get('/annotations/<int:ann_id>')
def api_get_annotation(ann_id: int):
    from ...core import annotations_sqlite as ann_db
    item = ann_db.get_annotation(ann_id)
    if not item:
        return jsonify({'error': 'not found'}), 404
    return jsonify(item), 200

@bp.patch('/annotations/<int:ann_id>')
def api_update_annotation(ann_id: int):
    from ...core import annotations_sqlite as ann_db
    payload = request.get_json(silent=True) or {}
    # Enforce privacy: only allow kind, label, note, data_json updates
    fields = {k: v for k, v in payload.items() if k in {'kind', 'label', 'note', 'data_json'}}
    updated = ann_db.update_annotation(ann_id, fields)
    if not updated:
        return jsonify({'error': 'not found'}), 404
    return jsonify(updated), 200

@bp.delete('/annotations/<int:ann_id>')
def api_delete_annotation(ann_id: int):
    from ...core import annotations_sqlite as ann_db
    ok = ann_db.delete_annotation(ann_id)
    if not ok:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'status': 'deleted', 'id': ann_id}), 200

# Scans endpoints
@bp.route('/scans', methods=['GET', 'POST'])
def api_scans():
    # POST creates a new scan (alias of legacy /api/scan)
    if request.method == 'POST':
        return api_scan()
    # GET: Prefer SQLite-backed history when state.backend=sqlite; fallback to in-memory
    summaries = []
    use_sqlite = (current_app.config.get('state.backend') == 'sqlite')
    if use_sqlite:
        try:
            from ...core import path_index_sqlite as pix
            import json as _json
            conn = pix.connect()
            try:
                from ...core import migrations as _migs
                _migs.migrate(conn)
                cur = conn.cursor()
                cur.execute("SELECT id, root, started, completed, status, extra_json FROM scans ORDER BY coalesce(completed, started) DESC LIMIT 500")
                rows = cur.fetchall()
                for (sid, root, started, completed, status, extra) in rows:
                    extra_obj = {}
                    try:
                        if extra:
                            extra_obj = _json.loads(extra)
                    except Exception:
                        extra_obj = {}
                    summaries.append({
                        'id': sid,
                        'path': root,
                        'recursive': bool((extra_obj or {}).get('recursive')),
                        'started': started,
                        'ended': completed,
                        'duration_sec': (extra_obj or {}).get('duration_sec'),
                        'file_count': (extra_obj or {}).get('file_count'),
                        'by_ext': (extra_obj or {}).get('by_ext') or {},
                        'source': (extra_obj or {}).get('source'),
                        'checksum_count': len((extra_obj or {}).get('checksums') or []),
                        'committed': bool((extra_obj or {}).get('committed', False)),
                        'committed_at': (extra_obj or {}).get('committed_at'),
                        'status': status,
                        'rescan_of': (extra_obj or {}).get('rescan_of'),
                    })
                # Merge in-memory committed flags to reflect immediate commits
                try:
                    inmem = {s.get('id'): s for s in current_app.extensions['scidk'].get('scans', {}).values()}
                    for i in range(len(summaries)):
                        sid = summaries[i].get('id')
                        if sid in inmem:
                            if bool(inmem[sid].get('committed')):
                                summaries[i]['committed'] = True
                                summaries[i]['committed_at'] = inmem[sid].get('committed_at')
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception:
            summaries = []
    if not summaries:
        scans = list(current_app.extensions['scidk'].get('scans', {}).values())
        scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        summaries = [
            {
                'id': s.get('id'),
                'path': s.get('path'),
                'recursive': s.get('recursive'),
                'started': s.get('started'),
                'ended': s.get('ended'),
                'duration_sec': s.get('duration_sec'),
                'file_count': s.get('file_count'),
                'by_ext': s.get('by_ext', {}),
                'source': s.get('source'),
                'checksum_count': len(s.get('checksums') or []),
                'committed': bool(s.get('committed', False)),
                'committed_at': s.get('committed_at'),
            }
            for s in scans
        ]
    return jsonify(summaries), 200

@bp.get('/scans/<scan_id>')
def api_scan_detail(scan_id):
    s = current_app.extensions['scidk'].get('scans', {}).get(scan_id)
    if not s:
        # Try to reconstruct minimal scan dict from SQLite persistence
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
                    extra_obj = {}
                    try:
                        if extra:
                            extra_obj = _json.loads(extra)
                    except Exception:
                        extra_obj = {}
                    s = {
                        'id': sid,
                        'path': root,
                        'recursive': bool((extra_obj or {}).get('recursive')),
                        'started': started,
                        'ended': completed,
                        'duration_sec': (extra_obj or {}).get('duration_sec'),
                        'file_count': (extra_obj or {}).get('file_count'),
                        'by_ext': (extra_obj or {}).get('by_ext') or {},
                        'source': (extra_obj or {}).get('source'),
                        'checksums': (extra_obj or {}).get('checksums') or [],
                        'committed': bool((extra_obj or {}).get('committed', False)),
                        'committed_at': (extra_obj or {}).get('committed_at'),
                        'provider_id': (extra_obj or {}).get('provider_id'),
                        'host_type': (extra_obj or {}).get('host_type'),
                        'host_id': (extra_obj or {}).get('host_id'),
                        'root_id': (extra_obj or {}).get('root_id'),
                        'root_label': (extra_obj or {}).get('root_label'),
                        'rescan_of': (extra_obj or {}).get('rescan_of'),
                    }
                    # Cache minimal record in-memory to help downstream endpoints
                    current_app.extensions['scidk'].setdefault('scans', {})[scan_id] = s
                else:
                    return jsonify({"error": "not found"}), 404
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception:
            return jsonify({"error": "not found"}), 404
    return jsonify(s), 200

@bp.get('/scans/<scan_id>/config')
def api_scan_config_get(scan_id):
    """Return stored selection config for a scan.
    Prefers scans.extra_json.selection; falls back to scan_selection_rules reconstruction."""
    try:
        from ...core import path_index_sqlite as pix
        from ...core import migrations as _migs
        import json as _json
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute("SELECT extra_json FROM scans WHERE id = ?", (scan_id,))
            row = cur.fetchone()
            if row and row[0]:
                try:
                    extra = _json.loads(row[0])
                    sel = (extra or {}).get('selection')
                    if sel:
                        return jsonify(sel), 200
                except Exception:
                    pass
            cur.execute("SELECT action, path, recursive, node_type, order_index FROM scan_selection_rules WHERE scan_id = ? ORDER BY order_index ASC", (scan_id,))
            rules = []
            for act, pth, rec, nt, oi in cur.fetchall() or []:
                rules.append({'action': act, 'path': pth, 'recursive': bool(rec), 'node_type': nt})
            return jsonify({'rules': rules, 'use_ignore': True, 'allow_override_ignores': True}), 200
        finally:
            try: conn.close()
            except Exception: pass
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.post('/scans/<scan_id>/config')
def api_scan_config_set(scan_id):
    data = request.get_json(force=True, silent=True) or {}
    try:
        from ...core import path_index_sqlite as pix
        from ...core import migrations as _migs
        import json as _json
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute("SELECT extra_json FROM scans WHERE id = ?", (scan_id,))
            row = cur.fetchone()
            extra_obj = {}
            if row and row[0]:
                try: extra_obj = _json.loads(row[0])
                except Exception: extra_obj = {}
            extra_obj['selection'] = data
            cur.execute("UPDATE scans SET extra_json = ? WHERE id = ?", (_json.dumps(extra_obj), scan_id))
            try:
                cur.execute("DELETE FROM scan_selection_rules WHERE scan_id = ?", (scan_id,))
            except Exception:
                pass
            rules = data.get('rules') or []
            for i, r in enumerate(rules):
                act = (r.get('action') or '').lower()
                pth = (r.get('path') or '').strip()
                rec = 1 if r.get('recursive') else 0
                ntyp = r.get('node_type')
                cur.execute(
                    "INSERT INTO scan_selection_rules(scan_id, action, path, recursive, node_type, order_index) VALUES(?,?,?,?,?,?)",
                    (scan_id, act, pth, rec, ntyp, i)
                )
            conn.commit()
            return jsonify({'ok': True}), 200
        finally:
            try: conn.close()
            except Exception: pass
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.post('/scans/<scan_id>/rescan')
def api_scan_rescan(scan_id):
    override = request.get_json(force=True, silent=True) or {}
    selection_override = override.get('selection_override')
    # Fetch original scan
    resp = api_scan_detail(scan_id)
    try:
        code = resp[1]
    except Exception:
        code = getattr(resp, 'status_code', 200)
    if code != 200:
        return resp
    try:
        original = resp.get_json()
    except Exception:
        original = resp[0].json
    if not original:
        return jsonify({'error': 'scan not found'}), 404
    # Load stored selection unless overridden
    sel = None
    if not selection_override:
        cfg = api_scan_config_get(scan_id)
        try:
            if getattr(cfg, 'status_code', 200) == 200:
                sel = cfg.get_json()
        except Exception:
            try:
                sel = cfg[0].json
            except Exception:
                sel = None
    else:
        sel = selection_override
    # Run a new scan with same params
    try:
        from .services.scans_service import ScansService
        svc = ScansService(app)
        result = svc.run_scan({
            'provider_id': original.get('provider_id') or 'local_fs',
            'root_id': original.get('root_id') or '/',
            'path': original.get('path'),
            'recursive': bool(original.get('recursive', True)),
            'fast_list': True if (original.get('provider_id')=='rclone' and original.get('recursive')) else False,
            'selection': sel or {},
        })
        if isinstance(result, dict) and result.get('status') == 'ok':
            # Persist selection snapshot/rules and link to original
            try:
                if sel and result.get('scan_id'):
                    from ...core import path_index_sqlite as pix
                    from ...core import migrations as _migs
                    import json as _json
                    conn = pix.connect()
                    try:
                        _migs.migrate(conn)
                        cur = conn.cursor()
                        cur.execute("SELECT extra_json FROM scans WHERE id = ?", (result['scan_id'],))
                        row = cur.fetchone()
                        extra_obj = {}
                        if row and row[0]:
                            try: extra_obj = _json.loads(row[0])
                            except Exception: extra_obj = {}
                        extra_obj['selection'] = sel
                        extra_obj['rescan_of'] = scan_id
                        cur.execute("UPDATE scans SET extra_json = ? WHERE id = ?", (_json.dumps(extra_obj), result['scan_id']))
                        try:
                            cur.execute("DELETE FROM scan_selection_rules WHERE scan_id = ?", (result['scan_id'],))
                        except Exception:
                            pass
                        rules = sel.get('rules') or []
                        for i, r in enumerate(rules):
                            act = (r.get('action') or '').lower(); pth = (r.get('path') or '').strip(); rec = 1 if r.get('recursive') else 0; ntyp = r.get('node_type')
                            cur.execute("INSERT INTO scan_selection_rules(scan_id, action, path, recursive, node_type, order_index) VALUES(?,?,?,?,?,?)", (result['scan_id'], act, pth, rec, ntyp, i))
                        conn.commit()
                    finally:
                        try: conn.close()
                        except Exception: pass
            except Exception:
                pass
            return jsonify(result), 200
        if isinstance(result, dict) and result.get('status') == 'error':
            code = int(result.get('http_status', 400)); return jsonify(result), code
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'rescan failed'}), 500


@bp.get('/scans/<scan_id>/status')
def api_scan_status(scan_id):
    s = current_app.extensions['scidk'].get('scans', {}).get(scan_id)
    if not s:
        return jsonify({"error": "not found"}), 404
    # Derive simple status and counters
    started = s.get('started')
    ended = s.get('ended')
    status = 'complete' if ended else 'running'
    return jsonify({
        'id': s.get('id'),
        'status': status,
        'started': started,
        'ended': ended,
        'duration_sec': s.get('duration_sec'),
        'file_count': s.get('file_count'),
        'ingested_rows': s.get('ingested_rows', 0),
        'by_ext': s.get('by_ext', {}),
        'folder_count': s.get('folder_count'),
        'source': s.get('source'),
    }), 200
