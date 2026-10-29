"""Explicit local human-purpose authority; never an AI destination approval."""
from contextlib import contextmanager
from dataclasses import dataclass, replace

from ..agent_tools.security import DisclosureDenied, PolicyStore, ResolvedPolicy, RANK


@dataclass(frozen=True)
class HumanIdentity:
    user_id: int
    channel: str = 'human'
    token_id: None = None


class HumanPolicyStore(PolicyStore):
    def initialize(self, *, admin_id):
        # Explicit trusted-local setup only. Reads never migrate or grant.
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('''CREATE TABLE IF NOT EXISTS human_purpose_grant (
                user_id INTEGER NOT NULL REFERENCES auth_users(id),
                purpose TEXT NOT NULL CHECK(purpose IN ('research_browse','review_read')),
                max_risk TEXT NOT NULL CHECK(max_risk IN ('low','medium')),
                granted_by INTEGER NOT NULL REFERENCES auth_users(id),
                revision INTEGER NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                PRIMARY KEY(user_id,purpose))''')

    def grant_purpose(self, user_id, purpose, max_risk, *, admin_id, allow=True):
        if purpose not in {'research_browse', 'review_read'} or max_risk not in RANK or type(allow) is not bool:
            raise DisclosureDenied()
        with self.connection(write=True) as conn:
            self._admin(conn, admin_id)
            conn.execute('''INSERT INTO human_purpose_grant VALUES (?,?,?,?,1,?)
                ON CONFLICT(user_id,purpose) DO UPDATE SET max_risk=excluded.max_risk,
                granted_by=excluded.granted_by, revision=revision+1, enabled=excluded.enabled''',
                (user_id, purpose, max_risk, admin_id, int(allow)))
            # Record exact subject, purpose, ceiling and revocation without content.
            self._audit(conn, admin_id, f'human_purpose:{user_id}:{purpose}:{max_risk}:{int(allow)}')

    @contextmanager
    def resolve(self, identity, purpose):
        if (type(identity) is not HumanIdentity or identity.channel != 'human' or identity.token_id
                or purpose not in {'research_browse', 'review_read'}):
            raise DisclosureDenied()
        with self.connection() as conn:
            conn.execute('BEGIN')
            if conn.execute('SELECT version FROM agent_disclosure_schema').fetchall() != [(1,)]:
                raise DisclosureDenied()
            user = conn.execute('SELECT username,enabled FROM auth_users WHERE id=?', (identity.user_id,)).fetchone()
            grant = conn.execute('''SELECT max_risk FROM human_purpose_grant
                WHERE user_id=? AND purpose=? AND enabled=1''', (identity.user_id, purpose)).fetchone()
            if not user or user[1] != 1 or not grant or grant[0] not in RANK:
                raise DisclosureDenied()
            modes = {(label, prop): mode for label, prop, mode in conn.execute(
                'SELECT label,property,mode FROM agent_sharing')}
            policy = ResolvedPolicy(conn, identity.user_id, user[0], None, modes)
            policy.max_risk = grant[0]
            yield policy


def human_context(app):
    from ..web.named_session import named_session
    from ..agent_tools.context import context_from_app
    user = named_session()
    return replace(context_from_app(app, channel='chat'), identity=HumanIdentity(user['id']))


def resolve_workspace(ctx, purpose):
    if type(ctx.identity) is HumanIdentity:
        return HumanPolicyStore(ctx.settings_db).resolve(ctx.identity, purpose)
    return PolicyStore(ctx.settings_db).resolve(ctx.identity)
