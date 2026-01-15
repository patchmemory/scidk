from __future__ import annotations
from typing import Dict, Any
from pathlib import Path
import os
import json

# This service encapsulates the scan orchestration that used to live inside app.api_scan
# It is intentionally kept very close to the original logic to preserve behavior and payload.

class ScansService:
    def __init__(self, app):
        self.app = app
        self.fs = app.extensions['scidk']['fs']
        self.registry = app.extensions['scidk']['registry']
        # Selective scan cache metrics (per-run)
        self._skipped_files = 0
        self._skipped_dirs = 0
        self._walk_time_ms = 0.0

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
                import time as _t
                t_walk0 = _t.time()
                # Load previous scan id for this root (if any)
                prev_scan_id = None
                try:
                    conn_prev = pix.connect()
                    from ..core import migrations as _migs
                    _migs.migrate(conn_prev)
                    curp = conn_prev.cursor()
                    curp.execute("SELECT id FROM scans WHERE root = ? ORDER BY COALESCE(completed, started) DESC LIMIT 1", (str(path),))
                    rowp = curp.fetchone()
                    if rowp:
                        prev_scan_id = rowp[0]
                except Exception:
                    prev_scan_id = None
                finally:
                    try:
                        conn_prev.close()
                    except Exception:
                        pass
                # Helper: compute immediate dir signature (files only)
                def _dir_signature(dir_path: Path):
                    total = 0
                    max_m = 0.0
                    files_n = 0
                    try:
                        with os.scandir(dir_path) as it:
                            for ent in it:
                                if ent.is_file(follow_symlinks=False):
                                    files_n += 1
                                    try:
                                        st = ent.stat(follow_symlinks=False)
                                        total += int(st.st_size)
                                        if st.st_mtime and float(st.st_mtime) > max_m:
                                            max_m = float(st.st_mtime)
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    return {'files': files_n, 'sum_size': int(total), 'max_mtime': float(max_m)}
                # Load previous cache for quick compare
                prev_cache = {}
                if prev_scan_id:
                    try:
                        conn2 = pix.connect()
                        cur2 = conn2.cursor()
                        cur2.execute("SELECT path, children_json FROM directory_cache WHERE scan_id = ?", (prev_scan_id,))
                        import json as _json
                        for (pth, js) in cur2.fetchall() or []:
                            try:
                                prev_cache[pth] = _json.loads(js) if js else {}
                            except Exception:
                                prev_cache[pth] = {}
                    except Exception:
                        prev_cache = {}
                    finally:
                        try:
                            conn2.close()
                        except Exception:
                            pass
                # Current cache rows to persist
                curr_cache_rows = []
                if recursive:
                    # Controlled walk with pruning
                    # Folder-config cache for effective config per directory
                    from ..core.folder_config import load_effective_config  # lazy import
                    _conf_cache: dict[str, dict] = {}
                    for dirpath, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
                        dpath = Path(dirpath)
                        # compute signature and compare
                        sig = _dir_signature(dpath)
                        prev_sig = prev_cache.get(str(dpath.resolve()))
                        # If unchanged vs previous, consider pruning traversal
                        if prev_sig and all(str(sig.get(k)) == str(prev_sig.get(k)) for k in ('files','sum_size','max_mtime')):
                            # For the base (root) directory: skip files in this dir but still traverse subdirectories
                            if dpath == base:
                                try:
                                    with os.scandir(dpath) as it2:
                                        for ent2 in it2:
                                            if ent2.is_file(follow_symlinks=False):
                                                self._skipped_files += 1
                                except Exception:
                                    pass
                                # Do not modify dirnames for root; we still want to descend
                            else:
                                self._skipped_dirs += 1
                                # estimate skipped files as current immediate files
                                self._skipped_files += int(sig.get('files') or 0)
                                dirnames[:] = []  # prune subdirs
                                # still record base dir
                                items_dirs.add(dpath)
                                # persist current cache for this dir
                                curr_cache_rows.append((scan_id, str(dpath.resolve()), json.dumps(sig), time.time()))
                                continue
                        # keep walking: record dir and files
                        items_dirs.add(dpath)
                        # persist cache row
                        curr_cache_rows.append((scan_id, str(dpath.resolve()), json.dumps(sig), time.time()))
                        # filter files by rules + folder-config include/exclude
                        # Load effective folder-config for this directory (cached)
                        key = str(dpath.resolve())
                        conf = _conf_cache.get(key)
                        if conf is None:
                            # Prefer local .scidk.toml in this directory (closest wins), then fall back to effective config
                            try:
                                tpath = Path(dpath) / '.scidk.toml'
                                if tpath.exists():
                                    try:
                                        import tomllib as _toml
                                    except ModuleNotFoundError:
                                        import tomli as _toml
                                    try:
                                        data = _toml.loads(tpath.read_text(encoding='utf-8'))
                                    except Exception:
                                        data = {}
                                    inc = data.get('include') if isinstance(data.get('include'), list) else []
                                    exc = data.get('exclude') if isinstance(data.get('exclude'), list) else []
                                    conf = {'include': [str(x) for x in inc], 'exclude': [str(x) for x in exc], 'interpreters': None}
                                else:
                                    conf = load_effective_config(dpath, stop_at=base)
                            except Exception:
                                conf = {'include': [], 'exclude': [], 'interpreters': None}
                            _conf_cache[key] = conf
                        fc_includes = conf.get('include') or []
                        fc_excludes = conf.get('exclude') or []
                        from pathlib import Path as _P
                        def _normalize_patterns(patterns: list[str]) -> list[str]:
                            out = []
                            for pat in patterns:
                                if not pat:
                                    continue
                                norm_pat = pat.strip()
                                if norm_pat.startswith('./'):
                                    norm_pat = norm_pat[2:]
                                if norm_pat.startswith('/'):
                                    norm_pat = norm_pat[1:]
                                out.append(norm_pat)
                                # If pattern starts with '**/', also consider without that prefix
                                if norm_pat.startswith('**/'):
                                    out.append(norm_pat[3:])
                                # If pattern contains path segments, add basename-only variant
                                if '/' in norm_pat:
                                    seg = norm_pat.split('/')[-1]
                                    if seg and seg not in out:
                                        out.append(seg)
                            return out
                        def _matches_any(rel_path: str, name: str, patterns: list[str]) -> bool:
                            # Normalize cases for case-insensitive filesystems and user patterns
                            rel_l = (rel_path or '').lower()
                            name_l = (name or '').lower()
                            pats = _normalize_patterns(patterns)
                            p_rel = _P(rel_l)
                            p_name = _P(name_l)
                            for pat in pats:
                                p = (pat or '').strip()
                                if not p:
                                    continue
                                p_l = p.lower()
                                try:
                                    if p_rel.match(p_l) or p_name.match(p_l):
                                        return True
                                except Exception:
                                    pass
                                # Suffix-based relaxed match for common patterns like '*.ext' or '**/*.ext'
                                if p_l.startswith('**/*.') or p_l.startswith('*.'):
                                    suf = p_l.split('*')[-1]
                                    # Normalize suffix by removing any leading path separator introduced by '**/' patterns
                                    if suf.startswith('/'):
                                        suf = suf[1:]
                                    if suf and name_l.endswith(suf):
                                        return True
                                # Always check basename-only equality as last resort
                                try:
                                    if '/' in p_l:
                                        base = p_l.split('/')[-1]
                                    else:
                                        base = p_l
                                    if base and name_l == base:
                                        return True
                                except Exception:
                                    pass
                                # Fallback to fnmatch-like simple compare
                                from fnmatch import fnmatch as _fn
                                if _fn(rel_l, p_l) or _fn(name_l, p_l):
                                    return True
                            return False
                        for fname in filenames:
                            try:
                                rel = str(Path(dirpath) / fname)
                                try:
                                    rel_disp = Path(rel).resolve().relative_to(base.resolve()).as_posix()
                                except Exception:
                                    rel_disp = fname
                                # Folder-config include/exclude first (match against base-relative, dir-relative, and basename)
                                rel_local = fname
                                from fnmatch import fnmatch as _fn2
                                def _simple_match(patterns: list[str]) -> bool:
                                    for pat in patterns or []:
                                        p = (pat or '').strip()
                                        if not p:
                                            continue
                                        p = p.lstrip('./')
                                        p_l = p.lower()
                                        if _fn2(rel_disp.lower(), p_l) or _fn2(rel_local.lower(), p_l):
                                            return True
                                        if p_l.startswith('**/*.') or p_l.startswith('*.'):
                                            suf = p_l.split('*')[-1]
                                            if suf.startswith('/'):
                                                suf = suf[1:]
                                            if suf and rel_local.lower().endswith(suf):
                                                return True
                                    return False
                                include_ok = True
                                if fc_includes:
                                    include_ok = _simple_match(fc_includes)
                                if not include_ok:
                                    continue
                                if fc_excludes and (_simple_match(fc_excludes)):
                                    continue
                                # .scidkignore and explicit selection rules
                                ignored = any(fnmatch(rel_disp, pat) for pat in ignore_patterns)
                                ok, _ = _decide(rel_disp, ignored)
                                if ok:
                                    items_files.append(Path(dirpath) / fname)
                            except Exception:
                                continue
                else:
                    # Non-recursive: list only base
                    items_dirs.add(base)
                    sig = _dir_signature(base)
                    curr_cache_rows.append((scan_id, str(base.resolve()), json.dumps(sig), time.time()))
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
                # Persist directory_cache rows (best-effort)
                try:
                    connc = pix.connect()
                    curc = connc.cursor()
                    curc.executemany("INSERT OR REPLACE INTO directory_cache(scan_id, path, children_json, created) VALUES(?,?,?,?)", curr_cache_rows)
                    connc.commit()
                except Exception:
                    pass
                finally:
                    try:
                        connc.close()
                    except Exception:
                        pass
                self._walk_time_ms = ( _t.time() - t_walk0 ) * 1000.0
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
        # Emit selective cache metrics to logs for observability
        try:
            app.logger.info(f"scan metrics: skipped_dirs={int(getattr(self, '_skipped_dirs', 0))} skipped_files={int(getattr(self, '_skipped_files', 0))} walk_time_ms={float(getattr(self, '_walk_time_ms', 0.0)):.2f}")
        except Exception:
            pass
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
                            'skipped_dirs': int(getattr(self, '_skipped_dirs', 0)),
                            'skipped_files': int(getattr(self, '_skipped_files', 0)),
                            'walk_time_ms': float(getattr(self, '_walk_time_ms', 0.0)),
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
