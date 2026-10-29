"""The one LLM provider setting: an OpenAI-compatible endpoint, per user.

Each user stores their own base URL, model and API key (table
``llm_user_settings`` in the settings DB). The key is encrypted at rest
(core/secret_store.py), write-only from the browser (only ``sk-…abcd`` is ever
returned), never logged and never part of a tool result or export.

With auth off there is one implicit user, stored under ``''``.

Which credentials a chat turn uses (Task 1): the user's own; then (later) an
admin-shared provider profile granted to them; then the legacy
SCIDK_CHAT_* environment settings, which an admin set for the instance.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import time
from typing import Any, Dict, List, Optional

from ..core import secret_store

PARLEY_DEFAULT_BASE_URL = 'https://parley.api.mit.edu/v1'


def presets() -> List[Dict[str, Any]]:
    return [
        {'id': 'parley', 'label': 'MIT Parley',
         'base_url': PARLEY_DEFAULT_BASE_URL,
         'key_placeholder': 'sk-parley-v1-…', 'needs_key': True,
         'note': 'Your own Parley key; usage is billed to you.'},
        {'id': 'openai', 'label': 'OpenAI', 'base_url': 'https://api.openai.com/v1',
         'key_placeholder': 'sk-…', 'needs_key': True, 'note': ''},
        {'id': 'ollama', 'label': 'Ollama (local)', 'base_url': 'http://localhost:11434/v1',
         'key_placeholder': '(none needed)', 'needs_key': False,
         'note': 'Runs on this machine; nothing leaves it.'},
        {'id': 'custom', 'label': 'Other OpenAI-compatible', 'base_url': '',
         'key_placeholder': '', 'needs_key': False, 'note': ''},
    ]


def _connect(settings_db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(settings_db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_user_settings ("
        " username TEXT PRIMARY KEY, preset TEXT, base_url TEXT, model TEXT,"
        " api_key_enc TEXT, updated_at REAL)")
    return conn


def _row(settings_db: str, username: str) -> Optional[Dict[str, Any]]:
    conn = _connect(settings_db)
    try:
        row = conn.execute("SELECT preset, base_url, model, api_key_enc, updated_at "
                           "FROM llm_user_settings WHERE username = ?", (username or '',)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return dict(zip(('preset', 'base_url', 'model', 'api_key_enc', 'updated_at'), row))


def public_settings(settings_db: str, username: Optional[str]) -> Dict[str, Any]:
    """What the browser may see: never the key, only whether one is set and its hint."""
    row = _row(settings_db, username or '') or {}
    key = secret_store.decrypt(settings_db, row.get('api_key_enc'))
    return {
        'configured': bool(row.get('base_url') and row.get('model')),
        'preset': row.get('preset') or '',
        'base_url': row.get('base_url') or '',
        'model': row.get('model') or '',
        'has_key': bool(key),
        'key_hint': secret_store.hint(key),
        'key_unreadable': bool(row.get('api_key_enc')) and key is None,
        'updated_at': row.get('updated_at'),
    }


_URL_RE = re.compile(r'^https?://[^\s/$.?#][^\s]*$', re.IGNORECASE)


def save(settings_db: str, username: Optional[str], *, preset: Optional[str] = None,
         base_url: Optional[str] = None, model: Optional[str] = None,
         api_key: Optional[str] = None, clear_key: bool = False) -> Dict[str, Any]:
    """Update the user's setting. ``api_key=None`` keeps the stored key;
    ``clear_key`` removes it. Raises ValueError on a bad URL."""
    username = username or ''
    current = _row(settings_db, username) or {}
    base_url = (base_url if base_url is not None else current.get('base_url') or '').strip()
    if base_url and not _URL_RE.match(base_url):
        raise ValueError('base_url must be an http(s) URL')
    if base_url:
        from ..agent_tools.security import endpoint_identity
        base_url = endpoint_identity(base_url)
    enc = current.get('api_key_enc')
    if clear_key:
        enc = None
    elif api_key:
        enc = secret_store.encrypt(settings_db, api_key.strip())
    conn = _connect(settings_db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO llm_user_settings(username, preset, base_url, model, api_key_enc, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (username, preset if preset is not None else current.get('preset'), base_url,
             (model if model is not None else current.get('model') or '').strip(), enc, time.time()))
        conn.commit()
    finally:
        conn.close()
    return public_settings(settings_db, username)


def stored_endpoint(settings_db: str, username: Optional[str]) -> Dict[str, Any]:
    """Server-side only: whatever is stored, complete or not ({} if nothing).
    Listing models needs the key before a model has been chosen."""
    row = _row(settings_db, username or '') or {}
    return {'base_url': row.get('base_url') or '', 'model': row.get('model') or '',
            'preset': row.get('preset') or '',
            'api_key': secret_store.decrypt(settings_db, row.get('api_key_enc'))}


def credentials(settings_db: str, username: Optional[str]) -> Optional[Dict[str, Any]]:
    """Server-side only: {base_url, model, api_key, preset}, or None until both a
    base URL and a model are set (what a chat turn needs)."""
    stored = stored_endpoint(settings_db, username)
    return stored if stored['base_url'] and stored['model'] else None


def provider_for(settings_db: str, username: Optional[str]):
    """The user's OpenAICompatibleProvider, or None if they haven't set one up."""
    creds = credentials(settings_db, username)
    if not creds:
        return None
    from .openai_compatible import OpenAICompatibleProvider
    return OpenAICompatibleProvider(creds['base_url'], creds['api_key'], creds['model'],
                                    label=creds['preset'] or 'openai_compatible')


def read_parley_env(timeout: float = 20) -> Dict[str, str]:
    """PARLEY_API_KEY / PARLEY_BASE_URL from ``parley env``. For the explicit,
    single-user-only import button; never called implicitly."""
    exe = shutil.which('parley')
    if not exe:
        raise RuntimeError('The parley CLI is not installed on this machine.')
    out = subprocess.run([exe, 'env', '--shell', 'bash'], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError('parley env failed; run `parley login` first.')
    found = {}
    for line in out.stdout.splitlines():
        m = re.match(r"^\s*export\s+(PARLEY_API_KEY|PARLEY_BASE_URL)=(['\"]?)(.*)\2\s*;?\s*$", line)
        if m:
            found[m.group(1)] = m.group(3)
    if not found.get('PARLEY_API_KEY'):
        raise RuntimeError('parley env printed no PARLEY_API_KEY; run `parley login` first.')
    return found


def disclosed_fact_turn(settings_db, identity, disclosure, fact_id, *, include_evidence=False):
    """Internal fixed-content send using the existing provider/client configuration.

    Not an agent tool. No arbitrary user prompt, system context, graph payload or
    history is accepted. Rechecks policy immediately before transport and binds
    the actual configured endpoint/model. Returns no provider errors/metadata.
    """
    from ..agent_tools.security import PolicyStore, REFUSAL, endpoint_identity
    from .openai_compatible import chat_completion
    try:
        from pathlib import Path
        if Path(settings_db).resolve() != disclosure.store.path:
            return dict(REFUSAL)
        result = disclosure.read_fact(fact_id, identity, include_evidence=include_evidence)
        if result.get('status') != 'success':
            return dict(REFUSAL)
        with PolicyStore(settings_db).resolve(identity) as policy:
            configured = credentials(settings_db, policy.username)
            if (not configured or endpoint_identity(configured['base_url']) != policy.destination[1]
                    or configured['model'] != policy.destination[2]):
                return dict(REFUSAL)
            # Re-authorize the content rather than reuse a caller-supplied envelope.
            current = disclosure.read_fact(fact_id, identity, include_evidence=include_evidence)
            if current.get('status') != 'success':
                return dict(REFUSAL)
            import json
            outbound = (configured['base_url'], configured['api_key'], configured['model'],
                        [{'role': 'user', 'content': json.dumps(current['fact'])}])
        # Do not hold the settings read transaction across network I/O: a slow
        # provider must not block administrative revocations or token activity.
        chat_completion(*outbound)
        # Backend text and metadata are not an authorized fact serialization.
        return {'status': 'success', 'finish_reason': 'sent'}
    except Exception:
        return dict(REFUSAL)


def disclosed_tool_turn(ctx, name, arguments):
    """Internal fixed-result send over the existing OpenAI-compatible client.

    No caller-supplied messages/history/provider overrides and no autonomous tool
    loop. Proposal invocation still requires the shared explicit capability and
    scoped grants. Provider text is not treated as authorized stored knowledge.
    """
    from ..agent_tools.registry import run_tool, openai_functions, available_tool_definitions
    from ..agent_tools.security import PolicyStore, REFUSAL, endpoint_identity
    from .openai_compatible import chat_completion
    try:
        with PolicyStore(ctx.settings_db).resolve(ctx.identity) as policy:
            configured = credentials(ctx.settings_db, policy.username)
            if (not configured or endpoint_identity(configured['base_url']) != policy.destination[1]
                    or configured['model'] != policy.destination[2]):
                return dict(REFUSAL)
        if name not in {t['name'] for t in available_tool_definitions(ctx)}:
            return dict(REFUSAL)
        result = run_tool(name, arguments, ctx)
        if result.get('status') != 'success':
            return dict(REFUSAL)
        with PolicyStore(ctx.settings_db).resolve(ctx.identity) as policy:
            current = credentials(ctx.settings_db, policy.username)
            if (not current or endpoint_identity(current['base_url']) != policy.destination[1]
                    or current['model'] != policy.destination[2]
                    or current['base_url'] != configured['base_url'] or current['model'] != configured['model']):
                return dict(REFUSAL)
            # All shared authorization is re-evaluated immediately before send.
            # submit_assertion replay is actor-scoped/idempotent, never a second proposal.
            result = run_tool(name, arguments, ctx)
            definitions = openai_functions(ctx=ctx)
            if result.get('status') != 'success' or name not in {d['function']['name'] for d in definitions}:
                return dict(REFUSAL)
            import json
            outbound = (current['base_url'], current['api_key'], current['model'],
                        [{'role': 'user', 'content': json.dumps(result)}])
        chat_completion(*outbound, tools=definitions)
        return {'status': 'success', 'finish_reason': 'sent'}
    except Exception:
        return dict(REFUSAL)
