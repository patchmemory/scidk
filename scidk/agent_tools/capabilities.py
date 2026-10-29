"""Explicit local administration extending the existing settings/policy store.

No initialization on read, no credentials, no routes and no role bypass.
"""
from .security import PolicyStore, DisclosureDenied
from .profiles import PROFILES

_DDL = '''
CREATE TABLE IF NOT EXISTS agent_tool_schema (version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO agent_tool_schema VALUES (1);
CREATE TABLE IF NOT EXISTS agent_tool_capability (
 user_id INTEGER NOT NULL REFERENCES auth_users(id), profile TEXT NOT NULL,
 tool TEXT NOT NULL, PRIMARY KEY(user_id,profile,tool)
);
CREATE TABLE IF NOT EXISTS agent_proposal_grant (
 user_id INTEGER NOT NULL REFERENCES auth_users(id), namespace TEXT NOT NULL,
 resource_id TEXT NOT NULL, PRIMARY KEY(user_id,namespace,resource_id),
 FOREIGN KEY(namespace,resource_id) REFERENCES agent_resource_classification(namespace,resource_id)
);
'''


class CapabilityStore(PolicyStore):
    def initialize(self, *, admin_id):
        """Explicit optional extension; Stage 3 policy must already be initialized."""
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            if conn.execute('SELECT version FROM agent_disclosure_schema').fetchall() != [(1,)]:
                raise DisclosureDenied()
            conn.executescript('BEGIN IMMEDIATE;\n' + _DDL + '\nCOMMIT;')
            self._audit(conn, admin_id, 'initialize_agent_tools')

    def grant_tool(self, user_id, profile, tool, *, admin_id, allow=True):
        if profile not in PROFILES or tool not in PROFILES[profile]:
            raise DisclosureDenied()
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            if allow:
                conn.execute('INSERT OR IGNORE INTO agent_tool_capability VALUES (?,?,?)', (user_id, profile, tool))
            else:
                conn.execute('DELETE FROM agent_tool_capability WHERE user_id=? AND profile=? AND tool=?',
                             (user_id, profile, tool))
            self._audit(conn, admin_id, 'agent_tool_capability')

    def grant_proposal(self, user_id, namespace, resource_id, *, admin_id, allow=True):
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            if allow:
                conn.execute('INSERT OR IGNORE INTO agent_proposal_grant VALUES (?,?,?)', (user_id, namespace, resource_id))
            else:
                conn.execute('DELETE FROM agent_proposal_grant WHERE user_id=? AND namespace=? AND resource_id=?',
                             (user_id, namespace, resource_id))
            self._audit(conn, admin_id, 'agent_proposal_grant')


def permitted_tools(policy, profile):
    if profile not in PROFILES:
        raise DisclosureDenied()
    if policy.conn.execute('SELECT version FROM agent_tool_schema').fetchall() != [(1,)]:
        raise DisclosureDenied()
    role = policy.conn.execute('SELECT role FROM auth_users WHERE id=?', (policy.user_id,)).fetchone()
    if role not in {('user',), ('admin',)}:
        raise DisclosureDenied()
    granted = {r[0] for r in policy.conn.execute(
        'SELECT tool FROM agent_tool_capability WHERE user_id=? AND profile=?', (policy.user_id, profile))}
    allowed = PROFILES[profile] & granted
    if 'submit_assertion' in allowed:
        scopes = policy.conn.execute('SELECT namespace,resource_id FROM agent_proposal_grant WHERE user_id=? LIMIT 51',
                                     (policy.user_id,)).fetchall()
        usable = False
        for namespace, resource_id in scopes[:50]:
            try:
                policy.resource({'namespace': namespace, 'resource_id': resource_id})
                usable = True
                break
            except DisclosureDenied:
                continue
        if not usable:
            allowed = allowed - {'submit_assertion'}
    return allowed


def require_proposal(policy, scope):
    policy.resource(scope)
    if not policy.conn.execute('SELECT 1 FROM agent_proposal_grant WHERE user_id=? AND namespace=? AND resource_id=?',
                               (policy.user_id, scope['namespace'], scope['resource_id'])).fetchone():
        raise DisclosureDenied()
