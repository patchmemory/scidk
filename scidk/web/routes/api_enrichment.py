"""HTTP entry point for the post-scan enrichment dispatcher.

The work itself is :func:`scidk.services.enrichment_service.run_enrichment`;
this is the request shape around it. The same run is available offline as
``python -m scidk.services.enrichment_service``, which is the better choice for
a full sweep — enrichment over an unfiltered 27M-row index takes minutes and
holds a request open for all of them. Scope a web-triggered run with
``scan_id``.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..decorators import require_role

bp = Blueprint('api_enrichment', __name__, url_prefix='/api/enrichment')

#: Enrichment writes: it MERGEs domain nodes and provenance edges into Neo4j
#: and updates rows in files.db. That puts it with the other write paths, admin
#: only. Note this is deliberately NOT @require_role('staff') — there is no
#: staff role (auth_users constrains role to ('admin','user'), core/auth.py:60)
#: and require_role is a flat membership test, so 'staff' would 403 every user
#: including admins. The same mistake shipped once in Cycle 2 Task E.
_RUN_ROLES = ('admin',)

#: Bounded so a typo cannot ask for a multi-hour request.
_MAX_LIMIT = 10_000


@bp.route('/run', methods=['POST'])
@require_role(*_RUN_ROLES)
def run_enrichment_route():
    """Run the dispatcher. All body fields optional.

    Body: ``{"interpreter": str, "limit": int, "scan_id": str, "force": bool}``
    """
    from ...services.enrichment_service import run_enrichment

    body = request.get_json(silent=True) or {}

    try:
        limit = int(body.get('limit', 500))
    except (TypeError, ValueError):
        return jsonify({'error': 'limit must be an integer'}), 400
    if limit < 1 or limit > _MAX_LIMIT:
        return jsonify({'error': f'limit must be between 1 and {_MAX_LIMIT}'}), 400

    interpreter = body.get('interpreter')
    if interpreter is not None:
        from ...interpreters.registry import get_interpreter_by_id, list_interpreter_ids
        if get_interpreter_by_id(interpreter) is None:
            # An unknown id would otherwise match no row and report a clean
            # zero, which reads exactly like "nothing left to enrich".
            return jsonify({
                'error': f'unknown interpreter: {interpreter}',
                'known_interpreters': list_interpreter_ids(),
            }), 400

    try:
        result = run_enrichment(
            interpreter_id=interpreter,
            limit=limit,
            scan_id=body.get('scan_id'),
            force=bool(body.get('force')),
        )
    except Exception as e:
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 500

    return jsonify(result), 200


@bp.route('/interpreters', methods=['GET'])
@require_role('admin', 'user')
def list_interpreters_route():
    """Registry ids accepted by ``interpreter``, with their dispatch kind."""
    from ...interpreters.registry import get_interpreter_by_id, list_interpreter_ids

    return jsonify({'interpreters': [
        {
            'id': interpreter_id,
            'name': getattr(get_interpreter_by_id(interpreter_id), 'name', ''),
            'dispatch': getattr(get_interpreter_by_id(interpreter_id), 'dispatch', 'file'),
            'extensions': list(getattr(get_interpreter_by_id(interpreter_id), 'extensions', [])),
        }
        for interpreter_id in list_interpreter_ids()
    ]}), 200
