"""Platform capability API — what this SciDK instance can do.

Cycle 6 Task A. One route so far:

``GET /api/platform/tools`` — the canonical tool registry from
:mod:`scidk.ai.mcp_tools`, optionally narrowed with ``?category=``. This is the
third consumer of that registry; the other two are the MCP server's
``list_tools`` handler and Concept Graph seeding. Nothing here defines a tool,
and no tool should be defined anywhere but the registry.

The response carries the registry's own key names, including snake_case
``input_schema`` — the MCP ``inputSchema`` spelling is applied only at the MCP
protocol boundary in :mod:`scidk.mcp_server`.
"""
import logging

from flask import Blueprint, jsonify, request

from ..decorators import require_role

logger = logging.getLogger(__name__)

bp = Blueprint('api_platform', __name__, url_prefix='/api/platform')

#: Reading the capability list is not privileged — it is the same information the
#: MCP server hands any connected client, and the UI shows it to whoever is
#: logged in. Both roles, per the two-role model in scidk/web/decorators.py.
_READ_ROLES = ('admin', 'user')


@bp.get('/tools')
@require_role(*_READ_ROLES)
def list_tools():
    """Return the platform's tool registry.

    Query params:
        category: Optional filter, one of ``TOOL_CATEGORIES``. An unknown value
            is a 400 rather than an empty list — silently answering ``[]`` would
            read as "this platform has no tools of that kind".

    Returns:
        200 ``{"tools": [{name, description, input_schema, category}, ...],
               "count": int, "categories": [str, ...]}``
        400 ``{"error": str}`` for an unknown category.

    ``categories`` is always the full set, not the set present in ``tools``, so a
    filtered response still tells the UI what else it could ask for.
    """
    from ...ai.mcp_tools import TOOL_CATEGORIES, get_tool_definitions

    category = request.args.get('category') or None

    try:
        tools = get_tool_definitions(category)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({
        'tools': tools,
        'count': len(tools),
        'categories': list(TOOL_CATEGORIES),
    })
