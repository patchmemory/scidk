"""RO-Crate build routes — the Files page entry point (Cycle 7, Task B).

``POST /build`` turns a Files page selection into a crate on disk;
``GET /<crate_id>/metadata`` hands the document back as a download. All of the
mapping lives in :mod:`scidk.rocrate_bridge`; this module is the HTTP shape
around it — validating the request, resolving a Neo4j connection, and turning the
three ways this can legitimately fail into three distinguishable answers.

Crates are written under ``SCIDK_ROCRATE_DIR`` (default ``~/.scidk/crates``),
the same store ``POST /api/ro-crates/referenced`` uses, so a crate built here can
also be fetched as a zip through the existing
``POST /api/ro-crates/<crate_id>/export?target=zip``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request, send_file

from ..decorators import require_role
from ...rocrate_bridge import METADATA_FILENAME, build_from_selection, crate_metadata_path

bp = Blueprint('api_rocrate', __name__, url_prefix='/api/rocrate')

# Building a crate reads the graph and writes a file the caller then downloads —
# not an admin action, but not an open one either. Both roles are listed because
# there are only two and require_role is a flat membership test: 'admin' does not
# satisfy @require_role('user'), and there is no 'staff' role at all (auth_users
# constrains role to ('admin','user'), core/auth.py:60). The Cycle 7 task block
# says "staff or admin"; that role does not exist and would 403 everyone.
_BUILD_ROLES = ('admin', 'user')

#: Crate ids are ours to mint, so they can be held to a shape that cannot
#: traverse out of the crate store.
_CRATE_ID_RE = re.compile(r'^[0-9a-f]{8,32}$')

#: Offered by the Files page panel. "Other" is a free-text field there, so any
#: string reaches us; this list is what the UI suggests, not a whitelist to
#: enforce — refusing a licence a lab actually uses would be unhelpful.
SUGGESTED_LICENSES = ('CC BY 4.0', 'CC BY-NC 4.0', 'MIT')


class Neo4jUnavailable(RuntimeError):
    """No usable graph connection. A 503, not a bug in the request."""


def _crate_root() -> Path:
    return Path(os.environ.get('SCIDK_ROCRATE_DIR') or os.path.expanduser('~/.scidk/crates'))


def _crate_dir(crate_id: str) -> Path:
    """The directory for ``crate_id``, or raise if the id is not one of ours."""
    if not _CRATE_ID_RE.match(crate_id or ''):
        raise ValueError('invalid crate id')
    root = _crate_root().resolve()
    target = (root / crate_id).resolve()
    if root != target.parent:
        raise ValueError('invalid crate id')
    return target


def _neo4j_client():
    """A connected :class:`~scidk.services.neo4j_client.Neo4jClient`.

    Factored out as a module function so tests can substitute a fake graph
    without standing up a database, and so both failure modes — not configured,
    and configured but unreachable — arrive at the caller as one exception with a
    message worth showing a user.
    """
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        raise Neo4jUnavailable(
            'No Neo4j connection is configured, so there is no graph to build a crate from. '
            'Configure one in Settings → Connections.'
        )
    try:
        return Neo4jClient(uri, user, password, database, auth_mode).connect()
    except Exception as exc:  # noqa: BLE001 - one answer for every connect failure
        raise Neo4jUnavailable(f'Could not reach Neo4j at {uri}: {exc}') from exc


def _selection_from_request(body: Dict[str, Any]) -> List[str]:
    """The selected identifiers, however the caller chose to name them.

    The Files page sends ``paths``; a graph-side caller sends ``node_ids`` of
    Neo4j elementIds. The bridge resolves either, so both keys are accepted and
    merged rather than making the UI care which kind it holds.
    """
    selection: List[str] = []
    for key in ('node_ids', 'paths', 'items'):
        for value in body.get(key) or []:
            text = str(value).strip()
            if text and text not in selection:
                selection.append(text)
    return selection


@bp.post('/build')
@require_role(*_BUILD_ROLES)
def build_crate():
    """Build an RO-Crate from a Files page selection.

    Body:
        ``paths`` / ``node_ids`` (list) — the selection. Paths or elementIds.
        ``name`` (str) — crate title. Defaults to the first selected item's name.
        ``license`` (str) — see :data:`SUGGESTED_LICENSES`.
        ``description`` (str, optional)
        ``include_files`` (bool) — default true. False builds a metadata-only
        crate: it describes the files without pointing at them.

    Returns 200 with ``{status, crate_id, download_url, entities, ...}``, or:
        400 ``empty_selection`` — nothing was selected.
        400 ``nothing_resolved`` — things were selected, but none of them are in
            the graph. Almost always "scanned but not committed yet", which is
            worth saying rather than handing back an empty crate that looks fine
            until someone opens it.
        503 ``neo4j_unavailable`` — no graph to read.
    """
    body = request.get_json(silent=True) or {}
    selection = _selection_from_request(body)
    if not selection:
        return jsonify({
            'status': 'error',
            'code': 'empty_selection',
            'error': 'Select at least one file or folder before building a crate.',
        }), 400

    default_name = Path(selection[0].rstrip('/')).name or selection[0]
    name = str(body.get('name') or default_name).strip() or default_name
    license_name = str(body.get('license') or '').strip() or None
    description = str(body.get('description') or '').strip() or None
    include_files = body.get('include_files')
    include_files = True if include_files is None else bool(include_files)

    crate_id = uuid.uuid4().hex[:12]
    out_dir = _crate_dir(crate_id)

    try:
        client = _neo4j_client()
    except Neo4jUnavailable as exc:
        return jsonify({'status': 'error', 'code': 'neo4j_unavailable', 'error': str(exc)}), 503

    try:
        text = build_from_selection(
            selection, client, str(out_dir),
            name=name, license=license_name, description=description,
            include_files=include_files,
        )
    except Exception as exc:  # noqa: BLE001 - a query failure is the user's answer
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({'status': 'error', 'code': 'build_failed', 'error': str(exc)}), 500
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass

    # The metadata descriptor and the root Dataset are always present; anything
    # beyond them is a resolved node.
    entities = max(len(json.loads(text).get('@graph') or []) - 2, 0)
    if entities == 0:
        shutil.rmtree(out_dir, ignore_errors=True)
        return jsonify({
            'status': 'error',
            'code': 'nothing_resolved',
            'error': (
                f'None of the {len(selection)} selected item(s) are in the graph, so there is '
                'nothing to describe. Scan them and commit the scan to Neo4j first.'
            ),
            'selected': len(selection),
        }), 400

    return jsonify({
        'status': 'ok',
        'crate_id': crate_id,
        'name': name,
        'license': license_name,
        'include_files': include_files,
        'entities': entities,
        'selected': len(selection),
        'filename': METADATA_FILENAME,
        'download_url': f'/api/rocrate/{crate_id}/metadata',
        'path': str(out_dir),
    }), 200


@bp.get('/<crate_id>/metadata')
@require_role(*_BUILD_ROLES)
def download_crate_metadata(crate_id: str):
    """Download a built crate's ``ro-crate-metadata.json``."""
    try:
        out_dir = _crate_dir(crate_id)
    except ValueError:
        return jsonify({'status': 'error', 'error': 'invalid crate id'}), 400

    target = crate_metadata_path(out_dir)
    if not target.is_file():
        return jsonify({'status': 'error', 'error': 'crate not found'}), 404

    return send_file(
        target,
        mimetype='application/ld+json',
        as_attachment=True,
        download_name=METADATA_FILENAME,
    )
