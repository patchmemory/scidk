"""Connections API — one endpoint set for every graph backend.

Cycle 4, Task A. Backs the Settings → Connections card grid. Everything here is
driven off :mod:`scidk.services.connection_registry`, so a new backend needs no
change in this file.

``GET  /api/connections``               config for every backend — no network I/O
``POST /api/connections/<id>/test``     one ``RETURN 1`` probe, records last_verified
``GET  /api/connections/<id>/counts``   node and relationship totals, on demand
``GET  /api/connections/concept-graph/export``   portable Concept Graph snapshot
``POST /api/connections/concept-graph/import``   apply one (upsert, non-destructive)

Access matches the sibling routes in :mod:`scidk.web.routes.api_neo4j` and every
existing concept-graph route in :mod:`scidk.web.routes.api_chat` — no role
decorator, and no endpoint ever returns a password. Worth being explicit about what
that means for the two routes below, because one of them writes: with auth enabled,
``auth_middleware.check_auth`` still requires a session, so they are
authenticated-any-role rather than open; with auth disabled they are open, as is
every other write on the Concept Graph card (re-seed, tool toggle, intent edit).
Gating only these two would break them on an auth-disabled deployment while
leaving equivalent writes reachable, which is why the whole family wants one
decision rather than a decorator here. See the Cycle 8 log entry.
"""
from __future__ import annotations

import json
import os

from flask import Blueprint, current_app, jsonify, request

from ...services import connection_registry as registry

bp = Blueprint('api_connections', __name__, url_prefix='/api/connections')

#: Version string ``export_concept_graph`` stamps and ``import`` will accept.
CONCEPT_GRAPH_FORMAT = '1.0'


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


# ─────────────────────────────────────────────
# Concept Graph portability (Cycle 8, Task C)
#
# The Connections page's Concept Graph card shipped in Cycle 4 without these, so
# `export_concept_graph` / `import_concept_graph` had existed since 5d8da6e with no
# way to reach them from the UI. They live here rather than in api_chat because the
# card does, and because import takes a file: the older
# `POST /api/chat/concept-graph/import` accepts a JSON body only, which a file input
# cannot produce without reading the whole snapshot into JavaScript first.
# ─────────────────────────────────────────────

def _concept_driver():
    """The app's concept-graph driver, or None when the graph is unavailable."""
    return current_app.extensions.get('scidk', {}).get('concept_driver')


def _ollama_endpoint() -> str:
    return os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')


@bp.get('/concept-graph/export')
def export_concept_graph_snapshot():
    """Download the Concept Graph as portable JSON.

    Intents, tools, SATISFIES weights and RETRIEVES edges. Embeddings are left out
    — they are regenerated on import, and they are the bulk of the graph.
    """
    driver = _concept_driver()
    if driver is None:
        return jsonify({'status': 'disabled',
                        'error': 'Concept graph not available'}), 501

    try:
        from ...services.concept_graph_service import export_concept_graph

        response = jsonify(export_concept_graph(driver))
        response.headers['Content-Disposition'] = (
            'attachment; filename=concept_graph.json')
        return response, 200
    except Exception as e:
        current_app.logger.error(f"Concept graph export failed: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500


@bp.post('/concept-graph/import')
def import_concept_graph_snapshot():
    """Apply an exported snapshot to this instance.

    Accepts the file from the card's Import input as multipart ``file``, or a raw
    JSON body for ``curl -d @concept_graph.json``.

    The upsert is non-destructive and the weights it brings are provenance-tagged by
    ``import_concept_graph``: a SATISFIES edge that already exists keeps the higher
    of the two weights, so importing a snapshot cannot silently discard feedback
    this instance has learned.
    """
    driver = _concept_driver()
    if driver is None:
        return jsonify({'status': 'disabled',
                        'error': 'Concept graph not available'}), 501

    upload = request.files.get('file')
    if upload is not None:
        try:
            data = json.loads(upload.read().decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            return jsonify({'status': 'error',
                            'error': f'{upload.filename or "file"} is not JSON: {e}'}), 400
    else:
        data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({'status': 'error',
                        'error': 'Expected a JSON object — upload a file as "file" '
                                 'or POST the snapshot as the request body'}), 400

    # Checked before anything is written: an unversioned or foreign document would
    # otherwise import as zero intents and zero tools and report success.
    if data.get('scidk_concept_graph') != CONCEPT_GRAPH_FORMAT:
        return jsonify({
            'status': 'error',
            'error': f'Not a SciDK concept graph export '
                     f'(expected scidk_concept_graph "{CONCEPT_GRAPH_FORMAT}", '
                     f'got {data.get("scidk_concept_graph")!r})',
        }), 400

    try:
        from ...services.concept_graph_service import import_concept_graph

        result = import_concept_graph(driver, data, _ollama_endpoint())
        return jsonify({'status': 'ok', **result}), 200
    except Exception as e:
        current_app.logger.error(f"Concept graph import failed: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
