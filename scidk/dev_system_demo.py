"""Explicit synthetic-only service hook and local deterministic fake provider.

Neither mode configures a remote model, creates review decisions or touches Neo4j.
See docs/design/gui-development-startup.md. Not production bootstrap.
"""
from pathlib import Path

RESOURCE = {'namespace': 'synthetic-system-demo', 'resource_id': 'prompt15-system-demo'}
ENTRY = 'system:synthetic-demo'


def configure(app):
    from .core.auth import AuthManager
    from .core.settings import InterpreterSettings
    from .pipeline.store import PipelineStore
    from .agent_tools.security import PolicyStore
    from .agent_tools.capabilities import CapabilityStore
    from .agent_tools.knowledge import KnowledgeServices
    from .knowledge.projection import Projection, ContextService, content_hash, git_revision
    db = app.config['SCIDK_SETTINGS_DB']
    auth = AuthManager(db)
    try:
        users = auth.list_users(include_disabled=True)
        if len(users) != 1 or users[0]['role'] != 'admin' or not users[0]['enabled']:
            raise ValueError('Synthetic bootstrap requires one enabled named development administrator')
        uid = users[0]['id']
    finally:
        auth.close()
    settings = InterpreterSettings(db); settings.close()
    store = PipelineStore(db)
    source = store.get_source(RESOURCE['resource_id'])
    if source and (source['plugin_type'] != 'synthetic-demo' or source['name'] != 'Synthetic System demo only'):
        raise ValueError('Reserved synthetic Resource identity is already in use')
    if not source:
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute('INSERT INTO pipeline_source(id,name,plugin_type) VALUES (?,?,?)',
                         (RESOURCE['resource_id'], 'Synthetic System demo only', 'synthetic-demo'))
    policy = PolicyStore(db); policy.initialize(admin_id=uid)
    policy.classify(**RESOURCE, risk='low', admin_id=uid)
    policy.grant_resource(uid, **RESOURCE, admin_id=uid)
    root = Path(__file__).resolve().parents[1]
    path = 'tests/fixtures/knowledge_curation/prompt15-system.md'
    node = {'id': ENTRY, 'name': 'Synthetic System demonstration', 'type': 'documentation',
            'visibility': 'restricted', 'source_scope': RESOURCE, 'git_revision': git_revision(root),
            'applicability': 'knowledge-context/1',
            'sources': [{'path': path, 'source_scope': RESOURCE, 'hash': content_hash((root / path).read_bytes())}]}
    projection = Projection([node], [], {'domain': 'system', 'synthetic': True})
    policy.grant_evidence(uid, ContextService.grant_id(node), admin_id=uid)
    caps = CapabilityStore(db); caps.initialize(admin_id=uid)
    caps.grant_tool(uid, 'overview', 'get_system_context', admin_id=uid)
    app.extensions['knowledge_services'] = KnowledgeServices(system=ContextService(projection, db, enabled=True), system_root=root)


def main():
    import argparse
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    parser = argparse.ArgumentParser(description='Local deterministic synthetic provider; no remote network calls')
    parser.add_argument('--port', type=int, default=5010)
    args = parser.parse_args()
    class FakeProvider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log credentials, request bodies or prompts.
        def send_json(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if self.path != '/v1/models':
                self.send_json(404, {'error': 'Not available'}); return
            self.send_json(200, {'data': [{'id': 'synthetic-demo'}]})
        def do_POST(self):
            size = int(self.headers.get('Content-Length', 0))
            if self.path != '/v1/chat/completions' or not 0 < size <= 32768:
                self.send_json(400, {'error': 'Invalid synthetic request'}); return
            self.rfile.read(size)
            self.send_json(200, {'model': 'synthetic-demo', 'choices': [{'message': {'content':
                'Synthetic demonstration only. Context system:synthetic-demo describes a fictional local workflow; no accepted research facts are asserted.'}, 'finish_reason': 'stop'}]})
    HTTPServer(('127.0.0.1', args.port), FakeProvider).serve_forever()


if __name__ == '__main__':
    main()
