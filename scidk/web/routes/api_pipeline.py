"""Pipeline source and pipeline management API.

Routes for Cycle 3B Tasks A, B and F. Plugin-agnostic throughout — nothing here
knows what a SharePoint list is. A source names a ``plugin_type``,
:mod:`scidk.pipeline.plugin_registry` turns that into a plugin, and the plugin's
four contract methods do the rest.

Task A  ``GET /pipeline/sources`` (page), and CRUD under ``/api/pipeline/sources``.
Task B  ``POST /api/pipeline/sources/test-connection`` and ``.../upload`` — both
        produce the same thing, a column list plus a row sample, so the column
        mapping step does not care which one the user chose.
Task C  ``.../schema`` (GET/PUT), ``.../schema/export/arrows``,
        ``.../schema/import/arrows`` and ``GET /api/pipeline/schema/derive`` — the
        Arrows.app document the schema canvas edits. See
        :mod:`scidk.pipeline.schema_arrows`.
Task D  ``.../mapping`` (GET/PUT) and ``.../columns`` — the mapping config the
        column mapping page builds, and the live column list it maps *from*.
Task F  ``.../run`` at both levels, plus pipeline CRUD and ``.../schedule``.

Plugin type discovery is ``GET /api/plugins/templates?category=data_import``,
which already existed; this module does not duplicate it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, current_app, jsonify, request

from ..decorators import require_role
from ..user_context import current_user_key

logger = logging.getLogger(__name__)

bp = Blueprint('api_pipeline', __name__, url_prefix='/api/pipeline')

#: Hard wall-clock budget for Test Connection, per Task B. The plugin contract
#: already asks find() to stay under 10s and the value is passed into the config
#: so a cooperative plugin bounds its own reads — but a wedged rclone process
#: would not, so the call is also raced against this timeout.
TEST_CONNECTION_TIMEOUT_SEC = 10

#: Rows shown in the connection preview. Task B specifies 3.
PREVIEW_ROWS = 3

#: Extensions accepted by the upload route. Anything else has no reader behind it.
ALLOWED_UPLOAD_SUFFIXES = ('.csv', '.tsv', '.tab', '.txt', '.xlsx', '.xlsm')

#: Cap on an uploaded file, so a stray multi-GB upload cannot fill the disk.
#: Override with SCIDK_PIPELINE_MAX_UPLOAD_MB.
DEFAULT_MAX_UPLOAD_MB = 200

#: Roles that may read pipeline configuration. There is no 'staff' role —
#: auth_users constrains role to ('admin', 'user') — so both are named.
_READ_ROLES = ('admin', 'user')

#: Anything that changes the graph or the schedule is admin-only, matching
#: /api/canvas/commit. A run writes to Neo4j; a schedule makes it write nightly.
_WRITE_ROLES = ('admin',)


# --------------------------------------------------------------- plumbing

def _settings_db() -> str:
    return current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')


def _store():
    from ...pipeline.store import PipelineStore
    return PipelineStore(_settings_db())


def _history():
    from ...pipeline.run_history import RunHistory
    return RunHistory(_settings_db())


def _upload_dir(create: bool = False) -> str:
    from ...pipeline.file_source import upload_dir
    return upload_dir(current_app, create=create)


def _max_upload_bytes() -> int:
    try:
        megabytes = int(
            current_app.config.get('SCIDK_PIPELINE_MAX_UPLOAD_MB')
            or os.environ.get('SCIDK_PIPELINE_MAX_UPLOAD_MB')
            or DEFAULT_MAX_UPLOAD_MB
        )
    except (TypeError, ValueError):
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return max(1, megabytes) * 1024 * 1024


def _body() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _error(message: str, status: int = 400, **extra):
    payload = {'status': 'error', 'error': message}
    payload.update(extra)
    return jsonify(payload), status


# ------------------------------------------------------- Task A: sources

@bp.get('/sources')
@require_role(*_READ_ROLES)
def list_sources():
    """Every configured source, with what the card needs to render.

    ``plugin_available`` is included so the UI can show a source whose plugin
    does not implement the contract without offering a Run button that would
    only fail. ``schema_summary`` and ``mapping_summary`` are computed here rather
    than on the page so the card, the schema canvas and the mapping page agree
    about what "schema defined" and "mapping defined" mean.

    Both summaries are structural. Neither resolves a plugin or validates a
    transform name, because this route runs once per source on every page load;
    whether a mapping can actually run is ``GET .../mapping``'s answer.
    """
    from ...pipeline.mapping_ui import mapping_summary
    from ...pipeline.plugin_registry import is_available
    from ...pipeline.schema_arrows import schema_summary

    sources = _store().list_sources()
    availability: Dict[str, bool] = {}
    for source in sources:
        plugin_type = source.get('plugin_type') or ''
        if plugin_type not in availability:
            availability[plugin_type] = is_available(plugin_type)
        source['plugin_available'] = availability[plugin_type]
        source['display_path'] = _display_path(source)
        source['schema_summary'] = schema_summary(source.get('schema_json'))
        source['mapping_summary'] = mapping_summary(source.get('mapping_json'))
    return jsonify({'status': 'ok', 'sources': sources}), 200


def _display_path(source: Dict[str, Any]) -> str:
    """The one-line location shown under a source's name on its card.

    Goes through ``source_config_of`` rather than re-reading the column, so the
    card and the runner agree about what a source points at — including for the
    dict/bare-string/unparseable cases that helper already handles.
    """
    from ...pipeline.orchestrator import source_config_of

    config = source_config_of(source)
    return str(config.get('upload_name') or config.get('source_path') or '')


@bp.get('/sources/<source_id>')
@require_role(*_READ_ROLES)
def get_source(source_id: str):
    from ...pipeline.mapping_ui import mapping_summary
    from ...pipeline.schema_arrows import schema_summary

    source = _store().get_source(source_id)
    if source is None:
        return _error('source not found', 404)
    source['display_path'] = _display_path(source)
    source['schema_summary'] = schema_summary(source.get('schema_json'))
    source['mapping_summary'] = mapping_summary(source.get('mapping_json'))
    return jsonify({'status': 'ok', 'source': source}), 200


@bp.post('/sources')
@require_role(*_WRITE_ROLES)
def create_source():
    """Create a source.

    Body:
        name: Display name. Required.
        plugin_type: Resolvable plugin type. Required — a source that names no
            plugin can never be run, so it is rejected at creation rather than
            saved and discovered later.
        preset: Optional ``preset_configs`` key from the plugin template. Its
            config is merged under anything explicitly supplied, which is what
            makes "Table Loader -> CSV" a two-click choice.
        config: Plugin instance config (``source_path``, ``sheet``, ...).
        schema_json / mapping_json: Optional, set by the later steps.
    """
    from ...pipeline.plugin_registry import is_available

    body = _body()
    name = str(body.get('name') or '').strip()
    plugin_type = str(body.get('plugin_type') or '').strip()
    if not name:
        return _error('name is required')
    if not plugin_type:
        return _error('plugin_type is required')
    if not is_available(plugin_type):
        return _error(
            f'no data source plugin implements {plugin_type!r}. It may register a '
            'UI template without implementing the DataSourcePlugin contract.'
        )

    config = _merged_config(body, plugin_type)
    source = _store().create_source(
        name=name,
        plugin_type=plugin_type,
        source_path=config,
        schema_json=body.get('schema_json'),
        mapping_json=body.get('mapping_json'),
    )
    logger.info("Created pipeline source %s (%s) by %s", source['id'], plugin_type,
                current_user_key())
    return jsonify({'status': 'ok', 'source': source}), 201


def _merged_config(body: Dict[str, Any], plugin_type: str) -> Dict[str, Any]:
    """Combine a template preset's config with what the request supplied.

    Explicit values win: the preset is a starting point the user is editing, not
    a constraint on them.
    """
    config: Dict[str, Any] = {}
    preset = str(body.get('preset') or '').strip()
    if preset:
        config.update(_preset_config(plugin_type, preset))
    supplied = body.get('config')
    if isinstance(supplied, dict):
        config.update(supplied)
    elif isinstance(body.get('source_path'), str):
        config['source_path'] = body['source_path'].strip()
    return config


def _preset_config(plugin_type: str, preset: str) -> Dict[str, Any]:
    """Look up a ``preset_configs`` entry in the plugin template registry."""
    try:
        registry = current_app.extensions['scidk']['plugin_templates']
        for template in registry.list_templates(category='data_import'):
            presets = template.get('preset_configs') or {}
            if preset in presets:
                return dict((presets[preset] or {}).get('config') or {})
    except Exception as e:  # noqa: BLE001 - an unknown preset is not fatal
        logger.debug("Could not resolve preset %r for %r: %s", preset, plugin_type, e)
    return {}


@bp.put('/sources/<source_id>')
@require_role(*_WRITE_ROLES)
def update_source(source_id: str):
    """Update a source's name, connection config, schema or mapping.

    Every step of the add/edit flow saves through here, so a user can close the
    browser mid-flow and come back to what they had.
    """
    body = _body()
    updates: Dict[str, Any] = {}
    if 'name' in body:
        name = str(body.get('name') or '').strip()
        if not name:
            return _error('name cannot be empty')
        updates['name'] = name
    if 'config' in body or 'source_path' in body:
        updates['source_path'] = _merged_config(body, str(body.get('plugin_type') or ''))
    for field in ('schema_json', 'mapping_json'):
        if field in body:
            updates[field] = body[field]

    if not updates:
        return _error('nothing to update')

    source = _store().update_source(source_id, **updates)
    if source is None:
        return _error('source not found', 404)
    return jsonify({'status': 'ok', 'source': source}), 200


@bp.delete('/sources/<source_id>')
@require_role(*_WRITE_ROLES)
def delete_source(source_id: str):
    """Delete a source and everything scoped to it.

    Three things beyond the row itself, none of which clean themselves up:

    * its ``canvas_session`` rows (``context_id = 'pipeline_source:<id>'``) — the
      schema canvas is scoped to this source and would otherwise be orphaned
      permanently, and inherited by any later source reusing the id;
    * its implicit single-source pipeline and that pipeline's run history;
    * its step in any *shared* pipeline's DAG, which would otherwise refer to a
      source that no longer exists and fail every subsequent run.

    The uploaded file, if any, is left on disk. Deleting user-supplied data as a
    side effect of removing a configuration record is not this route's call.
    """
    store = _store()
    source = store.get_source(source_id)
    if source is None:
        return _error('source not found', 404)

    removed: Dict[str, Any] = {}

    # Scoped canvas sessions.
    try:
        from ...services.canvas_service import get_canvas_service, pipeline_source_context

        canvas = get_canvas_service(db_path=_settings_db())
        removed['canvas_sessions'] = canvas.clear_context(pipeline_source_context(source_id))
    except Exception as e:  # noqa: BLE001 - the source must still be deletable
        logger.warning("Could not clear canvas sessions for source %s: %s", source_id, e)
        removed['canvas_sessions'] = 0

    # The implicit single-source pipeline, plus its history. A shared pipeline is
    # kept — other sources still need it — but this source's step is removed.
    history = _history()
    implicit_id = store.implicit_pipeline_id(source_id)
    removed['runs'] = 0
    removed['pipelines_deleted'] = 0
    removed['pipelines_updated'] = 0
    for pipeline in store.pipelines_referencing_source(source_id):
        if pipeline['id'] == implicit_id or store.source_ids_in_dag(pipeline) == [source_id]:
            _unschedule(pipeline['id'])
            removed['runs'] += history.delete_for_pipeline(pipeline['id'])
            store.delete_pipeline(pipeline['id'])
            removed['pipelines_deleted'] += 1
        else:
            store.update_pipeline(pipeline['id'], dag=_dag_without(pipeline, source_id))
            removed['pipelines_updated'] += 1

    store.delete_source(source_id)
    logger.info("Deleted pipeline source %s by %s (%s)", source_id, current_user_key(), removed)
    return jsonify({'status': 'ok', 'deleted': True, 'removed': removed}), 200


def _dag_without(pipeline: Dict[str, Any], source_id: str) -> Dict[str, Any]:
    """The pipeline's DAG with one source's step, and references to it, removed."""
    steps = []
    for step in (pipeline.get('dag_json') or {}).get('steps') or []:
        if not isinstance(step, dict) or str(step.get('source_id')) == source_id:
            continue
        step = dict(step)
        step['depends_on'] = [
            d for d in (step.get('depends_on') or []) if str(d) != source_id
        ]
        steps.append(step)
    return {'steps': steps}


def _unschedule(pipeline_id: str) -> None:
    """Remove a pipeline's cron job, tolerating a scheduler that is not running."""
    try:
        from ...pipeline.scheduler import get_schedule_store

        get_schedule_store(_settings_db()).remove(pipeline_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("Could not unschedule pipeline %s: %s", pipeline_id, e)


# ------------------------------------------ Task C: schema (the mapping target)
#
# A source's schema is held as an Arrows.app document, so the same bytes the
# schema canvas saves can be opened in arrows.app and brought back. Every write
# goes through schema_arrows.parse_arrows: the schema is Task D's mapping target,
# and one that names a label Cypher cannot address would produce a mapping that
# can never run.
#
# Nothing in this section touches Neo4j except the derive route, which only reads.

@bp.get('/sources/<source_id>/schema')
@require_role(*_READ_ROLES)
def get_source_schema(source_id: str):
    """The source's committed schema, or null when it has none.

    ``context_id`` is returned so the canvas does not have to construct the
    namespaced string itself — the scope of its working session is the server's
    definition, not the page's.
    """
    from ...pipeline.schema_arrows import schema_summary
    from ...services.canvas_service import pipeline_source_context

    source = _store().get_source(source_id)
    if source is None:
        return _error('source not found', 404)

    schema = source.get('schema_json')
    return jsonify({
        'status': 'ok',
        'source': {'id': source['id'], 'name': source.get('name')},
        'schema': schema,
        'saved_at': source.get('schema_saved_at'),
        'summary': schema_summary(schema),
        'context_id': pipeline_source_context(source_id),
    }), 200


@bp.put('/sources/<source_id>/schema')
@require_role(*_WRITE_ROLES)
def put_source_schema(source_id: str):
    """Commit a schema to ``pipeline_source.schema_json``.

    Body: an Arrows document, or ``{"schema": <arrows document>}``.

    This is the only write the schema canvas performs. It does not write to Neo4j
    — a schema is a mapping target, and creating the labels it names in the graph
    before any data has been mapped onto them would put empty nodes in the graph.
    """
    from ...pipeline.schema_arrows import SchemaError, parse_arrows, schema_summary

    store = _store()
    if store.get_source(source_id) is None:
        return _error('source not found', 404)

    body = _body()
    payload = body.get('schema') if 'schema' in body else body
    try:
        schema = parse_arrows(payload)
    except SchemaError as e:
        return _error(str(e), 400, problems=e.problems, ok=False)

    source = store.save_schema(source_id, schema)
    logger.info("Saved schema for pipeline source %s by %s (%d label(s))",
                source_id, current_user_key(), len(schema['nodes']))
    return jsonify({
        'status': 'ok',
        'saved_at': (source or {}).get('schema_saved_at'),
        'schema': schema,
        'summary': schema_summary(schema),
    }), 200


@bp.get('/sources/<source_id>/schema/export/arrows')
@require_role(*_READ_ROLES)
def export_source_schema(source_id: str):
    """Download the schema as ``schema.arrows.json``, ready to open in arrows.app."""
    from flask import Response

    source = _store().get_source(source_id)
    if source is None:
        return _error('source not found', 404)
    schema = source.get('schema_json')
    if not schema:
        return _error('this source has no schema to export', 404)

    return Response(
        json.dumps(schema, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename="schema.arrows.json"'},
    )


@bp.post('/sources/<source_id>/schema/import/arrows')
@require_role(*_READ_ROLES)
def import_source_schema(source_id: str):
    """Validate an Arrows document without saving it.

    Option A's gate. The canvas must never open on a broken schema, so the paste
    is checked here first and the canvas is only entered on a 200. Saving is a
    separate, deliberate act (the PUT above) — importing something and finding it
    had already overwritten the previous schema would be a nasty surprise.

    A 400 carries ``problems``: every offending element, so a malformed export can
    be fixed in one pass rather than one reload per mistake.
    """
    from ...pipeline.schema_arrows import SchemaError, parse_arrows, schema_summary

    if _store().get_source(source_id) is None:
        return _error('source not found', 404)

    # An unparseable body is the case this route exists to report, so the raw text
    # is used when Flask could not read it as JSON — otherwise a syntax error in
    # the paste would arrive as an empty dict and be reported as "no nodes array".
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        payload = body.get('schema') if 'schema' in body else body
    else:
        payload = request.get_data(as_text=True)

    try:
        schema = parse_arrows(payload)
    except SchemaError as e:
        return _error(str(e), 400, problems=e.problems, ok=False)

    return jsonify({
        'status': 'ok', 'ok': True, 'schema': schema,
        'summary': schema_summary(schema),
    }), 200


@bp.get('/schema/derive')
@require_role(*_READ_ROLES)
def derive_schema():
    """Option B: the live Neo4j schema as an Arrows document.

    Read-only, and not scoped to a source — the graph's shape is the same whichever
    source is being configured. ``strategy`` says which of the three derivation
    paths answered, and ``notes`` says why the earlier ones did not, because "your
    schema is empty" and "this Neo4j has no db.schema.visualization" look identical
    on the canvas otherwise.
    """
    from ...pipeline.schema_arrows import derive_from_graph, schema_summary
    from ...services.neo4j_client import Neo4jClient, get_neo4j_params

    uri, user, password, database, auth_mode = get_neo4j_params(current_app)
    if not uri:
        return _error('Neo4j is not configured. Configure a connection in Settings, '
                      'or import a schema from Arrows.app instead.', 400)

    try:
        client = Neo4jClient(uri, user, password, database, auth_mode)
        client.connect()
        try:
            result = derive_from_graph(client.execute_read)
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001 - a connection failure is the user's to see
        logger.warning("Could not derive a schema from Neo4j: %s", e, exc_info=True)
        return _error(f'Could not read the graph: {e}', 502)

    result['summary'] = schema_summary(result['schema'])
    result['status'] = 'ok'
    return jsonify(result), 200


# --------------------------------------------- Task D: the column mapping
#
# Step 3. The schema above says what the target graph looks like; the mapping says
# which source column fills which of its properties. The format is
# scidk/pipeline/mapping_schema.json and the consumer is MappingEngine, so these
# routes report that engine's verdict rather than inventing a second opinion about
# what a usable mapping is.
#
# The asymmetry with the schema routes is deliberate: parse_arrows *refuses* an
# unusable schema, and PUT .../mapping *accepts* an unusable mapping. A schema that
# cannot be written to is not worth storing; a half-finished mapping is exactly what
# a user closing the browser mid-task should come back to. The engine validates on
# load, so nothing incomplete here can make a run write something wrong — it makes
# the FAIR check fail, which is where the user is told.

#: Written into a config that arrives without one. The only version there is, and
#: the schema requires it — a config rejected solely for its absence would be a
#: validation error about nothing the user did.
MAPPING_CONFIG_VERSION = '1.0'


@bp.get('/sources/<source_id>/mapping')
@require_role(*_READ_ROLES)
def get_source_mapping(source_id: str):
    """The source's committed mapping, its summary, and whether it would run.

    ``validation`` is :meth:`MappingEngine.validate`'s report, so the page can say
    "this mapping is complete" with the same authority the runner will use. A source
    with no mapping at all reports ``mapping: null`` and no validation, which the
    Step 3 indicator reads as "not started" rather than "broken".
    """
    from ...pipeline.mapping_ui import mapping_summary
    from ...pipeline.schema_arrows import schema_summary

    source = _store().get_source(source_id)
    if source is None:
        return _error('source not found', 404)

    mapping = source.get('mapping_json')
    return jsonify({
        'status': 'ok',
        'source': {'id': source['id'], 'name': source.get('name')},
        'mapping': mapping,
        'saved_at': source.get('mapping_saved_at'),
        'summary': mapping_summary(mapping),
        'validation': _mapping_validation(source, mapping) if mapping else None,
        'schema_summary': schema_summary(source.get('schema_json')),
    }), 200


@bp.put('/sources/<source_id>/mapping')
@require_role(*_WRITE_ROLES)
def put_source_mapping(source_id: str):
    """Commit a mapping config to ``pipeline_source.mapping_json``.

    Body: a mapping config, or ``{"mapping": <config>}``. ``null`` clears it.

    Saves first and validates second, and returns the validation report either way.
    A partial mapping is a legitimate thing to store — Task D's flow saves at any
    point — so the only rejection here is a body that is not a JSON object at all,
    which is a client bug rather than an unfinished mapping.
    """
    from ...pipeline.mapping_ui import mapping_summary

    store = _store()
    if store.get_source(source_id) is None:
        return _error('source not found', 404)

    body = request.get_json(silent=True)
    if isinstance(body, dict) and 'mapping' in body:
        payload = body['mapping']
    else:
        payload = body

    if payload in (None, {}, ''):
        source = store.save_mapping(source_id, None)
        logger.info("Cleared the mapping for pipeline source %s by %s",
                    source_id, current_user_key())
        return jsonify({'status': 'ok', 'mapping': None, 'saved_at': None,
                        'summary': mapping_summary(None), 'validation': None}), 200

    if not isinstance(payload, dict):
        return _error(
            'a mapping config is a JSON object with "node_mappings"; this is '
            f'{type(payload).__name__}'
        )

    mapping = dict(payload)
    mapping.setdefault('version', MAPPING_CONFIG_VERSION)

    source = store.save_mapping(source_id, mapping) or {}
    validation = _mapping_validation(source, mapping)
    summary = mapping_summary(mapping)
    logger.info(
        "Saved mapping for pipeline source %s by %s (%d node mapping(s), valid=%s)",
        source_id, current_user_key(), summary['node_mapping_count'], validation['ok'],
    )
    return jsonify({
        'status': 'ok',
        'mapping': mapping,
        'saved_at': source.get('mapping_saved_at'),
        'summary': summary,
        'validation': validation,
    }), 200


def _mapping_validation(
    source: Dict[str, Any], mapping: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """``MappingEngine.validate()`` for one source's mapping.

    The transform library is the plugin's, because whether ``parse_rfc5322``
    resolves depends on which plugin serves this source. A plugin that cannot be
    loaded yields the core transforms and a warning saying so — reporting its
    transforms as unknown *errors* would condemn a mapping for a deployment problem
    it does not have.
    """
    from ...pipeline.mapping_engine import MappingConfigError, MappingEngine
    from ...pipeline.plugin_registry import resolve_plugin, transform_library_for

    plugin_type = str(source.get('plugin_type') or '')
    notes: List[str] = []
    try:
        plugin = resolve_plugin(plugin_type)
    except Exception as e:  # noqa: BLE001 - availability is the answer here
        plugin = None
        notes.append(
            f'the plugin for {plugin_type!r} could not be loaded ({e}), so only the '
            'core transforms were checked'
        )

    try:
        engine = MappingEngine(mapping or {}, transform_library=transform_library_for(plugin))
        report = engine.validate().to_dict()
    except MappingConfigError as e:
        return {'ok': False, 'errors': [str(e)], 'warnings': notes}
    report['warnings'] = notes + list(report.get('warnings') or [])
    return report


@bp.get('/sources/<source_id>/columns')
@require_role(*_READ_ROLES)
def source_columns(source_id: str):
    """The columns the mapping page maps *from*, read live from the source.

    Not served from the source record, because nothing stores them: Task B's
    preview lives in the browser for the length of the add flow. Reading them live
    is also the more useful answer — a column the source dropped since the mapping
    was written shows up here as missing rather than as a property that silently
    stops being filled.

    ``missing_columns`` is :meth:`MappingEngine.missing_columns` against what the
    source actually has, so the page can flag a mapping that has drifted from its
    source without running anything.
    """
    from ...pipeline.orchestrator import source_config_of
    from ...pipeline.plugin_registry import PluginNotAvailable, resolve_plugin

    store = _store()
    source = store.get_source(source_id)
    if source is None:
        return _error('source not found', 404)

    plugin_type = str(source.get('plugin_type') or '')
    config = dict(source_config_of(source))
    config.setdefault('sample_rows', PREVIEW_ROWS)
    config.setdefault('timeout_sec', TEST_CONNECTION_TIMEOUT_SEC)

    kwargs: Dict[str, Any] = {}
    if config.get('upload_name'):
        kwargs['base_dir'] = _upload_dir()
    try:
        plugin = resolve_plugin(plugin_type, **kwargs)
    except PluginNotAvailable as e:
        return jsonify({'status': 'error', 'ok': False, 'error': str(e),
                        'columns': [], 'sample': []}), 200

    result, failure = _bounded_find(plugin, config, plugin_type)
    if failure is not None:
        return jsonify({'status': 'error', 'ok': False, 'error': failure,
                        'columns': [], 'sample': []}), 200

    preview = _preview(result)
    preview['missing_columns'] = _drifted_columns(source, preview['columns'])
    return jsonify({'status': 'ok' if preview['ok'] else 'error', **preview}), 200


def _drifted_columns(source: Dict[str, Any], columns: List[str]) -> List[str]:
    """Mapped columns the source no longer has. Empty when there is no mapping."""
    mapping = source.get('mapping_json')
    if not isinstance(mapping, dict):
        return []
    from ...pipeline.mapping_engine import MappingEngine

    try:
        return MappingEngine(mapping).missing_columns(columns)
    except Exception as e:  # noqa: BLE001 - a broken config is validate()'s to report
        logger.debug("Could not compute missing columns for %s: %s", source.get('id'), e)
        return []


# ---------------------------------------------------- Task B: connection

@bp.post('/sources/test-connection')
@require_role(*_READ_ROLES)
def test_connection():
    """Call the plugin's ``find()`` and return columns plus a row preview.

    Body:
        plugin_type: Which plugin to ask. Required.
        config / source_path: The connection to test.
        source_id: Alternatively, test a saved source's stored config.

    Bounded by :data:`TEST_CONNECTION_TIMEOUT_SEC` in two ways: the value is
    passed into the plugin config so a cooperative plugin limits its own reads,
    and the call is raced against a wall-clock timeout so an uncooperative one
    still answers the user. A timed-out call leaves its thread running — Python
    cannot cancel one — but it is a bounded read that will end on its own.
    """
    from ...pipeline.plugin_registry import PluginNotAvailable, resolve_plugin

    body = _body()
    plugin_type, config, error = _connection_target(body)
    if error:
        return _error(error)

    config = dict(config)
    config.setdefault('sample_rows', PREVIEW_ROWS)
    config.setdefault('timeout_sec', TEST_CONNECTION_TIMEOUT_SEC)

    kwargs: Dict[str, Any] = {}
    if config.get('upload_name'):
        kwargs['base_dir'] = _upload_dir()
    try:
        plugin = resolve_plugin(plugin_type, **kwargs)
    except PluginNotAvailable as e:
        return _error(str(e))

    result, failure = _bounded_find(plugin, config, plugin_type)
    if failure is not None:
        return jsonify({'status': 'error', 'ok': False, 'error': failure}), 200

    preview = _preview(result)
    return jsonify({'status': 'ok' if preview['ok'] else 'error', **preview}), 200


def _bounded_find(
    plugin: Any, config: Dict[str, Any], label: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Call ``plugin.find()`` under a wall-clock limit.

    Returns:
        ``(result, None)`` on a call that returned, or ``(None, message)`` when it
        timed out or raised. A raising ``find()`` is a contract violation — the
        contract says it reports failure in its return value — so it is reported as
        a message rather than propagated as a 500.

    Not a ``with`` block: ``ThreadPoolExecutor.__exit__`` calls
    ``shutdown(wait=True)``, which joins the worker thread and so waits out exactly
    the hang the timeout exists to escape. ``shutdown(wait=False)`` returns
    immediately and leaves the thread to finish on its own — Python cannot cancel
    one, and a bounded read will end.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(plugin.find, config).result(
            timeout=TEST_CONNECTION_TIMEOUT_SEC
        ), None
    except FutureTimeout:
        return None, (
            f'The source did not respond within {TEST_CONNECTION_TIMEOUT_SEC} seconds. '
            'Check the path and that the remote is reachable.'
        )
    except Exception as e:  # noqa: BLE001 - the contract says find() reports, not raises
        logger.warning("find() failed for %r: %s", label, e, exc_info=True)
        return None, f'{type(e).__name__}: {e}'
    finally:
        pool.shutdown(wait=False)


def _connection_target(body: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
    """Resolve what to connect to: an explicit config, or a saved source's."""
    source_id = str(body.get('source_id') or '').strip()
    if source_id:
        from ...pipeline.orchestrator import source_config_of

        source = _store().get_source(source_id)
        if source is None:
            return '', {}, 'source not found'
        return str(source.get('plugin_type') or ''), source_config_of(source), None

    plugin_type = str(body.get('plugin_type') or '').strip()
    if not plugin_type:
        return '', {}, 'plugin_type or source_id is required'

    config = body.get('config')
    if not isinstance(config, dict):
        config = {}
    if body.get('source_path'):
        config['source_path'] = str(body['source_path']).strip()
    if not config.get('source_path'):
        return plugin_type, config, 'a source path is required'
    return plugin_type, config, None


def _preview(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a ``FindResult`` into what Step 2 consumes.

    The same shape for both connection options, which is the point of Task B:
    downstream steps see a column list and a row sample and never learn whether
    the bytes came off an rclone remote or a browser upload.
    """
    result = result or {}
    columns = list(result.get('columns') or [])
    sample = [dict(row) for row in (result.get('sample') or [])][:PREVIEW_ROWS]
    return {
        'ok': bool(result.get('ok')),
        'columns': columns,
        'row_count': result.get('row_count'),
        'sample': sample,
        'metadata': result.get('metadata') or {},
        'error': result.get('error'),
    }


@bp.post('/sources/upload')
@require_role(*_WRITE_ROLES)
def upload_source_file():
    """Accept a CSV/TSV/Excel upload and return the same preview as a remote path.

    The stored filename is generated, not the client's: a browser-supplied name
    reaches the filesystem otherwise, and ``../`` in it would write outside the
    upload directory. The original is kept in the config for display only.
    """
    from ...pipeline.file_source import TabularFilePlugin

    uploaded = request.files.get('file')
    if uploaded is None or not (uploaded.filename or '').strip():
        return _error('no file was uploaded')

    original = os.path.basename(uploaded.filename)
    suffix = os.path.splitext(original)[1].lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        return _error(
            f'{suffix or "that file type"} is not supported. '
            f'Upload one of: {", ".join(ALLOWED_UPLOAD_SUFFIXES)}'
        )

    target_dir = _upload_dir(create=True)
    # A generated name, so nothing from the client's filename reaches a path.
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = os.path.join(target_dir, stored_name)

    limit = _max_upload_bytes()
    written = 0
    try:
        with open(stored_path, 'wb') as out:
            while True:
                chunk = uploaded.stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise ValueError(
                        f'file is larger than the {limit // (1024 * 1024)}MB upload limit'
                    )
                out.write(chunk)
    except Exception as e:  # noqa: BLE001
        _remove_quietly(stored_path)
        return _error(str(e), 413 if isinstance(e, ValueError) else 500)

    config = {
        'source_path': stored_path,
        'upload_name': original,
        'upload_size_bytes': written,
    }
    sheet = (request.form.get('sheet') or '').strip()
    if sheet:
        config['sheet'] = sheet

    plugin = TabularFilePlugin(base_dir=target_dir)
    preview = _preview(plugin.find({**config, 'sample_rows': PREVIEW_ROWS}))
    if not preview['ok']:
        # An unreadable upload is not worth keeping — the user will try again.
        _remove_quietly(stored_path)
        return jsonify({'status': 'error', **preview}), 200

    return jsonify({'status': 'ok', 'config': config, **preview}), 200


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------- source-level runs

@bp.post('/sources/<source_id>/run')
@require_role(*_WRITE_ROLES)
def run_source_now(source_id: str):
    """Run one source: preflight, then ingest if the FAIR gate passes.

    Query params:
        dry_run: Map and report without writing.

    A FAIR failure writes nothing and returns 200 with ``fair`` showing which
    letter failed — a source that is misconfigured is a result to display, not an
    HTTP error.
    """
    from ...pipeline.orchestrator import run_source

    if _store().get_source(source_id) is None:
        return _error('source not found', 404)

    dry_run = str(request.args.get('dry_run') or '').lower() in ('1', 'true', 'yes')
    report = run_source(
        source_id,
        _store(),
        app=current_app,
        dry_run=dry_run,
        upload_dir=_upload_dir(),
    )
    return jsonify({'status': 'ok', 'run': report.to_dict()}), 200


@bp.post('/sources/<source_id>/preflight')
@require_role(*_READ_ROLES)
def preflight_source(source_id: str):
    """Report F, A, I and R without fetching data or writing anything.

    The gate the full FAIR check (Task E) will sit on top of: same four letters,
    no Neo4j reads, no sampled row preview.
    """
    from ...pipeline.orchestrator import build_runner
    from ...pipeline.plugin_registry import PluginNotAvailable

    store = _store()
    source = store.get_source(source_id)
    if source is None:
        return _error('source not found', 404)

    try:
        runner = build_runner(source, upload_dir=_upload_dir())
    except (PluginNotAvailable, ValueError) as e:
        return jsonify({
            'status': 'ok',
            'preflight': {
                'fair': {'F': False, 'A': False, 'I': False, 'R': False},
                'fair_ok': False,
                'errors': [str(e)],
            },
        }), 200

    report = runner.preflight()
    store.record_fair_check(source_id, {
        **report.fair,
        'fair_ok': report.fair_ok,
        'errors': report.errors,
        'warnings': report.warnings,
    })
    return jsonify({'status': 'ok', 'preflight': report.to_dict()}), 200


# ------------------------------------------------- Task F: pipelines (DAGs)

@bp.get('/pipelines')
@require_role(*_READ_ROLES)
def list_pipelines():
    """Every pipeline, with its schedule as the live scheduler sees it.

    ``schedule`` is what is stored; ``next_run_time`` comes from the jobstore, so a
    schedule that was saved but never reached the scheduler shows one without the
    other rather than looking healthy.
    """
    store = _store()
    scheduled = _scheduled_jobs()
    pipelines = []
    for pipeline in store.list_pipelines():
        source_ids = store.source_ids_in_dag(pipeline)
        job = scheduled.get(pipeline['id']) or {}
        pipelines.append({
            **pipeline,
            'source_ids': source_ids,
            'implicit': pipeline['id'] == f"src-{source_ids[0]}" if source_ids else False,
            'next_run_time': None if pipeline.get('schedule_paused') else job.get('next_run_time'),
            'scheduled': bool(job),
        })
    return jsonify({'status': 'ok', 'pipelines': pipelines}), 200


def _scheduled_jobs() -> Dict[str, Any]:
    """Persisted schedules, or {} when the jobstore is unreachable."""
    try:
        from ...pipeline.scheduler import get_schedule_store

        return get_schedule_store(_settings_db()).list_jobs()
    except Exception as e:  # noqa: BLE001 - a page must still render without it
        logger.debug("Could not read pipeline schedules: %s", e)
        return {}


@bp.post('/pipelines')
@require_role(*_WRITE_ROLES)
def create_pipeline():
    """Create a named pipeline.

    Body:
        name: Required.
        source_ids: Convenience — an ordered list becomes a linear DAG, each step
            depending on the one before. Use ``dag`` for anything branching.
        dag: ``{"steps": [{"source_id", "depends_on": [...]}]}``.
    """
    body = _body()
    name = str(body.get('name') or '').strip()
    if not name:
        return _error('name is required')

    dag = body.get('dag')
    if not isinstance(dag, dict):
        dag = _linear_dag(body.get('source_ids') or [])

    invalid = _unknown_sources(dag)
    if invalid:
        return _error(f'unknown source id(s): {", ".join(invalid)}')

    pipeline = _store().create_pipeline(
        name=name, dag=dag, description=body.get('description')
    )
    return jsonify({'status': 'ok', 'pipeline': pipeline}), 201


def _linear_dag(source_ids) -> Dict[str, Any]:
    """Turn an ordered id list into a chain, so order is expressed as dependency."""
    steps = []
    previous = None
    for source_id in source_ids:
        steps.append({
            'source_id': str(source_id),
            'depends_on': [previous] if previous else [],
        })
        previous = str(source_id)
    return {'steps': steps}


def _unknown_sources(dag: Dict[str, Any]) -> list:
    """Source ids in a DAG that no source record matches."""
    store = _store()
    referenced = [
        str(step.get('source_id'))
        for step in (dag or {}).get('steps') or []
        if isinstance(step, dict) and step.get('source_id')
    ]
    return [sid for sid in referenced if store.get_source(sid) is None]


@bp.put('/pipelines/<pipeline_id>')
@require_role(*_WRITE_ROLES)
def update_pipeline(pipeline_id: str):
    body = _body()
    updates: Dict[str, Any] = {}
    if 'name' in body:
        name = str(body.get('name') or '').strip()
        if not name:
            return _error('name cannot be empty')
        updates['name'] = name
    if 'description' in body:
        updates['description'] = body['description']
    if 'dag' in body or 'source_ids' in body:
        dag = body.get('dag')
        if not isinstance(dag, dict):
            dag = _linear_dag(body.get('source_ids') or [])
        invalid = _unknown_sources(dag)
        if invalid:
            return _error(f'unknown source id(s): {", ".join(invalid)}')
        updates['dag'] = dag

    if not updates:
        return _error('nothing to update')
    pipeline = _store().update_pipeline(pipeline_id, **updates)
    if pipeline is None:
        return _error('pipeline not found', 404)
    return jsonify({'status': 'ok', 'pipeline': pipeline}), 200


@bp.delete('/pipelines/<pipeline_id>')
@require_role(*_WRITE_ROLES)
def delete_pipeline(pipeline_id: str):
    """Delete a pipeline, its schedule and its run history. Sources are untouched."""
    store = _store()
    if store.get_pipeline(pipeline_id) is None:
        return _error('pipeline not found', 404)

    _unschedule(pipeline_id)
    runs = _history().delete_for_pipeline(pipeline_id)
    store.delete_pipeline(pipeline_id)
    return jsonify({'status': 'ok', 'deleted': True, 'removed': {'runs': runs}}), 200


@bp.post('/pipelines/<pipeline_id>/run')
@require_role(*_WRITE_ROLES)
def run_pipeline_now(pipeline_id: str):
    """Execute a pipeline's DAG now.

    Sources failing their FAIR check are recorded as skipped steps and the rest
    still run, so one broken source does not cost the others their refresh. The
    response is 200 for a ``'partial'`` or ``'error'`` run: the run happened, and
    its outcome is the payload.
    """
    from ...pipeline.orchestrator import run_pipeline

    if _store().get_pipeline(pipeline_id) is None:
        return _error('pipeline not found', 404)

    result = run_pipeline(
        pipeline_id,
        _store(),
        _history(),
        app=current_app,
        triggered_by='api' if _is_api_token_request() else 'manual',
        upload_dir=_upload_dir(),
    )
    return jsonify({'status': 'ok', 'run': result}), 200


def _is_api_token_request() -> bool:
    """Whether this came from an API token rather than a browser session."""
    return request.headers.get('Authorization', '').startswith('Bearer ')


@bp.get('/pipelines/<pipeline_id>/runs')
@require_role(*_READ_ROLES)
def list_pipeline_runs(pipeline_id: str):
    try:
        limit = int(request.args.get('limit') or 20)
    except (TypeError, ValueError):
        limit = 20
    runs = _history().list_runs(pipeline_id, limit=max(1, min(limit, 200)))
    return jsonify({'status': 'ok', 'runs': runs}), 200


# ------------------------------------------------------ Task F: schedules

@bp.get('/pipelines/<pipeline_id>/schedule')
@require_role(*_READ_ROLES)
def get_pipeline_schedule(pipeline_id: str):
    pipeline = _store().get_pipeline(pipeline_id)
    if pipeline is None:
        return _error('pipeline not found', 404)
    return jsonify({'status': 'ok', 'schedule': _schedule_view(pipeline)}), 200


def _schedule_view(
    pipeline: Dict[str, Any], job: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """What is stored, plus what the live scheduler actually holds.

    Args:
        pipeline: The pipeline record.
        job: The jobstore entry, when the caller already has it. Reading it costs
            a paused scheduler with its own thread and SQLAlchemy engine, and a
            write path has just been given one back by ``upsert``.
    """
    if job is None:
        job = _scheduled_jobs().get(pipeline['id']) or {}
    paused = bool(pipeline.get('schedule_paused'))
    return {
        'pipeline_id': pipeline['id'],
        'cron': pipeline.get('schedule'),
        'paused': paused,
        'scheduled': bool(job),
        # A paused schedule has no next run by definition; showing the job's
        # would claim it is about to fire.
        'next_run_time': None if paused else job.get('next_run_time'),
        'timezone': _schedule_timezone(),
    }


def _schedule_timezone() -> str:
    try:
        from ...pipeline.scheduler import SCHEDULE_TIMEZONE

        return SCHEDULE_TIMEZONE
    except Exception:  # noqa: BLE001
        return 'UTC'


@bp.post('/pipelines/<pipeline_id>/schedule')
@require_role(*_WRITE_ROLES)
def set_pipeline_schedule(pipeline_id: str):
    """Set, pause or clear a pipeline's schedule.

    Body:
        cron: A 5-field expression, or null/"" for manual only.
        paused: Keep the cron but do not fire it.

    Takes effect without a restart: the job is written to a jobstore the
    scheduler-owning process shares, and that process re-reads it on its next
    heartbeat. Validation happens before storing, so a malformed cron is a 400
    rather than a schedule that looks saved and silently never runs.
    """
    store = _store()
    if store.get_pipeline(pipeline_id) is None:
        return _error('pipeline not found', 404)
    return _apply_schedule(store, pipeline_id, _body())


def _apply_schedule(store, pipeline_id: str, body: Dict[str, Any]):
    """Shared by the pipeline-level and source-level schedule routes."""
    from ...pipeline.scheduler import get_schedule_store, validate_cron

    cron = body.get('cron')
    cron = str(cron).strip() if cron not in (None, '') else None
    paused = bool(body.get('paused'))

    if cron:
        problem = validate_cron(cron)
        if problem:
            return _error(f'invalid cron expression: {problem}')

    pipeline = store.update_pipeline(pipeline_id, schedule=cron, schedule_paused=paused)

    warning = None
    job: Dict[str, Any] = {}
    try:
        schedules = get_schedule_store(_settings_db())
        if cron and not paused:
            # upsert already reports the job it wrote, so the view below does not
            # need to open a second scheduler to read it back.
            job = schedules.upsert(pipeline_id, cron)
        else:
            # Pausing removes the job but keeps `schedule` on the record, which is
            # what "paused without clearing the cron" means. run_scheduled_pipeline
            # also re-checks the flag, so a stale job cannot fire a paused pipeline.
            schedules.remove(pipeline_id)
    except ValueError as e:
        return _error(str(e))
    except Exception as e:  # noqa: BLE001
        # The schedule is stored; it just is not live yet. Say so rather than
        # reporting a success the scheduler knows nothing about.
        logger.error("Could not update the live schedule for %s: %s", pipeline_id, e,
                     exc_info=True)
        warning = (
            'Saved, but the running scheduler could not be updated, so it will not '
            'take effect until the app restarts.'
        )

    view = _schedule_view(store.get_pipeline(pipeline_id) or pipeline, job=job)
    if warning:
        view['warning'] = warning
    return jsonify({'status': 'ok', 'schedule': view}), 200


@bp.get('/sources/<source_id>/schedule')
@require_role(*_READ_ROLES)
def get_source_schedule(source_id: str):
    """A source's schedule, via its implicit single-source pipeline.

    Reports the *shared* pipeline's schedule when the source belongs to one and
    has no implicit pipeline of its own — otherwise the UI would show "manual
    only" for a source that in fact runs nightly as part of a DAG.
    """
    store = _store()
    if store.get_source(source_id) is None:
        return _error('source not found', 404)

    implicit = store.get_pipeline(store.implicit_pipeline_id(source_id))
    if implicit is not None:
        return jsonify({'status': 'ok', 'schedule': _schedule_view(implicit)}), 200

    for pipeline in store.pipelines_referencing_source(source_id):
        if pipeline.get('schedule'):
            view = _schedule_view(pipeline)
            view['via_pipeline'] = {'id': pipeline['id'], 'name': pipeline['name']}
            return jsonify({'status': 'ok', 'schedule': view}), 200

    return jsonify({'status': 'ok', 'schedule': {
        'pipeline_id': None, 'cron': None, 'paused': False,
        'scheduled': False, 'next_run_time': None, 'timezone': _schedule_timezone(),
    }}), 200


@bp.post('/sources/<source_id>/schedule')
@require_role(*_WRITE_ROLES)
def set_source_schedule(source_id: str):
    """Schedule a single source.

    Schedules live on pipelines, never on sources — a source-level schedule is
    sugar over a one-step pipeline created here on demand. The pipeline's id is
    derived from the source's, so scheduling the same source twice updates one
    pipeline instead of accumulating them.
    """
    store = _store()
    if store.get_source(source_id) is None:
        return _error('source not found', 404)

    pipeline = store.ensure_single_source_pipeline(source_id)
    response = _apply_schedule(store, pipeline['id'], _body())
    payload = response[0].get_json()
    if isinstance(payload, dict) and isinstance(payload.get('schedule'), dict):
        payload['schedule']['source_id'] = source_id
        payload['schedule']['implicit_pipeline'] = True
        return jsonify(payload), response[1]
    return response
