"""
Blueprint for Graph schema and query API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
from typing import Optional
import json
import os

from ..helpers import get_neo4j_params, build_commit_rows, commit_to_neo4j, get_or_build_scan_index
bp = Blueprint('graph', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

@bp.get('/graph/schema')
def api_graph_schema():
        try:
            limit = int(request.args.get('limit') or 500)
        except Exception:
            limit = 500
        data = _get_ext()['graph'].schema_triples(limit=limit)
        return jsonify(data), 200


@bp.get('/graph/schema/combined')
def api_graph_schema_combined():
    """
    Unified schema endpoint combining local Labels, Neo4j schema, and in-memory graph.

    Query params:
    - source: 'labels' | 'neo4j' | 'graph' | 'all' (default: 'all')
    - include_properties: 'true' | 'false' (default: 'false')

    Returns:
    {
        "nodes": [{"label": "...", "count": 0, "source": "labels", "properties": [...]}],
        "edges": [{"start_label": "...", "rel_type": "...", "end_label": "...", "count": 0, "source": "labels"}],
        "sources": {"labels": {"count": N, "enabled": true}, ...}
    }
    """
    source = (request.args.get('source') or 'all').strip().lower()
    include_props = (request.args.get('include_properties') or 'false').strip().lower() == 'true'

    result = {'nodes': [], 'edges': [], 'sources': {}}

    # Track unique nodes/edges to avoid duplicates (key by label/triple)
    seen_nodes = {}
    seen_edges = {}

    # 1. Get local Labels definitions
    if source in ('labels', 'all'):
        try:
            from ...services.label_service import LabelService
            label_service = LabelService(current_app)
            labels = label_service.list_labels()

            for label in labels:
                label_name = label.get('name')
                if label_name and label_name not in seen_nodes:
                    node = {
                        'label': label_name,
                        'count': 0,  # No instances yet (definition only)
                        'source': 'labels'
                    }
                    if include_props:
                        node['properties'] = label.get('properties', [])
                    result['nodes'].append(node)
                    seen_nodes[label_name] = 'labels'

                # Add relationships
                for rel in label.get('relationships', []):
                    edge_key = (label_name, rel.get('type'), rel.get('target_label'))
                    if edge_key not in seen_edges:
                        result['edges'].append({
                            'start_label': label_name,
                            'rel_type': rel.get('type'),
                            'end_label': rel.get('target_label'),
                            'count': 0,
                            'source': 'labels'
                        })
                        seen_edges[edge_key] = 'labels'

            result['sources']['labels'] = {'count': len(labels), 'enabled': True}
        except Exception as e:
            result['sources']['labels'] = {'count': 0, 'enabled': False, 'error': str(e)}

    # 2. Get Neo4j schema (if connected and requested)
    if source in ('neo4j', 'all'):
        try:
            uri, user, pwd, database, auth_mode = get_neo4j_params()
            if uri:
                from neo4j import GraphDatabase
                driver = None
                try:
                    driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
                    with driver.session(database=database) as sess:
                        # Get node label counts
                        q_nodes = "MATCH (n) WITH head(labels(n)) AS l, count(*) AS c RETURN l AS label, c ORDER BY c DESC"
                        neo4j_nodes = [dict(record) for record in sess.run(q_nodes)]

                        # Get relationship triples counts
                        q_edges = (
                            "MATCH (s)-[r]->(t) "
                            "WITH head(labels(s)) AS sl, type(r) AS rt, head(labels(t)) AS tl, count(*) AS c "
                            "RETURN sl AS start_label, rt AS rel_type, tl AS end_label, c ORDER BY c DESC"
                        )
                        neo4j_edges = [dict(record) for record in sess.run(q_edges)]

                        # Add nodes from Neo4j (prefer Neo4j counts if already seen from labels)
                        for n in neo4j_nodes:
                            label_name = n.get('label')
                            if label_name:
                                if label_name in seen_nodes:
                                    # Update existing node with Neo4j count
                                    for node in result['nodes']:
                                        if node['label'] == label_name:
                                            node['count'] = n.get('c', 0)
                                            node['source'] = 'neo4j+labels' if node['source'] == 'labels' else 'neo4j'
                                            break
                                    seen_nodes[label_name] = 'neo4j'
                                else:
                                    result['nodes'].append({
                                        'label': label_name,
                                        'count': n.get('c', 0),
                                        'source': 'neo4j'
                                    })
                                    seen_nodes[label_name] = 'neo4j'

                        # Add edges from Neo4j
                        for e in neo4j_edges:
                            edge_key = (e.get('start_label'), e.get('rel_type'), e.get('end_label'))
                            if edge_key in seen_edges:
                                # Update existing edge with Neo4j count
                                for edge in result['edges']:
                                    if (edge['start_label'], edge['rel_type'], edge['end_label']) == edge_key:
                                        edge['count'] = e.get('c', 0)
                                        edge['source'] = 'neo4j+labels' if edge['source'] == 'labels' else 'neo4j'
                                        break
                            else:
                                result['edges'].append({
                                    'start_label': e.get('start_label'),
                                    'rel_type': e.get('rel_type'),
                                    'end_label': e.get('end_label'),
                                    'count': e.get('c', 0),
                                    'source': 'neo4j'
                                })
                                seen_edges[edge_key] = 'neo4j'

                        result['sources']['neo4j'] = {
                            'count': len(neo4j_nodes),
                            'enabled': True,
                            'connected': True
                        }
                finally:
                    if driver:
                        driver.close()
            else:
                result['sources']['neo4j'] = {'count': 0, 'enabled': False, 'connected': False}
        except Exception as e:
            result['sources']['neo4j'] = {
                'count': 0,
                'enabled': False,
                'connected': False,
                'error': str(e)
            }

    # 3. Get in-memory graph schema
    if source in ('graph', 'all'):
        try:
            graph_schema = _get_ext()['graph'].schema_triples(limit=500)

            for node in graph_schema.get('nodes', []):
                label_name = node.get('label')
                if label_name:
                    if label_name in seen_nodes:
                        # Update count for existing node
                        for n in result['nodes']:
                            if n['label'] == label_name:
                                n['count'] = node.get('count', 0)
                                if n['source'] == 'labels':
                                    n['source'] = 'graph+labels'
                                elif n['source'] == 'neo4j':
                                    n['source'] = 'graph+neo4j'
                                elif n['source'] == 'neo4j+labels':
                                    n['source'] = 'all'
                                else:
                                    n['source'] = 'graph'
                                break
                    else:
                        result['nodes'].append({
                            'label': label_name,
                            'count': node.get('count', 0),
                            'source': 'graph'
                        })
                        seen_nodes[label_name] = 'graph'

            for edge in graph_schema.get('edges', []):
                edge_key = (edge.get('start_label'), edge.get('rel_type'), edge.get('end_label'))
                if edge_key in seen_edges:
                    # Update count for existing edge
                    for e in result['edges']:
                        if (e['start_label'], e['rel_type'], e['end_label']) == edge_key:
                            e['count'] = edge.get('count', 0)
                            if e['source'] == 'labels':
                                e['source'] = 'graph+labels'
                            elif e['source'] == 'neo4j':
                                e['source'] = 'graph+neo4j'
                            elif e['source'] == 'neo4j+labels':
                                e['source'] = 'all'
                            else:
                                e['source'] = 'graph'
                            break
                else:
                    result['edges'].append({
                        'start_label': edge.get('start_label'),
                        'rel_type': edge.get('rel_type'),
                        'end_label': edge.get('end_label'),
                        'count': edge.get('count', 0),
                        'source': 'graph'
                    })
                    seen_edges[edge_key] = 'graph'

            result['sources']['graph'] = {
                'count': len(graph_schema.get('nodes', [])),
                'enabled': True
            }
        except Exception as e:
            result['sources']['graph'] = {'count': 0, 'enabled': False, 'error': str(e)}

    return jsonify(result), 200


@bp.get('/graph/schema.csv')
def api_graph_schema_csv():
        # Build a simple CSV with two sections: NodeLabels and RelationshipTypes
        g = _get_ext()['graph']
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


@bp.get('/graph/subschema')
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
        g = _get_ext()['graph']
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


@bp.get('/graph/instances')
def api_graph_instances():
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = _get_ext()['graph'].list_instances(label)
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


@bp.get('/graph/instances.csv')
def api_graph_instances_csv():
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = _get_ext()['graph'].list_instances(label)
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


@bp.get('/graph/instances.xlsx')
def api_graph_instances_xlsx():
        try:
            import openpyxl  # type: ignore
        except Exception:
            return jsonify({"error": "xlsx export requires openpyxl"}), 501
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = _get_ext()['graph'].list_instances(label)
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


@bp.get('/graph/instances.pkl')
def api_graph_instances_pickle():
        import pickle
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = _get_ext()['graph'].list_instances(label)
        payload = pickle.dumps(rows, protocol=pickle.HIGHEST_PROTOCOL)
        from flask import Response
        return Response(payload, mimetype='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="instances_{label}.pkl"'})


@bp.get('/graph/instances.arrow')
def api_graph_instances_arrow():
        try:
            import pyarrow as pa  # type: ignore
            import pyarrow.ipc as pa_ipc  # type: ignore
        except Exception:
            return jsonify({"error": "arrow export requires pyarrow"}), 501
        label = (request.args.get('label') or '').strip()
        if not label:
            return jsonify({"error": "missing label"}), 400
        rows = _get_ext()['graph'].list_instances(label)
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


@bp.get('/graph/schema.neo4j')
def api_graph_schema_neo4j():
        # Cypher-only triple derivation from a Neo4j instance if configured
        uri, user, pwd, database, auth_mode = get_neo4j_params()
        if not uri:
            return jsonify({"error": "neo4j not configured (set in Settings or env: NEO4J_URI, and NEO4J_USER/NEO4J_PASSWORD or NEO4J_AUTH=none)"}), 501
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception:
            return jsonify({"error": "neo4j driver not installed"}), 501
        try:
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
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
            finally:
                try:
                    if driver is not None:
                        driver.close()
                except Exception:
                    pass
            return jsonify({"nodes": nodes, "edges": edges, "truncated": False}), 200
        except Exception as e:
            return jsonify({"error": f"neo4j query failed: {str(e)}"}), 502


@bp.get('/graph/schema.apoc')
def api_graph_schema_apoc():
        # APOC-based schema where available; fall back is not done here; use /graph/schema or /graph/schema.neo4j otherwise
        uri, user, pwd, database, auth_mode = get_neo4j_params()
        if not uri:
            return jsonify({"error": "neo4j not configured (set in Settings or env: NEO4J_URI, and NEO4J_USER/NEO4J_PASSWORD or NEO4J_AUTH=none)"}), 501
        try:
            from neo4j import GraphDatabase  # type: ignore
        except Exception:
            return jsonify({"error": "neo4j driver not installed"}), 501
        try:
            driver = None
            try:
                driver = GraphDatabase.driver(uri, auth=None if auth_mode == 'none' else (user, pwd))
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
            finally:
                try:
                    if driver is not None:
                        driver.close()
                except Exception:
                    pass
            return jsonify({"nodes": nodes, "edges": edges, "truncated": False}), 200
        except Exception as e:
            # If APOC procedures are missing or fail, inform the client
            return jsonify({"error": f"apoc schema failed: {str(e)}"}), 502


@bp.get('/rocrate')
def api_rocrate():
        """Return a minimal RO-Crate JSON-LD for a given directory (depth=1).
        Query: provider_id (default local_fs), root_id ('/'), path (directory path)
        Caps: at most 1000 immediate children; include meta.truncated when applied.
        """
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        sel_path = (request.args.get('path') or '').strip() or root_id
        try:
            provs = _get_ext()['providers']
            prov = provs.get(prov_id)
            if not prov:
                return jsonify({'error': 'provider not available'}), 400
            from pathlib import Path as _P
            base = _P(root_id).resolve()
            target = _P(sel_path).resolve()
            # Ensure target resides under base (best-effort for local/mounted providers)
            try:
                target.relative_to(base)
            except Exception:
                # If not under base, fall back to base
                target = base
            if not target.exists() or not target.is_dir():
                return jsonify({'error': 'path not a directory'}), 400
            # Prepare root entity
            from datetime import datetime as _DT
            def iso(ts):
                try:
                    return _DT.fromtimestamp(float(ts)).isoformat()
                except Exception:
                    return None
            # Enumerate immediate children
            children = []
            total = 0
            LIMIT = 1000
            import mimetypes as _mt
            for child in target.iterdir():
                total += 1
                if len(children) >= LIMIT:
                    continue
                try:
                    st = child.stat()
                    is_dir = child.is_dir()
                    mime = None if is_dir else (_mt.guess_type(child.name)[0] or 'application/octet-stream')
                    children.append({
                        '@id': child.name + ('/' if is_dir else ''),
                        '@type': 'Dataset' if is_dir else 'File',
                        'name': child.name or str(child),
                        'contentSize': 0 if is_dir else int(st.st_size),
                        'dateModified': iso(st.st_mtime),
                        'encodingFormat': None if is_dir else mime,
                        'url': None if is_dir else (f"/api/files?provider_id={prov_id}&root_id={root_id}&path=" + str(child.resolve())),
                    })
                except Exception:
                    continue
            graph = [{
                '@id': './',
                '@type': 'Dataset',
                'name': target.name or str(target),
                'hasPart': [{'@id': c['@id']} for c in children],
            }] + children
            out = {
                '@context': 'https://w3id.org/ro/crate/1.1/context',
                '@graph': graph,
                'meta': {
                    'truncated': bool(total > len(children)),
                    'total_children': total,
                    'shown': len(children),
                }
            }
            return jsonify(out), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@bp.get('/files')
def api_files():
        """Stream a file's bytes with basic security and size limits.
        Query: provider_id, root_id, path
        Limits: default max 32MB unless SCIDK_FILE_MAX_BYTES is set.
        """
        prov_id = (request.args.get('provider_id') or 'local_fs').strip() or 'local_fs'
        root_id = (request.args.get('root_id') or '/').strip() or '/'
        file_path = (request.args.get('path') or '').strip()
        if not file_path:
            return jsonify({'error': 'missing path'}), 400
        try:
            from pathlib import Path as _P
            base = _P(root_id).resolve()
            target = _P(file_path).resolve()
            # Enforce that target is within base
            try:
                target.relative_to(base)
            except Exception:
                return jsonify({'error': 'path outside root'}), 400
            if not target.exists() or not target.is_file():
                return jsonify({'error': 'not a file'}), 400
            st = target.stat()
            max_bytes = int(os.environ.get('SCIDK_FILE_MAX_BYTES', '33554432'))  # 32MB
            if st.st_size > max_bytes:
                return jsonify({'error': 'file too large', 'limit': max_bytes, 'size': int(st.st_size)}), 413
            import mimetypes as _mt
            mime = _mt.guess_type(target.name)[0] or 'application/octet-stream'
            from flask import send_file as _send_file
            return _send_file(str(target), mimetype=mime, as_attachment=False, download_name=target.name)
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@bp.get('/search')
def api_search():
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify([]), 200
        q_lower = q.lower()
        results = []
        for ds in _get_ext()['graph'].list_datasets():
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


@bp.post('/ro-crates/referenced')
def api_ro_crates_referenced():
    """Create a referenced RO-Crate from dataset_ids and/or explicit files.
    Environment flags:
      - SCIDK_ENABLE_ROCRATE_REFERENCED: if not truthy, returns 404.
      - SCIDK_ROCRATE_DIR: base directory to store crates (default: ~/.scidk/crates).
    Payload (JSON): { dataset_ids?: [str], files?: [obj], title?: str }
    Returns: { status: 'ok', crate_id: str, path: str }
    """
    # Feature gate
    flag = str(os.environ.get('SCIDK_ENABLE_ROCRATE_REFERENCED', '')).strip().lower()
    if flag not in ('1', 'true', 'yes', 'on', 'enabled'):  # disabled by default
        return jsonify({'error': 'not found'}), 404

    data = request.get_json(force=True, silent=True) or {}
    dataset_ids = data.get('dataset_ids') or []
    files = data.get('files') or []
    title = (data.get('title') or 'Referenced RO-Crate').strip() or 'Referenced RO-Crate'

    import time as _t, hashlib as _h, json as _json
    now = _t.time()
    crate_id = _h.sha1(f"{title}|{now}".encode()).hexdigest()[:12]
    base_dir = os.environ.get('SCIDK_ROCRATE_DIR') or os.path.expanduser('~/.scidk/crates')
    out_dir = os.path.join(base_dir, crate_id)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as e:
        return jsonify({"status": "error", "error": f"could not create crate dir: {e}"}), 500

    # Gather items from dataset_ids and/or files
    items = []
    try:
        g = current_app.extensions['scidk']['graph']
    except Exception:
        g = None
    if dataset_ids and g is not None:
        ds_map = getattr(g, 'datasets', {})
        for did in dataset_ids:
            d = ds_map.get(did)
            if not d:
                continue
            items.append({
                'path': d.get('path'),
                'name': d.get('filename') or Path(d.get('path') or '').name,
                'size': int(d.get('size_bytes') or 0),
                'mime_type': d.get('mime_type'),
                'modified_time': float(d.get('modified') or 0.0),
                'checksum': d.get('checksum'),
            })
    for f in files:
        items.append({
            'path': f.get('path') or f.get('url') or f.get('contentUrl'),
            'name': f.get('name'),
            'size': f.get('size') or f.get('size_bytes') or 0,
            'mime_type': f.get('mime') or f.get('mime_type'),
            'modified_time': f.get('modified') or f.get('modified_time') or 0.0,
            'checksum': f.get('checksum'),
        })

    def to_rclone_url(p: Optional[str]) -> Optional[str]:
        if not p or not isinstance(p, str):
            return None
        if '://' in p:
            return p
        if ':' in p:
            remote, rest = p.split(':', 1)
            rest = (rest or '').lstrip('/')
            return f"rclone://{remote}/{rest}" if rest else f"rclone://{remote}/"
        try:
            return f"file://{str(Path(p).resolve())}"
        except Exception:
            return f"file://{p}"

    graph = []
    graph.append({
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"}
    })
    has_parts = []
    file_nodes = []
    import datetime as _dt
    for it in items:
        url = to_rclone_url(it.get('path'))
        if not url:
            continue
        has_parts.append({"@id": url})
        node = {"@id": url, "@type": "File", "contentUrl": url}
        if it.get('name'):
            node['name'] = it.get('name')
        try:
            node['contentSize'] = int(it.get('size') or 0)
        except Exception:
            pass
        if it.get('mime_type'):
            node['encodingFormat'] = it.get('mime_type')
        try:
            mt = float(it.get('modified_time') or 0.0)
            if mt:
                node['dateModified'] = _dt.datetime.utcfromtimestamp(mt).isoformat() + 'Z'
        except Exception:
            pass
        if it.get('checksum'):
            node['checksum'] = it.get('checksum')
        file_nodes.append(node)
    root = {"@id": "./", "@type": "Dataset", "name": title, "hasPart": has_parts}
    graph.append(root)
    graph.extend(file_nodes)
    ro = {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}
    try:
        with open(os.path.join(out_dir, 'ro-crate-metadata.json'), 'w', encoding='utf-8') as fh:
            _json.dump(ro, fh, indent=2)
    except Exception as e:
        return jsonify({"status": "error", "error": f"could not write ro-crate: {e}"}), 500
    return jsonify({"status": "ok", "crate_id": crate_id, "path": out_dir}), 200

    
@bp.post('/ro-crates/<crate_id>/export')
def api_ro_crates_export(crate_id):
    """Export a referenced RO-Crate directory as a ZIP (metadata-only).
    Query param: target=zip (required)
    Errors:
      - 400 for missing/invalid target or inaccessible path
      - 404 when crateId directory does not exist
    """
    target = (request.args.get('target') or '').strip().lower()
    if target not in ('zip', 'application/zip', 'zipfile'):
        return jsonify({'error': 'invalid or missing target; expected target=zip'}), 400
    base_dir = os.environ.get('SCIDK_ROCRATE_DIR') or os.path.expanduser('~/.scidk/crates')
    crate_dir = os.path.join(base_dir, crate_id)
    try:
        from pathlib import Path as _P
        p = _P(crate_dir)
        if not p.exists():
            return jsonify({'error': 'crate not found'}), 404
        if not p.is_dir():
            return jsonify({'error': 'crate path is not a directory'}), 400
        # Build a ZIP of the crate directory (metadata files only live here in referenced mode)
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            # include all files under the crate directory (non-recursive safe walk)
            for root, dirs, files in os.walk(str(p)):
                rel_root = os.path.relpath(root, str(p))
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = fname if rel_root == '.' else os.path.join(rel_root, fname)
                    try:
                        zf.write(fpath, arcname)
                    except Exception:
                        # skip unreadable files but continue building the archive
                        continue
                # Only shallow by default; but if metadata structure has subdirs, we include them
                # so we do not break out of walk intentionally.
        buf.seek(0)
        from flask import send_file as _send_file
        dl_name = f"{crate_id}.zip"
        return _send_file(buf, mimetype='application/zip', as_attachment=True, download_name=dl_name)
    except PermissionError:
        return jsonify({'error': 'inaccessible crate path'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

