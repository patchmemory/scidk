"""Explicit shared usage grants; secrets stay in the existing encrypted store.

No schema migration, environment fallback, or HTTP grant-management endpoint.
Only governed transports call resolve(); personal APIs never receive owner keys.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

GRANT_KEY = 'llm.shared_provider_usage'


def grant(settings_db, user_id, owner_id, *, admin_id, allow=True):
    """Trusted local admin setup. Pins usage to the owner's current endpoint/model."""
    from ..agent_tools.security import PolicyStore, endpoint_identity
    from .provider_settings import credentials
    with PolicyStore(settings_db).connection(write=True) as conn:
        PolicyStore._admin(conn, admin_id)
        PolicyStore._admin(conn, owner_id)
        owner = conn.execute('SELECT username FROM auth_users WHERE id=?', (owner_id,)).fetchone()[0]
        if not conn.execute('SELECT 1 FROM auth_users WHERE id=? AND enabled=1', (user_id,)).fetchone():
            raise ValueError('Enabled recipient required')
        row = conn.execute('SELECT value FROM interpreter_settings WHERE key=?', (GRANT_KEY,)).fetchone()
        grants = json.loads(row[0]) if row else {}
        grants.pop(str(user_id), None)
        if allow:
            provider = credentials(settings_db, owner)
            if not provider or not provider['api_key']:
                raise ValueError('Configured owner credential required')
            grants[str(user_id)] = {'owner_id': owner_id, 'admin_id': admin_id,
                'endpoint': endpoint_identity(provider['base_url']), 'model': provider['model']}
        conn.execute('INSERT OR REPLACE INTO interpreter_settings(key,value) VALUES (?,?)', (GRANT_KEY, json.dumps(grants)))
        PolicyStore._audit(conn, admin_id, 'shared_provider_usage')


def resolve(settings_db, username):
    """Resolve explicit per-user usage only for the selected exact destination.

    Authorization for source data and model approval is still required by the
    caller; this helper confers only permission to use a credential server-side.
    """
    from .provider_settings import credentials
    from ..agent_tools.security import endpoint_identity
    personal = credentials(settings_db, username)
    if not personal or personal.get('api_key'):
        return personal
    try:
        with closing(sqlite3.connect(Path(settings_db).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            user = conn.execute('SELECT id FROM auth_users WHERE username=? AND enabled=1', (username,)).fetchone()
            row = conn.execute('SELECT value FROM interpreter_settings WHERE key=?', (GRANT_KEY,)).fetchone()
            selected = json.loads(row[0]).get(str(user[0])) if user and row else None
            if not isinstance(selected, dict) or set(selected) != {'owner_id', 'admin_id', 'endpoint', 'model'}:
                return personal
            for uid in (selected['owner_id'], selected['admin_id']):
                if conn.execute('SELECT role,enabled FROM auth_users WHERE id=?', (uid,)).fetchone() != ('admin', 1):
                    return personal
            owner = conn.execute('SELECT username FROM auth_users WHERE id=?', (selected['owner_id'],)).fetchone()[0]
        shared = credentials(settings_db, owner)
        if (shared and shared.get('api_key') and endpoint_identity(shared['base_url']) == selected['endpoint'] == endpoint_identity(personal['base_url'])
                and shared['model'] == selected['model'] == personal['model']):
            return {**personal, 'api_key': shared['api_key']}
    except Exception:
        pass
    return personal
