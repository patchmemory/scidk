"""
Blueprint for UI routes.

Handles:
- Homepage (index)
- Chat interface
- Map visualization
- Datasets (file list and detail views)
- Workbook viewer (Excel files)
- Plugins page
- Interpreters page
- RO-Crate viewer
- Settings page
- Scan form submission
"""
from flask import Blueprint, jsonify, request, render_template, current_app, redirect, url_for
from pathlib import Path
import os
import time
import hashlib

# Create blueprint
bp = Blueprint('ui', __name__)


# Helper to access app extensions
def _get_ext():
    """Get SciDK extensions from current Flask app."""
    return current_app.extensions['scidk']


# Experimental shell is opt-in; reading pages never initializes policy/storage.
@bp.app_context_processor
def gui_context():
    return {'gui_v3': current_app.config.get('SCIDK_GUI_V3_ENABLED') is True,
            'overview_chat_enabled': current_app.config.get('SCIDK_OVERVIEW_CHAT_ENABLED') is True,
            'dataset_sharing_enabled': current_app.config.get('SCIDK_DATASET_SHARING_ENABLED') is True,
            'chat_readiness_enabled': current_app.config.get('SCIDK_CHAT_READINESS_ENABLED') is True}


def _gui_page(page):
    if current_app.config.get('SCIDK_GUI_V3_ENABLED') is not True:
        from flask import abort
        abort(404)
    if page == 'Knowledge' and current_app.config.get('SCIDK_KNOWLEDGE_WORKSPACE_ENABLED', True) is True:
        return render_template('gui/knowledge.html')
    if page == 'Review' and current_app.config.get('SCIDK_REVIEW_WORKSPACE_ENABLED') is True:
        return render_template('gui/review.html',
            assistant_enabled=current_app.config.get('SCIDK_REVIEW_CHAT_ENABLED') is True)
    return render_template('gui/workspace.html', page=page)


@bp.route('/api/knowledge/<domain>/<operation>', methods=['POST'])
def knowledge_adapter(domain, operation):
    """Governed human-only adapters, independent of preserved legacy APIs."""
    from dataclasses import replace
    from ...agent_tools.context import context_from_app
    from ...agent_tools.security import REFUSAL
    from ...services import knowledge_workspace as workspace
    headers = {'Cache-Control': 'no-store'}
    if (current_app.config.get('SCIDK_GUI_V3_ENABLED') is not True or
            current_app.config.get('SCIDK_KNOWLEDGE_WORKSPACE_ENABLED', True) is not True):
        return jsonify(REFUSAL), 403, headers
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(status='error', error='JSON object required'), 400, headers
    try:
        from ...services.human_policy import human_context
        ctx = replace(human_context(current_app) if domain == 'research' else
                      context_from_app(current_app, channel='chat'), profile='overview')
        from ...agent_tools.knowledge import KnowledgeServices
        if ctx.identity and (not isinstance(ctx.knowledge, KnowledgeServices) or (domain in workspace.DOMAINS and not ctx.knowledge.ready(workspace.DOMAINS[domain]))):
            return jsonify(status='unavailable', error='Knowledge service is not connected. Ask an administrator to connect this workspace.'), 503, headers
        if operation in {'search', 'inspect', 'expand'} and domain == 'research':
            result = workspace.research(ctx, operation, body)
        elif operation == 'context':
            result = workspace.context(ctx, domain, body)
        elif operation in {'load', 'save'}:
            if set(body) - {'kind', 'canvas'} or (operation == 'load' and 'canvas' in body) or (operation == 'save' and not isinstance(body.get('canvas'), dict)):
                raise ValueError()
            result = workspace.canvas(ctx, domain, body.get('canvas') if operation == 'save' else None,
                                      kind=body.get('kind', 'sketch'))
        else:
            raise ValueError()
        return jsonify(status='success', result=result), 200, headers
    except Exception:
        return jsonify(REFUSAL), 403, headers


@bp.post('/api/review/<operation>')
def review_adapter(operation):
    from ...agent_tools.context import context_from_app
    from ...agent_tools.security import REFUSAL
    from ...curation.contracts import ConflictError
    from ...services import review_workspace as workspace
    headers = {'Cache-Control': 'no-store'}
    if (current_app.config.get('SCIDK_GUI_V3_ENABLED') is not True or
            current_app.config.get('SCIDK_REVIEW_WORKSPACE_ENABLED') is not True or
            request.headers.get('Authorization') or
            request.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none') or
            (request.headers.get('Origin') and request.headers['Origin'].rstrip('/') != request.host_url.rstrip('/'))):
        return jsonify(REFUSAL), 403, headers
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(status='error', error='JSON object required'), 400, headers
    try:
        from ...services.human_policy import human_context
        ctx = workspace.authorized(context_from_app(current_app, channel='chat')
                                   if operation in {'assistant', 'propose'} else human_context(current_app))
        if operation == 'queue':
            result = workspace.queue(ctx, body)
        elif operation == 'inspect' and not set(body) - {'id', 'history'}:
            result = workspace.inspect(ctx, body.get('id'), history=body.get('history', False))
        elif operation == 'preview' and set(body) == {'id'}:
            if current_app.config.get('SCIDK_CURATION_ENABLED') is not True:
                raise ValueError()
            result = workspace.preview(ctx, current_app.extensions.get('curation_review'), body['id'])
        elif operation == 'decide':
            if current_app.config.get('SCIDK_CURATION_ENABLED') is not True:
                raise ValueError()
            result = workspace.decide(ctx, current_app.extensions.get('curation_review'), body)
        elif operation == 'assistant' and current_app.config.get('SCIDK_REVIEW_CHAT_ENABLED') is True:
            result = workspace.assistant(ctx, body)
            if result.get('status') != 'success':
                raise ValueError()
        elif operation == 'propose':
            result = workspace.propose(ctx, body)
        else:
            raise ValueError()
        return jsonify(status='success', result=result), 200, headers
    except ConflictError:
        return jsonify(status='conflict', error='This item changed. Reload it and prepare a new decision.'), 409, headers
    except Exception:
        return jsonify(REFUSAL), 403, headers


@bp.route('/admin/chat-readiness', methods=['GET', 'POST'])
def chat_readiness():
    from ..named_session import named_session
    if (current_app.config.get('SCIDK_GUI_V3_ENABLED') is not True or
            current_app.config.get('SCIDK_CHAT_READINESS_ENABLED') is not True):
        return jsonify(error='Readiness unavailable'), 404, {'Cache-Control': 'no-store'}
    try:
        named_session(admin=True)
    except Exception:
        return jsonify(error='Named administrator session required'), 403, {'Cache-Control': 'no-store'}
    if request.method == 'GET':
        return render_template('gui/chat_readiness.html'), 200, {'Cache-Control': 'no-store'}
    from ...agent_tools.context import context_from_app
    from ...services.chat_readiness import checklist
    try:
        result = checklist(current_app, context_from_app(current_app, channel='chat'), request.get_json(silent=True))
        return jsonify(result), 200, {'Cache-Control': 'no-store'}
    except Exception:
        return jsonify(error='Invalid or unavailable readiness check'), 400, {'Cache-Control': 'no-store'}


@bp.get('/annotations')
def annotations_page():
    # Reuse the full Files drawer; no second annotation page/store.
    return redirect(url_for('ui.datasets', panel='annotations'))


@bp.get('/overview')
def overview():
    return _gui_page('Overview')


@bp.get('/knowledge')
def knowledge():
    return _gui_page('Knowledge')


@bp.get('/review')
def review():
    return _gui_page('Review')


# Routes
@bp.get('/login')
def login():
    """Login page for authentication."""
    return render_template('login.html')


@bp.get('/')
def index():
    """Settings page, or opt-in Overview landing page."""
    if current_app.config.get("SCIDK_GUI_V3_ENABLED") is True and request.path != "/settings":
        return _gui_page("Overview")
    ext = _get_ext()
    datasets = ext['graph'].list_datasets()
    reg = ext['registry']
    info = {
        'host': os.environ.get('SCIDK_HOST', '127.0.0.1'),
        'port': os.environ.get('SCIDK_PORT', '5000'),
        'debug': os.environ.get('SCIDK_DEBUG', '1'),
        'feature_file_index': os.environ.get('SCIDK_FEATURE_FILE_INDEX', ''),
        'hash_policy': os.environ.get('SCIDK_HASH_POLICY', 'auto'),
        'dataset_count': len(datasets),
        'interpreter_count': len(reg.by_id),
        'channel': os.environ.get('SCIDK_CHANNEL', 'stable'),
        'files_viewer': os.environ.get('SCIDK_FILES_VIEWER', ''),
        'providers': os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs'),
    }
    # Provide interpreter mappings and rules, and plugin summary counts for the Settings page sections
    mappings = {ext: [getattr(i, 'id', 'unknown') for i in interps] for ext, interps in reg.by_extension.items()}
    rules = list(reg.rules.rules)
    ext_count = len(reg.by_extension)
    interp_count = len(reg.by_id)
    # Rclone mounts UI is now always enabled
    return render_template('index.html', info=info, mappings=mappings, rules=rules, ext_count=ext_count, interp_count=interp_count, rclone_mounts_feature=True)


@bp.get('/chat')
def chat():
    """Chat interface page."""
    return render_template('chat.html')


@bp.get('/map')
def map_page():
    """Map visualization page."""
    ext = _get_ext()
    schema_summary = ext['graph'].schema_summary()
    return render_template('map.html', schema_summary=schema_summary)


@bp.get('/results')
def results():
    """Results page - transparency layer for analyses."""
    return render_template('results.html')


@bp.get('/scripts')
def scripts_page():
    """Scripts page with script library and executor."""
    return render_template('scripts.html')


@bp.get('/datasets')
def datasets():
    """List all datasets (files), optionally filtered by scan."""
    ext = _get_ext()
    all_datasets = ext['graph'].list_datasets()
    scan_id = (request.args.get('scan_id') or '').strip()
    selected_scan = None
    if scan_id:
        selected_scan = ext.get('scans', {}).get(scan_id)
    if selected_scan:
        checks = set(selected_scan.get('checksums') or [])
        datasets = [d for d in all_datasets if d.get('checksum') in checks]
    else:
        datasets = all_datasets
    directories = list(ext.get('directories', {}).values())
    directories.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
    recent_scans = list(ext.get('scans', {}).values())
    recent_scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
    # Show only the most recent N scans for dropdown
    N = 20
    recent_scans = recent_scans[:N]
    # files viewer mode: allow query param override, else env, else classic
    files_viewer = (request.args.get('files_viewer') or os.environ.get('SCIDK_FILES_VIEWER') or 'classic').strip()
    # files/datasets.html is the modular Files page: a lean shell plus one
    # {% include %} per drawer. The 4,200-line monolith it replaced is kept at
    # _archive/datasets_monolith.html for reference only — nothing renders it.
    return render_template('files/datasets.html', datasets=datasets, directories=directories, recent_scans=recent_scans, selected_scan=selected_scan, files_viewer=files_viewer)


@bp.get('/datasets/<dataset_id>')
def dataset_detail(dataset_id):
    """Show detail page for a single dataset."""
    ext = _get_ext()
    item = ext['graph'].get_dataset(dataset_id)
    if not item:
        return render_template('dataset_detail.html', dataset=None), 404
    return render_template('dataset_detail.html', dataset=item)


@bp.get('/workbook/<dataset_id>')
def workbook_view(dataset_id):
    """Simple XLSX viewer: list sheets and preview first rows."""
    ext = _get_ext()
    item = ext['graph'].get_dataset(dataset_id)
    if not item:
        return render_template('workbook.html', dataset=None, error="Dataset not found"), 404
    file_path = Path(item['path'])
    if (item.get('extension') or '').lower() not in ['.xlsx', '.xlsm']:
        return render_template('workbook.html', dataset=item, error="Not an Excel workbook (.xlsx/.xlsm)"), 400
    try:
        from openpyxl import load_workbook
        wb = load_workbook(filename=str(file_path), read_only=True, data_only=True)
        sheetnames = wb.sheetnames
        previews = []
        max_rows = 20
        max_cols = 20
        for name in sheetnames:
            ws = wb[name]
            rows = []
            for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True), start=1):
                rows.append(list(row))
            previews.append({'name': name, 'rows': rows})
        wb.close()
        return render_template('workbook.html', dataset=item, sheetnames=sheetnames, previews=previews, error=None)
    except Exception as e:
        return render_template('workbook.html', dataset=item, sheetnames=[], previews=[], error=str(e)), 500


@bp.get('/plugins')
def plugins():
    """Plugins transparency layer - show active, inactive, and draft plugins."""
    from scidk.core.scripts import ScriptsManager

    manager = ScriptsManager()
    all_scripts = manager.list_scripts()

    # Filter and categorize scripts
    active_plugins = [s for s in all_scripts if s.validation_status == 'validated' and s.is_active]
    inactive_plugins = [s for s in all_scripts if s.validation_status == 'validated' and not s.is_active]
    draft_failed_plugins = [s for s in all_scripts if s.validation_status in ('draft', 'failed')]

    return render_template(
        'plugins.html',
        active_plugins=active_plugins,
        inactive_plugins=inactive_plugins,
        draft_failed_plugins=draft_failed_plugins
    )


@bp.get('/pipeline/sources')
def pipeline_sources():
    """Pipeline source management (Cycle 3B Task A).

    A Pipeline page, not a plugin page: it lists every configured data source
    whatever plugin serves it. The page renders empty and fetches
    /api/pipeline/sources, so a slow or unreachable source cannot block the page
    itself from loading.
    """
    return render_template('pipeline_sources.html')


@bp.get('/pipeline/sources/<source_id>/schema')
def pipeline_source_schema(source_id):
    """The Maps canvas in Schema mode, scoped to one Pipeline source (Task C).

    Unlike the sources list, this page is rendered with data: the committed schema
    and the source's name go into the template so the canvas and the breadcrumb are
    correct on first paint rather than after a round trip. The three entry points
    differ only in what is loaded — ``?start=arrows|neo4j|blank``, chosen in Step 2
    of the add flow.
    """
    from flask import abort

    from ...pipeline.store import PipelineStore
    from ...services.canvas_service import pipeline_source_context

    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    source = PipelineStore(db_path).get_source(source_id)
    if source is None:
        abort(404)

    start = (request.args.get('start') or '').strip().lower()
    if start not in ('arrows', 'neo4j', 'blank'):
        start = ''
    return render_template(
        'pipeline_schema.html',
        source={'id': source['id'], 'name': source.get('name') or source['id']},
        context_id=pipeline_source_context(source_id),
        schema_json=source.get('schema_json'),
        saved_at=source.get('schema_saved_at'),
        start=start,
    )


@bp.get('/pipeline/sources/<source_id>/mapping')
def pipeline_source_mapping(source_id):
    """Step 3: column mapping, scoped to one Pipeline source (Task D).

    Rendered with the schema, the mapping and the transform catalogue inline, so the
    two panels are populated on first paint. The *source columns* are not: reading
    them means a live ``find()`` against the source, which is bounded at 10s and
    must not be able to hold up the page. The page fetches
    ``/api/pipeline/sources/<id>/columns`` for those and says so while it waits.

    The transform catalogue is per-source because it depends on the plugin: which
    names a mapping config may use is the core library plus this plugin's
    ``transform_library()``, and offering a name the engine will not resolve would
    produce a config that fails its own R check.
    """
    from flask import abort

    from ...pipeline.mapping_ui import describe_transforms
    from ...pipeline.plugin_registry import resolve_plugin, transform_library_for
    from ...pipeline.store import PipelineStore

    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    source = PipelineStore(db_path).get_source(source_id)
    if source is None:
        abort(404)

    try:
        plugin = resolve_plugin(source.get('plugin_type') or '')
    except Exception:  # noqa: BLE001 - an unavailable plugin still has core transforms
        plugin = None

    return render_template(
        'pipeline_mapping.html',
        source={'id': source['id'], 'name': source.get('name') or source['id'],
                'plugin_type': source.get('plugin_type') or ''},
        schema_json=source.get('schema_json'),
        mapping_json=source.get('mapping_json'),
        saved_at=source.get('mapping_saved_at'),
        transforms=describe_transforms(transform_library_for(plugin)),
    )


@bp.get('/interpreters')
def interpreters():
    """Redirect to landing page interpreters section (backward compatibility)."""
    return redirect(url_for('ui.index') + '#interpreters')


@bp.get('/extensions')
def extensions():
    """Redirect to plugins section on home page."""
    return redirect(url_for('ui.index') + '#plugins')


@bp.get('/rocrate_view')
def rocrate_view():
    """Lightweight wrapper page to preview RO-Crate JSON-LD and prepare for embedding Crate-O."""
    prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
    root_id = (request.args.get('root_id') or '/').strip() or '/'
    sel_path = (request.args.get('path') or root_id).strip()
    try:
        from urllib.parse import urlencode
        qs = urlencode({'provider_id': prov_id, 'root_id': root_id, 'path': sel_path})
    except Exception:
        qs = f"provider_id={prov_id}&root_id={root_id}&path={sel_path}"
    metadata_url = '/api/rocrate?' + qs
    embed_mode = (os.environ.get('SCIDK_ROCRATE_EMBED') or 'json').strip()
    return render_template('rocrate_view.html', metadata_url=metadata_url, embed_mode=embed_mode, prov_id=prov_id, root_id=root_id, path=sel_path)


@bp.get('/entities')
def entities():
    """Entities page: the Labels and Links pages as two tabs under one nav item.

    The tab is selected server-side and each tab is a full page load, so only one
    of the two subpage templates is ever in the document. That is deliberate, not
    incidental: ``labels.html``'s inline scripts and ``static/js/links/*.js`` each
    declare top-level ``showToast``, ``escapeHtml``, ``handleGlobalKeydown`` and
    ``returnFocusToSidePanel``, so rendering both into one DOM would leave the
    later-parsed definitions bound for both tabs and break the keyboard and focus
    handling on one of them.

    Neither subpage template is modified; ``entities_tab`` only tells base.html to
    render the tab strip above the content.
    """
    tab = (request.args.get('tab') or '').strip().lower()
    if tab == 'relationships':
        return render_template('links.html', entities_tab='relationships')
    return render_template('labels.html', entities_tab='entities')


@bp.get('/labels')
def labels():
    """Backward compatibility redirect: /labels → the Entities tab."""
    return redirect(url_for('ui.entities', tab='entities'))


@bp.get('/links')
def links():
    """Backward compatibility redirect: /links → the Relationships tab."""
    return redirect(url_for('ui.entities', tab='relationships'))


@bp.get('/integrate')
def integrate_redirect():
    """Backward compatibility redirect: /integrate → the Relationships tab."""
    return redirect(url_for('ui.entities', tab='relationships'))


@bp.get('/settings')
def settings():
    """Redirect to landing page (backward compatibility)."""
    if current_app.config.get("SCIDK_GUI_V3_ENABLED") is True:
        return index()
    return redirect(url_for('ui.index'))


@bp.post('/scan')
def ui_scan():
    """Handle scan form submission from UI."""
    ext = _get_ext()
    fs = current_app.extensions['scidk']['fs']
    path = request.form.get('path') or os.getcwd()
    recursive = request.form.get('recursive') == 'on'
    # Pre-scan snapshot
    before = set(ds.get('checksum') for ds in ext['graph'].list_datasets())
    started = time.time()
    count = fs.scan_directory(Path(path), recursive=recursive)
    ended = time.time()
    duration = ended - started
    after = set(ds.get('checksum') for ds in ext['graph'].list_datasets())
    new_checksums = sorted(list(after - before))
    by_ext = {}
    ext_map = {ds.get('checksum'): ds.get('extension') or '' for ds in ext['graph'].list_datasets()}
    for ch in new_checksums:
        ext_val = ext_map.get(ch, '')
        by_ext[ext_val] = by_ext.get(ext_val, 0) + 1
    sid_src = f"{path}|{started}"
    scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
    scan = {
        'id': scan_id,
        'path': str(path),
        'recursive': bool(recursive),
        'started': started,
        'ended': ended,
        'duration_sec': duration,
        'file_count': int(count),
        'checksums': new_checksums,
        'by_ext': by_ext,
        'source': getattr(fs, 'last_scan_source', 'python'),
        'errors': [],
    }
    scans = ext.setdefault('scans', {})
    scans[scan_id] = scan
    from ...core import scan_owner as _scan_owner
    _scan_owner.record(scan_id, _scan_owner.current_username())
    # Persist scan summary to SQLite (best-effort)
    try:
        from ...core import path_index_sqlite as pix
        from ...core import migrations as _migs
        import json as _json
        conn = pix.connect()
        try:
            _migs.migrate(conn)
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO scans(id, root, started, completed, status, extra_json) VALUES(?,?,?,?,?,?)",
                (
                    scan_id,
                    str(path),
                    float(started or 0.0),
                    float(ended or 0.0),
                    'completed',
                    _json.dumps({
                        'recursive': bool(recursive),
                        'duration_sec': duration,
                        'file_count': int(count),
                        'by_ext': by_ext,
                        'source': getattr(fs, 'last_scan_source', 'python'),
                        'checksums': new_checksums,
                        'committed': bool(scan.get('committed', False)),
                        'committed_at': scan.get('committed_at'),
                    })
                )
            )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass
    telem = ext.setdefault('telemetry', {})
    telem['last_scan'] = {
        'path': str(path),
        'recursive': bool(recursive),
        'scanned': int(count),
        'started': started,
        'ended': ended,
        'duration_sec': duration,
    }
    # Track scanned directories here as well
    dirs = ext.setdefault('directories', {})
    drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': []})
    drec.update({'recursive': bool(recursive), 'scanned': int(count), 'last_scanned': ended})
    drec.setdefault('scan_ids', []).append(scan_id)
    return redirect(url_for('ui.datasets', scan_id=scan_id))
