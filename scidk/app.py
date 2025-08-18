from flask import Flask, Blueprint, jsonify, request, render_template, redirect, url_for
from pathlib import Path
import os

from .core.graph import InMemoryGraph
from .core.filesystem import FilesystemManager
from .core.registry import InterpreterRegistry
from .interpreters.python_code import PythonCodeInterpreter


def create_app():
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")

    # Core singletons (MVP: in-memory)
    graph = InMemoryGraph()
    registry = InterpreterRegistry()

    # Register a minimal interpreter (Python code)
    registry.register_extension(".py", PythonCodeInterpreter())

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
            count = fs.scan_directory(Path(path), recursive=recursive)
            return jsonify({"status": "ok", "scanned": count}), 200
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

    app.register_blueprint(api)

    # UI routes
    ui = Blueprint('ui', __name__)

    @ui.get('/')
    def index():
        datasets = app.extensions['scidk']['graph'].list_datasets()
        return render_template('index.html', datasets=datasets)

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

    @ui.get('/plugins')
    def plugins():
        return render_template('plugins.html')

    @ui.get('/extensions')
    def extensions():
        # In future, we can list registry mappings here
        return render_template('extensions.html')

    @ui.get('/settings')
    def settings():
        # Placeholder for settings
        return render_template('settings.html')

    @ui.post('/scan')
    def ui_scan():
        path = request.form.get('path') or os.getcwd()
        recursive = request.form.get('recursive') == 'on'
        fs.scan_directory(Path(path), recursive=recursive)
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
