"""Shared Chat workbench turn: one explicit, read-only, general conversation turn.

The inset dialog and the full-page workbench both post here. A turn sends ONLY the person's typed message plus a
fixed minimal system instruction through the one governed OpenAI-compatible client (``ai.openai_compatible``), using the
signed-in user's own server-side provider setting (or an explicitly granted shared credential).

Guarantees, all checked on the server before any transport:
  * a named, non-token, same-origin session;
  * not running in unrestricted ``full_access`` mode (the demo switch that turns destination approval and grants off);
  * the governed chat flags are on, the user has a configured provider, that exact endpoint/model is administrator-approved,
    and the user's tool-grant schema/role is valid with no write-capable (proposal) tool granted;
  * a per-user rate limit.
Never: tools, graph/Cypher/file/source context, history, assertions, imports or mapping changes. Prompt and response text
are never logged or audited; the audit rows carry only user, time, preset id, outcome category and request ids.
"""
import logging
import re
import threading
import time
import uuid
from collections import deque

from ..agent_tools import security
from ..agent_tools.capabilities import permitted_tools
from ..agent_tools.security import PolicyStore, BoundIdentity, endpoint_identity
from ..ai import openai_compatible
from ..ai.shared_provider import resolve as governed_credentials

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000
MAX_REPLY_CHARS = 16000
MAX_TOKENS = 1000
TIMEOUT_S = 60
RATE_LIMIT = 10          # turns per user ...
RATE_WINDOW_S = 60       # ... per rolling window, per server process
WRITE_CAPABLE_TOOLS = frozenset({'submit_assertion'})
AUDIT_ACTION = 'workbench_chat'
SYSTEM_PROMPT = ('You are SciDK Chat, a general assistant for research data management. Answer only the question asked. '
                 'You have no access to any SciDK data, files, graph or tools in this conversation, so do not claim '
                 'to have looked anything up. You cannot change anything. Suggestions are text only.')

#: Coarse, non-sensitive, user-facing reasons. Never policy detail, identifiers or secrets.
MESSAGES = {
    'session': 'Sign in with a named account to use Chat.',
    'full_access': 'Chat is unavailable while this instance runs in unrestricted full-access mode.',
    'disabled': 'Chat is not enabled on this instance.',
    'provider': 'No AI provider is configured for your account.',
    'approval': 'Your AI provider has not been approved for Chat by an administrator.',
    'grants': 'Chat access has not been granted to your account.',
    'audit': 'Chat is unavailable because the turn could not be recorded.',
    'rate_limited': 'Too many Chat messages. Wait a minute and try again.',
    'unreachable': "Couldn't reach the AI provider. Try again.",
    'provider_error': 'The AI provider could not answer. Try again later.',
    'refused': 'The AI provider declined to answer this message.',
    'invalid': 'Enter a message of up to %d characters.' % MAX_MESSAGE_CHARS,
}

_lock = threading.Lock()
_turns = {}


def _unavailable(reason, status='unavailable'):
    return {'status': status, 'reason': reason, 'error': MESSAGES[reason]}


def _db(app):
    return app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')


def evaluate(app, identity):
    """Return (reason, credentials, username). reason is None only when every gate passes. Read-only; no network."""
    if security.FULL_ACCESS:
        return 'full_access', None, None
    if app.config.get('SCIDK_GUI_V3_ENABLED') is not True or app.config.get('SCIDK_OVERVIEW_CHAT_ENABLED') is not True:
        return 'disabled', None, None
    if not isinstance(identity, BoundIdentity) or identity.token_id or identity.channel != 'chat':
        return 'session', None, None
    db = _db(app)
    try:
        with PolicyStore(db).connection() as conn:
            row = conn.execute('SELECT username FROM auth_users WHERE id=? AND enabled=1', (identity.user_id,)).fetchone()
    except Exception:
        row = None
    if not row:
        return 'session', None, None
    username = row[0]
    try:
        creds = governed_credentials(db, username)
    except Exception:
        creds = None
    # Local Ollama needs no key; every other preset does.
    if not creds or not creds.get('base_url') or not creds.get('model') or (not creds.get('api_key') and creds.get('preset') != 'ollama'):
        return 'provider', None, username
    try:
        with PolicyStore(db).resolve(identity) as policy:
            if (policy.destination[0] == 'full-access' or endpoint_identity(creds['base_url']) != policy.destination[1]
                    or creds['model'] != policy.destination[2]):
                return 'approval', None, username
            try:
                tools = set()
                for profile in ('overview', 'review'):
                    tools |= permitted_tools(policy, profile)
            except Exception:
                return 'grants', None, username
            if tools & WRITE_CAPABLE_TOOLS:
                return 'grants', None, username
    except Exception:
        return 'approval', None, username
    return None, creds, username


def state(app, identity):
    """Boolean-and-reason view for page rendering. Never raises, never returns credentials or policy."""
    try:
        reason = evaluate(app, identity)[0]
    except Exception:
        reason = 'session'
    return {'ready': reason is None, 'reason': reason or '', 'message': '' if reason is None else MESSAGES[reason]}


def _rate_ok(user_id, now):
    with _lock:
        window = _turns.setdefault(user_id, deque())
        while window and now - window[0] > RATE_WINDOW_S:
            window.popleft()
        if len(window) >= RATE_LIMIT:
            return False
        window.append(now)
        return True


def reset_rate_limits():
    with _lock:
        _turns.clear()


def _audit(app, username, details):
    """Content-free row in the existing auth_audit_log. Raises on failure so callers can fail closed."""
    with PolicyStore(_db(app)).connection(write=True) as conn:
        conn.execute('INSERT INTO auth_audit_log(timestamp,username,action,details,ip_address) VALUES (?,?,?,?,NULL)',
                     (time.time(), username, AUDIT_ACTION, details))


def _token(value, limit=64):
    return re.sub(r'[^A-Za-z0-9_.-]', '', str(value or ''))[:limit] or '-'


def turn(app, identity, body):
    request_id = uuid.uuid4().hex
    if (not isinstance(body, dict) or set(body) != {'message', 'send_question'} or body['send_question'] is not True
            or not isinstance(body['message'], str) or not body['message'].strip()
            or len(body['message']) > MAX_MESSAGE_CHARS):
        return _unavailable('invalid', 'invalid')
    reason, creds, username = evaluate(app, identity)
    if reason:
        return _unavailable(reason)
    if not _rate_ok(identity.user_id, time.time()):
        return _unavailable('rate_limited', 'rate_limited')
    preset = _token(creds.get('preset'), 32)
    try:
        _audit(app, username, 'request_id=%s preset=%s outcome=attempt' % (request_id, preset))
    except Exception:
        return _unavailable('audit')
    outcome, provider_request_id, result = 'error', '-', None
    try:
        # Exactly one system instruction and the typed message. No tools, context, history or other messages.
        answer = openai_compatible.chat_completion(
            creds['base_url'], creds['api_key'], creds['model'],
            [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': body['message']}],
            max_tokens=MAX_TOKENS, timeout=TIMEOUT_S)
        provider_request_id = _token(answer.get('request_id'))
        if answer.get('refusal') or answer.get('finish_reason') == 'content_filter':
            outcome, result = 'refused', _unavailable('refused', 'refused')
        elif not isinstance(answer.get('content'), str) or not answer['content'].strip():
            outcome, result = 'empty', _unavailable('provider_error')
        else:
            # Any tool call the model requests is ignored: none were offered and none are ever executed.
            outcome = 'success'
            result = {'status': 'success', 'reply': answer['content'][:MAX_REPLY_CHARS],
                      'notice': 'AI-generated. Verify important details. No SciDK data was used and nothing was saved.'}
    except openai_compatible.ProviderError as error:
        unreachable = str(error).startswith('Could not reach')
        outcome, result = ('unreachable' if unreachable else 'provider_error'), _unavailable('unreachable' if unreachable else 'provider_error')
    except Exception:
        outcome, result = 'error', _unavailable('provider_error')
    logger.info('workbench_chat request_id=%s outcome=%s', request_id, outcome)
    try:
        _audit(app, username, 'request_id=%s provider_request_id=%s preset=%s outcome=%s'
               % (request_id, provider_request_id, preset, outcome))
    except Exception:
        logger.warning('workbench_chat outcome audit failed request_id=%s', request_id)
    result['request_id'] = request_id
    return result
