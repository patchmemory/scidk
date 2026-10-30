"""The one LLM provider setting, per user (Task 1).

* ``GET  /api/llm/presets``            Parley / OpenAI / Ollama / custom
* ``GET  /api/llm/settings``           the caller's setting (key shown as a hint only)
* ``PUT  /api/llm/settings``           {preset, base_url, model, api_key?, clear_key?}
* ``GET  /api/llm/models``             models from the endpoint (?base_url= to try another)
* ``POST /api/llm/test``               Test connection: list models, optionally a 1-token turn
* ``POST /api/llm/import-parley-env``  named admin, single-user installs only

Provider settings are per caller. Environment import additionally requires a
named administrator on a single-user installation. Keys never return in full.
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..decorators import require_role

bp = Blueprint('api_llm', __name__, url_prefix='/api/llm')
_ROLES = ('admin', 'user')


@bp.before_request
def credential_boundary():
    # Preserve named header-session clients for personal settings. API tokens,
    # legacy/no-auth sessions and cross-origin browser calls cannot use keys.
    from ..named_session import named_session
    try:
        named_session(allow_header=request.endpoint != 'api_llm.import_parley_env')
    except Exception:
        return jsonify(error='Named authorized session required'), 403, {'Cache-Control': 'no-store'}


@bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


def _db():
    return current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')


def _me():
    return getattr(g, 'scidk_user', None) or ''


@bp.get('/presets')
@require_role(*_ROLES)
def presets():
    from ...ai.provider_settings import presets as _presets
    return jsonify({'presets': _presets()})


@bp.get('/settings')
@require_role(*_ROLES)
def get_settings():
    from ...ai.provider_settings import public_settings
    return jsonify(public_settings(_db(), _me()))


@bp.put('/settings')
@require_role(*_ROLES)
def put_settings():
    from ...ai.provider_settings import save
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or set(body) - {'preset', 'base_url', 'model', 'api_key', 'clear_key'}:
        return jsonify(error='Invalid provider settings'), 400
    try:
        out = save(_db(), _me(), preset=body.get('preset'), base_url=body.get('base_url'),
                   model=body.get('model'), api_key=body.get('api_key') or None,
                   clear_key=bool(body.get('clear_key')))
    except (ValueError, TypeError, AttributeError):
        return jsonify({'error': 'Invalid provider settings'}), 400
    return jsonify(out)


def _endpoint_from_request():
    """base_url/api_key to try: the request's (an unsaved form), else the stored ones."""
    from ...ai.provider_settings import stored_endpoint
    body = request.get_json(silent=True) or {}
    # The form also sends `preset`; it plays no part in trying an endpoint, so it is ignored.
    if not isinstance(body, dict) or set(body) - {'preset', 'base_url', 'api_key', 'model'}:
        raise ValueError()
    stored = stored_endpoint(_db(), _me())
    base_url = (body.get('base_url') or request.args.get('base_url') or stored.get('base_url') or '').strip()
    # The stored key only ever goes to the stored endpoint, never to a URL
    # typed into the form but not yet saved.
    same_host = base_url.rstrip('/') == (stored.get('base_url') or '').rstrip('/')
    api_key = body.get('api_key') or (stored.get('api_key') if same_host else None)
    model = (body.get('model') or stored.get('model') or '').strip()
    return base_url, api_key, model


@bp.get('/models')
@require_role(*_ROLES)
def models():
    from ...ai.openai_compatible import ProviderError, list_models
    try:
        base_url, api_key, _ = _endpoint_from_request()
    except (ValueError, TypeError, AttributeError):
        return jsonify(error='Invalid provider request', models=[]), 400
    if not base_url:
        return jsonify({'error': 'Set a base URL first', 'models': []}), 400
    try:
        return jsonify({'models': list_models(base_url, api_key)})
    except Exception:
        return jsonify({'error': 'Provider unavailable; check endpoint and your credential.', 'models': []}), 502


@bp.post('/test')
@require_role(*_ROLES)
def test_connection():
    """Lists models; with a model set, also runs a tiny completion so a bad
    model id or an exhausted budget shows up here rather than in the chat."""
    from ...ai.openai_compatible import ProviderError, chat_completion, list_models
    import re
    try:
        base_url, api_key, model = _endpoint_from_request()
    except (ValueError, TypeError, AttributeError):
        return jsonify(ok=False, error='Invalid provider request'), 400
    if not base_url:
        return jsonify({'ok': False, 'error': 'Set a base URL first'}), 400
    out = {'ok': False, 'base_url': base_url}
    try:
        names = list_models(base_url, api_key)
        out['models'] = len(names)
        if model:
            if names and model not in names:
                out['error'] = f'Model {model!r} is not offered by this endpoint'
                return jsonify(out), 200
            turn = chat_completion(base_url, api_key, model,
                                   [{'role': 'user', 'content': 'Reply with the single word: ok'}],
                                   max_tokens=256, timeout=60)
            out.update({'model': model, 'refusal': bool(turn.get('refusal')),
                        'finish_reason': turn.get('finish_reason') if turn.get('finish_reason') in
                        {'stop', 'length', 'content_filter'} else 'unknown'})
            if re.fullmatch(r'[0-9]{1,10}(\.[0-9]{1,10})?', str(turn.get('cost', ''))):
                out['cost'] = str(turn['cost'])
        out['ok'] = True
    except Exception:
        out['error'] = 'Provider unavailable; check endpoint and your credential.'
    return jsonify(out), 200


def _single_user_install() -> bool:
    from ...core.auth import get_auth_manager
    auth = get_auth_manager(db_path=_db())
    try:
        return auth.is_enabled() and len(auth.list_users(include_disabled=True)) == 1
    finally:
        auth.close()


@bp.post('/import-parley-env')
@require_role('admin')
def import_parley_env():
    """Explicit only. On a shared server `parley env` would hand every user the
    admin's key and billing, so this refuses unless the install has one user."""
    from ...ai.provider_settings import PARLEY_DEFAULT_BASE_URL, read_parley_env, save
    # require_role intentionally bypasses checks on no-auth installations. OS
    # credentials must never be imported through that bootstrap bypass or tokens.
    from ...core.auth import get_auth_manager
    auth = get_auth_manager(db_path=_db())
    try:
        token = request.cookies.get('scidk_session')
        user = auth.get_session_user(token) if token and auth.is_enabled() else None
        if (request.headers.get('Authorization') or not user or user.get('role') != 'admin'
                or auth.is_session_locked(token)
                or request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none')
                or (request.headers.get('Origin') and request.headers['Origin'].rstrip('/') != request.host_url.rstrip('/'))):
            return jsonify(error='Named administrator session required'), 403
    finally:
        auth.close()
    if not _single_user_install():
        return jsonify({'error': 'Importing from `parley env` is only offered on a single-user install. '
                                 'Paste your own key instead.'}), 403
    body = request.get_json(silent=True) or {}
    if (not isinstance(body, dict) or set(body) - {'model'}
            or (body.get('model') is not None and not isinstance(body['model'], str))):
        return jsonify(error='Invalid provider request'), 400
    try:
        env = read_parley_env()
        out = save(_db(), _me(), preset='parley',
                   base_url=env.get('PARLEY_BASE_URL') or PARLEY_DEFAULT_BASE_URL,
                   model=body.get('model'), api_key=env['PARLEY_API_KEY'])
    except Exception:
        return jsonify({'error': 'Parley environment import unavailable'}), 400
    return jsonify(out)
