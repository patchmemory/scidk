"""Blueprint for Collection → Dataset routes (Task group I).

The Collection panel accumulates files across folders; these two routes are
what it does with them:

* ``POST /api/collections`` and ``POST /api/datasets/collections`` — write the
  collection as a ``:Collection`` node with ``INCLUDES`` edges to its members
  (datasets by reference, folders, files, context nodes).
* ``POST /api/collections/sweep`` — ask whether the collection is a *complete*
  Dataset, or a partial copy of one the graph already knows.

Two constraints from the audit shape all of the Cypher here:

1. **File nodes are keyed by ``(path, host)``, not path alone.** The composite
   index only applies when both are matched; the path-only form is a label scan
   over every File node. Every match below supplies both.
2. **File nodes spell it ``filename`` and ``size_bytes``**, not ``name`` and
   ``size``. ``name`` exists, but on ``Folder`` and ``Dataset``. Cypher written
   against ``f.name`` returns nothing rather than erroring, which is the worst
   possible failure mode for a completeness check.

The collision with the legacy ``GET /api/datasets`` (an unrelated per-file
concept keyed by checksum, in ``api_files.py``) is why the write route lives at
``/api/datasets/collections`` rather than ``POST /api/datasets``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from flask import Blueprint, current_app, jsonify, request

from ...core.host_id import PROVIDER_IDS, host_id_for, is_host_label
from ..decorators import require_role

bp = Blueprint('annotation', __name__, url_prefix='/api')

#: Writing a Dataset creates graph nodes and edges; reading the sweep does not.
_WRITE_ROLES = ('admin',)
_READ_ROLES = ('admin', 'user')

#: One collection, one round trip. Past this the UNWIND parameter stops being a
#: reasonable request body.
_MAX_FILES = 5_000


class Neo4jUnavailable(RuntimeError):
    """Neo4j is not configured, or is configured and unreachable."""


def _neo4j_client():
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        raise Neo4jUnavailable(
            'No Neo4j connection is configured, so there is no graph to write to. '
            'Configure one in Settings → Connections.'
        )
    try:
        return Neo4jClient(uri, user, password, database, auth_mode).connect()
    except Exception as exc:  # noqa: BLE001 - one answer for every connect failure
        raise Neo4jUnavailable(f'Could not reach Neo4j at {uri}: {exc}') from exc


def _entry_host(entry: Dict[str, Any]) -> str:
    """The committed ``host`` label for one request entry, or '' if unknown.

    Derived server-side with :func:`host_id_for`, the function commit uses, so a
    Collect of a committed file lands on the same ``(path, host)`` node. The page
    sends ``provider_id`` + ``root_id`` (and ``scan_id`` in Index view, whose
    scan may be on another drive than the sidebar cursor). A ``host`` that is
    already a label is kept; a bare provider id in ``host`` / ``provider`` (what
    the page used to send) is treated as ``provider_id``.
    """
    scan_id = str(entry.get('scan_id') or '').strip()
    if scan_id:
        try:
            scan = current_app.extensions['scidk'].get('scans', {}).get(scan_id) or {}
        except Exception:
            scan = {}
        if is_host_label(scan.get('host_id')):
            return scan['host_id']

    root_id = str(entry.get('root_id') or '').strip()
    provider_id = str(entry.get('provider_id') or '').strip()
    host = str(entry.get('host') or entry.get('provider') or '').strip()
    if not provider_id and host in PROVIDER_IDS:
        provider_id = host
    if provider_id:
        if provider_id != 'local_fs' and not root_id:
            return ''
        return host_id_for(provider_id, root_id)
    return host if is_host_label(host) else ''


def _expand_folder(folder: str) -> Tuple[List[Dict[str, str]], bool]:
    """Files under ``folder`` in the scan index, and whether the index knows it.

    A folder is not a File, so it can't be a Dataset member itself (it used to
    become a ``:File {stub: true}``). Its indexed files are added instead: a range
    scan on ``idx_files_path``, deduplicated across scans, capped one past
    ``_MAX_FILES`` so the caller can refuse an oversized collection.
    """
    from ...core import path_index_sqlite as pix
    folder = folder.rstrip('/')
    try:
        conn = pix.connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT path, name FROM files "
                "WHERE path > ? AND path < ? AND type = 'file' LIMIT ?",
                (folder + '/', folder + '0', _MAX_FILES + 1),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return [], False
    return [{'path': r[0], 'filename': r[1]} for r in rows], bool(rows)


def _normalise_files(raw: Any) -> Tuple[List[Dict[str, str]], List[str]]:
    """Request file entries as ``{path, filename, host}``, plus any complaints.

    Accepts the structured form the page sends —
    ``{"name", "path", "provider_id", "root_id", "scan_id"?, "type"?}`` — where
    ``path`` may be either the file's own full path or the folder holding it.
    Both spellings appear in the page (the Collection stores a folder in
    ``path``; a selection id is a full path), so the two are reconciled here
    rather than in four call sites: if ``path`` does not already end in the
    filename, the filename is appended.

    ``type: "folder"`` entries are expanded to their indexed files (see
    :func:`_expand_folder`); a folder the index has never seen is reported in
    the complaints and skipped.
    """
    files: List[Dict[str, str]] = []
    problems: List[str] = []
    seen = set()

    def _add(path: str, filename: str, host: str) -> None:
        key = (path, host)
        if key not in seen:
            seen.add(key)
            files.append({'path': path, 'filename': filename, 'host': host})

    for i, entry in enumerate(raw or []):
        if not isinstance(entry, dict):
            problems.append(f'files[{i}] is not an object')
            continue
        filename = str(entry.get('name') or entry.get('filename') or '').strip()
        path = str(entry.get('path') or '').strip()

        if not filename and path:
            filename = path.rstrip('/').rsplit('/', 1)[-1]
        if not filename:
            problems.append(f'files[{i}] has neither name nor path')
            continue
        if not path:
            problems.append(f'files[{i}] ({filename}) has no path')
            continue
        if not path.endswith('/' + filename) and path != filename:
            path = path.rstrip('/') + '/' + filename

        host = _entry_host(entry)
        if not host:
            problems.append(f'files[{i}] ({filename}) has no provider_id/root_id to place it on a host')
            continue

        if str(entry.get('type') or '').lower() == 'folder':
            members, known = _expand_folder(path)
            if not known:
                problems.append(f'folder {path} has no scanned files; scan it first, or select its files')
            for m in members:
                _add(m['path'], m['filename'], host)
            continue

        _add(path, filename, host)

    return files, problems


# ── I1 — save a collection ──────────────────────────────────────────────────

def _created_by() -> str:
    from flask import g
    return str(getattr(g, 'scidk_user', '') or 'unknown')


def _save_collection_request(body: Dict[str, Any], raw_members: Any):
    """Shared by the two POST routes: validate, MERGE the Collection, report counts."""
    from ...services import collection_service as cs

    name = str(body.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400

    members, problems = cs.normalise_members(raw_members, _entry_host)
    total = cs.member_count(members)
    if not total:
        return jsonify({'error': 'members is required', 'problems': problems}), 400
    if total > _MAX_FILES:
        return jsonify({'error': f'too many members ({total}); the maximum is {_MAX_FILES}'}), 400

    try:
        client = _neo4j_client()
    except Neo4jUnavailable as e:
        return jsonify({'error': str(e)}), 503

    add_to_existing = bool(body.get('add_to_existing'))
    try:
        existing = cs.find_by_name(client, name)
        if existing and not add_to_existing:
            return jsonify({
                'error': f'A Collection named "{name}" already exists',
                'exists': True,
                'name': name,
                'members': int(existing[0].get('members') or 0),
            }), 409
        result = cs.save_collection(
            client, name=name, description=str(body.get('description') or '').strip() or None,
            created_by=_created_by(), members=members,
            collection_id=existing[0].get('id') if existing else None)
    except Exception as e:  # noqa: BLE001 - the write is the route's whole job
        return jsonify({'error': f'{type(e).__name__}: {e}'}), 502
    finally:
        try:
            client.close()
        except Exception:
            pass

    out: Dict[str, Any] = {
        'status': 'ok',
        'collection_id': result['id'],
        'name': name,
        'created': not existing,
        'linked': result['linked'],
        'files_linked': result['linked']['file'],
    }
    if result['not_found']:
        out['not_found'] = result['not_found']
    if problems:
        # Reported alongside a successful write rather than instead of one.
        out['problems'] = problems
    return jsonify(out), 200


@bp.post('/collections')
@require_role(*_WRITE_ROLES)
def api_collections_create():
    """Write a ``:Collection`` with ``INCLUDES`` edges to its members.

    Body: ``{name, description?, add_to_existing?, members: [...]}`` where each
    member is ``{kind: dataset|folder|file|context, ...}``:

    * ``dataset`` — ``scan_id``, ``root_path`` and optional ``profile``,
      ``file_count``, ``bytes``: joins by reference (a ``:Dataset`` keyed on
      ``(scan_id, root_path)``, ``source='files.db'``); no file rows are copied.
    * ``folder`` / ``file`` — ``path``, ``name`` and a host (``host``, or
      ``provider_id`` + ``root_id``).
    * ``context`` — ``label`` (e.g. Request, Study, Sample, SampleType,
      Investigator, Lab) and the node's element ``id``; the node must already exist.

    Graph writes are MERGE only. A name already taken answers 409 unless
    ``add_to_existing`` is set.
    """
    body = request.get_json(silent=True) or {}
    return _save_collection_request(body, body.get('members'))


@bp.post('/datasets/collections')
@require_role(*_WRITE_ROLES)
def api_datasets_from_collection():
    """The Files-page Collect panel's route: a collection of files and folders.

    Used to write a ``:Dataset`` with ``CONTAINS`` edges. It now writes a
    ``:Collection`` with ``INCLUDES`` edges (a Dataset is the smallest meaningful
    unit; a Collection is a purpose-built grouping). Entries are
    ``{name, path, provider_id, root_id, scan_id?, type?}``; ``type: "folder"``
    makes a ``:Folder`` member, anything else a ``:File``. Existing ``:Dataset``
    nodes written by the old route are left alone.
    """
    body = request.get_json(silent=True) or {}
    members = []
    for entry in body.get('files') or []:
        if not isinstance(entry, dict):
            members.append(entry)
            continue
        path = str(entry.get('path') or '').strip()
        filename = str(entry.get('name') or entry.get('filename') or '').strip()
        if not filename and path:
            filename = path.rstrip('/').rsplit('/', 1)[-1]
        if path and filename and not path.endswith('/' + filename) and path != filename:
            path = path.rstrip('/') + '/' + filename
        members.append(dict(entry, kind='folder' if str(entry.get('type') or '').lower() == 'folder' else 'file',
                            path=path, name=filename))
    return _save_collection_request(body, members)


@bp.get('/collections')
@require_role(*_READ_ROLES)
def api_collections_list():
    """Existing collections: id, name, description, created_by, created_at, member count."""
    from ...services import collection_service as cs
    try:
        client = _neo4j_client()
    except Neo4jUnavailable as e:
        return jsonify({'error': str(e), 'collections': []}), 503
    try:
        return jsonify({'collections': cs.list_collections(client)}), 200
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': f'{type(e).__name__}: {e}', 'collections': []}), 502
    finally:
        try:
            client.close()
        except Exception:
            pass


# ── I2 — completeness sweep ────────────────────────────────────────────────

@bp.post('/collections/sweep')
@require_role(*_READ_ROLES)
def api_collections_sweep():
    """Datasets this collection only partly covers.

    Answers "you have 3 of the 5 files in *AIPT Vevo June 2026* — do you want
    the other two?". Returns ``{"gaps": []}`` when every overlapping Dataset is
    fully represented, when nothing overlaps, or when Neo4j is not configured —
    the panel opens on every collection, and a missing graph is not something to
    interrupt it over.
    """
    body = request.get_json(silent=True) or {}
    files, _problems = _normalise_files(body.get('files'))
    if not files:
        return jsonify({'gaps': []}), 200

    try:
        client = _neo4j_client()
    except Neo4jUnavailable:
        return jsonify({'gaps': []}), 200

    # Matched on (path, host) pairs rather than bare filenames. Filenames are
    # not unique across a 5.5M-node graph — `session_001.fcs` recurs constantly
    # — and File.filename carries no index, so matching on it is both ambiguous
    # and a full label scan. Paths use the composite index.
    query = (
        "UNWIND $files AS row "
        "MATCH (f:File {path: row.path, host: row.host})<-[:CONTAINS]-(d:Dataset) "
        "WITH d, count(DISTINCT f) AS present "
        "MATCH (d)-[:CONTAINS]->(all_f:File) "
        "WITH d, present, count(DISTINCT all_f) AS total, collect(DISTINCT all_f) AS members "
        "WHERE present < total "
        "UNWIND members AS m "
        "WITH d, present, total, m "
        "WHERE NOT [m.path, m.host] IN $keys "
        "RETURN d.name AS dataset_name, d.path AS path, d.host AS host, "
        "       present, total, collect(DISTINCT m.filename)[..25] AS missing "
        "ORDER BY (total - present) DESC "
        "LIMIT 5"
    )
    try:
        records = client.execute_read(query, {
            'files': files,
            'keys': [[f['path'], f['host']] for f in files],
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({'error': f'{type(e).__name__}: {e}', 'gaps': []}), 502
    finally:
        try:
            client.close()
        except Exception:
            pass

    gaps = [{
        'dataset_name': r.get('dataset_name'),
        'path': r.get('path'),
        'host': r.get('host'),
        'present': int(r.get('present') or 0),
        'total': int(r.get('total') or 0),
        'missing': [m for m in (r.get('missing') or []) if m],
    } for r in records]
    return jsonify({'gaps': gaps}), 200
