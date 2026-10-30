"""Explicit administrative disclosure policy in the existing settings database.

Reads never initialize policy or infer approval. Management is trusted local
administration, not an HTTP or agent capability. BoundIdentity is supplied only
by a server authentication adapter, never from tool arguments.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit, unquote

REFUSAL = {'status': 'refused', 'error': 'SciDK cannot authorize disclosure for this operation.'}
RANK = {'low': 0, 'medium': 1}
#: Process-wide switch set only by the live-development runtime (runtime.json "full_access").
#: When on, destination approval and tool/grant gates pass; the sharing (privacy) modes still apply.
FULL_ACCESS = False


class DisclosureDenied(ValueError):
    pass


def endpoint_identity(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment or '%' in parsed.netloc or
                '%' in parsed.path or any(part in {'.', '..'} for part in unquote(parsed.path).split('/')) or
                any(c.isspace() for c in value)):
            raise DisclosureDenied()
        host = parsed.hostname.lower()
        if ':' in host:
            host = '[' + host + ']'
        port = parsed.port
        netloc = host + (':' + str(port) if port and (parsed.scheme, port) not in {('https', 443), ('http', 80)} else '')
        return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip('/'), '', ''))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DisclosureDenied() from exc


@dataclass(frozen=True)
class BoundIdentity:
    user_id: int
    channel: str
    token_id: str | None = None


_DDL = '''
CREATE TABLE IF NOT EXISTS agent_disclosure_schema (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO agent_disclosure_schema VALUES (1);
CREATE TABLE IF NOT EXISTS agent_resource_classification (
 namespace TEXT NOT NULL, resource_id TEXT NOT NULL REFERENCES pipeline_source(id),
 risk TEXT NOT NULL CHECK(risk IN ('low','medium','high')),
 classified_by INTEGER NOT NULL REFERENCES auth_users(id), revision INTEGER NOT NULL,
 PRIMARY KEY(namespace, resource_id)
);
CREATE TABLE IF NOT EXISTS agent_resource_grant (
 user_id INTEGER NOT NULL REFERENCES auth_users(id), namespace TEXT NOT NULL, resource_id TEXT NOT NULL,
 PRIMARY KEY(user_id, namespace, resource_id),
 FOREIGN KEY(namespace,resource_id) REFERENCES agent_resource_classification(namespace,resource_id)
);
CREATE TABLE IF NOT EXISTS agent_destination_approval (
 id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, model TEXT NOT NULL,
 max_risk TEXT NOT NULL CHECK(max_risk IN ('low','medium')),
 approved_by INTEGER NOT NULL REFERENCES auth_users(id), revision INTEGER NOT NULL,
 UNIQUE(endpoint, model)
);
CREATE TABLE IF NOT EXISTS agent_token_destination (
 token_id TEXT PRIMARY KEY REFERENCES api_tokens(id),
 destination_id TEXT NOT NULL REFERENCES agent_destination_approval(id)
);
CREATE TABLE IF NOT EXISTS agent_evidence_grant (
 user_id INTEGER NOT NULL REFERENCES auth_users(id), evidence_id TEXT NOT NULL,
 PRIMARY KEY(user_id,evidence_id)
);
CREATE TABLE IF NOT EXISTS agent_sharing (
 label TEXT NOT NULL, property TEXT NOT NULL, mode TEXT NOT NULL,
 updated_at REAL, updated_by TEXT, PRIMARY KEY(label,property)
);
'''


class PolicyStore:
    def __init__(self, settings_db):
        self.path = Path(settings_db).resolve() if settings_db else None

    @contextmanager
    def connection(self, write=False):
        if not self.path:
            raise DisclosureDenied()
        conn = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True)
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _admin(conn, user_id):
        row = conn.execute('SELECT role, enabled FROM auth_users WHERE id=?', (user_id,)).fetchone()
        if row != ('admin', 1):
            raise DisclosureDenied()

    @staticmethod
    def _audit(conn, admin_id, operation):
        username = conn.execute('SELECT username FROM auth_users WHERE id=?', (admin_id,)).fetchone()[0]
        conn.execute('INSERT INTO auth_audit_log(timestamp,username,action,details,ip_address) VALUES (?,?,?,?,NULL)',
                     (time.time(), username, 'agent_disclosure_policy', operation))

    def initialize(self, *, admin_id):
        """Explicit setup only, after existing authentication/Resource tables exist."""
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            # Validate the existing source authority instead of constructing a new one.
            conn.execute('SELECT id FROM pipeline_source LIMIT 0')
            conn.executescript('BEGIN IMMEDIATE;\n' + _DDL + '\nCOMMIT;')

    def classify(self, namespace, resource_id, risk, *, admin_id):
        if not isinstance(namespace, str) or not namespace or risk not in {'low', 'medium', 'high'}:
            raise DisclosureDenied()
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('INSERT INTO agent_resource_classification VALUES (?,?,?,?,1) '
                         'ON CONFLICT(namespace,resource_id) DO UPDATE SET risk=excluded.risk, '
                         'classified_by=excluded.classified_by, revision=revision+1',
                         (namespace, resource_id, risk, admin_id))
            self._audit(conn, admin_id, 'classify')

    def grant_resource(self, user_id, namespace, resource_id, *, admin_id, allow=True):
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            if allow:
                conn.execute('INSERT OR IGNORE INTO agent_resource_grant VALUES (?,?,?)', (user_id, namespace, resource_id))
            else:
                conn.execute('DELETE FROM agent_resource_grant WHERE user_id=? AND namespace=? AND resource_id=?',
                             (user_id, namespace, resource_id))
            self._audit(conn, admin_id, 'grant_resource')

    def approve_destination(self, destination_id, endpoint, model, max_risk, *, admin_id):
        endpoint = endpoint_identity(endpoint)
        if max_risk not in RANK or not isinstance(model, str) or not model.strip() or not destination_id:
            raise DisclosureDenied()
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('INSERT INTO agent_destination_approval VALUES (?,?,?,?,?,1) '
                         'ON CONFLICT(id) DO UPDATE SET endpoint=excluded.endpoint, model=excluded.model, '
                         'max_risk=excluded.max_risk, approved_by=excluded.approved_by, revision=revision+1',
                         (destination_id, endpoint, model, max_risk, admin_id))
            self._audit(conn, admin_id, 'approve_destination')

    def revoke_destination(self, destination_id, *, admin_id):
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('DELETE FROM agent_token_destination WHERE destination_id=?', (destination_id,))
            conn.execute('DELETE FROM agent_destination_approval WHERE id=?', (destination_id,))
            self._audit(conn, admin_id, 'revoke_destination')

    def bind_token(self, token_id, destination_id, *, admin_id):
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('INSERT INTO agent_token_destination VALUES (?,?) ON CONFLICT(token_id) '
                         'DO UPDATE SET destination_id=excluded.destination_id', (token_id, destination_id))
            self._audit(conn, admin_id, 'bind_token')

    def grant_evidence(self, user_id, evidence_id, *, admin_id, allow=True):
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            if allow:
                conn.execute('INSERT OR IGNORE INTO agent_evidence_grant VALUES (?,?)', (user_id, evidence_id))
            else:
                conn.execute('DELETE FROM agent_evidence_grant WHERE user_id=? AND evidence_id=?', (user_id, evidence_id))
            self._audit(conn, admin_id, 'grant_evidence')

    @contextmanager
    def resolve(self, identity):
        """Fresh read transaction; no cached grants, defaults or destination fallback."""
        if not isinstance(identity, BoundIdentity) or identity.channel not in {'http', 'chat'}:
            raise DisclosureDenied()
        with self.connection() as conn:
            conn.execute('BEGIN')
            if conn.execute('SELECT version FROM agent_disclosure_schema').fetchall() != [(1,)]:
                raise DisclosureDenied()
            user = conn.execute('SELECT username, enabled FROM auth_users WHERE id=?', (identity.user_id,)).fetchone()
            if not user or user[1] != 1:
                raise DisclosureDenied()
            if identity.token_id:
                token = conn.execute('SELECT user_id FROM api_tokens WHERE id=?', (identity.token_id,)).fetchone()
                if token != (identity.user_id,):
                    raise DisclosureDenied()
                destination = conn.execute('SELECT d.id,d.endpoint,d.model,d.max_risk FROM agent_destination_approval d '
                    'JOIN agent_token_destination b ON b.destination_id=d.id WHERE b.token_id=?', (identity.token_id,)).fetchone()
            elif FULL_ACCESS:
                configured = conn.execute('SELECT base_url,model FROM llm_user_settings WHERE username=?', (user[0],)).fetchone()
                if not configured:
                    raise DisclosureDenied()
                destination = ('full-access', endpoint_identity(configured[0]), configured[1], 'medium')
            elif identity.channel == 'chat':
                configured = conn.execute('SELECT base_url,model FROM llm_user_settings WHERE username=?', (user[0],)).fetchone()
                if not configured:
                    raise DisclosureDenied()
                destination = conn.execute('SELECT id,endpoint,model,max_risk FROM agent_destination_approval '
                    'WHERE endpoint=? AND model=?', (endpoint_identity(configured[0]), configured[1])).fetchone()
            else:
                raise DisclosureDenied()
            if not destination or destination[3] not in RANK or endpoint_identity(destination[1]) != destination[1]:
                raise DisclosureDenied()
            # Missing sharing table is policy unavailability, not an empty/raw policy.
            try:
                modes = {(label, prop): mode for label, prop, mode in conn.execute('SELECT label,property,mode FROM agent_sharing')}
            except sqlite3.OperationalError:
                if not FULL_ACCESS:
                    raise
                modes = {}
            yield ResolvedPolicy(conn, identity.user_id, user[0], destination, modes)


class ResolvedPolicy:
    def __init__(self, conn, user_id, username, destination, modes):
        self.conn, self.user_id, self.username = conn, user_id, username
        self.destination, self.modes = destination, modes
        self.max_risk = destination[3] if destination else None

    def resource(self, scope):
        if not isinstance(scope, dict) or set(scope) != {'namespace', 'resource_id'}:
            raise DisclosureDenied()
        row = self.conn.execute('SELECT c.risk FROM agent_resource_classification c '
            'JOIN pipeline_source s ON s.id=c.resource_id '
            'JOIN agent_resource_grant g ON g.namespace=c.namespace AND g.resource_id=c.resource_id '
            'WHERE c.namespace=? AND c.resource_id=? AND g.user_id=?',
            (scope['namespace'], scope['resource_id'], self.user_id)).fetchone()
        # High is globally forbidden even if a malformed approval claims high.
        if not row or row[0] not in RANK or self.max_risk not in RANK or RANK[row[0]] > RANK[self.max_risk]:
            raise DisclosureDenied()

    def property(self, label, prop):
        if self.modes.get((label, prop), 'raw') != 'raw':
            raise DisclosureDenied()

    def evidence_metadata(self, evidence_id, evidence):
        if evidence.get('visibility') == 'public':
            return
        if evidence.get('visibility') != 'restricted' or not self.conn.execute(
                'SELECT 1 FROM agent_evidence_grant WHERE user_id=? AND evidence_id=?',
                (self.user_id, evidence_id)).fetchone():
            raise DisclosureDenied()


def identity_from_request(settings_db, *, channel):
    """Authenticate again at the boundary; never trust usernames or request JSON."""
    from flask import request
    from ..core.auth import get_auth_manager
    auth = get_auth_manager(db_path=settings_db)
    try:
        if not auth.is_enabled():
            raise DisclosureDenied()
        header = request.headers.get('Authorization', '')
        if header:
            if not header.startswith('Bearer '):
                raise DisclosureDenied()
            token = header[7:]
            user = auth.verify_api_token(token)
            if user:
                return BoundIdentity(user['id'], channel, user['token_id'])
            # Session tokens in a header are supported only for the internal chat.
            if channel != 'chat':
                raise DisclosureDenied()
        else:
            token = request.cookies.get('scidk_session')
        user = auth.get_session_user(token) if token else None
        if not user or not user.get('id') or auth.is_session_locked(token):
            raise DisclosureDenied()
        return BoundIdentity(user['id'], channel)
    finally:
        auth.close()
