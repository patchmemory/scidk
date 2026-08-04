"""HTTP surface for the NIH DMS plan generator.

``GET /api/plugins/nih_dms/draft_plan`` returns the draft as markdown. Only the
HTTP shape lives here: reading the graph is
:mod:`plugins.nih_dms.graph_facts` and the prose is
:mod:`plugins.nih_dms.generator`.

There is deliberately no fixture or placeholder fallback. When Neo4j is not
configured or not reachable the route answers 503 with a message saying so,
because a DMS plan is a document someone submits to a funder — handing back
static prose that *looks* generated is the one failure this plugin must not have.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from scidk.web.decorators import require_role

from . import config as cfg
from .generator import render_plan
from .graph_facts import GraphUnavailable, collect_facts

logger = logging.getLogger(__name__)

bp = Blueprint('nih_dms', __name__, url_prefix='/api/plugins/nih_dms')

# Reads the graph and returns a document. Both roles are listed because
# require_role is a flat membership test — 'admin' does not satisfy
# require_role('user') — and because there is no 'staff' role: auth_users
# constrains role to ('admin','user'), so @require_role('staff') would 403 every
# real user including admins.
_PLAN_ROLES = ('admin', 'user')

#: Filename offered when the draft is downloaded rather than displayed.
DOWNLOAD_FILENAME = 'nih-dms-plan-draft.md'


def _neo4j_client():
    """A connected ``Neo4jClient``, or raise :class:`GraphUnavailable`.

    Both failure modes — nothing configured, and configured but unreachable —
    arrive at the caller as one exception carrying a message worth showing a user.
    """
    from scidk.services.neo4j_client import Neo4jClient, get_neo4j_params

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        raise GraphUnavailable(
            'No Neo4j connection is configured, so there is no graph to generate a plan '
            'from. Configure one in Settings → Connections and try again.'
        )
    try:
        return Neo4jClient(uri, user, password, database, auth_mode).connect()
    except Exception as exc:  # noqa: BLE001 - one answer for every connect failure
        raise GraphUnavailable(f'Could not reach Neo4j at {uri}: {exc}') from exc


def _settings_conn() -> Optional[sqlite3.Connection]:
    """Read-only connection to ``scidk_settings.db``, or None if unavailable.

    The schema layer is a bonus source, not a requirement: without it the draft
    says the schema layer was not consulted rather than implying a clean scan.
    Opened read-only — generating a document must not be able to write settings.
    """
    path = current_app.config.get('SCIDK_SETTINGS_DB')
    if not path:
        return None
    try:
        return sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    except sqlite3.Error as exc:
        logger.warning('nih_dms: settings db %s unreadable: %s', path, exc)
        return None


def _int_arg(name: str) -> Optional[int]:
    """A positive integer query argument, or None when absent or junk."""
    raw = request.args.get(name)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _bool_arg(name: str) -> bool:
    """A truthy query argument, accepting the usual spellings."""
    return str(request.args.get(name, '')).strip().lower() in ('1', 'true', 'yes', 'on')


def generate_markdown(sample_limit: Optional[int] = None,
                      deep: bool = False) -> Tuple[str, dict]:
    """Generate the draft plan and a small summary of what went into it.

    Factored out of the view so it can be called without a request context — by a
    test, or by any future caller that wants the markdown rather than a response.

    Returns:
        ``(markdown, summary)``.

    Raises:
        GraphUnavailable: no graph to read.
    """
    client = _neo4j_client()
    conn = _settings_conn()
    try:
        from scidk.core.settings import get_setting
    except Exception:  # noqa: BLE001 - settings are optional, placeholders are fine
        get_setting = None  # type: ignore[assignment]

    try:
        facts = collect_facts(
            client,
            sqlite_conn=conn,
            setting_getter=get_setting,
            sample_limit=sample_limit,
            deep=deep,
        )
    finally:
        for closeable in (conn, client):
            try:
                if closeable is not None:
                    closeable.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass

    summary = {
        'entity_types': len(facts.label_counts),
        'records': facts.total_nodes,
        'files': facts.file_count,
        'bytes': facts.file_bytes,
        'formats': len(facts.formats),
        'modalities': [finding.source for finding in facts.modalities],
        'phi_detected': facts.has_phi,
        'phi_properties': sorted({hit.property_name for hit in facts.phi_hits}),
        'sampled': facts.format_sample_limit,
        'warnings': list(facts.warnings),
    }
    return render_plan(facts), summary


@bp.get('/draft_plan')
@require_role(*_PLAN_ROLES)
def draft_plan():
    """Return a draft NIH DMS plan generated from the live graph.

    Query args:
        ``format`` — ``markdown`` (default) or ``json``. JSON wraps the same
            markdown alongside the summary, for a caller that wants both.
        ``download`` — truthy serves the markdown as a file attachment.
        ``sample_limit`` — cap the file scan at this many ``:File`` nodes. Faster
            on a very large graph, but the result is a store-order prefix and the
            draft says so; omit it for exact figures.
        ``deep`` — truthy also reads the per-label property schema, which is
            skipped when the cheap checks show it cannot add anything. Costs
            several seconds on a large graph.

    Returns 200 with the markdown, or:
        503 ``neo4j_unavailable`` — no graph is configured or it cannot be
            reached. Deliberately not a static placeholder plan.
        500 ``generation_failed`` — the graph answered but something else broke.
    """
    sample_limit = _int_arg('sample_limit')
    wants_json = str(request.args.get('format', '')).strip().lower() == 'json'

    try:
        markdown, summary = generate_markdown(sample_limit=sample_limit, deep=_bool_arg('deep'))
    except GraphUnavailable as exc:
        message = str(exc)
        if wants_json:
            return jsonify({
                'status': 'error', 'code': 'neo4j_unavailable', 'error': message,
            }), 503
        # Even the markdown response says what went wrong rather than returning a
        # document, so a caller that renders the body cannot mistake it for a plan.
        return (
            f'# Draft plan not generated\n\n{message}\n',
            503,
            {'Content-Type': 'text/markdown; charset=utf-8'},
        )
    except Exception as exc:  # noqa: BLE001 - report, do not emit a half-plan
        logger.exception('nih_dms: plan generation failed')
        message = f'Could not generate a plan from the graph: {exc}'
        if wants_json:
            return jsonify({
                'status': 'error', 'code': 'generation_failed', 'error': message,
            }), 500
        return (
            f'# Draft plan not generated\n\n{message}\n',
            500,
            {'Content-Type': 'text/markdown; charset=utf-8'},
        )

    if wants_json:
        return jsonify({
            'status': 'ok',
            'format': 'markdown',
            'filename': DOWNLOAD_FILENAME,
            'markdown': markdown,
            'summary': summary,
        }), 200

    headers = {'Content-Type': 'text/markdown; charset=utf-8'}
    if _bool_arg('download'):
        headers['Content-Disposition'] = f'attachment; filename="{DOWNLOAD_FILENAME}"'
    return markdown, 200, headers


@bp.get('/config')
@require_role(*_PLAN_ROLES)
def plan_config():
    """Report what the generator looks for and what it has been told.

    Exposed so the Settings UI can show which sharing modes are selectable and
    which property names count as identifiers without duplicating those tables in
    a template.
    """
    return jsonify({
        'status': 'ok',
        'phi_property_names': list(cfg.PHI_PROPERTY_NAMES),
        'modality_properties': list(cfg.MODALITY_PROPERTIES),
        'sharing_modes': cfg.SHARING_MODE_LABELS,
        'settings': {
            'repository': cfg.SETTING_REPOSITORY,
            'retention_years': cfg.SETTING_RETENTION_YEARS,
            'sharing_mode': cfg.SETTING_SHARING_MODE,
            'access_contact': cfg.SETTING_ACCESS_CONTACT,
        },
        'known_formats': len(cfg.FORMAT_STANDARDS),
    }), 200
