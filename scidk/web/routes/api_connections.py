"""Connections API — one endpoint set for every graph backend.

Cycle 4, Task A. Backs the Settings → Connections card grid. Everything here is
driven off :mod:`scidk.services.connection_registry`, so a new backend needs no
change in this file.

``GET  /api/connections``               config for every backend — no network I/O
``POST /api/connections/<id>/test``     one ``RETURN 1`` probe, records last_verified
``GET  /api/connections/<id>/counts``   node and relationship totals, on demand

Access matches the sibling routes in :mod:`scidk.web.routes.api_neo4j` — no role
decorator, and no endpoint ever returns a password.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from ...services import connection_registry as registry

bp = Blueprint('api_connections', __name__, url_prefix='/api/connections')


@bp.get('')
def list_connections():
    """Every graph backend with its current configuration.

    Config read only — no backend is dialled, so this stays fast on page load
    even when a backend is down or unreachable.
    """
    return jsonify({'backends': registry.describe_all()}), 200


@bp.post('/<backend_id>/test')
def test_connection(backend_id: str):
    """Verify connectivity to one backend via its own client factory."""
    backend = registry.get_backend(backend_id)
    if backend is None:
        return jsonify({'error': f'Unknown backend: {backend_id}'}), 404

    result = registry.verify(backend)
    result['id'] = backend.id
    result['last_verified'] = registry.get_last_verified(backend.id)
    # 200 either way: "reachable?" is the answer, not the request's success.
    return jsonify(result), 200


@bp.get('/<backend_id>/counts')
def connection_counts(backend_id: str):
    """Node and relationship totals for one backend.

    On demand rather than on page load — these are full-store aggregates and are
    not cheap on a large graph.
    """
    backend = registry.get_backend(backend_id)
    if backend is None:
        return jsonify({'error': f'Unknown backend: {backend_id}'}), 404

    result = registry.counts(backend)
    result['id'] = backend.id
    return jsonify(result), 200
