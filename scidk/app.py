"""SciDK Flask application factory.

This module provides the create_app() function that initializes the Flask application
with all necessary extensions, services, and route blueprints.

Most initialization logic has been extracted to separate modules in scidk/core/
and scidk/services/ to keep this file lean and maintainable.
"""

from flask import Flask
from pathlib import Path
import os

# Core components
from .core.filesystem import FilesystemManager
from .core.registry import InterpreterRegistry
from .core.logging_config import setup_logging
from .interpreters import register_all as register_interpreters

# Initialization modules (extracted from app.py)
from .core.channel_config import apply_channel_defaults
from .core.neo4j_config import create_graph_backend
from .core.interpreter_enablement import compute_enabled_interpreters
from .core.providers_init import initialize_fs_providers
from .core.telemetry_loader import load_last_scan_from_sqlite
from .core.rclone_settings import load_rclone_interpretation_settings
from .core.rclone_mounts_loader import rehydrate_rclone_mounts


def create_app():
    """Create and configure the Flask application.

    Returns:
        Flask: Configured Flask application instance with scidk extensions
    """
    # Setup logging first to capture all startup activity
    log_level = os.environ.get('SCIDK_LOG_LEVEL', 'INFO')
    setup_logging(log_level=log_level)

    # Apply channel-based defaults before reading env-driven config
    apply_channel_defaults()

    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")

    # Feature: selective dry-run UI flag (dev default)
    try:
        ch = (os.environ.get('SCIDK_CHANNEL') or 'stable').strip().lower()
        flag_env = (os.environ.get('SCIDK_FEATURE_SELECTIVE_DRYRUN') or '').strip().lower()
        flag = flag_env in ('1', 'true', 'yes', 'y', 'on')
        if flag_env == '' and ch == 'dev':
            flag = True
        app.config['feature.selectiveDryRun'] = bool(flag)
    except Exception:
        app.config['feature.selectiveDryRun'] = False

    # Auto-migrate SQLite schema on boot (best effort)
    try:
        from .core import migrations as _migs
        _migs.migrate()
    except Exception:
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

    # Core singletons: graph backend (Neo4j or InMemory)
    graph = create_graph_backend(app)

    # Interpreter registry
    registry = InterpreterRegistry()
    register_interpreters(registry)

    # Compute effective interpreter enablement (CLI > settings > defaults)
    app.extensions = getattr(app, 'extensions', {})
    app.extensions['scidk'] = {}
    enabled_set, source, settings = compute_enabled_interpreters(registry, app.extensions)

    # FilesystemManager
    fs = FilesystemManager(graph=graph, registry=registry)

    # Initialize filesystem providers (local_fs, mounted_fs, rclone)
    fs_providers = initialize_fs_providers(app)

    # Store refs on app for easy access in routes
    app.extensions['scidk'] = {
        'graph': graph,
        'registry': registry,
        'fs': fs,
        'providers': fs_providers,
        'interpreters': {'effective_enabled': enabled_set, 'source': source},
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
        # rclone mounts runtime registry
        'rclone_mounts': {},  # id/name -> { id, remote, subpath, path, read_only, started_at, pid, log_file }
        'settings': settings,
    }

    # Hydrate telemetry.last_scan from SQLite settings on startup
    last_scan = load_last_scan_from_sqlite()
    if last_scan:
        app.extensions['scidk']['telemetry']['last_scan'] = last_scan

    # Hydrate rclone interpretation settings (suggest mount threshold and batch size)
    load_rclone_interpretation_settings(app)

    # Rehydrate rclone mounts metadata from SQLite on startup (no process attached)
    mounts = rehydrate_rclone_mounts()
    app.extensions['scidk']['rclone_mounts'].update(mounts)

    # Feature flags for file indexing
    _ff_index = (os.environ.get('SCIDK_FEATURE_FILE_INDEX') or '').strip().lower() in (
        '1', 'true', 'yes', 'y', 'on'
    )

    # Register all blueprints from web.routes package
    from .web.routes import register_blueprints
    register_blueprints(app)

    # Initialize authentication middleware
    from .web.auth_middleware import init_auth_middleware
    init_auth_middleware(app)

    # Load plugins after all core initialization is complete
    from .core.plugin_loader import PluginLoader, get_all_plugin_states
    plugin_loader = PluginLoader()
    plugin_states = get_all_plugin_states()

    # Get list of enabled plugins from database
    discovered_plugins = plugin_loader.discover_plugins()
    enabled_plugins = [p for p in discovered_plugins if plugin_states.get(p, True)]

    # Load all plugins
    plugin_loader.load_all_plugins(app, enabled_plugins=enabled_plugins)

    # Store plugin loader in app extensions for access in routes
    app.extensions['scidk']['plugins'] = {
        'loader': plugin_loader,
        'loaded': plugin_loader.list_plugins(),
        'failed': plugin_loader.list_failed_plugins()
    }

    return app


def main():
    """Run the Flask development server."""
    app = create_app()
    # Read host/port from env for convenience
    host = os.environ.get('SCIDK_HOST', '127.0.0.1')
    port = int(os.environ.get('SCIDK_PORT', '5000'))
    debug = os.environ.get('SCIDK_DEBUG', '1') == '1'
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
