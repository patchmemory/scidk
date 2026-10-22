"""Agent adapters over the shared tool layer (Parley Task 5).

* ``GET  /api/agent/tools``            the registry (as /api/platform/tools, minus chat-only tools)
* ``POST /api/agent/tools/<name>``     run one tool; body is its arguments
* ``GET  /api/agent/functions.json``   OpenAI-style tool definitions (what the chat sends to Parley)
* ``GET  /api/agent/openapi.json``     OpenAPI 3.1 for the run routes (ChatGPT Actions, other agents)
* ``GET/PUT /api/agent/sharing``       per-property sharing_mode (raw / hidden)

Nothing here defines or runs a tool itself: every run goes through
``agent_tools.registry.run_tool``, which applies ``filter_for_agent``. Auth is the
app's own: a session or a per-user Bearer API token, same roles as the UI.
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..decorators import require_role

bp = Blueprint('api_agent', __name__, url_prefix='/api/agent')

_READ_ROLES = ('admin', 'user')


def _public(tool):
    return {k: tool[k] for k in ('name', 'description', 'input_schema', 'category')}


@bp.get('/tools')
@require_role(*_READ_ROLES)
def list_tools():
    from ...agent_tools.registry import CHAT_ONLY, TOOL_DEFINITIONS
    tools = [_public(t) for t in TOOL_DEFINITIONS if t['name'] not in CHAT_ONLY]
    return jsonify({'tools': tools, 'count': len(tools)})


@bp.post('/tools/<name>')
@require_role(*_READ_ROLES)
def run(name: str):
    from ...agent_tools.context import context_from_app
    from ...agent_tools.registry import CHAT_ONLY, run_tool, tool_names
    if name not in tool_names() or name in CHAT_ONLY:
        return jsonify({'status': 'error', 'error': f'Unknown tool: {name}'}), 404
    body = request.get_json(silent=True)
    if body is None and request.data:
        return jsonify({'status': 'error', 'error': 'Body must be JSON'}), 400
    ctx = context_from_app(current_app, getattr(g, 'scidk_user', None))
    result = run_tool(name, body or {}, ctx)
    return jsonify(result), 200


@bp.get('/functions.json')
@require_role(*_READ_ROLES)
def functions():
    from ...agent_tools.registry import openai_functions
    return jsonify(openai_functions())


@bp.get('/openapi.json')
def openapi():
    """No role check: it only describes the API. With auth on, the app middleware still
    requires a session or token, so a hosted importer needs one too."""
    from ...agent_tools.registry import CHAT_ONLY, TOOL_DEFINITIONS
    base = request.host_url.rstrip('/') + (request.script_root or '')
    paths = {}
    for t in TOOL_DEFINITIONS:
        if t['name'] in CHAT_ONLY:
            continue
        paths[f"/api/agent/tools/{t['name']}"] = {'post': {
            'operationId': t['name'],
            'summary': t['description'][:120],
            'description': t['description'],
            'requestBody': {'required': False, 'content': {'application/json': {'schema': t['input_schema']}}},
            'responses': {'200': {'description': 'Tool result. status is success, error, refused or '
                                                 'not_profiled; a disclosure note means data was withheld.',
                                  'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ToolResult'}}}},
                          '401': {'description': 'Missing or invalid token'}},
        }}
    return jsonify({
        'openapi': '3.1.0',
        'info': {'title': 'SciDK agent tools', 'version': '1.0.0',
                 'description': 'Read-only tools over this SciDK instance. Results are filtered by SciDK '
                                'sharing settings before they are returned.'},
        'servers': [{'url': base}],
        'paths': paths,
        'components': {
            'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer'}},
            'schemas': {'ToolResult': {'type': 'object', 'properties': {
                'status': {'type': 'string'}, 'error': {'type': 'string'},
                'disclosure': {'type': 'object'}}, 'additionalProperties': True}},
        },
        'security': [{'bearerAuth': []}],
    })


@bp.get('/sharing')
@require_role(*_READ_ROLES)
def sharing_list():
    from ...agent_tools import disclosure
    db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return jsonify({'modes': disclosure.list_modes(db), 'settable': list(disclosure.SETTABLE_MODES)})


@bp.put('/sharing')
@require_role('admin')
def sharing_set():
    """Body ``{label, property, sharing_mode}``. ``raw`` removes the setting."""
    from ...agent_tools import disclosure
    from ...agent_tools.tools_graph import _validate_identifier
    body = request.get_json(silent=True) or {}
    label, prop, mode = (str(body.get(k) or '').strip() for k in ('label', 'property', 'sharing_mode'))
    for value, kind in ((label, 'label'), (prop, 'property')):
        bad = _validate_identifier(value, kind) if value else f'{kind} is required'
        if bad:
            return jsonify({'error': bad}), 400
    db = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    try:
        disclosure.set_mode(db, label, prop, mode, getattr(g, 'scidk_user', None))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'status': 'ok', 'label': label, 'property': prop, 'sharing_mode': mode})
