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

def _get_feedback_service():
    """Get GraphRAGFeedbackService instance using settings DB path from config."""
    from ...services.graphrag_feedback_service import get_graphrag_feedback_service
    db_path = current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
    return get_graphrag_feedback_service(db_path=db_path)

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

            # Classify intent for routing (LOOKUP vs REASONING)
            from ...services.graphrag.intent_classifier import classify, Intent
            intent = classify(message)

            # Route based on intent
            if intent == Intent.LOOKUP:
                # LOOKUP path: Fast Text2Cypher via QueryEngine
                from ...services.graphrag.query_engine import QueryEngine
                anthropic_key = os.environ.get('SCIDK_ANTHROPIC_API_KEY')
                verbose = (os.environ.get('SCIDK_GRAPHRAG_VERBOSE') or '').strip().lower() in ('1','true','yes')

                query_engine = QueryEngine(
                    driver=driver,
                    neo4j_schema=neo4j_schema,
                    anthropic_api_key=anthropic_key,
                    database=database,
                    verbose=verbose
                )

                # Execute query
                result = query_engine.query(message)

                if result.get('status') == 'error':
                    return jsonify(result), 500

                result_text = result.get('answer', 'No results found')

                # Build response with engine type and cypher for UI
                response_data = {
                    "status": "ok",
                    "reply": result_text,
                    "engine": result.get('engine', 'graph_query'),  # For UI badge
                    "cypher_query": result.get('cypher_query'),  # For citations panel
                }

                # Include metadata
                response_data["metadata"] = {
                    "entities": result.get('entities', {}),
                    "execution_time_ms": result.get('execution_time_ms', 0),
                    "result_count": result.get('result_count', 0)
                }

                if verbose and 'results' in result:
                    response_data["metadata"]["results"] = result['results']

            else:
                # REASONING path: Use existing /v2 provider architecture
                # This gives full LLM reasoning with schema context
                from ...ai.schema_context import get_schema_context
                from ...ai.provider_factory import LLMProviderFactory

                schema_context = get_schema_context(driver, database=database or "neo4j")

                # Build settings dict from environment/config
                settings = {
                    'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                    'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                    'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                    'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                    'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                }

                provider_obj = LLMProviderFactory.from_settings(settings)

                # Base system prompt
                base_prompt = "You are a research data assistant for SciDK. Answer questions about the knowledge graph and scientific data."

                # Complete (non-streaming)
                start_time_reasoning = time.time()
                response_text = provider_obj.complete(
                    user_message=message,
                    system_prompt=base_prompt,
                    schema_context=schema_context
                )
                elapsed_ms = int((time.time() - start_time_reasoning) * 1000)

                # Build response
                provider_info = provider_obj.health_check()

                response_data = {
                    "status": "ok",
                    "reply": response_text,
                    "engine": "reasoning",  # For UI badge
                    "metadata": {
                        "provider": provider_info.get("provider"),
                        "model": provider_info.get("model"),
                        "cached_schema": schema_context.get("cached", False),
                        "schema_labels_count": len(schema_context.get("labels", [])),
                        "execution_time_ms": elapsed_ms
                    }
                }

            # Track history and minimal audit
            store = _get_ext().setdefault('chat', {"history": []})
            store['history'].extend([{"role":"user","content":message},{"role":"assistant","content":response_data.get('reply','')}])
            audit = _get_ext().setdefault('telemetry', {}).setdefault('graphrag_audit', [])
            try:
                audit.append({
                    'ts': int(time.time()),
                    'message': message[:500],
                    'reply_len': len(response_data.get('reply', '') or ''),
                    'execution_time_ms': response_data.get('metadata', {}).get('execution_time_ms', 0),
                    'engine': response_data.get('engine', 'unknown'),
                })
            except Exception:
                pass

            # Add history to response
            response_data["history"] = store['history']

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


# ========== Permissions & Sharing ==========

@bp.get('/chat/sessions/<session_id>/permissions')
def get_session_permissions(session_id):
    """Get all permissions for a session.

    Requires: Admin permission on the session

    Returns:
        200: {
            "permissions": [
                {
                    "username": "alice",
                    "permission": "edit",
                    "granted_at": 1234567890.0,
                    "granted_by": "bob"
                },
                ...
            ]
        }
        403: {"error": "Insufficient permissions"}
    """
    from flask import g

    chat_service = _get_chat_service()

    # Get current user from Flask g (set by auth middleware)
    username = getattr(g, 'scidk_username', None)
    if not username:
        return jsonify({'error': 'Authentication required'}), 401

    permissions = chat_service.list_permissions(session_id, username)
    if permissions is None:
        return jsonify({'error': 'Insufficient permissions'}), 403

    return jsonify({'permissions': permissions}), 200


@bp.post('/chat/sessions/<session_id>/permissions')
def grant_session_permission(session_id):
    """Grant permission to a user for a session.

    Requires: Admin permission on the session

    Request body:
        {
            "username": "alice",
            "permission": "view" | "edit" | "admin"
        }

    Returns:
        200: {"success": true}
        400: {"error": "Invalid request"}
        403: {"error": "Insufficient permissions"}
    """
    from flask import g

    chat_service = _get_chat_service()

    # Get current user
    current_user = getattr(g, 'scidk_username', None)
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json() or {}
    target_username = data.get('username', '').strip()
    permission = data.get('permission', '').strip()

    if not target_username or not permission:
        return jsonify({'error': 'Missing username or permission'}), 400

    if permission not in ('view', 'edit', 'admin'):
        return jsonify({'error': 'Invalid permission level'}), 400

    success = chat_service.grant_permission(session_id, target_username, permission, current_user)

    if not success:
        return jsonify({'error': 'Insufficient permissions or session not found'}), 403

    return jsonify({'success': True}), 200


@bp.delete('/chat/sessions/<session_id>/permissions/<username>')
def revoke_session_permission(session_id, username):
    """Revoke a user's permission for a session.

    Requires: Admin permission on the session

    Returns:
        200: {"success": true}
        403: {"error": "Insufficient permissions"}
    """
    from flask import g

    chat_service = _get_chat_service()

    # Get current user
    current_user = getattr(g, 'scidk_username', None)
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    success = chat_service.revoke_permission(session_id, username, current_user)

    if not success:
        return jsonify({'error': 'Insufficient permissions or permission not found'}), 403

    return jsonify({'success': True}), 200


@bp.put('/chat/sessions/<session_id>/visibility')
def set_session_visibility(session_id):
    """Set session visibility.

    Requires: Admin permission on the session

    Request body:
        {
            "visibility": "private" | "shared" | "public"
        }

    Returns:
        200: {"success": true}
        400: {"error": "Invalid visibility"}
        403: {"error": "Insufficient permissions"}
    """
    from flask import g

    chat_service = _get_chat_service()

    # Get current user
    username = getattr(g, 'scidk_username', None)
    if not username:
        return jsonify({'error': 'Authentication required'}), 401

    data = request.get_json() or {}
    visibility = data.get('visibility', '').strip()

    if visibility not in ('private', 'shared', 'public'):
        return jsonify({'error': 'Invalid visibility. Must be: private, shared, or public'}), 400

    success = chat_service.set_visibility(session_id, visibility, username)

    if not success:
        return jsonify({'error': 'Insufficient permissions or session not found'}), 403

    return jsonify({'success': True}), 200


# ========== GraphRAG Feedback ==========

@bp.post('/chat/graphrag/feedback')
def add_graphrag_feedback():
    """Submit feedback for a GraphRAG query.

    Request body:
        {
            "query": "original query text",
            "entities_extracted": {...},
            "cypher_generated": "MATCH ...",  // optional
            "session_id": "uuid",  // optional
            "message_id": "uuid",  // optional
            "feedback": {
                "answered_question": true/false,
                "entity_corrections": {
                    "removed": ["Dataset:ABC"],
                    "added": [{"type": "Sample", "value": "XYZ"}]
                },
                "query_corrections": "reformulated query text",
                "missing_results": "description of what was missing",
                "schema_terminology": {"user_term": "schema_term"},
                "notes": "free text feedback"
            }
        }

    Returns:
        201: {
            "feedback_id": "uuid",
            "status": "success"
        }
        400: {"error": "Missing required fields"}
    """
    data = request.get_json() or {}

    query = data.get('query', '').strip()
    entities_extracted = data.get('entities_extracted', {})
    feedback = data.get('feedback', {})

    if not query:
        return jsonify({'error': 'Missing query'}), 400

    if not feedback:
        return jsonify({'error': 'Missing feedback'}), 400

    feedback_service = _get_feedback_service()

    feedback_obj = feedback_service.add_feedback(
        query=query,
        entities_extracted=entities_extracted,
        feedback=feedback,
        session_id=data.get('session_id'),
        message_id=data.get('message_id'),
        cypher_generated=data.get('cypher_generated')
    )

    return jsonify({
        'feedback_id': feedback_obj.id,
        'status': 'success'
    }), 201


@bp.get('/chat/graphrag/feedback')
def list_graphrag_feedback():
    """List GraphRAG feedback entries.

    Query params:
        session_id (optional): Filter by session
        answered_question (optional): Filter by true/false
        limit (int): Maximum entries (default 100)
        offset (int): Skip entries (default 0)

    Returns:
        200: {
            "feedback": [
                {
                    "id": "uuid",
                    "query": "...",
                    "entities_extracted": {...},
                    "feedback": {...},
                    "timestamp": 1234567890.0
                },
                ...
            ]
        }
    """
    feedback_service = _get_feedback_service()

    session_id = request.args.get('session_id')
    answered_question = request.args.get('answered_question')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    # Convert answered_question string to bool
    answered_bool = None
    if answered_question is not None:
        answered_bool = answered_question.lower() in ('true', '1', 'yes')

    feedback_list = feedback_service.list_feedback(
        session_id=session_id,
        answered_question=answered_bool,
        limit=limit,
        offset=offset
    )

    return jsonify({
        'feedback': [f.to_dict() for f in feedback_list]
    }), 200


@bp.get('/chat/graphrag/feedback/<feedback_id>')
def get_graphrag_feedback(feedback_id):
    """Get a specific feedback entry.

    Returns:
        200: {
            "feedback": {...}
        }
        404: {"error": "Feedback not found"}
    """
    feedback_service = _get_feedback_service()
    feedback = feedback_service.get_feedback(feedback_id)

    if not feedback:
        return jsonify({'error': 'Feedback not found'}), 404

    return jsonify({
        'feedback': feedback.to_dict()
    }), 200


@bp.get('/chat/graphrag/feedback/stats')
def get_graphrag_feedback_stats():
    """Get aggregated feedback statistics.

    Returns:
        200: {
            "total_feedback_count": 100,
            "answered_yes_count": 75,
            "answered_no_count": 25,
            "answer_rate": 75.0,
            "entity_corrections_count": 30,
            "query_corrections_count": 15,
            "terminology_corrections_count": 10
        }
    """
    feedback_service = _get_feedback_service()
    stats = feedback_service.get_feedback_stats()

    return jsonify(stats), 200


@bp.get('/chat/graphrag/feedback/analysis/entities')
def get_entity_corrections():
    """Get entity corrections for analysis.

    Query params:
        limit (int): Maximum entries (default 50)

    Returns:
        200: {
            "corrections": [
                {
                    "query": "...",
                    "extracted": {...},
                    "corrections": {...},
                    "timestamp": 1234567890.0
                },
                ...
            ]
        }
    """
    feedback_service = _get_feedback_service()
    limit = request.args.get('limit', 50, type=int)

    corrections = feedback_service.get_entity_corrections(limit=limit)

    return jsonify({
        'corrections': corrections
    }), 200


@bp.get('/chat/graphrag/feedback/analysis/queries')
def get_query_reformulations():
    """Get query reformulations for training data.

    Query params:
        limit (int): Maximum entries (default 50)

    Returns:
        200: {
            "reformulations": [
                {
                    "original_query": "...",
                    "corrected_query": "...",
                    "entities_extracted": {...},
                    "timestamp": 1234567890.0
                },
                ...
            ]
        }
    """
    feedback_service = _get_feedback_service()
    limit = request.args.get('limit', 50, type=int)

    reformulations = feedback_service.get_query_reformulations(limit=limit)

    return jsonify({
        'reformulations': reformulations
    }), 200


@bp.get('/chat/graphrag/feedback/analysis/terminology')
def get_terminology_mappings():
    """Get schema terminology mappings from feedback.

    Returns:
        200: {
            "mappings": {
                "user_term": "schema_term",
                ...
            }
        }
    """
    feedback_service = _get_feedback_service()
    mappings = feedback_service.get_terminology_mappings()

    return jsonify({
        'mappings': mappings
    }), 200


# ============================================================================
# New Provider Architecture (Phase 2/3) - Multi-provider with streaming
# ============================================================================

@bp.post('/chat/graphrag/v2')
def api_chat_graphrag_v2():
    """
    GraphRAG with new provider architecture and schema grounding.

    Features:
    - Multi-provider support (Ollama/Claude/OpenAI)
    - Schema grounding (prevents LLM hallucination)
    - No streaming (use /chat/graphrag/v2/stream for streaming)

    Body:
        message: str (required)
        provider: str (optional, uses setting/env if not specified)

    Returns:
        200: {status, reply, metadata: {provider, model, cached_schema, ...}}
        500: {status: error, error: str}
    """
    enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
    if not enabled:
        from ...services.graphrag_schema import normalize_error
        return jsonify(normalize_error(
            status="disabled",
            error="GraphRAG disabled",
            code="GR_DISABLED",
            hint="Set SCIDK_GRAPHRAG_ENABLED=1"
        )), 501

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({"status": "error", "error": "message required"}), 400

    try:
        # Get Neo4j connection
        from ...services.neo4j_client import get_neo4j_params
        from neo4j import GraphDatabase
        uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)

        if not uri:
            return jsonify({
                "status": "error",
                "error": "Neo4j not configured",
                "hint": "Set NEO4J_URI and credentials"
            }), 500

        auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
        driver = GraphDatabase.driver(uri, auth=auth)

        # Get schema context for grounding (provider integrates it)
        from ...ai.schema_context import get_schema_context
        schema_context = get_schema_context(driver, database=database or "neo4j")

        # Get provider (allow override via request body)
        from ...ai.provider_factory import LLMProviderFactory

        # Build settings dict from environment/config
        settings = {
            'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
            'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
            'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
            'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
            'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
        }

        provider = LLMProviderFactory.from_settings(settings)

        # Base system prompt (provider will integrate schema_context)
        base_prompt = "You are a research data assistant for SciDK."

        # Complete (non-streaming) - schema grounding built into interface
        start_time = time.time()
        response_text = provider.complete(
            user_message=message,
            system_prompt=base_prompt,
            schema_context=schema_context
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Build response with engine field for UI badge
        provider_info = provider.health_check()

        return jsonify({
            "status": "ok",
            "reply": response_text,
            "engine": "reasoning",  # For UI badge
            "metadata": {
                "provider": provider_info.get("provider"),
                "model": provider_info.get("model"),
                "cached_schema": schema_context.get("cached", False),
                "schema_labels_count": len(schema_context.get("labels", [])),
                "execution_time_ms": elapsed_ms
            }
        }), 200

    except ConnectionError as e:
        return jsonify({"status": "error", "error": str(e)}), 503
    except ValueError as e:
        return jsonify({"status": "error", "error": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.post('/chat/graphrag/v2/stream')
def api_chat_graphrag_v2_stream():
    """
    GraphRAG with streaming responses.

    Critical for UX: At 13 tok/sec, streaming makes 15s responses feel instant.

    Body:
        message: str (required)
        provider: str (optional)

    Returns:
        200: Server-Sent Events (SSE) stream
            data: {"type": "token", "content": "..."}
            data: {"type": "done", "metadata": {...}}
    """
    enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
    if not enabled:
        return jsonify({
            "status": "disabled",
            "error": "GraphRAG disabled",
            "hint": "Set SCIDK_GRAPHRAG_ENABLED=1"
        }), 501

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({"status": "error", "error": "message required"}), 400

    def generate_stream():
        """Generator for SSE streaming."""
        try:
            # Get Neo4j connection and schema
            from ...services.neo4j_client import get_neo4j_params
            from neo4j import GraphDatabase
            uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)

            if not uri:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Neo4j not configured'})}\n\n"
                return

            auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
            driver = GraphDatabase.driver(uri, auth=auth)

            # Get schema context for grounding
            from ...ai.schema_context import get_schema_context
            schema_context = get_schema_context(driver, database=database or "neo4j")

            # Get provider
            from ...ai.provider_factory import LLMProviderFactory
            settings = {
                'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
            }

            provider = LLMProviderFactory.from_settings(settings)

            # Base system prompt
            base_prompt = "You are a research data assistant for SciDK."

            # Stream tokens - schema grounding built into interface
            start_time = time.time()
            for token in provider.stream(
                user_message=message,
                system_prompt=base_prompt,
                schema_context=schema_context
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Send completion metadata with engine field for UI badge
            provider_info = provider.health_check()
            yield f"data: {json.dumps({'type': 'done', 'metadata': {'provider': provider_info.get('provider'), 'model': provider_info.get('model'), 'execution_time_ms': elapsed_ms, 'engine': 'reasoning'}})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return current_app.response_class(
        generate_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@bp.get('/chat/providers')
def api_chat_providers():
    """
    Get available LLM providers and their status.

    Returns:
        200: {
            "providers": {
                "ollama": {status, endpoint, model, available_models, ...},
                "anthropic": {status, model, ...},
                "openai": {status, model, ...}
            }
        }
    """
    from ...ai.provider_factory import LLMProviderFactory

    settings = {
        'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
        'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
        'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
        'chat_claude_model': os.environ.get('SCIDK_CHAT_CLAUDE_MODEL'),
        'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
        'chat_openai_model': os.environ.get('SCIDK_CHAT_OPENAI_MODEL'),
    }

    providers = LLMProviderFactory.get_available_providers(settings)

    return jsonify({"providers": providers}), 200


@bp.post('/chat/schema/refresh')
def api_chat_schema_refresh():
    """
    Force refresh of schema cache.

    Useful after Neo4j schema changes or for testing.

    Returns:
        200: {status: ok, message: "Schema cache cleared"}
    """
    from ...ai.schema_context import refresh_schema_cache
    refresh_schema_cache()

    return jsonify({"status": "ok", "message": "Schema cache cleared"}), 200


@bp.get('/chat/schema/cache/stats')
def api_chat_schema_cache_stats():
    """
    Get schema cache statistics for observability.

    Returns:
        200: {size, keys, timestamps, ttl_seconds}
    """
    from ...ai.schema_context import get_cache_stats
    stats = get_cache_stats()

    return jsonify(stats), 200
