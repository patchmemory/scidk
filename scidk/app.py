from flask import Flask, Blueprint, jsonify, request, render_template, redirect, url_for
from pathlib import Path
import os

from .core.graph import InMemoryGraph
from .core.filesystem import FilesystemManager
from .core.registry import InterpreterRegistry
from .interpreters.python_code import PythonCodeInterpreter
from .core.pattern_matcher import Rule


def create_app():
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")

    # Core singletons (MVP: in-memory)
    graph = InMemoryGraph()
    registry = InterpreterRegistry()

    # Register a minimal interpreter (Python code)
    py_interp = PythonCodeInterpreter()
    registry.register_extension(".py", py_interp)
    # Register a simple rule to prefer python_code for *.py files
    registry.register_rule(Rule(id="rule.py.default", interpreter_id=py_interp.id, pattern="*.py", priority=10, conditions={"ext": ".py"}))

    fs = FilesystemManager(graph=graph, registry=registry)

    # Store refs on app for easy access
    app.extensions = getattr(app, 'extensions', {})
    app.extensions['scidk'] = {
        'graph': graph,
        'registry': registry,
        'fs': fs,
    }

    # API routes
    api = Blueprint('api', __name__, url_prefix='/api')

    @api.post('/scan')
    def api_scan():
        data = request.get_json(force=True, silent=True) or {}
        path = data.get('path') or os.getcwd()
        recursive = bool(data.get('recursive', True))
        try:
            import time
            started = time.time()
            count = fs.scan_directory(Path(path), recursive=recursive)
            ended = time.time()
            duration = ended - started
            # Save telemetry on app
            telem = app.extensions['scidk'].setdefault('telemetry', {})
            telem['last_scan'] = {
                'path': str(path),
                'recursive': bool(recursive),
                'scanned': int(count),
                'started': started,
                'ended': ended,
                'duration_sec': duration,
            }
            return jsonify({"status": "ok", "scanned": count, "duration_sec": duration, "path": str(path), "recursive": bool(recursive)}), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 400

    @api.get('/datasets')
    def api_datasets():
        items = graph.list_datasets()
        return jsonify(items)

    @api.get('/datasets/<dataset_id>')
    def api_dataset(dataset_id):
        item = graph.get_dataset(dataset_id)
        if not item:
            return jsonify({"error": "not found"}), 404
        return jsonify(item)

    @api.post('/interpret')
    def api_interpret():
        data = request.get_json(force=True, silent=True) or {}
        dataset_id = data.get('dataset_id')
        interpreter_id = data.get('interpreter_id')
        if not dataset_id:
            return jsonify({"status": "error", "error": "dataset_id required"}), 400
        ds = graph.get_dataset(dataset_id)
        if not ds:
            return jsonify({"status": "error", "error": "dataset not found"}), 404
        file_path = Path(ds['path'])
        if interpreter_id:
            interp = registry.get_by_id(interpreter_id)
            if not interp:
                return jsonify({"status": "error", "error": "interpreter not found"}), 404
            interps = [interp]
        else:
            interps = registry.select_for_dataset(ds)
            if not interps:
                return jsonify({"status": "error", "error": "no interpreters available"}), 400
        results = []
        for interp in interps:
            try:
                result = interp.interpret(file_path)
                graph.add_interpretation(ds['checksum'], interp.id, {
                    'status': result.get('status', 'success'),
                    'data': result.get('data', result),
                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                })
                results.append({'interpreter_id': interp.id, 'status': 'ok'})
            except Exception as e:
                graph.add_interpretation(ds['checksum'], interp.id, {
                    'status': 'error',
                    'data': {'error': str(e)},
                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                })
                results.append({'interpreter_id': interp.id, 'status': 'error', 'error': str(e)})
        return jsonify({"status": "ok", "results": results}), 200

    @api.post('/chat')
    def api_chat():
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"status": "error", "error": "message required"}), 400
        store = app.extensions['scidk'].setdefault('chat', {"history": []})
        # Simple echo bot with count
        reply = f"Echo: {message}"
        entry_user = {"role": "user", "content": message}
        entry_assistant = {"role": "assistant", "content": reply}
        store['history'].append(entry_user)
        store['history'].append(entry_assistant)
        return jsonify({"status": "ok", "reply": reply, "history": store['history']}), 200

    app.register_blueprint(api)

    # UI routes
    ui = Blueprint('ui', __name__)

    @ui.get('/')
    def index():
        datasets = app.extensions['scidk']['graph'].list_datasets()
        # Build lightweight summaries for the landing page
        by_ext = {}
        interp_types = set()
        for d in datasets:
            by_ext[d.get('extension') or ''] = by_ext.get(d.get('extension') or '', 0) + 1
            for k in (d.get('interpretations') or {}).keys():
                interp_types.add(k)
        schema_summary = app.extensions['scidk']['graph'].schema_summary()
        telemetry = app.extensions['scidk'].get('telemetry', {})
        return render_template('index.html', datasets=datasets, by_ext=by_ext, schema_summary=schema_summary, telemetry=telemetry)

    @ui.get('/datasets')
    def datasets():
        datasets = app.extensions['scidk']['graph'].list_datasets()
        return render_template('datasets.html', datasets=datasets)

    @ui.get('/datasets/<dataset_id>')
    def dataset_detail(dataset_id):
        item = app.extensions['scidk']['graph'].get_dataset(dataset_id)
        if not item:
            return render_template('dataset_detail.html', dataset=None), 404
        return render_template('dataset_detail.html', dataset=item)

    @ui.get('/workbook/<dataset_id>')
    def workbook_view(dataset_id):
        # Simple XLSX viewer: list sheets and preview first rows
        item = app.extensions['scidk']['graph'].get_dataset(dataset_id)
        if not item:
            return render_template('workbook.html', dataset=None, error="Dataset not found"), 404
        from pathlib import Path as _P
        file_path = _P(item['path'])
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

    @ui.get('/plugins')
    def plugins():
        # Placeholder: no dynamic plugins yet. Show counts from registry for context.
        reg = app.extensions['scidk']['registry']
        ext_count = len(reg.by_extension)
        interp_count = len(reg.by_id)
        return render_template('plugins.html', ext_count=ext_count, interp_count=interp_count)

    @ui.get('/extensions')
    def extensions():
        # List registry mappings and selection rules
        reg = app.extensions['scidk']['registry']
        mappings = {ext: [getattr(i, 'id', 'unknown') for i in interps] for ext, interps in reg.by_extension.items()}
        rules = list(reg.rules.rules)
        return render_template('extensions.html', mappings=mappings, rules=rules)

    @ui.get('/settings')
    def settings():
        # Basic settings from environment and current in-memory sizes
        datasets = app.extensions['scidk']['graph'].list_datasets()
        reg = app.extensions['scidk']['registry']
        info = {
            'host': os.environ.get('SCIDK_HOST', '127.0.0.1'),
            'port': os.environ.get('SCIDK_PORT', '5000'),
            'debug': os.environ.get('SCIDK_DEBUG', '1'),
            'dataset_count': len(datasets),
            'interpreter_count': len(reg.by_id),
        }
        return render_template('settings.html', info=info)

    @ui.post('/scan')
    def ui_scan():
        path = request.form.get('path') or os.getcwd()
        recursive = request.form.get('recursive') == 'on'
        import time
        started = time.time()
        count = fs.scan_directory(Path(path), recursive=recursive)
        ended = time.time()
        duration = ended - started
        telem = app.extensions['scidk'].setdefault('telemetry', {})
        telem['last_scan'] = {
            'path': str(path),
            'recursive': bool(recursive),
            'scanned': int(count),
            'started': started,
            'ended': ended,
            'duration_sec': duration,
        }
        return redirect(url_for('ui.datasets'))

    app.register_blueprint(ui)

    return app


def main():
    app = create_app()
    # Read host/port from env for convenience
    host = os.environ.get('SCIDK_HOST', '127.0.0.1')
    port = int(os.environ.get('SCIDK_PORT', '5000'))
    debug = os.environ.get('SCIDK_DEBUG', '1') == '1'
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
