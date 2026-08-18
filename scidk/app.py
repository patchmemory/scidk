"""SciDK Flask application factory.

This module provides the create_app() function that initializes the Flask application
with all necessary extensions, services, and route blueprints.

Most initialization logic has been extracted to separate modules in scidk/core/
and scidk/services/ to keep this file lean and maintainable.
"""
from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from pathlib import Path
import os
from flasgger import Swagger
from werkzeug.middleware.proxy_fix import ProxyFix

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


def _resolve_settings_db_path(app) -> str:
    """Resolve the scidk_settings.db path the same way every consumer does.

    Precedence: app.config (set by tests) > SCIDK_SETTINGS_DB env > cwd default.
    Route modules read this from ``app.config``; ``react_loop`` reads the env var
    directly, so both are consulted here to keep them pointing at one file.
    """
    return (
        app.config.get('SCIDK_SETTINGS_DB')
        or os.environ.get('SCIDK_SETTINGS_DB')
        or 'scidk_settings.db'
    )


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

    from datetime import datetime, timezone
    app.jinja_env.globals['now'] = lambda: datetime.now(timezone.utc)

    # Enable ProxyFix for reverse proxy support (nginx, Apache, etc.)
    # This ensures Flask correctly handles X-Forwarded-* headers
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,      # Trust 1 proxy for X-Forwarded-For
        x_proto=1,    # Trust 1 proxy for X-Forwarded-Proto
        x_host=1,     # Trust 1 proxy for X-Forwarded-Host
        x_prefix=1    # Trust 1 proxy for X-Forwarded-Prefix
    )

    # Initialize Swagger for API documentation
    swagger_template = {
        'info': {
            'title': 'SciDK API',
            'version': '1.0.0',
            'description': 'RESTful API for SciDK scientific data management and knowledge graph operations',
            'contact': {
                'name': 'SciDK Team',
                'url': 'https://github.com/scidk/scidk'
            }
        },
        'securityDefinitions': {
            'Bearer': {
                'type': 'apiKey',
                'name': 'Authorization',
                'in': 'header',
                'description': 'JWT Authorization header using the Bearer scheme. Example: "Authorization: Bearer {token}"'
            }
        },
        'security': [
            {'Bearer': []}
        ]
    }
    swagger_config = {
        'headers': [],
        'specs': [
            {
                'endpoint': 'apispec',
                'route': '/apispec.json',
                'rule_filter': lambda rule: True,
                'model_filter': lambda tag: True,
            }
        ],
        'static_url_path': '/flasgger_static',
        'swagger_ui': True,
        'specs_route': '/api/docs'
    }
    Swagger(app, template=swagger_template, config=swagger_config)

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

    # Create the Schema Intelligence tables in scidk_settings.db if missing.
    # These are NOT part of migrations.py (that module owns files.db) — the DDL
    # lives in services/schema_intelligence.py. Without this, a clean deploy has
    # no usage_event / property_ranking tables and the whole SI layer silently
    # degrades: usage logging swallows its insert error and property ranking
    # falls back to unranked order.
    settings_db = _resolve_settings_db_path(app)
    app.config.setdefault('SCIDK_SETTINGS_DB', settings_db)
    try:
        import sqlite3 as _sqlite3
        from .services.schema_intelligence import ensure_schema_intelligence_tables
        _si_conn = _sqlite3.connect(settings_db)
        try:
            ensure_schema_intelligence_tables(_si_conn)
        finally:
            _si_conn.close()
    except Exception as e:
        # Non-fatal: the app still serves without the SI layer. Log loudly —
        # this used to be invisible.
        import logging
        logging.error(
            f"Failed to create Schema Intelligence tables in {settings_db}: {e}. "
            "Usage logging and property ranking will be inert."
        )

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

    # Concept Graph driver (optional — graceful degradation if unavailable)
    concept_enabled = os.environ.get('SCIDK_CONCEPT_GRAPH_ENABLED', '1') == '1'
    if concept_enabled:
        from .services.concept_graph_service import get_concept_driver
        concept_driver = get_concept_driver(app)
        if concept_driver:
            app.logger.info("Concept graph connected")
        else:
            app.logger.warning("Concept graph unavailable — falling back to hard-coded classifier")
    else:
        concept_driver = None

    # Interpreter registry
    registry = InterpreterRegistry()
    register_interpreters(registry)

    # Dataset profile registry (loaded from bundled profile YAMLs)
    from .core.profile_registry import ProfileRegistry
    profile_registry = ProfileRegistry()
    profile_registry.load(Path(__file__).resolve().parent / 'interpreters' / 'profiles')

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
        'concept_driver': concept_driver,  # Concept Graph driver (may be None)
        'registry': registry,
        'profile_registry': profile_registry,
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

    # Hydrate Neo4j connection settings from SQLite on startup
    try:
        from .core.settings import get_setting
        import json
        neo4j_config_json = get_setting('neo4j_config')
        if neo4j_config_json:
            persisted_config = json.loads(neo4j_config_json)
            app.extensions['scidk']['neo4j_config'].update(persisted_config)

        # Load password separately
        neo4j_password = get_setting('neo4j_password')
        if neo4j_password:
            app.extensions['scidk']['neo4j_config']['password'] = neo4j_password
    except Exception as e:
        app.logger.warning(f"Failed to load persisted Neo4j settings: {e}")

    # Fall back to env vars (NEO4J_URI/USER/PASSWORD) when SQLite has no config,
    # so a fresh instance connects on first boot without a Settings UI step.
    try:
        from .core.neo4j_config import hydrate_neo4j_config_from_env
        if hydrate_neo4j_config_from_env(app):
            app.logger.info("Neo4j config loaded from environment variables (no SQLite config found)")
    except Exception as e:
        app.logger.warning(f"Failed to load Neo4j settings from environment: {e}")

    # Backfill the shared :Person label once here rather than on the first
    # attribution request of every worker. Must follow the two hydration blocks
    # above -- it reads whatever connection they resolved.
    _ensure_person_label(app)

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

    # Initialize label endpoint registry (for plugin-registered endpoints)
    from .core.label_endpoint_registry import LabelEndpointRegistry
    label_endpoint_registry = LabelEndpointRegistry()
    app.extensions['scidk']['label_endpoints'] = label_endpoint_registry

    # Initialize plugin template registry (for UI-instantiable plugins)
    from .core.plugin_template_registry import PluginTemplateRegistry
    plugin_template_registry = PluginTemplateRegistry()
    app.extensions['scidk']['plugin_templates'] = plugin_template_registry

    # Initialize plugin instance manager (for user-created instances)
    from .core.plugin_instance_manager import PluginInstanceManager
    settings_db = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    plugin_instance_manager = PluginInstanceManager(db_path=settings_db)
    app.extensions['scidk']['plugin_instances'] = plugin_instance_manager

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

    # Initialize the process-wide scheduler and register the backup jobs into it
    try:
        from .core.app_scheduler import get_app_scheduler
        from .core.backup_manager import get_backup_manager
        from .core.backup_scheduler import get_backup_scheduler

        # Get settings database path
        settings_db = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')

        # Get alert manager if available
        alert_manager = None
        try:
            from .core.alert_manager import AlertManager
            alert_manager = AlertManager(db_path=settings_db)
        except Exception:
            # Alert manager optional
            pass

        # One AppScheduler per process; features register jobs into it rather
        # than standing up their own BackgroundScheduler.
        app_scheduler = get_app_scheduler()
        app.extensions['scidk']['app_scheduler'] = app_scheduler

        # Initialize backup manager and scheduler
        # Scheduler will load settings from database (schedule, retention, etc.)
        backup_manager = get_backup_manager()
        backup_scheduler = get_backup_scheduler(
            backup_manager=backup_manager,
            settings_db_path=settings_db,
            alert_manager=alert_manager,
            app_scheduler=app_scheduler
        )

        # Store in app extensions for access in routes. Do this before starting
        # anything so the objects are reachable even when this process is not the
        # one that owns the scheduler.
        app.extensions['scidk']['backup_scheduler'] = backup_scheduler
        app.extensions['scidk']['backup_manager'] = backup_manager

        if _scheduler_should_start():
            # Register the backup job (it only fires if enabled in settings).
            backup_scheduler.start()

            # Everything else — ranking flush, pipeline schedules, concept-graph
            # weight decay — registers itself here and opens its own connections.
            register_scheduled_jobs(app, app_scheduler)

            app_scheduler.start()
            app.logger.info(
                f"Scheduler running (pid={os.getpid()}) with jobs: "
                f"{[j['id'] for j in app_scheduler.list_jobs()]}"
            )
        else:
            app.logger.info(
                "Scheduler start skipped for this process "
                "(reloader parent or SCIDK_DISABLE_SCHEDULER)"
            )
    except Exception as e:
        # Backup scheduler is optional - log but don't fail startup
        import logging
        logging.warning(f"Failed to initialize backup scheduler: {e}")

    # Nothing this factory opened may still be open when we return: under
    # gunicorn --preload this runs in the master process, and any live handle is
    # inherited by all 16 forked workers.
    _release_startup_connections(app)

    return app


def _ensure_person_label(app):
    """Give every ``:Investigator`` and ``:User`` node the shared ``:Person`` label.

    ``FolderAttributionService`` used to do this from ``__init__``, which meant
    two ``MATCH/SET`` queries on the first attribution request of every worker,
    because the guard flag is process-wide and does not survive a restart.

    Opens its own driver and closes it before returning: under gunicorn
    ``--preload`` this runs in the master process, so no connection may cross the
    fork (see :func:`_release_startup_connections`). Every failure -- Neo4j
    unconfigured, unreachable, driver not installed -- is logged and swallowed;
    attribution is not on the boot path and must not be able to break it.
    """
    driver = None
    try:
        from neo4j import GraphDatabase  # type: ignore

        from .services.folder_attribution import FolderAttributionService
        from .web.helpers import get_neo4j_params

        with app.app_context():
            uri, user, pwd, database, auth_mode = get_neo4j_params()
        if not uri:
            return
        driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
        FolderAttributionService(driver, database=database).ensure_person_label()
    except Exception as e:
        app.logger.warning(f"Could not apply the :Person label at startup: {e}")
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass


def _release_startup_connections(app):
    """Close database handles the startup path opened.

    ``create_app()`` runs in the gunicorn master process under ``--preload``.
    A SQLite connection or Neo4j connection pool left open here is inherited by
    every forked worker, which then share one file descriptor — interleaved
    writes, contended WAL locks, and corrupted Bolt traffic. Both objects below
    reopen lazily on next use, so workers and scheduled jobs get their own
    connection after the fork.

    Anything added to ``app.extensions['scidk']`` that holds a connection open
    from ``__init__`` belongs in this function.
    """
    ext = app.extensions.get('scidk', {})

    for key in ('settings', 'alert_manager'):
        holder = ext.get(key)
        close = getattr(holder, 'close', None)
        if callable(close):
            try:
                close()
            except Exception as e:
                app.logger.warning(f"Failed to release startup connection {key}: {e}")

    scheduler = ext.get('backup_scheduler')
    alert_manager = getattr(scheduler, 'alert_manager', None)
    close = getattr(alert_manager, 'close', None)
    if callable(close):
        try:
            close()
        except Exception as e:
            app.logger.warning(
                f"Failed to release backup scheduler alert connection: {e}"
            )


def _scheduler_should_start() -> bool:
    """Whether this process should own the scheduler.

    Two processes must not both start one:

    * The Werkzeug reloader runs the whole module twice — a parent that only
      watches files and a child that serves. ``main()`` sets
      ``SCIDK_RELOADER_ACTIVE`` before building the app, and Werkzeug sets
      ``WERKZEUG_RUN_MAIN=true`` only in the child, so the parent is skipped.
      Under gunicorn ``SCIDK_RELOADER_ACTIVE`` is never set and this is a no-op.
    * ``SCIDK_DISABLE_SCHEDULER=1`` opts out entirely, for CLI commands and
      one-shot scripts that import the app factory.
    """
    if (os.environ.get('SCIDK_DISABLE_SCHEDULER') or '').strip().lower() in (
        '1', 'true', 'yes', 'y', 'on'
    ):
        return False

    reloader_active = os.environ.get('SCIDK_RELOADER_ACTIVE') == '1'
    if reloader_active and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return False

    return True


def register_scheduled_jobs(app, app_scheduler):
    """Register recurring jobs owned by services rather than by BackupScheduler.

    Called once from ``create_app()``, only in the process that owns the
    scheduler. Job functions must open their own database connections and
    drivers — under ``--preload`` they run in the gunicorn master process, so
    anything captured here has crossed a fork.
    """
    from .core.scheduled_jobs import register_all as register_all_jobs
    register_all_jobs(app, app_scheduler)


def main():
    """Run the Flask development server."""
    # Read host/port from env for convenience
    host = os.environ.get('SCIDK_HOST', '0.0.0.0')
    port = int(os.environ.get('SCIDK_PORT', '5000'))
    debug = os.environ.get('SCIDK_DEBUG', '1') == '1'

    # Flag the reloader before building the app: with debug on, Werkzeug runs
    # this module in both a watcher parent and a serving child, and only the
    # child should own the scheduler. See _scheduler_should_start().
    if debug:
        os.environ['SCIDK_RELOADER_ACTIVE'] = '1'

    app = create_app()
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
