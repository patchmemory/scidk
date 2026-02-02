from flask import Flask, Blueprint, jsonify, request, render_template, redirect, url_for
from pathlib import Path
import os
from typing import Optional
import time
import json

from .core.graph import InMemoryGraph
from .core.filesystem import FilesystemManager
from .core.registry import InterpreterRegistry
from .interpreters import register_all as register_interpreters
from .core.providers import ProviderRegistry as FsProviderRegistry, LocalFSProvider, MountedFSProvider, RcloneProvider
from .web.helpers import commit_to_neo4j_batched


def _apply_channel_defaults():
    """Apply channel-based defaults for feature flags when unset.
    Channels: stable (default), dev, beta.
    Explicit env values always win; we only set defaults if unset.
    Also soft-disable rclone provider by removing it from SCIDK_PROVIDERS if rclone binary is missing,
    unless SCIDK_FORCE_RCLONE is truthy. Only perform soft-disable when SCIDK_PROVIDERS was not explicitly set by user.
    """
    import shutil
    ch = (os.environ.get('SCIDK_CHANNEL') or 'stable').strip().lower()
    had_prov_env = 'SCIDK_PROVIDERS' in os.environ
    def setdefault_env(name: str, value: str):
        if os.environ.get(name) is None:
            os.environ[name] = value
    if ch in ('dev', 'beta'):
        # Providers default: include rclone
        if os.environ.get('SCIDK_PROVIDERS') is None:
            os.environ['SCIDK_PROVIDERS'] = 'local_fs,mounted_fs,rclone'
        # Mounts UI
        setdefault_env('SCIDK_RCLONE_MOUNTS', '1')
        # Files viewer mode
        setdefault_env('SCIDK_FILES_VIEWER', 'rocrate')
        # File index work in progress
        setdefault_env('SCIDK_FEATURE_FILE_INDEX', '1')
    # Soft rclone detection: remove if missing and not forced, but only when we set providers implicitly
    if not had_prov_env:
        prov_env = os.environ.get('SCIDK_PROVIDERS')
        if prov_env:
            prov_list = [p.strip() for p in prov_env.split(',') if p.strip()]
            if 'rclone' in prov_list and not shutil.which('rclone'):
                force = (os.environ.get('SCIDK_FORCE_RCLONE') or '').strip().lower() in ('1','true','yes','y','on')
                if not force:
                    prov_list = [p for p in prov_list if p != 'rclone']
                    os.environ['SCIDK_PROVIDERS'] = ','.join(prov_list)
    # Record effective channel for UI/debug
    os.environ.setdefault('SCIDK_CHANNEL', ch or 'stable')
    # Default: commit to graph should read from index unless explicitly disabled
    if os.environ.get('SCIDK_COMMIT_FROM_INDEX') is None:
        os.environ['SCIDK_COMMIT_FROM_INDEX'] = '1'



def create_app():
    # Apply channel-based defaults before reading env-driven config
    _apply_channel_defaults()
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")
    # Feature: selective dry-run UI flag (dev default)
    try:
        ch = (os.environ.get('SCIDK_CHANNEL') or 'stable').strip().lower()
        flag_env = (os.environ.get('SCIDK_FEATURE_SELECTIVE_DRYRUN') or '').strip().lower()
        flag = flag_env in ('1','true','yes','y','on')
        if flag_env == '' and ch == 'dev':
            flag = True
        app.config['feature.selectiveDryRun'] = bool(flag)
    except Exception:
        app.config['feature.selectiveDryRun'] = False

    # Auto-migrate SQLite schema on boot (best effort)
    try:
        from .core import migrations as _migs
        _migs.migrate()
    except Exception as _e:
        # Defer reporting to /api/health if needed via app.extensions
        pass

    # State backend toggle (sqlite|memory) for app registries (reads)
    try:
        state_backend = (os.environ.get('SCIDK_STATE_BACKEND') or 'sqlite').strip().lower()
        if state_backend not in ('sqlite', 'memory'):
            state_backend = 'sqlite'
    except Exception:
        state_backend = 'sqlite'
    app.config['state.backend'] = state_backend

    # Core singletons (select backend)
    backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()
    if backend == 'neo4j':
        try:
            uri, user, pwd, database, auth_mode = _get_neo4j_params()
            from .core.neo4j_graph import Neo4jGraph
            auth = None if auth_mode == 'none' else (user, pwd)
            graph = Neo4jGraph(uri=uri, auth=auth, database=database)
        except Exception:
            # Fallback to in-memory if neo4j params invalid
            from .core.graph import InMemoryGraph as _IMG
            graph = _IMG()
    else:
        graph = InMemoryGraph()
    registry = InterpreterRegistry()
    # Load persisted interpreter toggle settings (optional)
    try:
        from .core.settings import InterpreterSettings
        settings = InterpreterSettings(os.environ.get('SCIDK_SETTINGS_DB', 'scidk_settings.db'))
        enabled = settings.load_enabled_interpreters()
        if enabled:
            registry.enabled_interpreters = set(enabled)
    except Exception:
        settings = None

    # Register interpreters with extensions and rules
    register_interpreters(registry)

    # Compute effective interpreter enablement (CLI envs > global settings > defaults)
    testing_env = bool(os.environ.get('PYTEST_CURRENT_TEST')) or bool(os.environ.get('SCIDK_DISABLE_SETTINGS'))
    try:
        from .core.settings import InterpreterSettings
        settings = None if testing_env else InterpreterSettings(db_path=str(Path(os.getcwd()) / 'scidk_settings.db'))
    except Exception:
        settings = None
    # Defaults from interpreter attributes (fallback True)
    all_ids = list(registry.by_id.keys())
    default_enabled_ids = set([iid for iid in all_ids if bool(getattr(registry.by_id[iid], 'default_enabled', True))])
    # CLI overrides via env
    # CLI overrides via env (case-insensitive); ignore unknown ids to avoid surprises
    en_raw = [s.strip() for s in (os.environ.get('SCIDK_ENABLE_INTERPRETERS') or '').split(',') if s.strip()]
    dis_raw = [s.strip() for s in (os.environ.get('SCIDK_DISABLE_INTERPRETERS') or '').split(',') if s.strip()]
    # Normalize to lowercase (registry ids are lowercase)
    en_list = [s.lower() for s in en_raw]
    dis_list = [s.lower() for s in dis_raw]
    source = 'default'
    if en_list or dis_list:
        known_ids = set(all_ids)
        unknown_en = [x for x in en_list if x not in known_ids]
        unknown_dis = [x for x in dis_list if x not in known_ids]
        # Start from defaults; remove DISABLE; add ENABLE; ENABLE wins on conflicts
        enabled_set = set(default_enabled_ids)
        for d in dis_list:
            if d in known_ids:
                enabled_set.discard(d)
        for e in en_list:
            if e in known_ids:
                enabled_set.add(e)
        source = 'cli'
        # Do NOT persist CLI-derived sets to settings to avoid masking user intentions
        try:
            _ist = app.extensions.setdefault('scidk', {}).setdefault('interpreters', {})
            _ist['unknown_env'] = {'enable': unknown_en, 'disable': unknown_dis}
        except Exception:
            pass
    else:
        # Load global saved set if any
        loaded = set()
        try:
            if settings:
                loaded = set(settings.load_enabled_interpreters())
        except Exception:
            loaded = set()
        if loaded:
            enabled_set = set(loaded)
            source = 'global'
        else:
            enabled_set = set(default_enabled_ids)
            source = 'default'
    # Store effective on app
    _interp_state = {'effective_enabled': enabled_set, 'source': source}
    # Apply effective enabled set to registry for selection logic
    try:
        registry.enabled_interpreters = set(enabled_set)
    except Exception:
        pass

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
        'interpreters': _interp_state,
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
        'settings': settings,
    }

    # Hydrate telemetry.last_scan from SQLite settings on startup (best-effort)
    try:
        from .core import path_index_sqlite as pix
        from .core import migrations as _migs
        import json as _json
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            row = cur.execute("SELECT value FROM settings WHERE key = ?", ("telemetry.last_scan",)).fetchone()
            if row and row[0]:
                try:
                    last_scan = _json.loads(row[0])
                    app.extensions.setdefault('scidk', {}).setdefault('telemetry', {})['last_scan'] = last_scan
                except Exception:
                    pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass

    # Hydrate rclone interpretation settings (suggest mount threshold and batch size)
    try:
        def _env_int(name: str, dflt: int) -> int:
            try:
                v = os.environ.get(name)
                return int(v) if v is not None and v != '' else dflt
            except Exception:
                return dflt
        suggest_dflt = _env_int('SCIDK_RCLONE_INTERPRET_SUGGEST_MOUNT', 400)
        max_batch_dflt = _env_int('SCIDK_RCLONE_INTERPRET_MAX_FILES', 1000)
        max_batch_dflt = min(max(100, max_batch_dflt), 2000)
        from .core import path_index_sqlite as pix
        from .core import migrations as _migs
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            def _get_setting_int(key: str, dflt: int) -> int:
                row = cur.execute("SELECT value FROM settings WHERE key= ?", (key,)).fetchone()
                if row and row[0] not in (None, ''):
                    try:
                        return int(row[0])
                    except Exception:
                        return dflt
                return dflt
            suggest_mount_threshold = _get_setting_int('rclone.interpret.suggest_mount_threshold', suggest_dflt)
            max_files_per_batch = _get_setting_int('rclone.interpret.max_files_per_batch', max_batch_dflt)
            max_files_per_batch = min(max(100, int(max_files_per_batch)), 2000)
            app.config['rclone.interpret.suggest_mount_threshold'] = int(suggest_mount_threshold)
            app.config['rclone.interpret.max_files_per_batch'] = int(max_files_per_batch)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        # Defaults if hydration fails
        app.config.setdefault('rclone.interpret.suggest_mount_threshold', 400)
        app.config.setdefault('rclone.interpret.max_files_per_batch', 1000)

    # Feature flag for rclone mount manager (define before first use)
    def _feature_rclone_mounts() -> bool:
        val = (os.environ.get('SCIDK_RCLONE_MOUNTS') or os.environ.get('SCIDK_FEATURE_RCLONE_MOUNTS') or '').strip().lower()
        return val in ('1', 'true', 'yes', 'y', 'on')

    # Rehydrate rclone mounts metadata from SQLite on startup (no process attached)
    if _feature_rclone_mounts():
        try:
            from .core import path_index_sqlite as pix
            from .core import migrations as _migs
            import json as _json
            conn = pix.connect()
            try:
                _migs.migrate(conn)
                cur = conn.cursor()
                cur.execute("SELECT id, provider, root, created, status, extra_json FROM provider_mounts WHERE provider='rclone'")
                rows = cur.fetchall() or []
                rm = app.extensions['scidk'].setdefault('rclone_mounts', {})
                for (mid, provider, remote, created, status_persisted, extra) in rows:
                    try:
                        extra_obj = _json.loads(extra) if extra else {}
                    except Exception:
                        extra_obj = {}
                    rm[mid] = {
                        'id': mid,
                        'name': mid,
                        'remote': remote,
                        'subpath': extra_obj.get('subpath'),
                        'path': extra_obj.get('path'),
                        'read_only': extra_obj.get('read_only'),
                        'started_at': created,
                        'process': None,
                        'pid': None,
                        'log_file': extra_obj.get('log_file'),
                    }
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception:
            pass

    # API routes
    api = Blueprint('api', __name__, url_prefix='/api')

    # Import SQLite layer for selections/annotations lazily to avoid circular deps
    from .core import annotations_sqlite as ann_db


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
        """Legacy builder from in-memory datasets."""
        try:
            from .services.commit_service import CommitService
            return CommitService().build_rows_legacy_from_datasets(scan, ds_map)
        except Exception:
            # Fallback to empty on unexpected import/runtime error
            return [], []

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
            from .services.neo4j_client import Neo4jClient
            client = Neo4jClient(uri, user, pwd, database, auth_mode).connect()
            try:
                client.ensure_constraints()
                wres = client.write_scan(rows, folder_rows, scan)
                result['written_files'] = wres.get('written_files', 0)
                result['written_folders'] = wres.get('written_folders', 0)
                vres = client.verify(scan.get('id'))
                result.update(vres)
            finally:
                client.close()
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

        from .core.path_utils import parse_remote_path, parent_remote_path
        from pathlib import Path as _P

        folder_info = {}
        children_files = {}

        def ensure_complete_parent_chain(path_str: str):
            """Ensure all parent folders exist in folder_info for any given path"""
            if not path_str or path_str in folder_info:
                return

            info = parse_remote_path(path_str)
            if info.get('is_remote'):
                parent = parent_remote_path(path_str)
                name = (info.get('parts')[-1] if info.get('parts') else info.get('remote_name') or path_str)
            else:
                try:
                    p = _P(path_str)
                    parent = str(p.parent)
                    name = p.name or path_str
                except Exception:
                    parent = ''
                    name = path_str

            folder_info[path_str] = {
                'path': path_str,
                'name': name,
                'parent': parent,
            }

            if parent and parent != path_str:
                ensure_complete_parent_chain(parent)

        # Seed scan base path (stable roots even on empty scans)
        try:
            base_path = s.get('path') or ''
            if base_path:
                ensure_complete_parent_chain(base_path)
        except Exception:
            pass

        # Process files and ensure their parent chains exist
        for ch in checksums:
            d = ds_map.get(ch)
            if not d:
                continue
            file_path = d.get('path')
            if not file_path:
                continue

            info = parse_remote_path(file_path)
            if info.get('is_remote'):
                parent = parent_remote_path(file_path)
                filename = (info.get('parts')[-1] if info.get('parts') else info.get('remote_name') or file_path)
            else:
                try:
                    p = _P(file_path)
                    parent = str(p.parent)
                    filename = p.name or file_path
                except Exception:
                    parent = ''
                    filename = file_path

            file_entry = {
                'id': d.get('id'),
                'path': file_path,
                'filename': d.get('filename') or filename,
                'extension': d.get('extension'),
                'size_bytes': int(d.get('size_bytes') or 0),
                'modified': float(d.get('modified') or 0),
                'mime_type': d.get('mime_type'),
                'checksum': d.get('checksum'),
            }
            children_files.setdefault(parent, []).append(file_entry)

            if parent:
                ensure_complete_parent_chain(parent)

        # Process explicitly recorded folders
        for f in (s.get('folders') or []):
            path = f.get('path')
            if path:
                ensure_complete_parent_chain(path)

        # Build children_folders map
        children_folders = {}
        for fpath, info in folder_info.items():
            par = info.get('parent')
            if par and par in folder_info:
                children_folders.setdefault(par, []).append(fpath)

        # Find actual roots
        roots = sorted([fp for fp, info in folder_info.items()
                        if not info.get('parent') or info.get('parent') not in folder_info])

        # Prefer scan base as visible root and drop its ancestors
        try:
            base_path = s.get('path') or ''
            if base_path and base_path in folder_info:
                if base_path not in roots:
                    roots.append(base_path)
                def _is_ancestor(candidate: str, child: str) -> bool:
                    if not candidate or candidate == child:
                        return False
                    cinf = parse_remote_path(candidate)
                    chinf = parse_remote_path(child)
                    if chinf.get('is_remote') and cinf.get('is_remote'):
                        return child.startswith(candidate.rstrip('/') + '/')
                    try:
                        return str(_P(child)).startswith(str(_P(candidate)) + '/')
                    except Exception:
                        return False
                roots = [r for r in roots if not _is_ancestor(r, base_path) or r == base_path]
                roots = sorted(list(dict.fromkeys(roots)))
        except Exception:
            pass

        # Sort children deterministically
        for k in list(children_folders.keys()):
            children_folders[k].sort(key=lambda p: folder_info.get(p, {}).get('name', '').lower())
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

    # Feature flags for file indexing
    _ff_index = (os.environ.get('SCIDK_FEATURE_FILE_INDEX') or '').strip().lower() in ('1','true','yes','y','on')


    # Register all blueprints from web.routes package
    from .web.routes import register_blueprints
    register_blueprints(app)

    # Note: Old UI routes (256 lines) have been moved to scidk/web/routes/ui.py

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
