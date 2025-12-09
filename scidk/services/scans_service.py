from __future__ import annotations
from typing import Dict, Any
from pathlib import Path
import os

# This service encapsulates the scan orchestration that used to live inside app.api_scan
# It is intentionally kept very close to the original logic to preserve behavior and payload.

class ScansService:
    def __init__(self, app):
        self.app = app
        self.fs = app.extensions['scidk']['fs']
        self.registry = app.extensions['scidk']['registry']

    def run_scan(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a scan synchronously and return the same payload dict that api_scan used to return.
        This method performs all the same side effects: populates SQLite index, in-memory datasets, and
        updates app.extensions registries (scans, directories, telemetry).
        """
        # Import inside to avoid heavy imports at module import time
        from flask import jsonify  # type: ignore
        from ..core import path_index_sqlite as pix  # type: ignore
        from ..core.path_utils import parse_remote_path, join_remote_path, parent_remote_path  # type: ignore
        import time, hashlib

        app = self.app
        fs = self.fs
        registry = self.registry

        provider_id = (data.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (data.get('root_id') or '/').strip() or '/'
        path = data.get('path') or (root_id if provider_id != 'local_fs' else os.getcwd())
        recursive = bool(data.get('recursive', True))
        fast_list = bool(data.get('fast_list', False))
        client_specified_fast_list = ('fast_list' in data)

        # Optional selection configuration (rules + ignore policy)
        selection = data.get('selection') or {}
        rules = selection.get('rules') or []
        use_ignore = bool(selection.get('use_ignore', True))
        allow_override_ignores = bool(selection.get('allow_override_ignores', True))

        # Compile a simple selector (MVP): decide(path)->(include,bool) + prune_dir(dir)->bool
        from fnmatch import fnmatch
        def _normalize_rules(rules_list):
            out = []
            for i, r in enumerate(rules_list or []):
                act = (r.get('action') or '').lower()
                p = (r.get('path') or '').rstrip('/')
                if not act or not p:
                    continue
                rec = bool(r.get('recursive', False))
                nt = r.get('node_type')
                depth = p.count('/')
                out.append({'action': act, 'path': p, 'recursive': rec, 'node_type': nt, 'depth': depth, 'order_index': i})
            out.sort(key=lambda x: (x['depth'], x['order_index']), reverse=True)
            return out
        _rules = _normalize_rules(rules)
        def _decide(path_str: str, ignored: bool) -> tuple[bool, str]:
            if ignored and not allow_override_ignores:
                return False, 'ignored_by_scidkignore'
            for r in _rules:
                rp = r['path']
                if r['recursive']:
                    if path_str == rp or path_str.startswith(rp + '/'):
                        return (r['action'] == 'include'), (r['action'] + '_by_rule')
                else:
                    if path_str == rp:
                        return (r['action'] == 'include'), (r['action'] + '_by_rule')
            if ignored:
                return False, 'ignored_by_scidkignore'
            return True, 'inherited'
        def _prune_dir(dir_path: str) -> bool:
            for r in _rules:
                if r['action'] == 'exclude' and r['recursive']:
                    rp = r['path']
                    if dir_path == rp or dir_path.startswith(rp + '/'):
                        return True
            return False

        # Snapshot before
        before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
        started = time.time()
        sid_src = f"{path}|{started}"
        scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
        count = 0
        ingested = 0
        folders = []

        if provider_id in ('local_fs', 'mounted_fs'):
            base = Path(path)
            items_files = []
            items_dirs = set()
            # Source detection compatibility
            try:
                probe_ncdu = fs._list_files_with_ncdu(base, recursive=recursive)  # type: ignore
                if probe_ncdu:
                    fs.last_scan_source = 'ncdu'
                else:
                    probe_gdu = fs._list_files_with_gdu(base, recursive=recursive)  # type: ignore
                    if probe_gdu:
                        fs.last_scan_source = 'gdu'
                    else:
                        fs.last_scan_source = 'python'
            except Exception:
                fs.last_scan_source = 'python'
            # Optional ignore patterns from .scidkignore at base
            ignore_patterns = []
            if use_ignore:
                try:
                    ign = base / '.scidkignore'
                    if ign.exists():
                        for line in ign.read_text(encoding='utf-8').splitlines():
                            s = line.strip()
                            if s and not s.startswith('#'):
                                ignore_patterns.append(s)
                except Exception:
                    ignore_patterns = []
            try:
                if recursive:
                    for p in base.rglob('*'):
                        try:
                            if p.is_dir():
                                items_dirs.add(p)
                            else:
                                # Filter file by selection rules
                                try:
                                    rel = p.resolve().relative_to(base.resolve()).as_posix()
                                except Exception:
                                    rel = str(p)
                                ignored = any(fnmatch(rel, pat) for pat in ignore_patterns)
                                ok, _ = _decide(rel, ignored)
                                if ok:
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
                    items_dirs.add(base)
                else:
                    for p in base.iterdir():
                        try:
                            if p.is_dir():
                                items_dirs.add(p)
                            else:
                                rel = p.name
                                ignored = any(fnmatch(rel, pat) for pat in ignore_patterns)
                                ok, _ = _decide(rel, ignored)
                                if ok:
                                    items_files.append(p)
                        except Exception:
                            continue
                    items_dirs.add(base)
            except Exception:
                items_files = []
                items_dirs = set()

            rows = []
            def _row_from_local(pth: Path, typ: str) -> tuple:
                full = str(pth.resolve())
                parent = str(pth.parent.resolve()) if pth != pth.parent else ''
                name = pth.name or full
                depth = 0 if pth == base else max(0, len(str(pth.resolve()).rstrip('/').split('/')) - len(str(base.resolve()).rstrip('/').split('/')))
                size = 0
                mtime = None
                ext = ''
                mime = None
                if typ == 'file':
                    try:
                        st = pth.stat()
                        size = int(st.st_size)
                        mtime = float(st.st_mtime)
                    except Exception:
                        size = 0
                        mtime = None
                    ext = pth.suffix.lower()
                remote = f"local:{os.uname().nodename}" if provider_id == 'local_fs' else f"mounted:{root_id}"
                return (full, parent, name, depth, typ, size, mtime, ext, mime, None, None, remote, scan_id, None)
            for d in sorted(items_dirs, key=lambda x: str(x)):
                rows.append(_row_from_local(d, 'folder'))
            for fpath in items_files:
                rows.append(_row_from_local(fpath, 'file'))
            ingested = pix.batch_insert_files(rows)

            # Legacy: create in-memory datasets and run interpreters
            count = 0
            for fpath in items_files:
                try:
                    ds = fs.create_dataset_node(fpath)
                    app.extensions['scidk']['graph'].upsert_dataset(ds)
                    interps = registry.select_for_dataset(ds)
                    for interp in interps:
                        try:
                            result = interp.interpret(fpath)
                            app.extensions['scidk']['graph'].add_interpretation(ds['checksum'], interp.id, {
                                'status': result.get('status', 'success'),
                                'data': result.get('data', result),
                                'interpreter_version': getattr(interp, 'version', '0.0.1'),
                            })
                        except Exception as e:
                            app.extensions['scidk']['graph'].add_interpretation(ds['checksum'], interp.id, {
                                'status': 'error',
                                'data': {'error': str(e)},
                                'interpreter_version': getattr(interp, 'version', '0.0.1'),
                            })
                    count += 1
                except Exception:
                    continue
            # Build folders metadata
            for d in items_dirs:
                try:
                    parent = str(d.parent.resolve()) if d != d.parent else ''
                    folders.append({'path': str(d.resolve()), 'name': d.name, 'parent': parent, 'parent_name': Path(parent).name if parent else ''})
                except Exception:
                    continue
        elif provider_id == 'rclone':
            provs = app.extensions['scidk'].get('providers')
            prov = provs.get('rclone') if provs else None
            if not prov:
                return {'status': 'error', 'error': 'rclone provider not available', 'http_status': 400}

            # Normalize to full remote path if needed
            try:
                info = parse_remote_path(path or '')
                is_remote = bool(info.get('is_remote'))
            except Exception:
                is_remote = False
            if not is_remote:
                path = join_remote_path(root_id, (path or '').lstrip('/'))
            if recursive and not client_specified_fast_list:
                fast_list = True

            # seed base folder row to ensure folder synthesis
            try:
                info_t = parse_remote_path(path)
                base_name = (info_t.get('parts')[-1] if info_t.get('parts') else info_t.get('remote_name') or path)
                base_parent = parent_remote_path(path)
                base_item = {"Name": base_name, "Path": "", "IsDir": True, "Size": 0}
                rows = [pix.map_rclone_item_to_row(base_item, path, scan_id)]
                # folders list should include base as well
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
                folders.append({'path': path, 'name': base_name, 'parent': base_parent, 'parent_name': parent_name})
            except Exception:
                rows = []

            try:
                if app.config.get('TESTING') and not recursive:
                    items = []
                else:
                    items = prov.list_files(path, recursive=recursive, fast_list=fast_list)  # type: ignore[attr-defined]
            except Exception as ee:
                return {'status': 'error', 'error': str(ee), 'http_status': 400}

            seen_folders = set()
            def _add_folder(full_path: str, name: str, parent: str):
                if full_path in seen_folders:
                    return
                seen_folders.add(full_path)
                try:
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
                    if it.get('IsDir'):
                        rel = it.get('Path') or it.get('Name') or ''
                        if rel:
                            full = join_remote_path(path, rel)
                            parent = parent_remote_path(full)
                            leaf = rel.rsplit('/',1)[-1] if isinstance(rel, str) and '/' in rel else rel
                            _add_folder(full, leaf, parent)
                        rows.append(pix.map_rclone_item_to_row(it, path, scan_id))
                        continue
                    # File row with selection filter (no .scidkignore for remotes here)
                    rel = it.get('Path') or it.get('Name') or ''
                    full_remote = join_remote_path(path, rel) if rel else join_remote_path(path, it.get('Name') or '')
                    ok, _ = _decide(full_remote, ignored=False)
                    if ok:
                        rows.append(pix.map_rclone_item_to_row(it, path, scan_id))
                    # Synthesize folder chain for file rel paths
                    rel = it.get('Path') or it.get('Name') or ''
                    if rel:
                        parts = [p for p in (rel.split('/') if isinstance(rel, str) else []) if p]
                        cur_rel = ''
                        for i in range(len(parts)-1):
                            cur_rel = parts[i] if i == 0 else (cur_rel + '/' + parts[i])
                            full = join_remote_path(path, cur_rel)
                            parent = parent_remote_path(full)
                            _add_folder(full, parts[i], parent)
                            try:
                                folder_item = {"Name": parts[i], "Path": cur_rel, "IsDir": True, "Size": 0}
                                rows.append(pix.map_rclone_item_to_row(folder_item, path, scan_id))
                            except Exception:
                                pass
                    backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()
                    if backend != 'neo4j':
                        size = int(it.get('Size') or 0)
                        full = join_remote_path(path, rel)
                        ds = fs.create_dataset_remote(full, size_bytes=size, modified_ts=0.0, mime=None)
                        app.extensions['scidk']['graph'].upsert_dataset(ds)
                        count += 1
                except Exception:
                    continue
            try:
                # Dedup by (path,type)
                seen = set(); uniq = []
                for r in rows:
                    key = (r[0], r[4])
                    if key in seen:
                        continue
                    seen.add(key); uniq.append(r)
                rows = uniq
            except Exception:
                pass
            try:
                ingested = pix.batch_insert_files(rows, batch_size=10000)
                try:
                    _chg = pix.apply_basic_change_history(scan_id, path)
                    app.extensions['scidk'].setdefault('telemetry', {})['last_change_counts'] = _chg
                except Exception as __e:
                    app.extensions['scidk'].setdefault('telemetry', {})['last_change_error'] = str(__e)
            except Exception as _e:
                app.extensions['scidk'].setdefault('telemetry', {})['last_sqlite_error'] = str(_e)
        else:
            return {'status': 'error', 'error': f'provider {provider_id} not supported for scan', 'http_status': 400}

        ended = time.time()
        duration = ended - started
        after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
        new_checksums = sorted(list(after - before))

        # by_ext calculation preserved
        by_ext: Dict[str, int] = {}
        backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()
        if backend == 'neo4j':
            try:
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
            for ds in app.extensions['scidk']['graph'].list_datasets():
                ext_map[ds.get('checksum')] = ds.get('extension') or ''
            for ch in new_checksums:
                ext = ext_map.get(ch, '')
                by_ext[ext] = by_ext.get(ext, 0) + 1

        # Non-recursive local: include immediate subfolders
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

        provs = app.extensions['scidk'].get('providers')
        prov = provs.get(provider_id) if provs else None
        root_label = None
        try:
            if prov:
                root_label = Path(root_id).name or str(root_id)
        except Exception:
            root_label = None

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
            'source': getattr(fs, 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
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
        }
        scans = app.extensions['scidk'].setdefault('scans', {})
        scans[scan_id] = scan
        try:
            app.extensions['scidk'].setdefault('scan_fs', {}).pop(scan_id, None)
        except Exception:
            pass
        telem = app.extensions['scidk'].setdefault('telemetry', {})
        telem['last_scan'] = {
            'path': str(path),
            'recursive': bool(recursive),
            'scanned': int(count),
            'started': started,
            'ended': ended,
            'duration_sec': duration,
            'source': getattr(fs, 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
            'provider_id': provider_id,
            'root_id': root_id,
        }
        dirs = app.extensions['scidk'].setdefault('directories', {})
        drec = dirs.setdefault(str(path), {
            'path': str(path),
            'recursive': bool(recursive),
            'scanned': 0,
            'last_scanned': 0,
            'scan_ids': [],
            'source': getattr(fs, 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
            'provider_id': provider_id,
            'root_id': root_id,
            'root_label': root_label,
        })
        drec.update({
            'recursive': bool(recursive),
            'scanned': int(count),
            'last_scanned': ended,
            'source': getattr(fs, 'last_scan_source', 'python') if provider_id in ('local_fs','mounted_fs') else f"provider:{provider_id}",
            'provider_id': provider_id,
            'root_id': root_id,
            'root_label': root_label,
        })
        drec.setdefault('scan_ids', []).append(scan_id)
        # Persist scan summary to SQLite (best-effort), mirroring background worker
        try:
            conn = pix.connect()
            try:
                from ..core import migrations as _migs
                import json as _json
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
                            'selection': (selection or {}),
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
        # return payload identical to previous endpoint
        return {"status": "ok", "scan_id": scan_id, "scanned": count, "folder_count": len(folders), "ingested_rows": int(ingested), "duration_sec": duration, "path": str(path), "recursive": bool(recursive), "provider_id": provider_id}
