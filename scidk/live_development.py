"""Operator-controlled live development profile using the existing dev_gui factory.

Initialization and grant provisioning are explicit CLI actions. Startup does not
seed graph records, grant permissions, import schemas, or attach fake services.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GRAPH_ENV = ('NEO4J_URI', 'BOLT_URI', 'NEO4J_USER', 'NEO4J_USERNAME', 'NEO4J_PASSWORD',
             'NEO4J_AUTH', 'SCIDK_NEO4J_DATABASE', 'CHAT_NEO4J_URI', 'CHAT_NEO4J_AUTH',
             'SCIDK_CONCEPT_NEO4J_URI', 'SCIDK_CONCEPT_NEO4J_AUTH')


def write_private(path, value):
    with open(path, 'x', encoding='utf-8') as stream:
        os.chmod(path, 0o600)
        stream.write(value)


def source_connection(path, database):
    from dotenv import dotenv_values
    from .services.graph_management_policy import connection_key
    values = dotenv_values(path, interpolate=False)
    uri = values.get('NEO4J_URI') or values.get('BOLT_URI')
    user = values.get('NEO4J_USER') or values.get('NEO4J_USERNAME')
    password = values.get('NEO4J_PASSWORD')
    auth = values.get('NEO4J_AUTH') or ''
    mode = 'none' if auth.lower() == 'none' else 'basic'
    if mode == 'basic' and not (user and password) and '/' in auth:
        user, password = auth.split('/', 1)
    if mode == 'basic' and not (user and password):
        raise ValueError('Development credential configuration is incomplete')
    target = connection_key(uri, user, database, mode)
    return dict(uri=uri, user=user, database=database, auth_mode=mode), password, target


def load(state):
    config = json.loads((state / 'runtime.json').read_text())
    connection, password, target = source_connection(config['source_env'], config['database'])
    if target != config['connection_key']:
        raise ValueError('Source connection changed; existing grants cannot transfer to a new target')
    manifest = json.loads((state / 'management.json').read_text())
    if any(manifest.get(key) != value for key, value in connection.items()):
        raise ValueError('Runtime manifest and approved source connection differ')
    return config, connection, password


def prepare(state):
    config, connection, password = load(state)
    for name in GRAPH_ENV:
        os.environ.pop(name, None)
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    os.environ['SCIDK_GRAPH_MANAGEMENT_MANIFEST'] = str(state / 'management.json')
    os.environ['SCIDK_LIVE_NEO4J_PASSWORD'] = password or ''
    os.environ['SCIDK_LIVE_STATE'] = str(state)
    from .dev_gui import build_app
    return build_app(state, configure='scidk.live_development:configure'), config


def read_only_request():
    from flask import request, jsonify
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return None
    # These existing operations authenticate, inspect, or persist private/local
    # view state. All graph-mutating legacy/Pipeline routes are unavailable in
    # this read-only activation profile, including to the named administrator.
    safe = ('/api/auth/', '/api/knowledge/', '/api/maps/saved', '/api/queries')
    if (request.path.startswith(safe) or request.path in {
            '/api/development/readiness', '/api/canvas/session', '/api/chat/overview',
            '/admin/chat-readiness'}):
        return None
    return jsonify(status='unavailable', error='This live development profile permits graph reads and local view state only.'), 403, {'Cache-Control':'no-store'}


def configure(app):
    from .services.graph_management_policy import configure as configure_management
    configure_management(app)
    app.before_request(read_only_request)
    state = Path(os.environ['SCIDK_LIVE_STATE'])
    config = json.loads((state / 'runtime.json').read_text())
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'diff', '--name-only', 'HEAD'], text=True).strip())
    # Never return the private state/source paths, usernames or credentials.
    fingerprint = hashlib.sha256()
    for path in sorted((ROOT / 'scidk').rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.html', '.js', '.css'}:
            fingerprint.update(str(path.relative_to(ROOT)).encode())
            fingerprint.update(path.read_bytes())
    app.extensions['development_runtime'] = dict(git_revision=revision, startup_dirty=dirty,
        code_fingerprint=fingerprint.hexdigest(), profile='live-development-readonly',
        python_version=sys.version.split()[0], python_environment=hashlib.sha256(sys.prefix.encode()).hexdigest()[:12],
        port=config['port'])


def initialize(state, args):
    if not args.confirm_development_source or not args.grant_read:
        raise ValueError('Initialization requires explicit development-source confirmation and --grant-read')
    if not 1024 <= args.port <= 65535:
        raise ValueError('Choose an unprivileged loopback port')
    if not args.source_env or not args.database:
        raise ValueError('--source-env and an explicit --database are required')
    connection, _, target = source_connection(Path(args.source_env).resolve(strict=True), args.database)
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    from .core.auth import AuthManager
    from .services.graph_management_policy import ManagementPolicyStore
    auth = AuthManager(str(state / 'scidk_settings.db'))
    try:
        password = secrets.token_urlsafe(24)
        uid = auth.create_user(args.operator, password, role='admin')
        if not uid:
            raise ValueError('Named operator creation failed')
        policy = ManagementPolicyStore(str(state / 'scidk_settings.db'))
        policy.initialize(admin_id=uid)
        policy.grant(uid, target, 'graph_management_read', admin_id=uid)
        # No graph writes, schema writes, AI, Resource or evidence grants.
        write_private(state / 'operator-login.json', json.dumps(dict(username=args.operator, password=password)))
    finally:
        auth.close()
    write_private(state / 'management.json', json.dumps(dict(development=True, **connection,
        password_env='SCIDK_LIVE_NEO4J_PASSWORD')))
    write_private(state / 'runtime.json', json.dumps(dict(source_env=str(Path(args.source_env).resolve()),
        database=args.database, connection_key=target, port=args.port), indent=2))
    print('Initialized named operator and audited read-only management grant. Login is in the private operator-login.json file.')


def sync_schema(state):
    """Explicit metadata-only refresh into the NEW local catalog, never the graph."""
    from neo4j import GraphDatabase, READ_ACCESS, Query
    from .services.label_service import LabelService
    app, _ = prepare(state)
    _, connection, password = load(state)
    auth = None if connection['auth_mode'] == 'none' else (connection['user'], password)
    with GraphDatabase.driver(connection['uri'], auth=auth, connection_timeout=5) as driver:
        with driver.session(database=connection['database'], default_access_mode=READ_ACCESS) as session:
            class MetadataClient:
                def execute_read(self, query):
                    # The reused service issues two fixed metadata-only queries.
                    return [dict(row) for row in session.run(Query(query + '\nLIMIT 2048', timeout=15))]
            with app.app_context():
                result = LabelService(app).pull_from_neo4j(MetadataClient())
    if result.get('status') != 'success' or not result.get('count'):
        raise ValueError('Schema refresh failed or returned no definitions; private log may be inspected locally')
    print(json.dumps(dict(status='ready', imported_definition_count=result['count'], graph_writes=0)))


def owned_process(state):
    record = json.loads((state / 'process.json').read_text())
    process = Path('/proc') / str(record['pid'])
    args = (process / 'cmdline').read_bytes().decode().split('\0')
    if ('scidk.live_development' not in args or 'serve' not in args or str(state) not in args
            or (process / 'stat').read_text().split()[21] != record['start_ticks']):
        raise ValueError('PID no longer identifies this launch profile; refusing to signal it')
    return record['pid']


def start(state):
    config, _, _ = load(state)
    if (state / 'process.json').exists():
        try:
            owned_process(state)
        except FileNotFoundError:
            pass
        else:
            raise ValueError('This development instance is already running')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', config['port']))
    environment = dict(os.environ, PYTHONPATH=str(ROOT), PYTHON_DOTENV_DISABLED='1')
    for name in GRAPH_ENV:
        environment.pop(name, None)
    with open(state / 'server.log', 'ab') as log:
        os.chmod(state / 'server.log', 0o600)
        process = subprocess.Popen([sys.executable, '-m', 'scidk.live_development', 'serve',
            '--state-dir', str(state)], cwd=ROOT, env=environment, stdout=log, stderr=log,
            stdin=subprocess.DEVNULL, start_new_session=True)
    record = dict(pid=process.pid, start_ticks=(Path('/proc') / str(process.pid) / 'stat').read_text().split()[21])
    (state / 'process.json').write_text(json.dumps(record))
    os.chmod(state / 'process.json', 0o600)
    print(f'Started PID {process.pid}; verify http://127.0.0.1:{config["port"]}/login and /admin/development-readiness')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'sync-schema', 'start', 'serve', 'stop', 'status'])
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--source-env')
    parser.add_argument('--database')
    parser.add_argument('--operator', default='development-operator')
    parser.add_argument('--port', type=int, default=5010)
    parser.add_argument('--confirm-development-source', action='store_true')
    parser.add_argument('--grant-read', action='store_true')
    args = parser.parse_args()
    state = Path(args.state_dir).expanduser().resolve()
    try:
        if args.action == 'init':
            initialize(state, args)
        elif args.action == 'sync-schema':
            sync_schema(state)
        elif args.action == 'start':
            start(state)
        elif args.action == 'serve':
            app, config = prepare(state)
            app.run(host='127.0.0.1', port=config['port'], debug=False, use_reloader=False)
        elif args.action == 'stop':
            os.kill(owned_process(state), signal.SIGTERM)
            print('Sent TERM only to this launch profile; existing services are unchanged.')
        else:
            print(json.dumps(dict(profile='live-development-readonly', pid=owned_process(state))))
    except (ValueError, OSError, KeyError) as exc:
        # Do not echo exception strings: driver/filesystem errors can contain secrets/paths.
        parser.exit(1, f'{type(exc).__name__}: runtime action unavailable; check the documented prerequisites.\n')


if __name__ == '__main__':
    main()
