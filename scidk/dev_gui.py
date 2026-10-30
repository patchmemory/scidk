"""Explicit authenticated development launcher; no global defaults are changed.

Run with --help. Configure services using an administrator-owned Python hook;
this launcher never approves destinations or invents accepted graph facts.
"""
import argparse
import getpass
import importlib
import os
from pathlib import Path


def build_app(state_dir, *, init_admin=None, configure=None):
    state = Path(state_dir).expanduser().resolve()
    if state == Path('/') or state == Path.home():
        raise ValueError('Choose a dedicated development state directory')
    # A fresh state DB does not override graph credentials inherited by the
    # production factory. Refuse those before it can initialize any driver.
    graph_vars = {'NEO4J_URI', 'BOLT_URI', 'CHAT_NEO4J_URI', 'SCIDK_CONCEPT_NEO4J_URI',
                  'NEO4J_AUTH', 'CHAT_NEO4J_AUTH', 'SCIDK_CONCEPT_NEO4J_AUTH'}
    if any(os.environ.get(key) for key in graph_vars):
        raise ValueError('Use a clean development environment without inherited graph connection configuration')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings = state / 'scidk_settings.db'
    from .core.auth import AuthManager
    auth = AuthManager(str(settings))
    try:
        users = auth.list_users(include_disabled=True)
        if init_admin:
            if users:
                raise ValueError('Initialization requires a fresh development authentication store')
            password = getpass.getpass('New development administrator password: ')
            if len(password) < 12 or password != getpass.getpass('Repeat password: '):
                raise ValueError('Use a matching password of at least 12 characters')
            if not auth.create_user(init_admin, password, role='admin'):
                raise ValueError('Administrator initialization failed')
        if not auth.is_enabled() or not any(u['role'] == 'admin' and u['enabled'] for u in auth.list_users()):
            raise ValueError('An enabled named administrator is required; initialize a fresh development state explicitly')
    finally:
        auth.close()
    os.environ['SCIDK_DISABLE_SCHEDULER'] = '1'
    os.environ['SCIDK_CONCEPT_GRAPH_ENABLED'] = '0'
    os.environ['SCIDK_GRAPH_BACKEND'] = 'memory'
    os.environ['SCIDK_SETTINGS_DB'] = str(settings)
    os.environ['SCIDK_DB_PATH'] = str(state / 'files.db')
    os.environ['SCIDK_SCAN_DB_DIR'] = str(state / 'scans')
    os.environ['SCIDK_ROCRATE_DIR'] = str(state / 'crates')
    # Contain other cwd-relative legacy stores in the dedicated state directory.
    os.chdir(state)
    # Prevent repository .env discovery from reintroducing production connections.
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    from .app import create_app
    if any(os.environ.get(key) for key in graph_vars):
        raise ValueError('Use a clean development environment without inherited graph connection configuration')
    app = create_app()
    app.config.update(SCIDK_SETTINGS_DB=str(settings), SCIDK_GUI_V3_ENABLED=True, SCIDK_CHAT_READINESS_ENABLED=True,
        SCIDK_OVERVIEW_CHAT_ENABLED=True, SCIDK_REVIEW_WORKSPACE_ENABLED=True,
        SCIDK_REVIEW_CHAT_ENABLED=True, SCIDK_KNOWLEDGE_CONTEXT_ENABLED=True,
        SCIDK_CURATION_ENABLED=True, SCIDK_DATASET_SHARING_ENABLED=True)
    # The launcher runs from the state directory, so the relative plugins/ discovery finds
    # nothing; register the sharing-plan routes (dataset and collection) explicitly.
    if 'nih_dms' not in app.blueprints:
        from plugins.nih_dms.routes import bp as nih_dms_bp
        app.register_blueprint(nih_dms_bp)
    if 'api_curation' not in app.blueprints:
        from .web.routes.api_curation import register_curation
        register_curation(app)
    if configure:
        module, function = configure.split(':', 1)
        getattr(importlib.import_module(module), function)(app)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--init-admin', help='Initialize a fresh development auth store; password is prompted, never a command argument')
    parser.add_argument('--configure', help='Trusted local module:function attaching existing KnowledgeServices and ReviewService')
    parser.add_argument('--port', type=int, default=5002, help='Use 5002 to leave an existing port-5001 server untouched')
    args = parser.parse_args()
    try:
        app = build_app(args.state_dir, init_admin=args.init_admin, configure=args.configure)
    except ValueError as exc:
        parser.error(str(exc))
    app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
