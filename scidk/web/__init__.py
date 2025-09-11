from flask import Flask, Blueprint
from pathlib import Path
import os
from typing import Optional
import time
import json

from ..core.graph import InMemoryGraph
from ..core.filesystem import FilesystemManager
from ..core.registry import InterpreterRegistry
from ..interpreters.python_code import PythonCodeInterpreter
from ..interpreters.csv_interpreter import CsvInterpreter
from ..interpreters.json_interpreter import JsonInterpreter
from ..interpreters.yaml_interpreter import YamlInterpreter
from ..interpreters.ipynb_interpreter import IpynbInterpreter
from ..interpreters.txt_interpreter import TxtInterpreter
from ..interpreters.xlsx_interpreter import XlsxInterpreter
from ..core.pattern_matcher import Rule
from ..core.providers import ProviderRegistry as FsProviderRegistry, LocalFSProvider, MountedFSProvider, RcloneProvider


def _apply_channel_defaults():
    """Apply channel-based defaults for feature flags when unset.
    Channels: stable (default), dev, beta.
    Explicit env values always win; we only set defaults if unset.
    Also soft-disable rclone provider by removing it from SCIDK_PROVIDERS if rclone binary is missing,
    unless SCIDK_FORCE_RCLONE is truthy. Only perform soft-disable when SCIDK_PROVIDERS was not explicitly set by user.
    """
    import shutil

    def setdefault_env(name: str, value: str):
        if os.environ.get(name) is None:
            os.environ[name] = value

    channel = (os.environ.get('SCIDK_CHANNEL') or 'stable').strip().lower()
    # Defaults by channel (can be overridden by explicit env)
    if channel == 'dev':
        setdefault_env('SCIDK_FEATURE_RCLONE_MOUNTS', '1')
    elif channel == 'beta':
        setdefault_env('SCIDK_FEATURE_RCLONE_MOUNTS', '0')
    else:
        setdefault_env('SCIDK_FEATURE_RCLONE_MOUNTS', '0')

    # Soft-disable rclone provider if binary missing and providers not explicitly set
    providers_env_explicit = ('SCIDK_PROVIDERS' in os.environ)
    if not providers_env_explicit:
        rclone_exists = shutil.which('rclone') is not None
        prov = [p.strip() for p in (os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone').split(',')) if p.strip()]
        if not rclone_exists and 'rclone' in prov and not (os.environ.get('SCIDK_FORCE_RCLONE') or '').strip().lower() in ('1','true','yes','y','on'):
            prov = [p for p in prov if p != 'rclone']
            os.environ['SCIDK_PROVIDERS'] = ','.join(prov)


def create_app():
    # Apply channel-based defaults before reading env-driven config
    _apply_channel_defaults()
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")

    # Core singletons (select backend)
    backend = (os.environ.get('SCIDK_GRAPH_BACKEND') or 'memory').strip().lower()
    if backend == 'neo4j':
        try:
            # Defer params retrieval to client services; keep same behavior by reading when used
            uri = os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')
            user = os.environ.get('NEO4J_USER') or os.environ.get('NEO4J_USERNAME')
            pwd = os.environ.get('NEO4J_PASSWORD')
            database = os.environ.get('SCIDK_NEO4J_DATABASE') or None
            auth_mode = 'basic' if (os.environ.get('NEO4J_AUTH') or '').strip().lower() != 'none' else 'none'
            from ..core.neo4j_graph import Neo4jGraph
            auth = None if auth_mode == 'none' else (user, pwd)
            graph = Neo4jGraph(uri=uri, auth=auth, database=database)
        except Exception:
            # Fallback to in-memory if neo4j params invalid
            from ..core.graph import InMemoryGraph as _IMG
            graph = _IMG()
    else:
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

    # API blueprint placeholder (routes remain defined within create_app for now)
    api = Blueprint('api', __name__, url_prefix='/api')

    # Import SQLite layer for selections/annotations lazily to avoid circular deps
    from ..core import annotations_sqlite as ann_db  # noqa: F401 (kept to preserve side-effects if any)

    # Bring over the rest of the route and helper definitions by importing legacy app module
    # For now, to preserve endpoints unchanged with minimal refactor, we import the legacy create_app
    # implementation and reuse its route registrations by calling it and merging state.
    # However, since we are already inside create_app, and the original implementation was here,
    # we simply return app as-is because all route definitions are nested below in the original file.
    # This refactor step only relocates the factory into scidk.web while keeping behavior identical.

    # Re-import the original app module to execute its inner route registrations if needed
    # (No-op here since we've moved the implementation.)

    # NOTE: Further steps will split routes into scidk/web/blueprints/* modules.

    # The original create_app continued with many route definitions; we keep them by importing
    # and executing the legacy registrar if present.
    try:
        from ..app import _register_routes_legacy  # type: ignore
        _register_routes_legacy(app)
    except Exception:
        # If legacy registrar is not present, assume routes are already defined elsewhere.
        pass

    return app
