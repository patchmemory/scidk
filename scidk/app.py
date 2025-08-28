from flask import Flask, Blueprint, jsonify, request, render_template, redirect, url_for
from pathlib import Path
import os
from typing import Optional

from .core.graph import InMemoryGraph
from .core.filesystem import FilesystemManager
from .core.registry import InterpreterRegistry
from .interpreters.python_code import PythonCodeInterpreter
from .interpreters.csv_interpreter import CsvInterpreter
from .interpreters.json_interpreter import JsonInterpreter
from .interpreters.yaml_interpreter import YamlInterpreter
from .interpreters.ipynb_interpreter import IpynbInterpreter
from .interpreters.txt_interpreter import TxtInterpreter
from .interpreters.xlsx_interpreter import XlsxInterpreter
from .core.pattern_matcher import Rule
from .core.providers import ProviderRegistry as FsProviderRegistry, LocalFSProvider, MountedFSProvider, RcloneProvider


def create_app():
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")

    # Core singletons (MVP: in-memory)
    graph = InMemoryGraph()
    registry = InterpreterRegistry()

    # Register interpreters
    py_interp = PythonCodeInterpreter()
    csv_interp = CsvInterpreter()
    json_interp = JsonInterpreter()
    yaml_interp = YamlInterpreter()
    ipynb_interp = IpynbInterpreter()
    txt_interp = TxtInterpreter()
    xlsx_interp = XlsxInterpreter()
    registry.register_extension(".py", py_interp)
    registry.register_extension(".csv", csv_interp)
    registry.register_extension(".json", json_interp)
    registry.register_extension(".yml", yaml_interp)
    registry.register_extension(".yaml", yaml_interp)
    registry.register_extension(".ipynb", ipynb_interp)
    registry.register_extension(".txt", txt_interp)
    registry.register_extension(".xlsx", xlsx_interp)
    registry.register_extension(".xlsm", xlsx_interp)
    # Register simple rules to prefer interpreters for extensions
    registry.register_rule(Rule(id="rule.py.default", interpreter_id=py_interp.id, pattern="*.py", priority=10, conditions={"ext": ".py"}))
    registry.register_rule(Rule(id="rule.csv.default", interpreter_id=csv_interp.id, pattern="*.csv", priority=10, conditions={"ext": ".csv"}))
    registry.register_rule(Rule(id="rule.json.default", interpreter_id=json_interp.id, pattern="*.json", priority=10, conditions={"ext": ".json"}))
    registry.register_rule(Rule(id="rule.yml.default", interpreter_id=yaml_interp.id, pattern="*.yml", priority=10, conditions={"ext": ".yml"}))
    registry.register_rule(Rule(id="rule.yaml.default", interpreter_id=yaml_interp.id, pattern="*.yaml", priority=10, conditions={"ext": ".yaml"}))
    registry.register_rule(Rule(id="rule.ipynb.default", interpreter_id=ipynb_interp.id, pattern="*.ipynb", priority=10, conditions={"ext": ".ipynb"}))
    registry.register_rule(Rule(id="rule.txt.default", interpreter_id=txt_interp.id, pattern="*.txt", priority=10, conditions={"ext": ".txt"}))
    registry.register_rule(Rule(id="rule.xlsx.default", interpreter_id=xlsx_interp.id, pattern="*.xlsx", priority=10, conditions={"ext": ".xlsx"}))
    registry.register_rule(Rule(id="rule.xlsm.default", interpreter_id=xlsx_interp.id, pattern="*.xlsm", priority=10, conditions={"ext": ".xlsm"}))

    fs = FilesystemManager(graph=graph, registry=registry)

    # Initialize filesystem providers (Phase 0)
    prov_enabled = [p.strip() for p in (os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs').split(',')) if p.strip()]
    # If rclone mounts feature is enabled, ensure rclone provider is also enabled for listremotes validation
    _ff_rc = (os.environ.get('SCIDK_RCLONE_MOUNTS') or os.environ.get('SCIDK_FEATURE_RCLONE_MOUNTS') or '').strip().lower() in ('1','true','yes','y','on')
    if _ff_rc and 'rclone' not in prov_enabled:
        prov_enabled.append('rclone')
    fs_providers = FsProviderRegistry(enabled=prov_enabled)
    p_local = LocalFSProvider(); p_local.initialize(app, {})
    p_mounted = MountedFSProvider(); p_mounted.initialize(app, {})
    p_rclone = RcloneProvider(); p_rclone.initialize(app, {})
    fs_providers.register(p_local)
    fs_providers.register(p_mounted)
    fs_providers.register(p_rclone)

    # Store refs on app for easy access
    app.extensions = getattr(app, 'extensions', {})
    app.extensions['scidk'] = {
        'graph': graph,
        'registry': registry,
        'fs': fs,
        'providers': fs_providers,
        # in-session registries
        'scans': {},  # scan_id -> scan session dict
        'directories': {},  # path -> aggregate info incl. scan_ids
        'telemetry': {},
        'tasks': {},  # task_id -> task dict (background jobs like scans)
        'scan_fs': {},  # per-scan filesystem index cache for snapshot navigation
        'neo4j_config': {
            'uri': None,
            'user': None,
            'password': None,
            'database': None,
        },
        'neo4j_state': {
            'connected': False,
            'last_error': None,
        },
        # rclone mounts runtime registry (feature-flagged API will use this)
        'rclone_mounts': {},  # id/name -> { id, remote, subpath, path, read_only, started_at, pid, log_file }
    }

    # API routes
    api = Blueprint('api', __name__, url_prefix='/api')

    # Feature flag for rclone mount manager
    def _feature_rclone_mounts() -> bool:
        val = (os.environ.get('SCIDK_RCLONE_MOUNTS') or os.environ.get('SCIDK_FEATURE_RCLONE_MOUNTS') or '').strip().lower()
        return val in ('1', 'true', 'yes', 'y', 'on')

    # Helper to read Neo4j configuration, preferring in-app settings over environment
    # Returns tuple: (uri, user, password, database, auth_mode)
    # auth_mode: 'basic' (username+password) or 'none' (no authentication)
    def _get_neo4j_params():
        cfg = app.extensions['scidk'].get('neo4j_config', {})
        uri = cfg.get('uri') or os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')
        user = cfg.get('user') or os.environ.get('NEO4J_USER') or os.environ.get('NEO4J_USERNAME')
        pwd = cfg.get('password') or os.environ.get('NEO4J_PASSWORD')
        database = cfg.get('database') or os.environ.get('SCIDK_NEO4J_DATABASE') or None
        # Parse NEO4J_AUTH env var if provided (formats: "user/pass" or "none")
        neo4j_auth = (os.environ.get('NEO4J_AUTH') or '').strip()
        if neo4j_auth:
            if neo4j_auth.lower() == 'none':
                user = user or None
                pwd = pwd or None
                auth_mode = 'none'
            else:
                try:
                    # Expecting user/password
                    parts = neo4j_auth.split('/')
                    if len(parts) >= 2 and not (user and pwd):
                        user = user or parts[0]
                        pwd = pwd or '/'.join(parts[1:])
                except Exception:
                    pass
        # If user/password still missing, try to parse from URI (bolt://user:pass@host:port)
        auth_mode = 'basic'
        try:
            if uri and (not user or not pwd):
                from urllib.parse import urlparse, unquote
                parsed = urlparse(uri)
                if parsed.username and parsed.password:
                    user = user or unquote(parsed.username)
                    pwd = pwd or unquote(parsed.password)
        except Exception:
            pass
        # Determine auth mode: none only when explicitly set via NEO4J_AUTH=none
        if (os.environ.get('NEO4J_AUTH') or '').strip().lower() == 'none':
            auth_mode = 'none'
        else:
            auth_mode = 'basic'
        return uri, user, pwd, database, auth_mode

    # Build rows for commit: files (rows) and standalone folders (folder_rows)
    def build_commit_rows(scan, ds_map):
        checksums = scan.get('checksums') or []
        # Helpers to handle local paths and rclone remote paths like "remote:folder/sub/file"
        def _split_remote(p: str):
            # Returns (remote_prefix or None, rest)
            try:
                if p and (':' in p) and (p.index(':') < p.index('/') if '/' in p else True):
                    i = p.index(':')
                    return p[:i+1], p[i+1:]
            except Exception:
                pass
            return None, p
        def _parent_of(p: str) -> str:
            rp, rest = _split_remote(p)
            if rp is not None:
                if not rest:
                    # at remote root
                    return rp
                if '/' in rest:
                    return rp + rest.rsplit('/', 1)[0]
                # file directly under remote root
                return rp
            # Fallback to pathlib for local/absolute paths
            from pathlib import Path as __P
            try:
                return str(__P(p).parent)
            except Exception:
                return ''
        def _name_of(p: str) -> str:
            rp, rest = _split_remote(p)
            if rp is not None:
                seg = rest.rsplit('/', 1)[-1] if rest else rp.rstrip(':')
                return seg
            from pathlib import Path as __P
            try:
                return __P(p).name
            except Exception:
                return p
        def _parent_name_of(p: str) -> str:
            par = _parent_of(p)
            rp, rest = _split_remote(par)
            if rp is not None:
                if not rest:
                    return rp.rstrip(':')
                return rest.rsplit('/', 1)[-1]
            from pathlib import Path as __P
            try:
                return __P(par).name
            except Exception:
                return par
        # Precompute folders observed in this scan (parents of files)
        folder_set = set()
        for ch in checksums:
            dtmp = ds_map.get(ch)
            if not dtmp:
                continue
            folder_set.add(_parent_of(dtmp.get('path') or ''))
        rows = []
        for ch in checksums:
            d = ds_map.get(ch)
            if not d:
                continue
            parent = _parent_of(d.get('path') or '')
            interps = list((d.get('interpretations') or {}).keys())
            # derive folder fields
            folder_path = parent
            folder_name = _name_of(folder_path) if folder_path else ''
            folder_parent = _parent_of(folder_path) if folder_path else ''
            folder_parent_name = _parent_name_of(folder_path) if folder_parent else ''
            rows.append({
                'checksum': d.get('checksum'),
                'path': d.get('path'),
                'filename': d.get('filename'),
                'extension': d.get('extension'),
                'size_bytes': int(d.get('size_bytes') or 0),
                'created': float(d.get('created') or 0),
                'modified': float(d.get('modified') or 0),
                'mime_type': d.get('mime_type'),
                'folder': folder_path,
                'folder_name': folder_name,
                'folder_parent': folder_parent,
                'folder_parent_name': folder_parent_name,
                'parent_in_scan': bool(folder_parent and (folder_parent in folder_set)),
                'interps': interps,
            })
        # Build folder rows captured during non-recursive scan
        folder_rows = []
        for f in (scan.get('folders') or []):
            folder_rows.append({
                'path': f.get('path'),
                'name': f.get('name'),
                'parent': f.get('parent'),
                'parent_name': f.get('parent_name'),
            })
        return rows, folder_rows

    # Execute Neo4j commit using simplified, idempotent Cypher
    def commit_to_neo4j(rows, folder_rows, scan, neo4j_params):
        # Support 4-tuple (backward compat) and 5-tuple with auth_mode
        try:
            uri, user, pwd, database, auth_mode = neo4j_params
        except Exception:
            uri, user, pwd, database = neo4j_params
            auth_mode = 'basic'
        result = {'attempted': False, 'written_files': 0, 'written_folders': 0, 'error': None}
        if not uri:
            return result
        # Decide if we can attempt a connection
        can_basic = bool(user and pwd)
        can_connect = (auth_mode == 'none') or can_basic
        if not can_connect:
            return result
        # Backoff on recent auth failures to avoid rate limiting
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
        import time as _t
        now = _t.time()
        next_after = float(st.get('next_connect_after') or 0)
        if next_after and now < next_after:
            result['error'] = f"neo4j connect backoff active; retry after {int(next_after-now)}s"
            return result
        result['attempted'] = True
        try:
            from neo4j import GraphDatabase  # type: ignore
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                with driver.session(database=database) as sess:
                    cypher = (
                        "WITH $rows AS rows, $folders AS folders, $scan_id AS scan_id, $scan_path AS scan_path, $scan_started AS scan_started, $scan_ended AS scan_ended, $scan_provider AS scan_provider, $scan_host_type AS scan_host_type, $scan_host_id AS scan_host_id, $scan_root_id AS scan_root_id, $scan_root_label AS scan_root_label, $scan_source AS scan_source "
                        "MERGE (s:Scan {id: scan_id}) SET s.path = scan_path, s.started = scan_started, s.ended = scan_ended "
                        "WITH rows, folders, s CALL { WITH rows, s UNWIND rows AS r "
                        "  MERGE (f:File {checksum: r.checksum}) "
                        "    SET f.path = r.path, f.filename = r.filename, f.extension = r.extension, f.size_bytes = r.size_bytes, "
                        "        f.created = r.created, f.modified = r.modified, f.mime_type = r.mime_type, f.provider_id = $scan_provider, f.host_type = $scan_host_type, f.host_id = $scan_host_id "
                        "  MERGE (f)-[:SCANNED_IN]->(s) "
                        "  FOREACH (_ IN CASE WHEN coalesce(r.folder,'') <> '' THEN [1] ELSE [] END | "
                        "    MERGE (fo:Folder {path: r.folder}) SET fo.name = r.folder_name, fo.provider_id = $scan_provider, fo.host_type = $scan_host_type, fo.host_id = $scan_host_id "
                        "    MERGE (fo)-[:CONTAINS]->(f) "
                        "    MERGE (fo)-[:SCANNED_IN]->(s) "
                        "    FOREACH (__ IN CASE WHEN coalesce(r.folder_parent,'') <> '' AND r.parent_in_scan THEN [1] ELSE [] END | "
                        "      MERGE (fop:Folder {path: r.folder_parent}) SET fop.name = r.folder_parent_name, fop.provider_id = $scan_provider, fop.host_type = $scan_host_type, fop.host_id = $scan_host_id "
                        "      MERGE (fop)-[:CONTAINS]->(fo) ) "
                        "  ) RETURN 0 AS _files_done } "
                        "WITH folders, s CALL { WITH folders, s UNWIND folders AS r2 "
                        "  MERGE (fo:Folder {path: r2.path}) SET fo.name = r2.name, fo.provider_id = $scan_provider, fo.host_type = $scan_host_type, fo.host_id = $scan_host_id "
                        "  MERGE (fo)-[:SCANNED_IN]->(s) "
                        "  FOREACH (__ IN CASE WHEN coalesce(r2.parent,'') <> '' THEN [1] ELSE [] END | "
                        "    MERGE (fop:Folder {path: r2.parent}) SET fop.name = r2.parent_name, fop.provider_id = $scan_provider, fop.host_type = $scan_host_type, fop.host_id = $scan_host_id "
                        "    MERGE (fop)-[:CONTAINS]->(fo) ) "
                        "  RETURN 0 AS _folders_done } "
                        "WITH s SET s.provider_id = $scan_provider, s.host_type = $scan_host_type, s.host_id = $scan_host_id, s.root_id = $scan_root_id, s.root_label = $scan_root_label, s.scan_source = $scan_source "
                        "RETURN s.id AS scan_id"
                    )
                    res = sess.run(cypher, rows=rows, folders=folder_rows, scan_id=scan.get('id'), scan_path=scan.get('path'), scan_started=scan.get('started'), scan_ended=scan.get('ended'), scan_provider=scan.get('provider_id'), scan_host_type=scan.get('host_type'), scan_host_id=scan.get('host_id'), scan_root_id=scan.get('root_id'), scan_root_label=scan.get('root_label'), scan_source=scan.get('scan_source'))
                    _ = list(res)
                    result['written_files'] = len(rows)
                    result['written_folders'] = len(folder_rows)
                    # Post-commit verification: confirm that Scan exists and at least one SCANNED_IN relationship was created
                    verify_q = (
                        "OPTIONAL MATCH (s:Scan {id: $scan_id}) "
                        "WITH s "
                        "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(f:File) "
                        "WITH s, count(DISTINCT f) AS files_cnt "
                        "OPTIONAL MATCH (s)<-[:SCANNED_IN]-(fo:Folder) "
                        "RETURN coalesce(s IS NOT NULL, false) AS scan_exists, files_cnt AS files_cnt, count(DISTINCT fo) AS folders_cnt"
                    )
                    vrec = sess.run(verify_q, scan_id=scan.get('id')).single()
                    if vrec:
                        scan_exists = bool(vrec.get('scan_exists'))
                        files_cnt = int(vrec.get('files_cnt') or 0)
                        folders_cnt = int(vrec.get('folders_cnt') or 0)
                        result['db_scan_exists'] = scan_exists
                        result['db_files'] = files_cnt
                        result['db_folders'] = folders_cnt
                        result['db_verified'] = bool(scan_exists and (files_cnt > 0 or folders_cnt > 0))
            finally:
                try:
                    if driver is not None:
                        driver.close()
                except Exception:
                    pass
        except Exception as e:
            msg = str(e)
            result['error'] = msg
            # On auth-related errors, set a backoff to avoid rate limiting
            try:
                emsg = msg.lower()
                if ('unauthorized' in emsg) or ('authentication' in emsg):
                    # Exponential-ish backoff min 20s
                    prev = float(st.get('next_connect_after') or 0)
                    base = 20.0
                    delay = base
                    if prev and now < prev:
                        # increase delay up to 120s
                        rem = prev - now
                        delay = min(max(base*2, rem*2), 120.0)
                    st['next_connect_after'] = now + delay
                    st['last_error'] = msg
            except Exception:
                pass
        return result

    # Build or fetch per-scan filesystem index for snapshot navigation
    def _get_or_build_scan_index(scan_id: str):
        cache = app.extensions['scidk'].setdefault('scan_fs', {})
        if scan_id in cache:
            return cache[scan_id]
        scans = app.extensions['scidk'].get('scans', {})
        s = scans.get(scan_id)
        if not s:
            return None
        checksums = s.get('checksums') or []
        ds_map = app.extensions['scidk']['graph'].datasets  # checksum -> dataset
        from pathlib import Path as _P
        folder_info = {}
        children_files = {}
        # Add files by parent folder
        for ch in checksums:
            d = ds_map.get(ch)
            if not d:
                continue
            try:
                p = _P(d.get('path'))
            except Exception:
                continue
            parent = str(p.parent)
            file_entry = {
                'id': d.get('id'),
                'path': d.get('path'),
                'filename': d.get('filename'),
                'extension': d.get('extension'),
                'size_bytes': int(d.get('size_bytes') or 0),
                'modified': float(d.get('modified') or 0),
                'mime_type': d.get('mime_type'),
                'checksum': d.get('checksum'),
            }
            children_files.setdefault(parent, []).append(file_entry)
            # ensure folder info
            folder_info[parent] = folder_info.get(parent) or {
                'path': parent,
                'name': _P(parent).name,
                'parent': str(_P(parent).parent) if parent else '',
            }
        # Include folders captured on non-recursive scans
        for f in (s.get('folders') or []):
            path = f.get('path'); parent = f.get('parent')
            name = f.get('name')
            if path:
                folder_info[path] = folder_info.get(path) or {
                    'path': path,
                    'name': name,
                    'parent': parent,
                }
                if parent:
                    folder_info[parent] = folder_info.get(parent) or {
                        'path': parent,
                        'name': _P(parent).name,
                        'parent': str(_P(parent).parent),
                    }
        # Build children_folders map
        children_folders = {}
        for fpath, info in folder_info.items():
            par = info.get('parent')
            if par and par in folder_info:
                children_folders.setdefault(par, []).append(fpath)
        # Derive roots: folders with no parent in folder_info
        roots = sorted([fp for fp, info in folder_info.items() if not info.get('parent') or info.get('parent') not in folder_info])
        # Sort child folders
        for k in list(children_folders.keys()):
            children_folders[k].sort(key=lambda p: _P(p).name.lower())
        # Sort files by filename
        for k in list(children_files.keys()):
            children_files[k].sort(key=lambda f: (f.get('filename') or '').lower())
        idx = {
            'folder_info': folder_info,
            'children_folders': children_folders,
            'children_files': children_files,
            'roots': roots,
        }
        cache[scan_id] = idx
        return idx

    @api.post('/scan')
    def api_scan():
        data = request.get_json(force=True, silent=True) or {}
        provider_id = (data.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (data.get('root_id') or '/').strip() or '/'
        path = data.get('path') or (root_id if provider_id != 'local_fs' else os.getcwd())
        recursive = bool(data.get('recursive', True))
        try:
            import time, hashlib, json
            # Pre-scan snapshot of checksums
            before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
            started = time.time()
            count = 0
            folders = []
            if provider_id in ('local_fs', 'mounted_fs'):
                count = fs.scan_directory(Path(path), recursive=recursive)
            elif provider_id == 'rclone':
                # Use rclone lsjson to enumerate remote files; create dataset nodes without downloading.
                provs = app.extensions['scidk'].get('providers')
                prov = provs.get('rclone') if provs else None
                if not prov:
                    raise RuntimeError('rclone provider not available')
                try:
                    items = prov.list_files(path, recursive=recursive)  # type: ignore[attr-defined]
                except Exception as ee:
                    return jsonify({"status": "error", "error": str(ee)}), 400
                for it in (items or []):
                    try:
                        if it.get('IsDir'):
                            # collect immediate subfolders only when non-recursive
                            if not recursive:
                                # rclone returns entries with only Name; reconstruct full path
                                name = it.get('Name') or it.get('Path') or ''
                                if name:
                                    parent = path if path.endswith(':') else path.rstrip('/')
                                    full = f"{parent}/{name}" if not parent.endswith(':') else f"{parent}{name}"
                                    folders.append({'path': full, 'name': name, 'parent': path, 'parent_name': Path(path).name if path else ''})
                            continue
                        # File entry
                        name = it.get('Name') or it.get('Path') or ''
                        size = int(it.get('Size') or 0)
                        # Construct full remote path safely
                        parent = path if path.endswith(':') else path.rstrip('/')
                        full = f"{parent}/{name}" if not parent.endswith(':') else f"{parent}{name}"
                        ds = fs.create_dataset_remote(full, size_bytes=size, modified_ts=0.0, mime=None)
                        app.extensions['scidk']['graph'].upsert_dataset(ds)
                        count += 1
                    except Exception:
                        continue
            else:
                return jsonify({"status": "error", "error": f"provider {provider_id} not supported for scan"}), 400
            ended = time.time()
            duration = ended - started
            after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
            new_checksums = sorted(list(after - before))
            # Build simple by_ext from new datasets
            by_ext = {}
            ext_map = {}
            for ds in app.extensions['scidk']['graph'].list_datasets():
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
            # Create scan session id (short sha1 of path+started)
            sid_src = f"{path}|{started}"
            scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
            # Provider metadata for scan/session records
            provs = app.extensions['scidk'].get('providers')
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
            }
            scans = app.extensions['scidk'].setdefault('scans', {})
            scans[scan_id] = scan
            # Save telemetry on app
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
            # Track scanned directories (in-session registry)
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
            return jsonify({"status": "ok", "scan_id": scan_id, "scanned": count, "duration_sec": duration, "path": str(path), "recursive": bool(recursive), "provider_id": provider_id}), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 400

    @api.post('/tasks')
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
        running = sum(1 for t in app.extensions['scidk'].get('tasks', {}).values() if t.get('status') == 'running')
        if running >= max_tasks:
            return jsonify({'error': 'too many tasks running', 'code': 'max_tasks', 'max': max_tasks}), 429

        if ttype == 'scan':
            path = data.get('path') or os.getcwd()
            recursive = bool(data.get('recursive', True))
            tid_src = f"scan|{path}|{started}"
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
            }
            app.extensions['scidk'].setdefault('tasks', {})[task_id] = task

            def _worker():
                try:
                    # Snapshot before
                    before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
                    # Estimate total using Python traversal (MVP)
                    files = [p for p in fs._iter_files_python(Path(path), recursive=recursive)]  # type: ignore
                    total = len(files)
                    task['total'] = total
                    # Process each file similarly to scan_directory
                    processed = 0
                    for p in files:
                        if task.get('cancel_requested'):
                            task['status'] = 'canceled'
                            task['ended'] = time.time()
                            # progress remains as-is; do not create scan record
                            return
                        # upsert
                        ds = fs.create_dataset_node(p)
                        app.extensions['scidk']['graph'].upsert_dataset(ds)
                        # interpreters
                        interps = registry.select_for_dataset(ds)
                        for interp in interps:
                            try:
                                result = interp.interpret(p)
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
                        processed += 1
                        task['processed'] = processed
                        if total:
                            task['progress'] = processed / total
                    ended = time.time()
                    # Build scan record (reuse logic from api_scan)
                    after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
                    new_checksums = sorted(list(after - before))
                    by_ext = {}
                    ext_map = {ds.get('checksum'): ds.get('extension') or '' for ds in app.extensions['scidk']['graph'].list_datasets()}
                    for ch in new_checksums:
                        ext = ext_map.get(ch, '')
                        by_ext[ext] = by_ext.get(ext, 0) + 1
                    sid_src = f"{path}|{started}"
                    scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
                    # For non-recursive scans, include immediate subfolders
                    folders = []
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
                        folders = []
                    scan = {
                        'id': scan_id,
                        'path': str(path),
                        'recursive': bool(recursive),
                        'started': started,
                        'ended': ended,
                        'duration_sec': ended - started,
                        'file_count': int(processed),
                        'folder_count': len(folders),
                        'checksums': new_checksums,
                        'folders': folders,
                        'by_ext': by_ext,
                        'source': 'python',
                        'errors': [],
                        'committed': False,
                        'committed_at': None,
                    }
                    app.extensions['scidk']['scans'][scan_id] = scan
                    # Telemetry
                    app.extensions['scidk'].setdefault('telemetry', {})['last_scan'] = {
                        'path': str(path), 'recursive': bool(recursive), 'scanned': int(processed),
                        'started': started, 'ended': ended, 'duration_sec': ended - started, 'source': 'python'
                    }
                    # Directory registry
                    dirs = app.extensions['scidk'].setdefault('directories', {})
                    drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': [], 'source': 'python'})
                    drec.update({'recursive': bool(recursive), 'scanned': int(processed), 'last_scanned': ended, 'source': 'python'})
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
            scans = app.extensions['scidk'].setdefault('scans', {})
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
            app.extensions['scidk'].setdefault('tasks', {})[task_id] = task

            def _worker_commit():
                try:
                    if task.get('cancel_requested'):
                        task['status'] = 'canceled'
                        task['ended'] = time.time()
                        return
                    g = app.extensions['scidk']['graph']
                    # In-memory commit first
                    g.commit_scan(s)
                    s['committed'] = True
                    s['committed_at'] = time.time()
                    # Build rows once using helper
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
                    result = commit_to_neo4j(rows, folder_rows, s, (uri, user, pwd, database, auth_mode))
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

    @api.get('/tasks')
    def api_tasks_list():
        tasks = list(app.extensions['scidk'].get('tasks', {}).values())
        # sort newest first
        tasks.sort(key=lambda t: t.get('started') or 0, reverse=True)
        return jsonify(tasks), 200

    @api.get('/tasks/<task_id>')
    def api_tasks_detail(task_id):
        task = app.extensions['scidk'].get('tasks', {}).get(task_id)
        if not task:
            return jsonify({"error": "not found"}), 404
        return jsonify(task), 200

    @api.post('/tasks/<task_id>/cancel')
    def api_tasks_cancel(task_id):
        tasks = app.extensions['scidk'].setdefault('tasks', {})
        task = tasks.get(task_id)
        if not task:
            return jsonify({'error': 'not found'}), 404
        # only running tasks can be canceled
        if task.get('status') != 'running':
            return jsonify({'status': task.get('status'), 'message': 'task not running'}), 400
        task['cancel_requested'] = True
        return jsonify({'status': 'canceling'}), 202

    @api.get('/datasets')
    def api_datasets():
        items = graph.list_datasets()
        return jsonify(items)

    @api.get('/datasets/<dataset_id>')
    def api_dataset(dataset_id):
        item = graph.get_dataset(dataset_id)
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)

    @api.post('/interpret')
    def api_interpret():
        data = request.get_json(force=True, silent=True) or {}
        dataset_id = data.get('dataset_id')
        interpreter_id = data.get('interpreter_id')
        if not dataset_id:
            return jsonify({"status": "error", "error": "dataset_id required"}), 400
        ds = graph.get_dataset(dataset_id)
        if not ds:
            return jsonify({"status": "error", "error": "dataset not found"}), 404
        file_path = Path(ds['path'])
        if interpreter_id:
            interp = registry.get_by_id(interpreter_id)
            if not interp:
                return jsonify({"status": "error", "error": "interpreter not found"}), 404
            interps = [interp]
        else:
            interps = registry.select_for_dataset(ds)
            if not interps:
                return jsonify({"status": "error", "error": "no interpreters available"}), 400
        results = []
        for interp in interps:
            try:
                result = interp.interpret(file_path)
                graph.add_interpretation(ds['checksum'], interp.id, {
                    'status': result.get('status', 'success'),
                    'data': result.get('data', result),
                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                })
                results.append({'interpreter_id': interp.id, 'status': 'ok'})
            except Exception as e:
                graph.add_interpretation(ds['checksum'], interp.id, {
                    'status': 'error',
                    'data': {'error': str(e)},
                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                })
                results.append({'interpreter_id': interp.id, 'status': 'error', 'error': str(e)})
        return jsonify({"status": "ok", "results": results}), 200

    @api.post('/chat')
    def api_chat():
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"status": "error", "error": "message required"}), 400
        store = app.extensions['scidk'].setdefault('chat', {"history": []})
        # Simple echo bot with count
        reply = f"Echo: {message}"
        entry_user = {"role": "user", "content": message}
        entry_assistant = {"role": "assistant", "content": reply}
        store['history'].append(entry_user)
        store['history'].append(entry_assistant)
        return jsonify({"status": "ok", "reply": reply, "history": store['history']}), 200

    @api.get('/search')
    def api_search():
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify([]), 200
        q_lower = q.lower()
        results = []
        for ds in graph.list_datasets():
            matched_on = []
            # Match filename
            if q_lower in (ds.get('filename') or '').lower() or q_lower in (ds.get('path') or '').lower():
                matched_on.append('filename')
            # Match interpreter ids present
            interps = (ds.get('interpretations') or {})
            for interp_id in interps.keys():
                if q_lower in interp_id.lower():
                    if 'interpreter_id' not in matched_on:
                        matched_on.append('interpreter_id')
            if matched_on:
                results.append({
                    'id': ds.get('id'),
                    'path': ds.get('path'),
                    'filename': ds.get('filename'),
                    'extension': ds.get('extension'),
                    'matched_on': matched_on,
                })
        # Simple ordering: filename matches first, then interpreter_id
        def score(r):
            return (0 if 'filename' in r['matched_on'] else 1, r['filename'] or '')
        results.sort(key=score)
        return jsonify(results), 200

    @api.get('/providers')
    def api_providers():
        provs = app.extensions['scidk']['providers']
        out = []
        for d in provs.list():
            out.append({
                'id': d.id,
                'display_name': d.display_name,
                'capabilities': d.capabilities,
                'auth': d.auth,
            })
        return jsonify(out), 200

    @api.get('/provider_roots')
    def api_provider_roots():
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        try:
            provs = app.extensions['scidk']['providers']
            prov = provs.get(prov_id)
            if not prov:
                return jsonify({'error': 'provider not available'}), 400
            roots = prov.list_roots()
            return jsonify([{'id': r.id, 'name': r.name, 'path': r.path} for r in roots]), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.get('/browse')
    def api_browse():
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        path_q = (request.args.get('path') or '').strip()
        try:
            provs = app.extensions['scidk']['providers']
            prov = provs.get(prov_id)
            if not prov:
                return jsonify({'error': 'provider not available', 'code': 'provider_not_available'}), 400
            # If path empty, default to root_id
            listing = prov.list(root_id=root_id, path=path_q or root_id)
            # Bubble provider-level errors clearly
            if isinstance(listing, dict) and listing.get('error'):
                return jsonify({'error': listing.get('error'), 'code': 'browse_failed'}), 400
            # Augment with provider badge and convenience fields
            for e in listing.get('entries', []):
                e['provider_id'] = prov_id
            return jsonify(listing), 200
        except Exception as e:
            return jsonify({'error': str(e), 'code': 'browse_exception'}), 500

    @api.get('/directories')
    def api_directories():
        dirs = app.extensions['scidk'].get('directories', {})
        # Return stable order: most recently scanned first
        values = list(dirs.values())
        values.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        return jsonify(values), 200

    # -----------------------------
    # Rclone Mount Manager (flagged)
    # -----------------------------
    if _feature_rclone_mounts():
        import time, subprocess, shutil, json as _json

        def _mounts_dir() -> Path:
            d = Path(app.root_path).parent / 'data' / 'mounts'
            d.mkdir(parents=True, exist_ok=True)
            return d

        def _sanitize_name(name: str) -> str:
            safe = ''.join([c for c in (name or '') if c.isalnum() or c in ('-', '_')]).strip()
            return safe[:64] if safe else ''

        def _listremotes() -> list:
            try:
                provs = app.extensions['scidk']['providers']
                rp = provs.get('rclone') if provs else None
                roots = rp.list_roots() if rp else []
                return [r.id for r in roots]
            except Exception:
                return []

        def _rclone_exe() -> Optional[str]:
            return shutil.which('rclone')

        @api.get('/rclone/mounts')
        def api_rclone_mounts_list():
            mounts = app.extensions['scidk'].setdefault('rclone_mounts', {})
            out = []
            for mid, m in list(mounts.items()):
                proc = m.get('process')
                alive = (proc is not None) and (proc.poll() is None)
                status = 'running' if alive else ('exited' if proc is not None else 'unknown')
                exit_code = None if alive else (proc.returncode if proc is not None else None)
                out.append({
                    'id': m.get('id'),
                    'name': m.get('name'),
                    'remote': m.get('remote'),
                    'subpath': m.get('subpath'),
                    'path': m.get('path'),
                    'read_only': m.get('read_only'),
                    'started_at': m.get('started_at'),
                    'status': status,
                    'exit_code': exit_code,
                    'log_file': m.get('log_file'),
                })
            return jsonify(out), 200

        @api.post('/rclone/mounts')
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
                mounts = app.extensions['scidk'].setdefault('rclone_mounts', {})
                mounts[name] = rec
                return jsonify({'id': name, 'path': str(mpath)}), 201
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @api.delete('/rclone/mounts/<mid>')
        def api_rclone_mounts_delete(mid):
            mounts = app.extensions['scidk'].setdefault('rclone_mounts', {})
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
            return jsonify({'ok': True}), 200

        @api.get('/rclone/mounts/<mid>/logs')
        def api_rclone_mounts_logs(mid):
            mounts = app.extensions['scidk'].setdefault('rclone_mounts', {})
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

        @api.get('/rclone/mounts/<mid>/health')
        def api_rclone_mounts_health(mid):
            mounts = app.extensions['scidk'].setdefault('rclone_mounts', {})
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

    @api.get('/fs/list')
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
        dirs = app.extensions['scidk'].get('directories', {})
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
            for d in app.extensions['scidk']['graph'].list_datasets():
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

    @api.get('/scans')
    def api_scans():
        scans = list(app.extensions['scidk'].get('scans', {}).values())
        scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        # Return a lighter summary by default
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

    @api.get('/scans/<scan_id>')
    def api_scan_detail(scan_id):
        s = app.extensions['scidk'].get('scans', {}).get(scan_id)
        if not s:
            return jsonify({"error": "not found"}), 404
        return jsonify(s), 200

    @api.get('/scans/<scan_id>/fs')
    def api_scan_fs(scan_id):
        idx = _get_or_build_scan_index(scan_id)
        if not idx:
            return jsonify({'error': 'scan not found'}), 404
        from pathlib import Path as _P
        req_path = (request.args.get('path') or '').strip()
        folder_info = idx['folder_info']
        children_folders = idx['children_folders']
        children_files = idx['children_files']
        roots = idx['roots']
        # Virtual root listing when no path specified
        if not req_path:
            folders = [{'name': _P(p).name, 'path': p, 'file_count': len(children_files.get(p, []))} for p in roots]
            folders.sort(key=lambda r: r['name'].lower())
            breadcrumb = [{'name': '(scan roots)', 'path': ''}]
            return jsonify({'scan_id': scan_id, 'path': '', 'breadcrumb': breadcrumb, 'folders': folders, 'files': []}), 200
        # Validate path exists in snapshot
        if req_path not in folder_info:
            return jsonify({'error': 'folder not found in scan'}), 404
        # Breadcrumb from this scan’s perspective
        bc_chain = []
        cur = req_path
        while cur and cur in folder_info:
            bc_chain.append(cur)
            par = folder_info[cur].get('parent')
            if par == cur:
                break
            cur = par
        bc_chain.reverse()
        breadcrumb = [{'name': '(scan roots)', 'path': ''}] + [{'name': _P(p).name, 'path': p} for p in bc_chain]
        # Children
        sub_folders = [{'name': _P(p).name, 'path': p, 'file_count': len(children_files.get(p, []))} for p in children_folders.get(req_path, [])]
        sub_folders.sort(key=lambda r: r['name'].lower())
        files = children_files.get(req_path, [])
        return jsonify({'scan_id': scan_id, 'path': req_path, 'breadcrumb': breadcrumb, 'folders': sub_folders, 'files': files}), 200

    @api.post('/scans/<scan_id>/commit')
    def api_scan_commit(scan_id):
        scans = app.extensions['scidk'].setdefault('scans', {})
        s = scans.get(scan_id)
        if not s:
            return jsonify({"status": "error", "error": "scan not found"}), 404
        try:
            checksums = s.get('checksums') or []
            total = len(checksums)
            # How many of these files are present in the current graph
            g = app.extensions['scidk']['graph']
            present = sum(1 for ch in checksums if ch in getattr(g, 'datasets', {}))
            missing = total - present
            # Commit into graph (idempotent add of Scan + edges)
            g.commit_scan(s)
            import time as _t
            s['committed'] = True
            s['committed_at'] = _t.time()

            # Attempt Neo4j write if configuration is present (do not rely solely on connected flag)
            neo_state = app.extensions['scidk'].get('neo4j_state', {})
            neo_attempted = False
            neo_written = 0
            neo_error = None
            db_verified = None
            db_files = 0
            db_folders = 0
            uri, user, pwd, database, auth_mode = _get_neo4j_params()
            if uri and ((auth_mode == 'none') or (user and pwd)):
                neo_attempted = True
                try:
                    ds_map = getattr(g, 'datasets', {})
                    rows, folder_rows = build_commit_rows(s, ds_map)
                    result = commit_to_neo4j(rows, folder_rows, s, (uri, user, pwd, database, auth_mode))
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
                # DB verification results (if commit attempted)
                "neo4j_db_verified": db_verified,
                "neo4j_db_files": db_files,
                "neo4j_db_folders": db_folders,
            }
            if neo_error:
                payload["neo4j_error"] = neo_error
            # Add user-facing warnings
            if total == 0:
                payload["warning"] = "This scan has 0 files; nothing was linked."
            elif present == 0:
                payload["warning"] = "None of the scanned files are currently present in the graph; verify you scanned in this session or refresh."
            # Neo4j-specific warning when verification fails but no explicit error was raised
            if neo_attempted and (db_verified is not None) and (not db_verified) and (not neo_error):
                payload["neo4j_warning"] = "Neo4j post-commit verification found 0 SCANNED_IN edges for this scan. Check Neo4j credentials, database name, or permissions."
            return jsonify(payload), 200
        except Exception as e:
            return jsonify({"status": "error", "error": "commit failed", "error_detail": str(e)}), 500

    @api.delete('/scans/<scan_id>')
    def api_scan_delete(scan_id):
        scans = app.extensions['scidk'].setdefault('scans', {})
        existed = scan_id in scans
        # Remove from graph first
        app.extensions['scidk']['graph'].delete_scan(scan_id)
        if existed:
            del scans[scan_id]
        return jsonify({"status": "ok", "deleted": True, "scan_id": scan_id, "existed": existed}), 200

    @api.get('/graph/schema')
    def api_graph_schema():
        try:
            limit = int(request.args.get('limit') or 500)
        except Exception:
            limit = 500
        data = app.extensions['scidk']['graph'].schema_triples(limit=limit)
        return jsonify(data), 200

    @api.get('/graph/schema.csv')
    def api_graph_schema_csv():
        # Build a simple CSV with two sections: NodeLabels and RelationshipTypes
        g = app.extensions['scidk']['graph']
        triples = g.schema_triples(limit=int(request.args.get('limit') or 0 or 0))
        # If limit is 0 treat as no limit
        if (request.args.get('limit') or '').strip() == '0':
            triples = g.schema_triples(limit=0)
        nodes = triples.get('nodes', [])
        edges = triples.get('edges', [])
        lines = []
        lines.append('NodeLabels')
        lines.append('label,count')
        for n in nodes:
            lines.append(f"{n.get('label','')},{n.get('count',0)}")
        lines.append('')
        lines.append('RelationshipTypes')
        lines.append('start_label,rel_type,end_label,count')
        for e in edges:
            lines.append(f"{e.get('start_label','')},{e.get('rel_type','')},{e.get('end_label','')},{e.get('count',0)}")
        csv_text = "\n".join(lines) + "\n"
        from flask import Response
        return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename="schema.csv"'})

    @api.get('/graph/subschema')
    def api_graph_subschema():
        # Filters: name (optional), labels (csv), rel_types (csv), limit (int)
        params = {k: (request.args.get(k) or '').strip() for k in ['name','labels','rel_types','limit']}
        # Named queries
        if params['name']:
            if params['name'].lower() == 'interpreted_as':
                params['rel_types'] = 'INTERPRETED_AS' if not params['rel_types'] else params['rel_types']
            # Future named queries can be added here
        # Parse filters
        labels = set([s for s in (params['labels'].split(',')) if s]) if params['labels'] else set()
        rel_types = set([s for s in (params['rel_types'].split(',')) if s]) if params['rel_types'] else set()
        try:
            limit = int(params['limit']) if params['limit'] else 500
        except Exception:
            limit = 500
        g = app.extensions['scidk']['graph']
        base = g.schema_triples(limit=0 if limit == 0 else 1000000)  # fetch all, filter then trim
        edges = base.get('edges', [])
        # Apply filters
        def edge_ok(e):
            if rel_types and e.get('rel_type') not in rel_types:
                return False
            if labels and (e.get('start_label') not in labels and e.get('end_label') not in labels):
                return False
            return True
        filtered_edges = [e for e in edges if edge_ok(e)]
        # Truncate if needed
        truncated = False
        if limit and limit > 0 and len(filtered_edges) > limit:
            filtered_edges = filtered_edges[:limit]
            truncated = True
        # Build nodes: start with base nodes filtered by labels (if any)
        base_nodes = {n['label']: n.get('count', 0) for n in base.get('nodes', [])}
        node_map = {}
        # Include from filtered edges endpoints
        for e in filtered_edges:
            for lab in [e.get('start_label'), e.get('end_label')]:
                if lab not in node_map:
                    node_map[lab] = base_nodes.get(lab, 1 if lab else 1)
        # If labels filter provided, ensure inclusion even if no edges
        for lab in labels:
            if lab not in node_map:
                node_map[lab] = base_nodes.get(lab, 0)
        out = {
            'nodes': [{'label': k, 'count': v} for k, v in node_map.items()],
            'edges': filtered_edges,
            'truncated': truncated,
        }
        return jsonify(out), 200

    @api.get('/graph/instances')
    def api_graph_instances():
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # preview only (cap to 100 rows)
        limit = 100
        if request.args.get('limit'):
            try:
                limit = int(request.args.get('limit'))
            except Exception:
                pass
        return jsonify({
            'label': label,
            'count': len(rows),
            'rows': rows[:max(0, limit)]
        }), 200

    @api.get('/graph/instances.csv')
    def api_graph_instances_csv():
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # Build CSV
        if not rows:
            headers = ['id']
        else:
            # union columns
            cols = set()
            for r in rows:
                cols.update(r.keys())
            headers = sorted(list(cols))
        import io, csv
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in headers})
        from flask import Response
        return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="instances_{label}.csv"'})

    @api.get('/graph/instances.xlsx')
    def api_graph_instances_xlsx():
        try:
            import openpyxl  # type: ignore
        except Exception:
            return jsonify({"error": "xlsx export requires openpyxl"}), 501
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # Determine headers
        if not rows:
            headers = ['id']
        else:
            cols = set()
            for r in rows:
                cols.update(r.keys())
            headers = sorted(list(cols))
        from openpyxl import Workbook  # type: ignore
        wb = Workbook()
        ws = wb.active
        ws.title = label or 'Sheet1'
        ws.append(headers)
        for r in rows:
            ws.append([r.get(k, '') for k in headers])
        import io
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        from flask import Response
        return Response(bio.read(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="instances_{label}.xlsx"'})

    @api.get('/graph/instances.pkl')
    def api_graph_instances_pickle():
        import pickle
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        payload = pickle.dumps(rows, protocol=pickle.HIGHEST_PROTOCOL)
        from flask import Response
        return Response(payload, mimetype='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="instances_{label}.pkl"'})

    @api.get('/graph/instances.arrow')
    def api_graph_instances_arrow():
        try:
            import pyarrow as pa  # type: ignore
            import pyarrow.ipc as pa_ipc  # type: ignore
        except Exception:
            return jsonify({"error": "arrow export requires pyarrow"}), 501
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # Normalize rows to a table (handle missing keys by union of columns)
        cols = set()
        for r in rows:
            cols.update(r.keys())
        cols = sorted(list(cols)) if rows else ['id']
        arrays = {c: [] for c in cols}
        for r in rows:
            for c in cols:
                arrays[c].append(r.get(c))
        table = pa.table({c: pa.array(arrays[c]) for c in cols})
        sink = pa.BufferOutputStream()
        with pa_ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        buf = sink.getvalue()
        from flask import Response
        return Response(buf.to_pybytes(), mimetype='application/vnd.apache.arrow.stream', headers={'Content-Disposition': f'attachment; filename="instances_{label}.arrow"'})

    @api.get('/graph/schema.neo4j')
    def api_graph_schema_neo4j():
        # Cypher-only triple derivation from a Neo4j instance if configured
        uri, user, pwd, database, auth_mode = _get_neo4j_params()
        if not uri:
            return jsonify({"error": "neo4j not configured (set in Settings or env: NEO4J_URI, and NEO4J_USER/NEO4J_PASSWORD or NEO4J_AUTH=none)"}), 501
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception:
            return jsonify({"error": "neo4j driver not installed"}), 501
        try:
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                with driver.session(database=database) as sess:
                    # Node label counts
                    q_nodes = "MATCH (n) WITH head(labels(n)) AS l, count(*) AS c RETURN l AS label, c ORDER BY c DESC"
                    nodes = [dict(record) for record in sess.run(q_nodes)]
                    # Unique triples counts
                    q_edges = (
                        "MATCH (s)-[r]->(t) "
                        "WITH head(labels(s)) AS sl, type(r) AS rt, head(labels(t)) AS tl, count(*) AS c "
                        "RETURN sl AS start_label, rt AS rel_type, tl AS end_label, c ORDER BY c DESC"
                    )
                    edges = [dict(record) for record in sess.run(q_edges)]
            finally:
                try:
                    if driver is not None:
                        driver.close()
                except Exception:
                    pass
            return jsonify({"nodes": nodes, "edges": edges, "truncated": False}), 200
        except Exception as e:
            return jsonify({"error": f"neo4j query failed: {str(e)}"}), 502

    @api.get('/graph/schema.apoc')
    def api_graph_schema_apoc():
        # APOC-based schema where available; fall back is not done here; use /graph/schema or /graph/schema.neo4j otherwise
        uri, user, pwd, database, auth_mode = _get_neo4j_params()
        if not uri:
            return jsonify({"error": "neo4j not configured (set in Settings or env: NEO4J_URI, and NEO4J_USER/NEO4J_PASSWORD or NEO4J_AUTH=none)"}), 501
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception:
            return jsonify({"error": "neo4j driver not installed"}), 501
        try:
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                with driver.session(database=database) as sess:
                    # Use apoc.meta.data() to derive nodes and edges
                    # Relationship triples aggregation
                    q_apoc = (
                        "CALL apoc.meta.data() YIELD label, other, elementType, type, count "
                        "WITH label, other, elementType, type, count "
                        "WHERE elementType = 'relationship' "
                        "RETURN label AS start_label, type AS rel_type, other AS end_label, count ORDER BY count DESC"
                    )
                    edges = [dict(record) for record in sess.run(q_apoc)]
                    # Node label counts via apoc (fallback to Cypher if needed)
                    q_nodes = "CALL apoc.meta.stats() YIELD labels RETURN [k IN keys(labels) | {label:k, count: labels[k]}] AS pairs"
                    rec = sess.run(q_nodes).single()
                    nodes = []
                    if rec and 'pairs' in rec:
                        for p in rec['pairs']:
                            nodes.append({'label': p['label'], 'count': p['count']})
            finally:
                try:
                    if driver is not None:
                        driver.close()
                except Exception:
                    pass
            return jsonify({"nodes": nodes, "edges": edges, "truncated": False}), 200
        except Exception as e:
            # If APOC procedures are missing or fail, inform the client
            return jsonify({"error": f"apoc schema failed: {str(e)}"}), 502

    @api.get('/health/graph')
    def api_health_graph():
        """Basic health for graph backend. In-memory is always OK; if Neo4j settings/env are provided, try a connection."""
        backend = os.environ.get('SCIDK_GRAPH_BACKEND', 'in_memory').lower() or 'in_memory'
        info = {
            'backend': backend,
            'in_memory_ok': True,
            'neo4j': {
                'configured': False,
                'connectable': False,
                'error': None,
            }
        }
        uri, user, pwd, database, auth_mode = _get_neo4j_params()
        if uri:
            info['neo4j']['configured'] = True
            try:
                from neo4j import GraphDatabase  # type: ignore
            except Exception as e:
                info['neo4j']['error'] = f"neo4j driver not installed: {e}"
                return jsonify(info), 200
            # Respect auth-failure backoff
            st = app.extensions['scidk'].setdefault('neo4j_state', {})
            import time as _t
            now = _t.time()
            next_after = float(st.get('next_connect_after') or 0)
            if next_after and now < next_after:
                info['neo4j']['error'] = f"backoff active; retry after {int(next_after-now)}s"
                return jsonify(info), 200
            try:
                driver = None
                try:
                    driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                    with driver.session(database=database) as sess:
                        rec = sess.run("RETURN 1 AS ok").single()
                        if rec and rec.get('ok') == 1:
                            info['neo4j']['connectable'] = True
                finally:
                    try:
                        if driver is not None:
                            driver.close()
                    except Exception:
                        pass
            except Exception as e:
                info['neo4j']['error'] = str(e)
        return jsonify(info), 200

    # Settings APIs for Neo4j configuration
    @api.get('/settings/neo4j')
    def api_settings_neo4j_get():
        cfg = app.extensions['scidk'].get('neo4j_config', {})
        state = app.extensions['scidk'].get('neo4j_state', {})
        # Do not return password
        out = {
            'uri': cfg.get('uri') or '',
            'user': cfg.get('user') or '',
            'database': cfg.get('database') or '',
            'connected': bool(state.get('connected')),
            'last_error': state.get('last_error'),
        }
        return jsonify(out), 200

    @api.post('/settings/neo4j')
    def api_settings_neo4j_set():
        data = request.get_json(force=True, silent=True) or {}
        cfg = app.extensions['scidk'].setdefault('neo4j_config', {})
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
        # Reset state error on change
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
        st['last_error'] = None
        return jsonify({'status':'ok'}), 200

    @api.post('/settings/neo4j/connect')
    def api_settings_neo4j_connect():
        uri, user, pwd, database, auth_mode = _get_neo4j_params()
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
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

    @api.post('/settings/neo4j/disconnect')
    def api_settings_neo4j_disconnect():
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
        st['connected'] = False
        return jsonify({'connected': False}), 200

    @api.get('/rocrate')
    def api_rocrate():
        """Return a minimal RO-Crate JSON-LD for a given directory (depth=1).
        Query: provider_id (default local_fs), root_id ('/'), path (directory path)
        Caps: at most 1000 immediate children; include meta.truncated when applied.
        """
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        sel_path = (request.args.get('path') or '').strip() or root_id
        try:
            provs = app.extensions['scidk']['providers']
            prov = provs.get(prov_id)
            if not prov:
                return jsonify({'error': 'provider not available'}), 400
            from pathlib import Path as _P
            base = _P(root_id).resolve()
            target = _P(sel_path).resolve()
            # Ensure target resides under base (best-effort for local/mounted providers)
            try:
                target.relative_to(base)
            except Exception:
                # If not under base, fall back to base
                target = base
            if not target.exists() or not target.is_dir():
                return jsonify({'error': 'path not a directory'}), 400
            # Prepare root entity
            from datetime import datetime as _DT
            def iso(ts):
                try:
                    return _DT.fromtimestamp(float(ts)).isoformat()
                except Exception:
                    return None
            # Enumerate immediate children
            children = []
            total = 0
            LIMIT = 1000
            import mimetypes as _mt
            for child in target.iterdir():
                total += 1
                if len(children) >= LIMIT:
                    continue
                try:
                    st = child.stat()
                    is_dir = child.is_dir()
                    mime = None if is_dir else (_mt.guess_type(child.name)[0] or 'application/octet-stream')
                    children.append({
                        '@id': child.name + ('/' if is_dir else ''),
                        '@type': 'Dataset' if is_dir else 'File',
                        'name': child.name or str(child),
                        'contentSize': 0 if is_dir else int(st.st_size),
                        'dateModified': iso(st.st_mtime),
                        'encodingFormat': None if is_dir else mime,
                        'url': None if is_dir else (f"/api/files?provider_id={prov_id}&root_id={root_id}&path=" + str(child.resolve())),
                    })
                except Exception:
                    continue
            graph = [{
                '@id': './',
                '@type': 'Dataset',
                'name': target.name or str(target),
                'hasPart': [{'@id': c['@id']} for c in children],
            }] + children
            out = {
                '@context': 'https://w3id.org/ro/crate/1.1/context',
                '@graph': graph,
                'meta': {
                    'truncated': bool(total > len(children)),
                    'total_children': total,
                    'shown': len(children),
                }
            }
            return jsonify(out), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.get('/files')
    def api_files():
        """Stream a file's bytes with basic security and size limits.
        Query: provider_id, root_id, path
        Limits: default max 32MB unless SCIDK_FILE_MAX_BYTES is set.
        """
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        file_path = (request.args.get('path') or '').strip()
        if not file_path:
            return jsonify({'error': 'missing path'}), 400
        try:
            from pathlib import Path as _P
            base = _P(root_id).resolve()
            target = _P(file_path).resolve()
            # Enforce that target is within base
            try:
                target.relative_to(base)
            except Exception:
                return jsonify({'error': 'path outside root'}), 400
            if not target.exists() or not target.is_file():
                return jsonify({'error': 'not a file'}), 400
            st = target.stat()
            max_bytes = int(os.environ.get('SCIDK_FILE_MAX_BYTES', '33554432'))  # 32MB
            if st.st_size > max_bytes:
                return jsonify({'error': 'file too large', 'limit': max_bytes, 'size': int(st.st_size)}), 413
            import mimetypes as _mt
            mime = _mt.guess_type(target.name)[0] or 'application/octet-stream'
            from flask import send_file as _send_file
            return _send_file(str(target), mimetype=mime, as_attachment=False, download_name=target.name)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api.post('/research_objects')
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
            from pathlib import Path as _P
            base = _P(root_id).resolve()
            target = _P(sel_path).resolve()
            try:
                target.relative_to(base)
            except Exception:
                return jsonify({'error': 'path outside root'}), 400
            if not target.exists() or not target.is_dir():
                return jsonify({'error': 'path not a directory'}), 400
            # Build file checksum list by matching datasets whose path is under target
            g = app.extensions['scidk']['graph']
            file_checksums = []
            folder_paths = set()
            for ds in g.list_datasets():
                try:
                    p = _P(ds.get('path') or '').resolve()
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

    @api.get('/research_objects')
    def api_research_objects_list():
        g = app.extensions['scidk']['graph']
        return jsonify(g.list_research_objects()), 200

    @api.get('/research_objects/<ro_id>')
    def api_research_objects_get(ro_id):
        g = app.extensions['scidk']['graph']
        ro = g.get_research_object(ro_id)
        if not ro:
            return jsonify({'error': 'not found'}), 404
        # expand lightweight links counts
        files = len(g.ro_files.get(ro_id, set()))
        folders = len(g.ro_folders.get(ro_id, set()))
        out = ro.copy()
        out.update({'file_count': files, 'folder_count': folders})
        return jsonify(out), 200

    app.register_blueprint(api)

    # UI routes
    ui = Blueprint('ui', __name__)

    @ui.get('/')
    def index():
        datasets = app.extensions['scidk']['graph'].list_datasets()
        # Build lightweight summaries for the landing page
        by_ext = {}
        interp_types = set()
        for d in datasets:
            by_ext[d.get('extension') or ''] = by_ext.get(d.get('extension') or '', 0) + 1
            for k in (d.get('interpretations') or {}).keys():
                interp_types.add(k)
        schema_summary = app.extensions['scidk']['graph'].schema_summary()
        telemetry = app.extensions['scidk'].get('telemetry', {})
        directories = list(app.extensions['scidk'].get('directories', {}).values())
        directories.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        scans = list(app.extensions['scidk'].get('scans', {}).values())
        scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        return render_template('index.html', datasets=datasets, by_ext=by_ext, schema_summary=schema_summary, telemetry=telemetry, directories=directories, scans=scans)

    @ui.get('/chat')
    def chat():
        return render_template('chat.html')

    @ui.get('/map')
    def map_page():
        schema_summary = app.extensions['scidk']['graph'].schema_summary()
        return render_template('map.html', schema_summary=schema_summary)

    @ui.get('/datasets')
    def datasets():
        all_datasets = app.extensions['scidk']['graph'].list_datasets()
        scan_id = (request.args.get('scan_id') or '').strip()
        selected_scan = None
        if scan_id:
            selected_scan = app.extensions['scidk'].get('scans', {}).get(scan_id)
        if selected_scan:
            checks = set(selected_scan.get('checksums') or [])
            datasets = [d for d in all_datasets if d.get('checksum') in checks]
        else:
            datasets = all_datasets
        directories = list(app.extensions['scidk'].get('directories', {}).values())
        directories.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        recent_scans = list(app.extensions['scidk'].get('scans', {}).values())
        recent_scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        # Show only the most recent N scans for dropdown
        N = 20
        recent_scans = recent_scans[:N]
        # files viewer mode: allow query param override, else env, else classic
        files_viewer = (request.args.get('files_viewer') or os.environ.get('SCIDK_FILES_VIEWER') or 'classic').strip()
        return render_template('datasets.html', datasets=datasets, directories=directories, recent_scans=recent_scans, selected_scan=selected_scan, files_viewer=files_viewer)

    @ui.get('/datasets/<dataset_id>')
    def dataset_detail(dataset_id):
        item = app.extensions['scidk']['graph'].get_dataset(dataset_id)
        if not item:
            return render_template('dataset_detail.html', dataset=None), 404
        return render_template('dataset_detail.html', dataset=item)

    @ui.get('/workbook/<dataset_id>')
    def workbook_view(dataset_id):
        # Simple XLSX viewer: list sheets and preview first rows
        item = app.extensions['scidk']['graph'].get_dataset(dataset_id)
        if not item:
            return render_template('workbook.html', dataset=None, error="Dataset not found"), 404
        from pathlib import Path as _P
        file_path = _P(item['path'])
        if (item.get('extension') or '').lower() not in ['.xlsx', '.xlsm']:
            return render_template('workbook.html', dataset=item, error="Not an Excel workbook (.xlsx/.xlsm)"), 400
        try:
            from openpyxl import load_workbook
            wb = load_workbook(filename=str(file_path), read_only=True, data_only=True)
            sheetnames = wb.sheetnames
            previews = []
            max_rows = 20
            max_cols = 20
            for name in sheetnames:
                ws = wb[name]
                rows = []
                for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True), start=1):
                    rows.append(list(row))
                previews.append({'name': name, 'rows': rows})
            wb.close()
            return render_template('workbook.html', dataset=item, sheetnames=sheetnames, previews=previews, error=None)
        except Exception as e:
            return render_template('workbook.html', dataset=item, sheetnames=[], previews=[], error=str(e)), 500

    @ui.get('/plugins')
    def plugins():
        # Placeholder: no dynamic plugins yet. Show counts from registry for context.
        reg = app.extensions['scidk']['registry']
        ext_count = len(reg.by_extension)
        interp_count = len(reg.by_id)
        return render_template('plugins.html', ext_count=ext_count, interp_count=interp_count)

    @ui.get('/interpreters')
    def interpreters():
        # List registry mappings and selection rules
        reg = app.extensions['scidk']['registry']
        mappings = {ext: [getattr(i, 'id', 'unknown') for i in interps] for ext, interps in reg.by_extension.items()}
        rules = list(reg.rules.rules)
        return render_template('extensions.html', mappings=mappings, rules=rules)

    # Backward-compatible route
    @ui.get('/extensions')
    def extensions_legacy():
        return redirect(url_for('ui.interpreters'))

    @ui.get('/rocrate_view')
    def rocrate_view():
        # Lightweight wrapper page to preview RO-Crate JSON-LD and prepare for embedding Crate-O
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        sel_path = (request.args.get('path') or root_id).strip()
        try:
            from urllib.parse import urlencode
            qs = urlencode({'provider_id': prov_id, 'root_id': root_id, 'path': sel_path})
        except Exception:
            qs = f"provider_id={prov_id}&root_id={root_id}&path={sel_path}"
        metadata_url = '/api/rocrate?' + qs
        embed_mode = (os.environ.get('SCIDK_ROCRATE_EMBED') or 'json').strip()
        return render_template('rocrate_view.html', metadata_url=metadata_url, embed_mode=embed_mode, prov_id=prov_id, root_id=root_id, path=sel_path)

    @ui.get('/settings')
    def settings():
        # Basic settings from environment and current in-memory sizes
        datasets = app.extensions['scidk']['graph'].list_datasets()
        reg = app.extensions['scidk']['registry']
        info = {
            'host': os.environ.get('SCIDK_HOST', '127.0.0.1'),
            'port': os.environ.get('SCIDK_PORT', '5000'),
            'debug': os.environ.get('SCIDK_DEBUG', '1'),
            'dataset_count': len(datasets),
            'interpreter_count': len(reg.by_id),
        }
        # Provide interpreter mappings and rules, and plugin summary counts for the Set page sections
        mappings = {ext: [getattr(i, 'id', 'unknown') for i in interps] for ext, interps in reg.by_extension.items()}
        rules = list(reg.rules.rules)
        ext_count = len(reg.by_extension)
        interp_count = len(reg.by_id)
        # Feature flag for rclone mounts UI
        rclone_mounts_feature = _feature_rclone_mounts()
        return render_template('settings.html', info=info, mappings=mappings, rules=rules, ext_count=ext_count, interp_count=interp_count, rclone_mounts_feature=rclone_mounts_feature)

    @ui.post('/scan')
    def ui_scan():
        path = request.form.get('path') or os.getcwd()
        recursive = request.form.get('recursive') == 'on'
        import time, hashlib
        # Pre-scan snapshot
        before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
        started = time.time()
        count = fs.scan_directory(Path(path), recursive=recursive)
        ended = time.time()
        duration = ended - started
        after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
        new_checksums = sorted(list(after - before))
        by_ext = {}
        ext_map = {ds.get('checksum'): ds.get('extension') or '' for ds in app.extensions['scidk']['graph'].list_datasets()}
        for ch in new_checksums:
            ext = ext_map.get(ch, '')
            by_ext[ext] = by_ext.get(ext, 0) + 1
        sid_src = f"{path}|{started}"
        scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
        scan = {
            'id': scan_id,
            'path': str(path),
            'recursive': bool(recursive),
            'started': started,
            'ended': ended,
            'duration_sec': duration,
            'file_count': int(count),
            'checksums': new_checksums,
            'by_ext': by_ext,
            'source': getattr(fs, 'last_scan_source', 'python'),
            'errors': [],
        }
        scans = app.extensions['scidk'].setdefault('scans', {})
        scans[scan_id] = scan
        telem = app.extensions['scidk'].setdefault('telemetry', {})
        telem['last_scan'] = {
            'path': str(path),
            'recursive': bool(recursive),
            'scanned': int(count),
            'started': started,
            'ended': ended,
            'duration_sec': duration,
        }
        # Track scanned directories here as well
        dirs = app.extensions['scidk'].setdefault('directories', {})
        drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': []})
        drec.update({'recursive': bool(recursive), 'scanned': int(count), 'last_scanned': ended})
        drec.setdefault('scan_ids', []).append(scan_id)
        return redirect(url_for('ui.datasets', scan_id=scan_id))

    app.register_blueprint(ui)

    return app


def main():
    app = create_app()
    # Read host/port from env for convenience
    host = os.environ.get('SCIDK_HOST', '127.0.0.1')
    port = int(os.environ.get('SCIDK_PORT', '5000'))
    debug = os.environ.get('SCIDK_DEBUG', '1') == '1'
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
