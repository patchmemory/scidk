"""Explicit legacy management authority, separate from governed disclosure.

Only trusted local administration provisions development connections and grants.
Requests never initialize state, grant authority, or infer development status.
"""
import hashlib
import json
import re
from urllib.parse import urlsplit

from flask import current_app, g, request

from ..agent_tools.security import PolicyStore, DisclosureDenied, REFUSAL
from ..web.named_session import named_session

PERMISSIONS = {'graph_management_read', 'graph_entity_write', 'graph_schema_write'}


def connection_key(uri, user, database, auth_mode='basic'):
    parsed = urlsplit(uri or '')
    if (parsed.scheme not in {'bolt', 'bolt+s', 'bolt+ssc', 'neo4j', 'neo4j+s', 'neo4j+ssc'}
            or not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.path not in ('', '/') or not database):
        raise DisclosureDenied()
    # Preserve exact endpoint spelling: a changed alias does not inherit authority.
    return hashlib.sha256(json.dumps([uri, user, database, auth_mode], separators=(',', ':')).encode()).hexdigest()


class ManagementPolicyStore(PolicyStore):
    def initialize(self, *, admin_id):
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('''CREATE TABLE IF NOT EXISTS graph_management_grant (
                user_id INTEGER NOT NULL REFERENCES auth_users(id), connection_key TEXT NOT NULL,
                permission TEXT NOT NULL CHECK(permission IN
                ('graph_management_read','graph_entity_write','graph_schema_write')),
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), revision INTEGER NOT NULL,
                granted_by INTEGER NOT NULL REFERENCES auth_users(id),
                PRIMARY KEY(user_id,connection_key,permission))''')

    def grant(self, user_id, target, permission, *, admin_id, allow=True):
        if (permission not in PERMISSIONS or type(allow) is not bool or
                not isinstance(target, str) or len(target) != 64):
            raise DisclosureDenied()
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('''INSERT INTO graph_management_grant VALUES (?,?,?,?,1,?)
                ON CONFLICT(user_id,connection_key,permission) DO UPDATE SET
                enabled=excluded.enabled,revision=revision+1,granted_by=excluded.granted_by''',
                (user_id, target, permission, int(allow), admin_id))
            self._audit(conn, admin_id, f'graph_management:{user_id}:{target}:{permission}:{int(allow)}')

    def check(self, user_id, target, permission):
        with self.connection() as conn:
            if conn.execute('SELECT enabled FROM auth_users WHERE id=?', (user_id,)).fetchone() != (1,):
                raise DisclosureDenied()
            if conn.execute('''SELECT enabled FROM graph_management_grant
                    WHERE user_id=? AND connection_key=? AND permission=?''',
                    (user_id, target, permission)).fetchone() != (1,):
                raise DisclosureDenied()


def require_connection(uri, user, database, auth_mode='basic', permission=None):
    """Recheck current authority at actual graph-client use, including profiles."""
    identity = named_session()
    target = connection_key(uri, user, database, auth_mode)
    if target not in current_app.config.get('SCIDK_DEVELOPMENT_GRAPH_CONNECTIONS', ()):
        raise DisclosureDenied()
    store = ManagementPolicyStore(current_app.config['SCIDK_SETTINGS_DB'])
    store.check(identity['id'], target, 'graph_management_read')
    if permission and permission != 'graph_management_read':
        store.check(identity['id'], target, permission)
    return target


def primary(permission='graph_management_read'):
    from ..core.neo4j_config import get_neo4j_params
    uri, user, _, database, mode = get_neo4j_params(current_app)
    return require_connection(uri, user, database, mode, permission)


def authorize_profile(name, permission='graph_management_read'):
    if not name:
        return primary(permission)
    from ..core.settings import get_setting
    raw = get_setting('neo4j_profile_' + name.replace(' ', '_'))
    if not raw:
        raise DisclosureDenied()
    profile = json.loads(raw)
    return require_connection(profile.get('uri'), profile.get('user'), profile.get('database'), 'basic', permission)


def operation_permission():
    path = request.path
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return 'graph_management_read'
    if ('/instances/' in path or path.endswith(('/execute', '/run', '/commit', '/enrich'))
            or '/import-triples/' in path or path.endswith(('/transfer-to-primary', '/import-csv'))):
        return 'graph_entity_write'
    if '/api/canvas/' in path or '/api/maps/' in path or path.startswith('/api/queries') or path == '/api/graph/query':
        return 'graph_management_read'  # private view state, not graph application
    return 'graph_schema_write'


def protected_path():
    return (request.path.startswith(('/api/labels', '/api/links', '/api/v2/links',
                '/api/neo4j/', '/api/canvas/', '/api/maps/', '/api/queries', '/api/graph/', '/api/schema/'))
            or request.path in {'/entities', '/labels', '/links', '/map'})


def enforce():
    if not protected_path():
        return None
    from flask import jsonify
    try:
        # Raw query facilities are not conferred by management grants. Existing
        # curated operations remain the only available graph write paths.
        if request.path == '/api/neo4j/query':
            raise DisclosureDenied()
        # Raw Cypher is read-only: it needs the management read grant for the exact
        # connection (or named profile) and is executed in a read transaction.
        raw_cypher = request.path == '/api/graph/query' and request.method == 'POST'
        if raw_cypher:
            authorize_profile((request.get_json(silent=True) or {}).get('profile_name'))
        permission = operation_permission()
        primary(permission)
        g.graph_management_permission = permission
        shared = request.path.startswith(('/api/labels', '/api/links', '/api/v2/links', '/api/maps/', '/api/queries'))
        if (request.method == 'DELETE' and shared) or request.path.endswith('/batch/delete'):
            primary('graph_schema_write')
            if request.headers.get('X-SciDK-Confirm') != 'destructive-shared-change':
                raise DisclosureDenied()
        # Existing bulk profile operations can open drivers outside Neo4jClient.
        # Do not allow an unscoped "all configured graphs" fallback.
        if request.path.endswith(('/labels/pull', '/labels/push-all', '/labels/batch/pull')):
            raise DisclosureDenied()
        if (request.path == '/api/graph/schema/combined' and
                request.args.get('source', 'all') in {'graph', 'all'} and
                current_app.config.get('graph_backend') != 'memory' and
                current_app.config.get('graph_backend') != 'in-memory'):
            raise DisclosureDenied()
        # Existing background jobs lose the originating request authorization.
        # They must not execute until a scoped worker authorization contract
        # exists. Ordinary synchronous entity/property editing remains supported.
        if request.path.endswith(('/execute', '/run', '/transfer-to-primary', '/import-csv', '/enrich', '/discovered/import')):
            raise DisclosureDenied()
        body = request.get_json(silent=True) or {}
        saved_map = request.path.startswith(('/api/maps/saved', '/api/queries')) or raw_cypher
        if isinstance(body, dict) and body.get('query') and not saved_map:
            raise DisclosureDenied()
        # The legacy label writer interpolates identifiers. Values remain
        # parameters; validate every dynamic label/property/schema identifier.
        def identifier(value):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
                raise DisclosureDenied()
        # These legacy endpoints interpolate schema identifiers into Cypher.
        # Validate request identifiers even for read-only property discovery.
        def validate_fields(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {'label', 'source_label', 'target_label', 'rel_type',
                               'relationship_type', 'target_field', 'source_field', 'matching_key'} and item:
                        identifier(item)
                    elif key in {'where_clause', 'query', 'cypher'} and item and not saved_map:
                        raise DisclosureDenied()
                    else:
                        validate_fields(item)
            elif isinstance(value, list):
                for item in value:
                    validate_fields(item)
        validate_fields(body)
        if '/property-values/' in request.path:
            identifier(request.path.rsplit('/', 1)[-1])
        if request.path.startswith('/api/labels/'):
            part = request.path.split('/')[3]
            if part not in {'batch', 'import', 'export', 'neo4j', 'pull', 'push-all', 'list'}:
                identifier(part)
                from .label_service import LabelService
                definition = LabelService(current_app).get_label(part)
                profile_name = (definition or {}).get('neo4j_source_profile')
                if profile_name:
                    from ..core.settings import get_setting
                    raw = get_setting('neo4j_profile_' + profile_name.replace(' ', '_'))
                    if not raw:
                        raise DisclosureDenied()
                    profile = json.loads(raw)
                    require_connection(profile.get('uri'), profile.get('user'),
                                       profile.get('database'), 'basic', permission)
                    if request.method == 'PUT' or request.path.endswith('/push'):
                        raise DisclosureDenied()  # these legacy methods ignore the source profile
        if request.path == '/api/labels' and request.method == 'POST':
            identifier(body.get('name'))
            authorize_profile(body.get('neo4j_source_profile'), 'graph_schema_write')
            from .label_service import LabelService
            previous = LabelService(current_app).get_label(body['name'])
            if previous:
                removed = ({p['name'] for p in previous['properties']} -
                           {p.get('name') for p in body.get('properties', [])})
                removed_rels = ({(r['type'], r['target_label']) for r in previous['relationships']} -
                                {(r.get('type'), r.get('target_label')) for r in body.get('relationships', [])})
                if (removed or removed_rels) and request.headers.get('X-SciDK-Confirm') != 'destructive-shared-change':
                    raise DisclosureDenied()
            for prop in body.get('properties', []):
                identifier(prop.get('name'))
            for rel in body.get('relationships', []):
                identifier(rel.get('type')); identifier(rel.get('target_label'))
        if '/instances/' in request.path and request.method in {'PATCH', 'PUT'}:
            if request.method == 'PATCH':
                identifier(body.get('property'))
            else:
                for key in body.get('properties', {}):
                    identifier(key)
    except Exception:
        if request.path in {'/entities', '/labels', '/links', '/map'}:
            from flask import render_template
            return render_template('gui/management_unavailable.html'), 403, {'Cache-Control': 'no-store'}
        return jsonify(REFUSAL), 403, {'Cache-Control': 'no-store'}


def configure(app):
    """Explicit dev_gui hook; does not initialize policy or issue any grants."""
    import os
    from pathlib import Path
    path = Path(os.environ['SCIDK_GRAPH_MANAGEMENT_MANIFEST']).resolve(strict=True)
    if path.stat().st_size > 16384:
        raise ValueError('Management manifest exceeds limit')
    value = json.loads(path.read_text())
    if (set(value) - {'development', 'uri', 'user', 'database', 'auth_mode', 'password_env'}
            or value.get('development') is not True or value.get('auth_mode') not in {'none', 'basic'}):
        raise ValueError('Explicit development graph manifest required')
    target = connection_key(value['uri'], value.get('user'), value['database'], value['auth_mode'])
    if value['auth_mode'] == 'basic' and not os.environ.get(value.get('password_env', '')):
        raise ValueError('Configured development credential environment variable required')
    # This hook runs after the isolated factory. No graph driver, startup label
    # backfill, constraint change, policy migration or grant happens here.
    os.environ['NEO4J_AUTH'] = 'none' if value['auth_mode'] == 'none' else ''
    app.extensions['scidk']['neo4j_config'] = dict(uri=value['uri'], user=value.get('user'),
        database=value['database'], password=os.environ.get(value.get('password_env', '')))
    app.config['SCIDK_DEVELOPMENT_GRAPH_CONNECTIONS'] = [target]
