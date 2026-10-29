"""Production UI routes with explicit synthetic services; never create_app()."""
from pathlib import Path
from types import SimpleNamespace
from flask import Flask, jsonify, request
from scidk.web.routes.ui import bp

ROOT = Path(__file__).resolve().parents[2]
FILE = {'id': '/synthetic/vevo/metadata.xml', 'path': '/synthetic/vevo/metadata.xml',
        'name': 'metadata.xml', 'type': 'file', 'size': 2048, 'mtime': 1793275200,
        'scientific_metadata': {'modality': 'Ultrasound', 'instrument': 'Synthetic Vevo'},
        'raw_xml': '<instrument><modality>Ultrasound</modality></instrument>'}
DATASET = {'id': '42', 'element_id': 'synthetic:dataset:42', 'name': 'Synthetic Vevo study',
           'label': 'Dataset', 'labels': ['Dataset'], 'properties': {
               'source': 'collection', 'path': '/synthetic/vevo', 'modality': 'Ultrasound',
               'metadata': {'instrument': 'Synthetic Vevo', 'acquisition': {'frames': 12}},
               'provenance': {'source_version': 'fixture-1', 'method': 'synthetic fixture'}}}


def make_gui_app():
    app = Flask(__name__, template_folder=str(ROOT/'scidk/ui/templates'),
                static_folder=str(ROOT/'scidk/ui/static'))
    app.register_blueprint(bp)
    app.config.update(TESTING=True)
    app.extensions['scidk'] = {
        'graph': SimpleNamespace(list_datasets=lambda: [], schema_summary=lambda: {}),
        'registry': SimpleNamespace(by_id={}, by_extension={}, rules=SimpleNamespace(rules=[]))}
    return app


def make_disposable_app():
    app = make_gui_app()
    app.config['SCIDK_GUI_V3_ENABLED'] = True
    # Preserve the Prompt 10/12 visual fixture while new Knowledge candidates
    # receive separate human review. Real governed workflows use their own app.
    app.config['SCIDK_KNOWLEDGE_WORKSPACE_ENABLED'] = False
    app.extensions['gui_test_requests'] = []

    @app.before_request
    def prohibit_writes():
        app.extensions['gui_test_requests'].append((request.method, request.full_path))
        if request.method not in ('GET', 'HEAD'):
            return jsonify(error='Writes disabled in GUI fixture'), 405
        allowed_ui = {'/', '/overview', '/knowledge', '/review', '/datasets', '/settings',
                      '/pipeline/sources', '/map', '/chat', '/entities', '/labels', '/links',
                      '/integrate', '/results', '/login'}
        if not (request.path in allowed_ui or request.path.startswith('/static/')
                or request.path.startswith('/api/')):
            return jsonify(error='Route unavailable in disconnected GUI fixture'), 404

    @app.get('/api/<path:path>')
    def synthetic_api(path):
        fixed = {
            'auth/status': {'authenticated': False, 'auth_enabled': False},
            'servers': [{'id': 'local_fs', 'display_name': 'Synthetic drive',
                         'root_id': '/synthetic', 'root_path': '/synthetic', 'connected': True}],
            'datasets': [FILE], 'tasks': [], 'tasks/queue': {'queue': {'running': [], 'queued': []}},
            'scans': [], 'health/comprehensive': {'components': {'neo4j': {'status': 'disconnected'}}},
            'pipeline/sources': {'sources': []}, 'pipeline/pipelines': {'pipelines': []},
            'plugins/templates': {'templates': []},
            'settings/smtp': {}, 'logs/viewer': {'entries': [], 'logs': []},
            'scanner/settings': {'settings': {}}, 'connections': {'connections': []},
            'settings/neo4j/profiles': {'profiles': []}, 'chat/sessions': {'sessions': []},
            'chat/concept-graph/status': {}, 'chat/concept-graph/intents': {'intents': []},
            'chat/concept-graph/tools': {'tools': []}, 'providers': {'providers': []},
            'settings/rclone-interpret': {}, 'rclone/mounts': {'mounts': []},
            'llm/presets': {'presets': []}, 'chat/schema/status': {}, 'users': {'users': []},
            'audit-log': {'entries': []}, 'scripts/scripts': {'status': 'ok', 'scripts': []},
            'labels': {'status':'success', 'labels': []}, 'settings/table-formats': {'formats': []},
            'settings/plugin-endpoints': {'status': 'success', 'endpoints': []},
            'v2/links': {'status': 'success', 'links': [], 'count': 0},
            'settings/alerts': {}, 'llm/settings': {}, 'settings/tokens': {'tokens': []},
            **{'settings/neo4j/profiles/by-role/'+role: {'profile': None}
               for role in ['primary','labels_source','readonly','ingestion_target']},
        }
        if path in fixed:
            return jsonify(fixed[path])
        if path == 'browse':
            location = request.args.get('path', '')
            if location.endswith('/vevo'):
                return jsonify(entries=[FILE])
            return jsonify(entries=[{'id': '/synthetic/vevo', 'path': '/synthetic/vevo',
                                      'name': 'vevo', 'type': 'folder'}])
        if path == 'canvas/nodes/search' and request.args.get('label') == 'Dataset':
            q = request.args.get('q', '').lower()
            return jsonify(results=[DATASET] if q and q in DATASET['name'].lower() else [])
        if path == 'annotations' and request.args.get('file_id'):
            return jsonify(items=[{'id': 1, 'file_id': request.args['file_id'],
                                    'kind': 'note', 'label': 'Synthetic annotation',
                                    'note': 'Instrument metadata checked in this synthetic example.'}])
        # Missing fake responses must be discovered, never silently treated as success.
        return jsonify(error='Unconfigured synthetic API: ' + path), 501

    return app


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5075)
    args = parser.parse_args()
    make_disposable_app().run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False)
