from flask import Flask, Blueprint, jsonify, request, render_template, redirect, url_for
from pathlib import Path
import os

from .core.graph import InMemoryGraph
from .core.filesystem import FilesystemManager
from .core.registry import InterpreterRegistry
from .interpreters.python_code import PythonCodeInterpreter
from .interpreters.csv_interpreter import CsvInterpreter
from .interpreters.json_interpreter import JsonInterpreter
from .interpreters.yaml_interpreter import YamlInterpreter
from .interpreters.ipynb_interpreter import IpynbInterpreter
from .core.pattern_matcher import Rule


def create_app():
    app = Flask(__name__, template_folder="ui/templates", static_folder="ui/static")

    # Core singletons (MVP: in-memory)
    graph = InMemoryGraph()
    registry = InterpreterRegistry()

    # Register interpreters
    py_interp = PythonCodeInterpreter()
    csv_interp = CsvInterpreter()
    json_interp = JsonInterpreter()
    yaml_interp = YamlInterpreter()
    ipynb_interp = IpynbInterpreter()
    registry.register_extension(".py", py_interp)
    registry.register_extension(".csv", csv_interp)
    registry.register_extension(".json", json_interp)
    registry.register_extension(".yml", yaml_interp)
    registry.register_extension(".yaml", yaml_interp)
    registry.register_extension(".ipynb", ipynb_interp)
    # Register simple rules to prefer interpreters for extensions
    registry.register_rule(Rule(id="rule.py.default", interpreter_id=py_interp.id, pattern="*.py", priority=10, conditions={"ext": ".py"}))
    registry.register_rule(Rule(id="rule.csv.default", interpreter_id=csv_interp.id, pattern="*.csv", priority=10, conditions={"ext": ".csv"}))
    registry.register_rule(Rule(id="rule.json.default", interpreter_id=json_interp.id, pattern="*.json", priority=10, conditions={"ext": ".json"}))
    registry.register_rule(Rule(id="rule.yml.default", interpreter_id=yaml_interp.id, pattern="*.yml", priority=10, conditions={"ext": ".yml"}))
    registry.register_rule(Rule(id="rule.yaml.default", interpreter_id=yaml_interp.id, pattern="*.yaml", priority=10, conditions={"ext": ".yaml"}))
    registry.register_rule(Rule(id="rule.ipynb.default", interpreter_id=ipynb_interp.id, pattern="*.ipynb", priority=10, conditions={"ext": ".ipynb"}))

    fs = FilesystemManager(graph=graph, registry=registry)

    # Store refs on app for easy access
    app.extensions = getattr(app, 'extensions', {})
    app.extensions['scidk'] = {
        'graph': graph,
        'registry': registry,
        'fs': fs,
        # in-session registries
        'scans': {},  # scan_id -> scan session dict
        'directories': {},  # path -> aggregate info incl. scan_ids
        'telemetry': {},
        'tasks': {},  # task_id -> task dict (background jobs like scans)
        'neo4j_config': {
            'uri': None,
            'user': None,
            'password': None,
            'database': None,
        },
        'neo4j_state': {
            'connected': False,
            'last_error': None,
        },
    }

    # API routes
    api = Blueprint('api', __name__, url_prefix='/api')

    # Helper to read Neo4j configuration, preferring in-app settings over environment
    def _get_neo4j_params():
        cfg = app.extensions['scidk'].get('neo4j_config', {})
        uri = cfg.get('uri') or os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')
        user = cfg.get('user') or os.environ.get('NEO4J_USER') or os.environ.get('NEO4J_USERNAME')
        pwd = cfg.get('password') or os.environ.get('NEO4J_PASSWORD')
        database = cfg.get('database') or os.environ.get('SCIDK_NEO4J_DATABASE') or None
        return uri, user, pwd, database

    @api.post('/scan')
    def api_scan():
        data = request.get_json(force=True, silent=True) or {}
        path = data.get('path') or os.getcwd()
        recursive = bool(data.get('recursive', True))
        try:
            import time, hashlib
            # Pre-scan snapshot of checksums
            before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
            started = time.time()
            count = fs.scan_directory(Path(path), recursive=recursive)
            ended = time.time()
            duration = ended - started
            after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
            new_checksums = sorted(list(after - before))
            # Build simple by_ext from new datasets
            by_ext = {}
            ext_map = {}
            for ds in app.extensions['scidk']['graph'].list_datasets():
                ext_map[ds.get('checksum')] = ds.get('extension') or ''
            for ch in new_checksums:
                ext = ext_map.get(ch, '')
                by_ext[ext] = by_ext.get(ext, 0) + 1
            # Create scan session id (short sha1 of path+started)
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
                'committed': False,
                'committed_at': None,
            }
            scans = app.extensions['scidk'].setdefault('scans', {})
            scans[scan_id] = scan
            # Save telemetry on app
            telem = app.extensions['scidk'].setdefault('telemetry', {})
            telem['last_scan'] = {
                'path': str(path),
                'recursive': bool(recursive),
                'scanned': int(count),
                'started': started,
                'ended': ended,
                'duration_sec': duration,
                'source': getattr(fs, 'last_scan_source', 'python'),
            }
            # Track scanned directories (in-session registry)
            dirs = app.extensions['scidk'].setdefault('directories', {})
            drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': [], 'source': getattr(fs, 'last_scan_source', 'python')})
            drec.update({'recursive': bool(recursive), 'scanned': int(count), 'last_scanned': ended, 'source': getattr(fs, 'last_scan_source', 'python')})
            drec.setdefault('scan_ids', []).append(scan_id)
            return jsonify({"status": "ok", "scan_id": scan_id, "scanned": count, "duration_sec": duration, "path": str(path), "recursive": bool(recursive)}), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 400

    @api.post('/tasks')
    def api_tasks_create():
        """Create a background task. Supports type=scan and type=commit."""
        data = request.get_json(force=True, silent=True) or {}
        ttype = (data.get('type') or 'scan').strip().lower()
        import time, hashlib, threading
        started = time.time()

        if ttype == 'scan':
            path = data.get('path') or os.getcwd()
            recursive = bool(data.get('recursive', True))
            tid_src = f"scan|{path}|{started}"
            task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]
            task = {
                'id': task_id,
                'type': 'scan',
                'status': 'running',
                'path': str(path),
                'recursive': bool(recursive),
                'started': started,
                'ended': None,
                'total': 0,
                'processed': 0,
                'progress': 0.0,
                'scan_id': None,
                'error': None,
            }
            app.extensions['scidk']['tasks'][task_id] = task

            def _worker():
                try:
                    # Snapshot before
                    before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
                    # Estimate total using Python traversal (MVP)
                    files = [p for p in fs._iter_files_python(Path(path), recursive=recursive)]  # type: ignore
                    total = len(files)
                    task['total'] = total
                    # Process each file similarly to scan_directory
                    processed = 0
                    for p in files:
                        # upsert
                        ds = fs.create_dataset_node(p)
                        app.extensions['scidk']['graph'].upsert_dataset(ds)
                        # interpreters
                        interps = registry.select_for_dataset(ds)
                        for interp in interps:
                            try:
                                result = interp.interpret(p)
                                app.extensions['scidk']['graph'].add_interpretation(ds['checksum'], interp.id, {
                                    'status': result.get('status', 'success'),
                                    'data': result.get('data', result),
                                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                                })
                            except Exception as e:
                                app.extensions['scidk']['graph'].add_interpretation(ds['checksum'], interp.id, {
                                    'status': 'error',
                                    'data': {'error': str(e)},
                                    'interpreter_version': getattr(interp, 'version', '0.0.1'),
                                })
                        processed += 1
                        task['processed'] = processed
                        if total:
                            task['progress'] = processed / total
                    ended = time.time()
                    # Build scan record (reuse logic from api_scan)
                    after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
                    new_checksums = sorted(list(after - before))
                    by_ext = {}
                    ext_map = {ds.get('checksum'): ds.get('extension') or '' for ds in app.extensions['scidk']['graph'].list_datasets()}
                    for ch in new_checksums:
                        ext = ext_map.get(ch, '')
                        by_ext[ext] = by_ext.get(ext, 0) + 1
                    sid_src = f"{path}|{started}"
                    scan_id = hashlib.sha1(sid_src.encode()).hexdigest()[:12]
                    scan = {
                        'id': scan_id,
                        'path': str(path),
                        'recursive': bool(recursive),
                        'started': started,
                        'ended': ended,
                        'duration_sec': ended - started,
                        'file_count': int(processed),
                        'checksums': new_checksums,
                        'by_ext': by_ext,
                        'source': 'python',
                        'errors': [],
                        'committed': False,
                        'committed_at': None,
                    }
                    app.extensions['scidk']['scans'][scan_id] = scan
                    # Telemetry
                    app.extensions['scidk'].setdefault('telemetry', {})['last_scan'] = {
                        'path': str(path), 'recursive': bool(recursive), 'scanned': int(processed),
                        'started': started, 'ended': ended, 'duration_sec': ended - started, 'source': 'python'
                    }
                    # Directory registry
                    dirs = app.extensions['scidk'].setdefault('directories', {})
                    drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': [], 'source': 'python'})
                    drec.update({'recursive': bool(recursive), 'scanned': int(processed), 'last_scanned': ended, 'source': 'python'})
                    drec.setdefault('scan_ids', []).append(scan_id)
                    # Complete task
                    task['ended'] = ended
                    task['status'] = 'completed'
                    task['scan_id'] = scan_id
                    task['progress'] = 1.0
                except Exception as e:
                    import time as _t
                    task['ended'] = _t.time()
                    task['status'] = 'error'
                    task['error'] = str(e)
            threading.Thread(target=_worker, daemon=True).start()
            return jsonify({'task_id': task_id, 'status': 'running'}), 202

        elif ttype == 'commit':
            scan_id = (data.get('scan_id') or '').strip()
            scans = app.extensions['scidk'].setdefault('scans', {})
            s = scans.get(scan_id)
            if not s:
                return jsonify({'error': 'scan not found'}), 404
            checksums = s.get('checksums') or []
            total = len(checksums)
            tid_src = f"commit|{scan_id}|{started}"
            task_id = hashlib.sha1(tid_src.encode()).hexdigest()[:12]
            task = {
                'id': task_id,
                'type': 'commit',
                'status': 'running',
                'scan_id': scan_id,
                'path': s.get('path'),
                'started': started,
                'ended': None,
                'total': total,
                'processed': 0,
                'progress': 0.0,
                'neo4j_attempted': False,
                'neo4j_written': 0,
                'neo4j_error': None,
                'error': None,
            }
            app.extensions['scidk']['tasks'][task_id] = task

            def _worker_commit():
                try:
                    g = app.extensions['scidk']['graph']
                    # In-memory commit first
                    g.commit_scan(s)
                    s['committed'] = True
                    s['committed_at'] = time.time()
                    # Build rows and advance progress
                    ds_map = getattr(g, 'datasets', {})
                    rows = []
                    from pathlib import Path as _P
                    processed = 0
                    for ch in checksums:
                        d = ds_map.get(ch)
                        if not d:
                            continue
                        try:
                            parent = str(_P(d.get('path')).parent)
                        except Exception:
                            parent = ''
                        interps = list((d.get('interpretations') or {}).keys())
                        rows.append({
                            'checksum': d.get('checksum'),
                            'path': d.get('path'),
                            'filename': d.get('filename'),
                            'extension': d.get('extension'),
                            'size_bytes': int(d.get('size_bytes') or 0),
                            'created': float(d.get('created') or 0),
                            'modified': float(d.get('modified') or 0),
                            'mime_type': d.get('mime_type'),
                            'folder': parent,
                            'interps': interps,
                        })
                        processed += 1
                        task['processed'] = processed
                        if total:
                            task['progress'] = processed / total
                    # Neo4j write if configured
                    uri, user, pwd, database = _get_neo4j_params()
                    if uri and user and pwd:
                        task['neo4j_attempted'] = True
                        try:
                            from neo4j import GraphDatabase  # type: ignore
                            driver = GraphDatabase.driver(uri, auth=(user, pwd))
                            with driver.session(database=database) as sess:
                                cypher = (
                                    "UNWIND $rows AS r "
                                    "MERGE (f:File {checksum:r.checksum}) "
                                    "SET f.path=r.path, f.filename=r.filename, f.extension=r.extension, f.size_bytes=r.size_bytes, "
                                    "    f.created=r.created, f.modified=r.modified, f.mime_type=r.mime_type "
                                    "FOREACH (_ IN CASE WHEN r.folder IS NOT NULL AND r.folder <> '' THEN [1] ELSE [] END | "
                                    "  MERGE (fo:Folder {path:r.folder}) MERGE (fo)-[:CONTAINS]->(f) ) "
                                    "MERGE (s:Scan {id:$scan_id}) SET s.path=$scan_path, s.started=$scan_started, s.ended=$scan_ended "
                                    "MERGE (f)-[:SCANNED_IN]->(s) "
                                    "WITH r,f "
                                    "FOREACH (it IN r.interps | MERGE (t:Type {id:it}) MERGE (f)-[:INTERPRETED_AS]->(t))"
                                )
                                res = sess.run(cypher, rows=rows, scan_id=s.get('id'), scan_path=s.get('path'), scan_started=s.get('started'), scan_ended=s.get('ended'))
                                _ = list(res)
                                task['neo4j_written'] = len(rows)
                            driver.close()
                        except Exception as ne:
                            task['neo4j_error'] = str(ne)
                    # Done
                    task['ended'] = time.time()
                    task['status'] = 'completed'
                    task['progress'] = 1.0
                except Exception as e:
                    task['ended'] = time.time()
                    task['status'] = 'error'
                    task['error'] = str(e)
            threading.Thread(target=_worker_commit, daemon=True).start()
            return jsonify({'task_id': task_id, 'status': 'running'}), 202

        else:
            return jsonify({"error": "unsupported task type"}), 400

    @api.get('/tasks')
    def api_tasks_list():
        tasks = list(app.extensions['scidk'].get('tasks', {}).values())
        # sort newest first
        tasks.sort(key=lambda t: t.get('started') or 0, reverse=True)
        return jsonify(tasks), 200

    @api.get('/tasks/<task_id>')
    def api_tasks_detail(task_id):
        task = app.extensions['scidk'].get('tasks', {}).get(task_id)
        if not task:
            return jsonify({"error": "not found"}), 404
        return jsonify(task), 200

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

    @api.get('/search')
    def api_search():
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify([]), 200
        q_lower = q.lower()
        results = []
        for ds in graph.list_datasets():
            matched_on = []
            # Match filename
            if q_lower in (ds.get('filename') or '').lower() or q_lower in (ds.get('path') or '').lower():
                matched_on.append('filename')
            # Match interpreter ids present
            interps = (ds.get('interpretations') or {})
            for interp_id in interps.keys():
                if q_lower in interp_id.lower():
                    if 'interpreter_id' not in matched_on:
                        matched_on.append('interpreter_id')
            if matched_on:
                results.append({
                    'id': ds.get('id'),
                    'path': ds.get('path'),
                    'filename': ds.get('filename'),
                    'extension': ds.get('extension'),
                    'matched_on': matched_on,
                })
        # Simple ordering: filename matches first, then interpreter_id
        def score(r):
            return (0 if 'filename' in r['matched_on'] else 1, r['filename'] or '')
        results.sort(key=score)
        return jsonify(results), 200

    @api.get('/directories')
    def api_directories():
        dirs = app.extensions['scidk'].get('directories', {})
        # Return stable order: most recently scanned first
        values = list(dirs.values())
        values.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        return jsonify(values), 200

    @api.get('/fs/list')
    def api_fs_list():
        """List immediate children within a scanned base directory.
        Query params:
          - base (required): must equal a previously scanned directory path
          - path (optional): if provided, must resolve under base; otherwise list base
        Returns JSON with breadcrumb and items. Prevents path traversal outside base.
        """
        base = (request.args.get('base') or '').strip()
        rel_path = (request.args.get('path') or '').strip()
        if not base:
            return jsonify({"error": "missing base"}), 400
        dirs = app.extensions['scidk'].get('directories', {})
        if base not in dirs:
            return jsonify({"error": "unknown base (run a scan first)"}), 400
        try:
            base_p = Path(base).resolve()
            cur_p = Path(rel_path).resolve() if rel_path else base_p
            # Ensure cur_p is under base
            try:
                cur_p.relative_to(base_p)
            except Exception:
                cur_p = base_p
            if not cur_p.exists() or not cur_p.is_dir():
                return jsonify({"error": "path not a directory"}), 400
            # Build breadcrumb from base to cur
            breadcrumb = []
            # iterate ancestors from base to cur
            parts = []
            tmp = cur_p
            while True:
                parts.append(tmp)
                if tmp == base_p:
                    break
                tmp = tmp.parent
                if tmp == tmp.parent:  # reached filesystem root
                    break
            parts.reverse()
            for p in parts:
                try:
                    breadcrumb.append({"name": p.name or str(p), "path": str(p)})
                except Exception:
                    breadcrumb.append({"name": str(p), "path": str(p)})
            # Precompute scanned dataset paths
            scanned_paths = {}
            for d in app.extensions['scidk']['graph'].list_datasets():
                scanned_paths[d.get('path')] = d.get('id')
            # List items
            items = []
            for child in cur_p.iterdir():
                try:
                    st = child.stat()
                    is_dir = child.is_dir()
                    item = {
                        'name': child.name,
                        'path': str(child.resolve()),
                        'is_dir': bool(is_dir),
                        'size_bytes': 0 if is_dir else int(st.st_size),
                        'modified': float(st.st_mtime),
                        'ext': '' if is_dir else child.suffix.lower(),
                        'scanned': False,
                        'dataset_id': None,
                    }
                    if not is_dir:
                        dsid = scanned_paths.get(str(child.resolve()))
                        if dsid:
                            item['scanned'] = True
                            item['dataset_id'] = dsid
                    items.append(item)
                except Exception:
                    continue
            # Sort: directories first, then files by name
            items.sort(key=lambda x: (0 if x['is_dir'] else 1, x['name'].lower()))
            return jsonify({
                'base': str(base_p),
                'path': str(cur_p),
                'breadcrumb': breadcrumb,
                'items': items,
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @api.get('/scans')
    def api_scans():
        scans = list(app.extensions['scidk'].get('scans', {}).values())
        scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        # Return a lighter summary by default
        summaries = [
            {
                'id': s.get('id'),
                'path': s.get('path'),
                'recursive': s.get('recursive'),
                'started': s.get('started'),
                'ended': s.get('ended'),
                'duration_sec': s.get('duration_sec'),
                'file_count': s.get('file_count'),
                'by_ext': s.get('by_ext', {}),
                'source': s.get('source'),
                'checksum_count': len(s.get('checksums') or []),
                'committed': bool(s.get('committed', False)),
                'committed_at': s.get('committed_at'),
            }
            for s in scans
        ]
        return jsonify(summaries), 200

    @api.get('/scans/<scan_id>')
    def api_scan_detail(scan_id):
        s = app.extensions['scidk'].get('scans', {}).get(scan_id)
        if not s:
            return jsonify({"error": "not found"}), 404
        return jsonify(s), 200

    @api.post('/scans/<scan_id>/commit')
    def api_scan_commit(scan_id):
        scans = app.extensions['scidk'].setdefault('scans', {})
        s = scans.get(scan_id)
        if not s:
            return jsonify({"status": "error", "error": "scan not found"}), 404
        try:
            checksums = s.get('checksums') or []
            total = len(checksums)
            # How many of these files are present in the current graph
            g = app.extensions['scidk']['graph']
            present = sum(1 for ch in checksums if ch in getattr(g, 'datasets', {}))
            missing = total - present
            # Commit into graph (idempotent add of Scan + edges)
            g.commit_scan(s)
            import time as _t
            s['committed'] = True
            s['committed_at'] = _t.time()

            # Attempt Neo4j write if configuration is present (do not rely solely on connected flag)
            neo_state = app.extensions['scidk'].get('neo4j_state', {})
            neo_attempted = False
            neo_written = 0
            neo_error = None
            uri, user, pwd, database = _get_neo4j_params()
            if uri and user and pwd:
                neo_attempted = True
                try:
                    from neo4j import GraphDatabase  # type: ignore
                    driver = GraphDatabase.driver(uri, auth=(user, pwd))
                    # Prepare rows for UNWIND from present datasets only
                    ds_map = getattr(g, 'datasets', {})
                    rows = []
                    from pathlib import Path as _P
                    for ch in checksums:
                        d = ds_map.get(ch)
                        if not d:
                            continue
                        parent = ''
                        try:
                            parent = str(_P(d.get('path')).parent)
                        except Exception:
                            parent = ''
                        interps = list((d.get('interpretations') or {}).keys())
                        rows.append({
                            'checksum': d.get('checksum'),
                            'path': d.get('path'),
                            'filename': d.get('filename'),
                            'extension': d.get('extension'),
                            'size_bytes': int(d.get('size_bytes') or 0),
                            'created': float(d.get('created') or 0),
                            'modified': float(d.get('modified') or 0),
                            'mime_type': d.get('mime_type'),
                            'folder': parent,
                            'interps': interps,
                        })
                    with driver.session(database=database) as sess:
                        # MERGE File, Folder, Scan and relationships in batches
                        cypher = (
                            "UNWIND $rows AS r "
                            "MERGE (f:File {checksum:r.checksum}) "
                            "SET f.path=r.path, f.filename=r.filename, f.extension=r.extension, f.size_bytes=r.size_bytes, "
                            "    f.created=r.created, f.modified=r.modified, f.mime_type=r.mime_type "
                            "FOREACH (_ IN CASE WHEN r.folder IS NOT NULL AND r.folder <> '' THEN [1] ELSE [] END | "
                            "  MERGE (fo:Folder {path:r.folder}) MERGE (fo)-[:CONTAINS]->(f) ) "
                            "MERGE (s:Scan {id:$scan_id}) SET s.path=$scan_path, s.started=$scan_started, s.ended=$scan_ended "
                            "MERGE (f)-[:SCANNED_IN]->(s) "
                            "WITH r,f "
                            "FOREACH (it IN r.interps | MERGE (t:Type {id:it}) MERGE (f)-[:INTERPRETED_AS]->(t))"
                        )
                        res = sess.run(cypher, rows=rows, scan_id=s.get('id'), scan_path=s.get('path'), scan_started=s.get('started'), scan_ended=s.get('ended'))
                        # Consume result to ensure execution
                        _ = list(res)
                        neo_written = len(rows)
                    driver.close()
                    # Update state on success
                    neo_state['connected'] = True
                    neo_state['last_error'] = None
                except Exception as ne:
                    neo_error = str(ne)
                    neo_state['connected'] = False
                    neo_state['last_error'] = neo_error
                # Note: even on Neo4j error we still return 200 for in-memory commit but include error details

            # In our in-memory model, linked_edges_added ~= present (File→Scan per matched dataset)
            payload = {
                "status": "ok",
                "committed": True,
                "scan_id": scan_id,
                "files_in_scan": total,
                "matched_in_graph": present,
                "missing_from_graph": max(0, missing),
                "linked_edges_added": present,
                "neo4j_attempted": neo_attempted,
                "neo4j_written_files": neo_written,
            }
            if neo_error:
                payload["neo4j_error"] = neo_error
            if total == 0:
                payload["warning"] = "This scan has 0 files; nothing was linked."
            elif present == 0:
                payload["warning"] = "None of the scanned files are currently present in the graph; verify you scanned in this session or refresh."
            return jsonify(payload), 200
        except Exception as e:
            return jsonify({"status": "error", "error": "commit failed", "error_detail": str(e)}), 500

    @api.delete('/scans/<scan_id>')
    def api_scan_delete(scan_id):
        scans = app.extensions['scidk'].setdefault('scans', {})
        existed = scan_id in scans
        # Remove from graph first
        app.extensions['scidk']['graph'].delete_scan(scan_id)
        if existed:
            del scans[scan_id]
        return jsonify({"status": "ok", "deleted": True, "scan_id": scan_id, "existed": existed}), 200

    @api.get('/graph/schema')
    def api_graph_schema():
        try:
            limit = int(request.args.get('limit') or 500)
        except Exception:
            limit = 500
        data = app.extensions['scidk']['graph'].schema_triples(limit=limit)
        return jsonify(data), 200

    @api.get('/graph/schema.csv')
    def api_graph_schema_csv():
        # Build a simple CSV with two sections: NodeLabels and RelationshipTypes
        g = app.extensions['scidk']['graph']
        triples = g.schema_triples(limit=int(request.args.get('limit') or 0 or 0))
        # If limit is 0 treat as no limit
        if (request.args.get('limit') or '').strip() == '0':
            triples = g.schema_triples(limit=0)
        nodes = triples.get('nodes', [])
        edges = triples.get('edges', [])
        lines = []
        lines.append('NodeLabels')
        lines.append('label,count')
        for n in nodes:
            lines.append(f"{n.get('label','')},{n.get('count',0)}")
        lines.append('')
        lines.append('RelationshipTypes')
        lines.append('start_label,rel_type,end_label,count')
        for e in edges:
            lines.append(f"{e.get('start_label','')},{e.get('rel_type','')},{e.get('end_label','')},{e.get('count',0)}")
        csv_text = "\n".join(lines) + "\n"
        from flask import Response
        return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename="schema.csv"'})

    @api.get('/graph/subschema')
    def api_graph_subschema():
        # Filters: name (optional), labels (csv), rel_types (csv), limit (int)
        params = {k: (request.args.get(k) or '').strip() for k in ['name','labels','rel_types','limit']}
        # Named queries
        if params['name']:
            if params['name'].lower() == 'interpreted_as':
                params['rel_types'] = 'INTERPRETED_AS' if not params['rel_types'] else params['rel_types']
            # Future named queries can be added here
        # Parse filters
        labels = set([s for s in (params['labels'].split(',')) if s]) if params['labels'] else set()
        rel_types = set([s for s in (params['rel_types'].split(',')) if s]) if params['rel_types'] else set()
        try:
            limit = int(params['limit']) if params['limit'] else 500
        except Exception:
            limit = 500
        g = app.extensions['scidk']['graph']
        base = g.schema_triples(limit=0 if limit == 0 else 1000000)  # fetch all, filter then trim
        edges = base.get('edges', [])
        # Apply filters
        def edge_ok(e):
            if rel_types and e.get('rel_type') not in rel_types:
                return False
            if labels and (e.get('start_label') not in labels and e.get('end_label') not in labels):
                return False
            return True
        filtered_edges = [e for e in edges if edge_ok(e)]
        # Truncate if needed
        truncated = False
        if limit and limit > 0 and len(filtered_edges) > limit:
            filtered_edges = filtered_edges[:limit]
            truncated = True
        # Build nodes: start with base nodes filtered by labels (if any)
        base_nodes = {n['label']: n.get('count', 0) for n in base.get('nodes', [])}
        node_map = {}
        # Include from filtered edges endpoints
        for e in filtered_edges:
            for lab in [e.get('start_label'), e.get('end_label')]:
                if lab not in node_map:
                    node_map[lab] = base_nodes.get(lab, 1 if lab else 1)
        # If labels filter provided, ensure inclusion even if no edges
        for lab in labels:
            if lab not in node_map:
                node_map[lab] = base_nodes.get(lab, 0)
        out = {
            'nodes': [{'label': k, 'count': v} for k, v in node_map.items()],
            'edges': filtered_edges,
            'truncated': truncated,
        }
        return jsonify(out), 200

    @api.get('/graph/instances')
    def api_graph_instances():
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # preview only (cap to 100 rows)
        limit = 100
        if request.args.get('limit'):
            try:
                limit = int(request.args.get('limit'))
            except Exception:
                pass
        return jsonify({
            'label': label,
            'count': len(rows),
            'rows': rows[:max(0, limit)]
        }), 200

    @api.get('/graph/instances.csv')
    def api_graph_instances_csv():
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # Build CSV
        if not rows:
            headers = ['id']
        else:
            # union columns
            cols = set()
            for r in rows:
                cols.update(r.keys())
            headers = sorted(list(cols))
        import io, csv
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in headers})
        from flask import Response
        return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename="instances_{label}.csv"'})

    @api.get('/graph/instances.xlsx')
    def api_graph_instances_xlsx():
        try:
            import openpyxl  # type: ignore
        except Exception:
            return jsonify({"error": "xlsx export requires openpyxl"}), 501
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # Determine headers
        if not rows:
            headers = ['id']
        else:
            cols = set()
            for r in rows:
                cols.update(r.keys())
            headers = sorted(list(cols))
        from openpyxl import Workbook  # type: ignore
        wb = Workbook()
        ws = wb.active
        ws.title = label or 'Sheet1'
        ws.append(headers)
        for r in rows:
            ws.append([r.get(k, '') for k in headers])
        import io
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        from flask import Response
        return Response(bio.read(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="instances_{label}.xlsx"'})

    @api.get('/graph/instances.pkl')
    def api_graph_instances_pickle():
        import pickle
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        payload = pickle.dumps(rows, protocol=pickle.HIGHEST_PROTOCOL)
        from flask import Response
        return Response(payload, mimetype='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="instances_{label}.pkl"'})

    @api.get('/graph/instances.arrow')
    def api_graph_instances_arrow():
        try:
            import pyarrow as pa  # type: ignore
            import pyarrow.ipc as pa_ipc  # type: ignore
        except Exception:
            return jsonify({"error": "arrow export requires pyarrow"}), 501
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = app.extensions['scidk']['graph'].list_instances(label)
        # Normalize rows to a table (handle missing keys by union of columns)
        cols = set()
        for r in rows:
            cols.update(r.keys())
        cols = sorted(list(cols)) if rows else ['id']
        arrays = {c: [] for c in cols}
        for r in rows:
            for c in cols:
                arrays[c].append(r.get(c))
        table = pa.table({c: pa.array(arrays[c]) for c in cols})
        sink = pa.BufferOutputStream()
        with pa_ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        buf = sink.getvalue()
        from flask import Response
        return Response(buf.to_pybytes(), mimetype='application/vnd.apache.arrow.stream', headers={'Content-Disposition': f'attachment; filename="instances_{label}.arrow"'})

    @api.get('/graph/schema.neo4j')
    def api_graph_schema_neo4j():
        # Cypher-only triple derivation from a Neo4j instance if configured
        uri, user, pwd, database = _get_neo4j_params()
        if not (uri and user and pwd):
            return jsonify({"error": "neo4j not configured (set in Settings or env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)"}), 501
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception:
            return jsonify({"error": "neo4j driver not installed"}), 501
        try:
            driver = GraphDatabase.driver(uri, auth=(user, pwd))
            with driver.session(database=database) as sess:
                # Node label counts
                q_nodes = "MATCH (n) WITH head(labels(n)) AS l, count(*) AS c RETURN l AS label, c ORDER BY c DESC"
                nodes = [dict(record) for record in sess.run(q_nodes)]
                # Unique triples counts
                q_edges = (
                    "MATCH (s)-[r]->(t) "
                    "WITH head(labels(s)) AS sl, type(r) AS rt, head(labels(t)) AS tl, count(*) AS c "
                    "RETURN sl AS start_label, rt AS rel_type, tl AS end_label, c ORDER BY c DESC"
                )
                edges = [dict(record) for record in sess.run(q_edges)]
            driver.close()
            return jsonify({"nodes": nodes, "edges": edges, "truncated": False}), 200
        except Exception as e:
            return jsonify({"error": f"neo4j query failed: {str(e)}"}), 502

    @api.get('/graph/schema.apoc')
    def api_graph_schema_apoc():
        # APOC-based schema where available; fall back is not done here; use /graph/schema or /graph/schema.neo4j otherwise
        uri, user, pwd, database = _get_neo4j_params()
        if not (uri and user and pwd):
            return jsonify({"error": "neo4j not configured (set in Settings or env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)"}), 501
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception:
            return jsonify({"error": "neo4j driver not installed"}), 501
        try:
            driver = GraphDatabase.driver(uri, auth=(user, pwd))
            with driver.session(database=database) as sess:
                # Use apoc.meta.data() to derive nodes and edges
                # Relationship triples aggregation
                q_apoc = (
                    "CALL apoc.meta.data() YIELD label, other, elementType, type, count "
                    "WITH label, other, elementType, type, count "
                    "WHERE elementType = 'relationship' "
                    "RETURN label AS start_label, type AS rel_type, other AS end_label, count ORDER BY count DESC"
                )
                edges = [dict(record) for record in sess.run(q_apoc)]
                # Node label counts via apoc (fallback to Cypher if needed)
                q_nodes = "CALL apoc.meta.stats() YIELD labels RETURN [k IN keys(labels) | {label:k, count: labels[k]}] AS pairs"
                rec = sess.run(q_nodes).single()
                nodes = []
                if rec and 'pairs' in rec:
                    for p in rec['pairs']:
                        nodes.append({'label': p['label'], 'count': p['count']})
            driver.close()
            return jsonify({"nodes": nodes, "edges": edges, "truncated": False}), 200
        except Exception as e:
            # If APOC procedures are missing or fail, inform the client
            return jsonify({"error": f"apoc schema failed: {str(e)}"}), 502

    @api.get('/health/graph')
    def api_health_graph():
        """Basic health for graph backend. In-memory is always OK; if Neo4j settings/env are provided, try a connection."""
        backend = os.environ.get('SCIDK_GRAPH_BACKEND', 'in_memory').lower() or 'in_memory'
        info = {
            'backend': backend,
            'in_memory_ok': True,
            'neo4j': {
                'configured': False,
                'connectable': False,
                'error': None,
            }
        }
        uri, user, pwd, database = _get_neo4j_params()
        if uri and user and pwd:
            info['neo4j']['configured'] = True
            try:
                from neo4j import GraphDatabase  # type: ignore
            except Exception as e:
                info['neo4j']['error'] = f"neo4j driver not installed: {e}"
                return jsonify(info), 200
            try:
                driver = GraphDatabase.driver(uri, auth=(user, pwd))
                with driver.session(database=database) as sess:
                    rec = sess.run("RETURN 1 AS ok").single()
                    if rec and rec.get('ok') == 1:
                        info['neo4j']['connectable'] = True
                driver.close()
            except Exception as e:
                info['neo4j']['error'] = str(e)
        return jsonify(info), 200

    # Settings APIs for Neo4j configuration
    @api.get('/settings/neo4j')
    def api_settings_neo4j_get():
        cfg = app.extensions['scidk'].get('neo4j_config', {})
        state = app.extensions['scidk'].get('neo4j_state', {})
        # Do not return password
        out = {
            'uri': cfg.get('uri') or '',
            'user': cfg.get('user') or '',
            'database': cfg.get('database') or '',
            'connected': bool(state.get('connected')),
            'last_error': state.get('last_error'),
        }
        return jsonify(out), 200

    @api.post('/settings/neo4j')
    def api_settings_neo4j_set():
        data = request.get_json(force=True, silent=True) or {}
        cfg = app.extensions['scidk'].setdefault('neo4j_config', {})
        # Accept free text fields; empty strings treated as None
        for k in ['uri','user','password','database']:
            v = data.get(k)
            if v is not None:
                v = v.strip()
                cfg[k] = v if v else None
        # Reset state error on change
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
        st['last_error'] = None
        return jsonify({'status':'ok'}), 200

    @api.post('/settings/neo4j/connect')
    def api_settings_neo4j_connect():
        uri, user, pwd, database = _get_neo4j_params()
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
        st['connected'] = False
        st['last_error'] = None
        if not (uri and user and pwd):
            st['last_error'] = 'Missing uri/user/password'
            return jsonify({'connected': False, 'error': st['last_error']}), 400
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception as e:
            st['last_error'] = f'neo4j driver not installed: {e}'
            return jsonify({'connected': False, 'error': st['last_error']}), 501
        try:
            driver = GraphDatabase.driver(uri, auth=(user, pwd))
            with driver.session(database=database) as sess:
                rec = sess.run('RETURN 1 AS ok').single()
                ok = bool(rec and rec.get('ok') == 1)
            driver.close()
            st['connected'] = ok
            return jsonify({'connected': ok}), 200 if ok else 502
        except Exception as e:
            st['last_error'] = str(e)
            st['connected'] = False
            return jsonify({'connected': False, 'error': st['last_error']}), 502

    @api.post('/settings/neo4j/disconnect')
    def api_settings_neo4j_disconnect():
        st = app.extensions['scidk'].setdefault('neo4j_state', {})
        st['connected'] = False
        return jsonify({'connected': False}), 200

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
        directories = list(app.extensions['scidk'].get('directories', {}).values())
        directories.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        scans = list(app.extensions['scidk'].get('scans', {}).values())
        scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        return render_template('index.html', datasets=datasets, by_ext=by_ext, schema_summary=schema_summary, telemetry=telemetry, directories=directories, scans=scans)

    @ui.get('/chat')
    def chat():
        return render_template('chat.html')

    @ui.get('/map')
    def map_page():
        schema_summary = app.extensions['scidk']['graph'].schema_summary()
        return render_template('map.html', schema_summary=schema_summary)

    @ui.get('/datasets')
    def datasets():
        all_datasets = app.extensions['scidk']['graph'].list_datasets()
        scan_id = (request.args.get('scan_id') or '').strip()
        selected_scan = None
        if scan_id:
            selected_scan = app.extensions['scidk'].get('scans', {}).get(scan_id)
        if selected_scan:
            checks = set(selected_scan.get('checksums') or [])
            datasets = [d for d in all_datasets if d.get('checksum') in checks]
        else:
            datasets = all_datasets
        directories = list(app.extensions['scidk'].get('directories', {}).values())
        directories.sort(key=lambda d: d.get('last_scanned') or 0, reverse=True)
        recent_scans = list(app.extensions['scidk'].get('scans', {}).values())
        recent_scans.sort(key=lambda s: s.get('ended') or s.get('started') or 0, reverse=True)
        # Show only the most recent N scans for dropdown
        N = 20
        recent_scans = recent_scans[:N]
        return render_template('datasets.html', datasets=datasets, directories=directories, recent_scans=recent_scans, selected_scan=selected_scan)

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

    @ui.get('/interpreters')
    def interpreters():
        # List registry mappings and selection rules
        reg = app.extensions['scidk']['registry']
        mappings = {ext: [getattr(i, 'id', 'unknown') for i in interps] for ext, interps in reg.by_extension.items()}
        rules = list(reg.rules.rules)
        return render_template('extensions.html', mappings=mappings, rules=rules)

    # Backward-compatible route
    @ui.get('/extensions')
    def extensions_legacy():
        return redirect(url_for('ui.interpreters'))

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
        import time, hashlib
        # Pre-scan snapshot
        before = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
        started = time.time()
        count = fs.scan_directory(Path(path), recursive=recursive)
        ended = time.time()
        duration = ended - started
        after = set(ds.get('checksum') for ds in app.extensions['scidk']['graph'].list_datasets())
        new_checksums = sorted(list(after - before))
        by_ext = {}
        ext_map = {ds.get('checksum'): ds.get('extension') or '' for ds in app.extensions['scidk']['graph'].list_datasets()}
        for ch in new_checksums:
            ext = ext_map.get(ch, '')
            by_ext[ext] = by_ext.get(ext, 0) + 1
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
        scans = app.extensions['scidk'].setdefault('scans', {})
        scans[scan_id] = scan
        telem = app.extensions['scidk'].setdefault('telemetry', {})
        telem['last_scan'] = {
            'path': str(path),
            'recursive': bool(recursive),
            'scanned': int(count),
            'started': started,
            'ended': ended,
            'duration_sec': duration,
        }
        # Track scanned directories here as well
        dirs = app.extensions['scidk'].setdefault('directories', {})
        drec = dirs.setdefault(str(path), {'path': str(path), 'recursive': bool(recursive), 'scanned': 0, 'last_scanned': 0, 'scan_ids': []})
        drec.update({'recursive': bool(recursive), 'scanned': int(count), 'last_scanned': ended})
        drec.setdefault('scan_ids', []).append(scan_id)
        return redirect(url_for('ui.datasets', scan_id=scan_id))

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
