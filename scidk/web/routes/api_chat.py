"""
Blueprint for Chat/LLM API routes.
"""
from flask import Blueprint, jsonify, request, current_app
from pathlib import Path
import json
import os
import time

bp = Blueprint('chat', __name__, url_prefix='/api')

def _get_ext():
    """Get SciDK extensions from current Flask current_app."""
    return current_app.extensions['scidk']

def _get_chat_service():
    """Get ChatService instance using settings DB path from config."""
    from ...services.chat_service import get_chat_service
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_chat_service(db_path=db_path)

@bp.post('/chat')
def api_chat():
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"status": "error", "error": "message required"}), 400
        store = _get_ext().setdefault('chat', {"history": []})
        # Simple echo bot with count
        reply = f"Echo: {message}"
        entry_user = {"role": "user", "content": message}
        entry_assistant = {"role": "assistant", "content": reply}
        store['history'].append(entry_user)
        store['history'].append(entry_assistant)
        return jsonify({"status": "ok", "reply": reply, "history": store['history']}), 200

    # --- GraphRAG endpoints (Phase 1 scaffold) ---

@bp.post('/chat/graphrag')
def api_chat_graphrag():
        """Natural language to Cypher and graph-augmented reply (scaffold).
        Privacy-first: only enabled when SCIDK_GRAPHRAG_ENABLED is truthy.
        If neo4j-graphrag is unavailable or disabled, returns a clear message.
        """
        enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
        if not enabled:
            from ...services.graphrag_schema import normalize_error
            return jsonify(normalize_error(status="disabled", error="GraphRAG disabled", code="GR_DISABLED", hint="Set SCIDK_GRAPHRAG_ENABLED=1")), 501
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"status": "error", "error": "message required"}), 400
        # Reuse existing Neo4j connection params
        try:
            from ...services.neo4j_client import get_neo4j_params
            uri, user, pwd, database, auth_mode = get_neo4j_params(app)
        except Exception:
            uri = user = pwd = database = auth_mode = None
        if not uri:
            from ...services.graphrag_schema import normalize_error
            return jsonify(normalize_error(status="error", error="Neo4j is not configured", code="NEO4J_CONFIG_MISSING", hint="Set NEO4J_URI and credentials or NEO4J_AUTH=none")), 500
        # Attempt lazy import and minimal flow
        try:
            from neo4j import GraphDatabase  # type: ignore
            # Soft optional import for graphrag; if missing, report capability
            try:
                from neo4j_graphrag.retrievers import Text2CypherRetriever  # type: ignore
                from neo4j_graphrag.generation import GraphRAG  # type: ignore
            except Exception as e:
                from ...services.graphrag_schema import normalize_error
                return jsonify(normalize_error(status="unavailable", error="neo4j-graphrag not installed", code="GR_LIB_MISSING", hint="pip install neo4j-graphrag>=0.3.0", detail=str(e))), 501
            # Privacy-preserving LLM selection
            provider = (os.environ.get('SCIDK_GRAPHRAG_LLM_PROVIDER') or 'local_ollama').strip().lower()
            model = (os.environ.get('SCIDK_GRAPHRAG_MODEL') or 'llama3:8b').strip()
            llm = None
            if provider in ('local_ollama', 'ollama'):
                try:
                    from ollama import Client as OllamaClient  # type: ignore
                    oc = OllamaClient()
                    class _OllamaLLM:
                        def __init__(self, client, model):
                            self.client = client; self.model = model
                        def complete(self, prompt: str) -> str:
                            r = self.client.generate(model=self.model, prompt=prompt)
                            return r.get('response') or ''
                    llm = _OllamaLLM(oc, model)
                except Exception as e:
                    from ...services.graphrag_schema import normalize_error
                    return jsonify(normalize_error(status="error", error="Ollama not available", code="LLM_NOT_AVAILABLE", detail=str(e), hint="Ensure Ollama is installed and running, and SCIDK_GRAPHRAG_MODEL is available")), 500
            elif provider in ('openai','azure_openai'):
                return jsonify({"status": "forbidden", "error": "External providers disabled for privacy in Phase 1"}), 403
            else:
                return jsonify({"status": "error", "error": f"Unknown provider: {provider}"}), 400
            auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
            driver = GraphDatabase.driver(uri, auth=auth)
            # Schema cache with privacy filtering
            from ...services.graphrag_schema import parse_ttl, filter_schema
            from ...services.graphrag_examples import examples as t2c_examples
            schema_cache = _get_ext().setdefault('graphrag_schema', {})
            last = schema_cache.get('last_loaded_ts') or 0
            ttl = 0
            ttl_env = os.environ.get('SCIDK_GRAPHRAG_SCHEMA_CACHE_TTL_SEC') or os.environ.get('SCIDK_GRAPHRAG_SCHEMA_CACHE_TTL')
            if ttl_env:
                ttl = parse_ttl(ttl_env)
            now = int(time.time())
            if (now - last) > max(0, ttl):
                with driver.session(database=database) if database else driver.session() as s:
                    labels = [r[0] for r in s.run("CALL db.labels()").values()]
                    rels = [r[0] for r in s.run("CALL db.relationshipTypes()").values()]
                raw_schema = {"labels": labels, "relationships": rels}
                allow_labels = [x.strip() for x in (os.environ.get('SCIDK_GRAPHRAG_ALLOW_LABELS') or '').split(',') if x.strip()]
                deny_labels = [x.strip() for x in (os.environ.get('SCIDK_GRAPHRAG_DENY_LABELS') or '').split(',') if x.strip()]
                prop_excl = [x.strip() for x in (os.environ.get('SCIDK_GRAPHRAG_EXCLUDE_PROPERTIES') or '').split(',') if x.strip()]
                filtered = filter_schema(raw_schema, allow_labels or None, deny_labels or None, prop_excl or None)
                schema_cache['schema'] = filtered
                schema_cache['last_loaded_ts'] = now
            neo4j_schema = schema_cache.get('schema') or {"labels": [], "relationships": []}

            # Use new QueryEngine with entity extraction
            from ...services.graphrag.query_engine import QueryEngine
            anthropic_key = os.environ.get('SCIDK_ANTHROPIC_API_KEY')
            verbose = (os.environ.get('SCIDK_GRAPHRAG_VERBOSE') or '').strip().lower() in ('1','true','yes')

            engine = QueryEngine(
                driver=driver,
                neo4j_schema=neo4j_schema,
                anthropic_api_key=anthropic_key,
                examples=t2c_examples,
                verbose=verbose
            )

            # Execute query
            result = engine.query(message)

            if result.get('status') == 'error':
                return jsonify(result), 500

            result_text = result.get('answer', 'No results found')

            # Track history and minimal audit
            store = _get_ext().setdefault('chat', {"history": []})
            store['history'].extend([{"role":"user","content":message},{"role":"assistant","content":result_text}])
            audit = _get_ext().setdefault('telemetry', {}).setdefault('graphrag_audit', [])
            try:
                audit.append({
                    'ts': int(time.time()),
                    'message': message[:500],
                    'reply_len': len(result_text or ''),
                    'execution_time_ms': result.get('execution_time_ms', 0),
                })
            except Exception:
                pass

            # Build response with metadata for enhanced UI
            response_data = {
                "status": "ok",
                "reply": result_text,
                "history": store['history']
            }

            # Include metadata if verbose mode
            if verbose:
                response_data["metadata"] = {
                    "entities": result.get('entities', {}),
                    "execution_time_ms": result.get('execution_time_ms', 0),
                    "result_count": len(result.get('results', []))
                }

            return jsonify(response_data), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500


@bp.get('/chat/history')
def api_chat_history():
        store = _get_ext().setdefault('chat', {"history": []})
        return jsonify({"status": "ok", "history": store['history']}), 200


@bp.post('/chat/context/refresh')
def api_chat_context_refresh():
        enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
        if not enabled:
            from ...services.graphrag_schema import normalize_error
            return jsonify(normalize_error(status="disabled", error="GraphRAG disabled", code="GR_DISABLED", hint="Set SCIDK_GRAPHRAG_ENABLED=1")), 501
        # Force refresh schema cache
        try:
            from ...services.neo4j_client import get_neo4j_params
            from neo4j import GraphDatabase  # type: ignore
            uri, user, pwd, database, auth_mode = get_neo4j_params(app)
            if not uri:
                from ...services.graphrag_schema import normalize_error
                return jsonify(normalize_error(status="error", error="Neo4j not configured", code="NEO4J_CONFIG_MISSING", hint="Set NEO4J_URI and credentials or NEO4J_AUTH=none")), 500
            auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
            driver = GraphDatabase.driver(uri, auth=auth)
            with driver.session(database=database) if database else driver.session() as s:
                labels = [r[0] for r in s.run("CALL db.labels()").values()]
                rels = [r[0] for r in s.run("CALL db.relationshipTypes()").values()]
            from ...services.graphrag_schema import filter_schema
            raw_schema = {"labels": labels, "relationships": rels}
            allow_labels = [x.strip() for x in (os.environ.get('SCIDK_GRAPHRAG_ALLOW_LABELS') or '').split(',') if x.strip()]
            deny_labels = [x.strip() for x in (os.environ.get('SCIDK_GRAPHRAG_DENY_LABELS') or '').split(',') if x.strip()]
            prop_excl = [x.strip() for x in (os.environ.get('SCIDK_GRAPHRAG_EXCLUDE_PROPERTIES') or '').split(',') if x.strip()]
            filtered = filter_schema(raw_schema, allow_labels or None, deny_labels or None, prop_excl or None)
            schema_cache = _get_ext().setdefault('graphrag_schema', {})
            schema_cache['schema'] = filtered
            schema_cache['last_loaded_ts'] = int(time.time())
            return jsonify({"status": "ok", "schema": schema_cache['schema']}), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500


@bp.get('/chat/capabilities')
def api_chat_capabilities():
        enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
        provider = (os.environ.get('SCIDK_GRAPHRAG_LLM_PROVIDER') or 'local_ollama').strip().lower()
        model = (os.environ.get('SCIDK_GRAPHRAG_MODEL') or 'llama3:8b').strip()
        return jsonify({
            "graphrag": {
                "enabled": bool(enabled),
                "llm_provider": provider,
                "model": model,
            }
        }), 200


@bp.get('/chat/observability/graphrag')
def api_chat_observability_graphrag():
        from ...services.graphrag_schema import parse_ttl
        enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
        provider = (os.environ.get('SCIDK_GRAPHRAG_LLM_PROVIDER') or 'local_ollama').strip().lower()
        model = (os.environ.get('SCIDK_GRAPHRAG_MODEL') or 'llama3:8b').strip()
        schema_cache = _get_ext().setdefault('graphrag_schema', {})
        schema = schema_cache.get('schema') or {"labels": [], "relationships": []}
        last_loaded = schema_cache.get('last_loaded_ts')
        ttl_env = os.environ.get('SCIDK_GRAPHRAG_SCHEMA_CACHE_TTL_SEC') or os.environ.get('SCIDK_GRAPHRAG_SCHEMA_CACHE_TTL')
        ttl = parse_ttl(ttl_env) if ttl_env else 0
        audit = _get_ext().setdefault('telemetry', {}).setdefault('graphrag_audit', [])
        # Return only last 20 entries with redacted message preview
        recent = []
        for a in audit[-20:]:
            recent.append({
                'ts': a.get('ts'),
                'message_preview': (a.get('message') or '')[:120],
                'reply_len': a.get('reply_len'),
                'provider': a.get('provider'),
            })
        return jsonify({
            'status': 'ok',
            'enabled': bool(enabled),
            'llm_provider': provider,
            'model': model,
            'schema': {
                'labels_count': len(schema.get('labels') or []),
                'relationships_count': len(schema.get('relationships') or []),
                'last_loaded_ts': last_loaded,
                'cache_ttl_sec': ttl,
            },
            'audit': recent,
        }), 200


# ========== Chat Session Persistence ==========

@bp.get('/chat/sessions')
def list_sessions():
    """List all chat sessions, ordered by most recently updated.

    Query params:
        limit (int): Maximum number of sessions (default 100)
        offset (int): Number of sessions to skip (default 0)

    Returns:
        200: {
            "sessions": [
                {
                    "id": "uuid",
                    "name": "Session Name",
                    "created_at": 1234567890.0,
                    "updated_at": 1234567890.0,
                    "message_count": 5,
                    "metadata": {}
                },
                ...
            ]
        }
    """
    chat_service = _get_chat_service()

    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    sessions = chat_service.list_sessions(limit=limit, offset=offset)

    return jsonify({
        'sessions': [s.to_dict() for s in sessions]
    }), 200


@bp.post('/chat/sessions')
def create_session():
    """Create a new chat session.

    Request body:
        {
            "name": "Session Name",
            "metadata": {}  // optional
        }

    Returns:
        201: {
            "session": {
                "id": "uuid",
                "name": "Session Name",
                "created_at": 1234567890.0,
                "updated_at": 1234567890.0,
                "message_count": 0,
                "metadata": {}
            }
        }
        400: {"error": "Missing session name"}
    """
    chat_service = _get_chat_service()

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    metadata = data.get('metadata')

    if not name:
        return jsonify({'error': 'Missing session name'}), 400

    session = chat_service.create_session(name=name, metadata=metadata)

    return jsonify({
        'session': session.to_dict()
    }), 201


@bp.get('/chat/sessions/<session_id>')
def get_session(session_id):
    """Get a session with its messages.

    Query params:
        limit (int): Maximum number of messages (default: all)
        offset (int): Number of messages to skip (default: 0)

    Returns:
        200: {
            "session": {...},
            "messages": [
                {
                    "id": "uuid",
                    "session_id": "uuid",
                    "role": "user",
                    "content": "message text",
                    "timestamp": 1234567890.0,
                    "metadata": {}
                },
                ...
            ]
        }
        404: {"error": "Session not found"}
    """
    chat_service = _get_chat_service()

    session = chat_service.get_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', 0, type=int)

    messages = chat_service.get_messages(session_id, limit=limit, offset=offset)

    return jsonify({
        'session': session.to_dict(),
        'messages': [m.to_dict() for m in messages]
    }), 200


@bp.put('/chat/sessions/<session_id>')
def update_session(session_id):
    """Update session metadata.

    Request body:
        {
            "name": "New Name",  // optional
            "metadata": {}       // optional
        }

    Returns:
        200: {"success": true}
        404: {"error": "Session not found"}
        400: {"error": "No updates provided"}
    """
    chat_service = _get_chat_service()

    data = request.get_json() or {}
    name = data.get('name')
    metadata = data.get('metadata')

    if name is None and metadata is None:
        return jsonify({'error': 'No updates provided'}), 400

    success = chat_service.update_session(session_id, name=name, metadata=metadata)

    if not success:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({'success': True}), 200


@bp.delete('/chat/sessions/<session_id>')
def delete_session(session_id):
    """Delete a session and all its messages.

    Returns:
        200: {"success": true}
        404: {"error": "Session not found"}
    """
    chat_service = _get_chat_service()

    success = chat_service.delete_session(session_id)

    if not success:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({'success': True}), 200


@bp.post('/chat/sessions/<session_id>/messages')
def add_message(session_id):
    """Add a message to a session.

    Request body:
        {
            "role": "user" or "assistant",
            "content": "message text",
            "metadata": {}  // optional
        }

    Returns:
        201: {
            "message": {
                "id": "uuid",
                "session_id": "uuid",
                "role": "user",
                "content": "message text",
                "timestamp": 1234567890.0,
                "metadata": {}
            }
        }
        400: {"error": "Missing role or content"}
        404: {"error": "Session not found"}
    """
    chat_service = _get_chat_service()

    # Verify session exists
    session = chat_service.get_session(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    data = request.get_json() or {}
    role = data.get('role', '').strip()
    content = data.get('content', '').strip()
    metadata = data.get('metadata')

    if not role or not content:
        return jsonify({'error': 'Missing role or content'}), 400

    if role not in ('user', 'assistant'):
        return jsonify({'error': 'Role must be "user" or "assistant"'}), 400

    message = chat_service.add_message(
        session_id=session_id,
        role=role,
        content=content,
        metadata=metadata
    )

    return jsonify({
        'message': message.to_dict()
    }), 201


@bp.get('/chat/sessions/<session_id>/export')
def export_session(session_id):
    """Export a session and its messages as JSON.

    Returns:
        200: {
            "session": {...},
            "messages": [...]
        }
        404: {"error": "Session not found"}
    """
    chat_service = _get_chat_service()

    export_data = chat_service.export_session(session_id)

    if not export_data:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify(export_data), 200


@bp.post('/chat/sessions/import')
def import_session():
    """Import a session from exported JSON.

    Request body:
        {
            "data": {
                "session": {...},
                "messages": [...]
            },
            "new_name": "Optional New Name"
        }

    Returns:
        201: {
            "session": {
                "id": "new-uuid",
                "name": "Session Name",
                ...
            }
        }
        400: {"error": "Invalid import data"}
    """
    chat_service = _get_chat_service()

    body = request.get_json() or {}
    data = body.get('data')
    new_name = body.get('new_name')

    if not data or 'session' not in data:
        return jsonify({'error': 'Invalid import data'}), 400

    try:
        session = chat_service.import_session(data, new_name=new_name)
        return jsonify({
            'session': session.to_dict()
        }), 201
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 400


@bp.delete('/chat/sessions/test-cleanup')
def cleanup_test_sessions():
    """Delete test sessions for e2e test cleanup.

    Query params:
        test_id (optional): Delete only sessions with this test_id

    Returns:
        200: {"deleted_count": 5}
    """
    chat_service = _get_chat_service()

    test_id = request.args.get('test_id')
    deleted_count = chat_service.delete_test_sessions(test_id=test_id)

    return jsonify({'deleted_count': deleted_count}), 200
