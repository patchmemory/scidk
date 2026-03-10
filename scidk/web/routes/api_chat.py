"""
Blueprint for Chat/LLM API routes.
"""
from flask import Blueprint, jsonify, request, current_app, Response
from pathlib import Path
import json
import os
import time
import threading

bp = Blueprint('chat', __name__, url_prefix='/api')

# ========== SSE Connection Limiter ==========
# Track active SSE connections to prevent worker pool exhaustion
# With 16 sync gunicorn workers, limit to 12 concurrent streams
_sse_connection_lock = threading.Lock()
_active_sse_connections = 0
MAX_SSE_CONNECTIONS = 12

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

def _map_concept_intent_to_legacy(intent_name: str):
    """Map concept graph intent name back to legacy Intent enum for execution routing."""
    from ...services.graphrag.intent_classifier import Intent

    # Map concept intent names to legacy execution paths
    INTENT_MAP = {
        'data_lookup': Intent.LOOKUP,
        'count_simple': Intent.LOOKUP,
        'count_filtered': Intent.REACT,
        'summarize_dataset': Intent.SUMMARIZE,
        'relationship_traversal': Intent.REACT,
        'property_exploration': Intent.REASONING,
        'reasoning_multi_step': Intent.REACT,
    }

    return INTENT_MAP.get(intent_name, Intent.REASONING)  # Default to REASONING for safety

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

        # Fetch recent conversation context from SQLite for continuity
        session_id = data.get('session_id', 'default')

        # DEBUG: Log session_id being used
        print(f"DEBUG session_id from request: {session_id}")
        print(f"DEBUG request data keys: {list(data.keys())}")

        chat_service = _get_chat_service()
        conversation_context = chat_service.get_recent_turns(session_id, n=4)

        # DEBUG: Log conversation context
        print(f"DEBUG context length: {len(conversation_context)}")
        print(f"DEBUG conversation_context: {conversation_context}")

        # Prepend context to message for intent classification and execution
        message_with_context = f"{conversation_context}\n{message}" if conversation_context else message

        # DEBUG: Log enriched message
        print(f"DEBUG message_with_context: {message_with_context[:300]}")

        # Reuse existing Neo4j connection params
        try:
            from ...services.neo4j_client import get_neo4j_params
            uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)
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

            # Classify intent for routing using Concept Graph or fallback to hard-coded classifier
            from ...services.graphrag.intent_classifier import classify, Intent
            concept_driver = _get_ext().get('concept_driver')
            traversal_log = None

            try:
                if concept_driver is not None:
                    # Use Concept Graph for intent classification and planning
                    from ...services.concept_graph_service import (
                        classify_intent, plan_execution, build_traversal_log,
                        ConceptGraphUnavailableError
                    )
                    from ...services.schema_intelligence import get_relevant_schema_context

                    # Get SQLite connection
                    chat_service_tmp = _get_chat_service()
                    sqlite_conn_tmp = chat_service_tmp._get_conn()

                    try:
                        ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')

                        # Get relevant schema context (for semantic retrieval)
                        schema_context = get_relevant_schema_context(
                            message_with_context, sqlite_conn_tmp, driver,
                            ollama_url, database=database or "neo4j"
                        )
                        relevant_labels = schema_context.get('labels', [])

                        # Classify intent using concept graph
                        # Use raw message (not context) for intent - context pollutes classification
                        intent_name, intent_confidence = classify_intent(
                            message, concept_driver, sqlite_conn_tmp, ollama_url
                        )
                        print(f"DEBUG concept_graph: intent_name={intent_name}, confidence={intent_confidence}")

                        # Plan execution
                        plan = plan_execution(intent_name, relevant_labels, concept_driver)
                        print(f"DEBUG concept_graph: plan={plan}")

                        # Build traversal log
                        traversal_log = build_traversal_log(
                            query=message,
                            intent_matched=intent_name,
                            intent_confidence=intent_confidence,
                            plan=plan,
                            labels_considered=list(schema_context.get('labels', []))
                        )

                        # Map concept intent to legacy Intent enum
                        intent = _map_concept_intent_to_legacy(intent_name)
                        print(f"DEBUG concept_graph: mapped to legacy intent={intent}, value={intent.value}")

                        # Log traversal to SQLite
                        sqlite_conn_tmp.execute(
                            "INSERT INTO usage_event (event_type, label_name, session_id, "
                            "source, traversal_json) VALUES (?, ?, ?, ?, ?)",
                            ('concept_graph_plan', '', data.get('session_id', 'default'),
                             'chat', json.dumps(traversal_log))
                        )
                        sqlite_conn_tmp.commit()

                    finally:
                        sqlite_conn_tmp.close()

                else:
                    # Fallback to hard-coded classifier
                    intent = classify(message_with_context)

            except Exception as e:
                # Concept graph error — fall back to hard-coded classifier
                import logging
                logging.warning(f"Concept graph classification failed: {e}")
                intent = classify(message_with_context)
                traversal_log = None

            # DEBUG: Log classified intent
            print(f"DEBUG classified intent: {intent}")
            print(f"DEBUG intent value: {intent.value}")

            # Route based on intent
            if intent == Intent.LOOKUP:
                # LOOKUP path: Direct Cypher generation using provider
                # This path bypasses QueryEngine to avoid neo4j-graphrag LLM interface requirements
                from ...ai.cypher_utils import build_cypher_system_prompt, extract_cypher
                from ...ai.provider_factory import LLMProviderFactory

                # Build settings dict from environment/config
                settings = {
                    'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                    'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                    'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                    'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                    'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                }

                provider_obj = LLMProviderFactory.from_settings(settings)
                start_time_lookup = time.time()

                # Step 1: Generate Cypher using specialized prompt
                cypher_prompt = build_cypher_system_prompt(neo4j_schema)

                try:
                    cypher_response = provider_obj.complete(
                        user_message=message_with_context,
                        system_prompt=cypher_prompt,
                        schema_context=None  # Don't inject schema - already in cypher_prompt
                    )

                    # Step 2: Extract Cypher from response
                    cypher_query = extract_cypher(cypher_response)

                    if cypher_query is None:
                        # Fallback to REASONING path if no valid Cypher extracted
                        from ...ai.schema_context import get_schema_context
                        import os as os_mod
                        try:
                            from ...services.schema_intelligence import get_relevant_schema_context
                            chat_service_tmp = _get_chat_service()
                            sqlite_conn_tmp = chat_service_tmp._get_conn()
                            try:
                                schema_context = get_relevant_schema_context(
                                    user_query=message_with_context,
                                    sqlite_conn=sqlite_conn_tmp,
                                    neo4j_driver=driver,
                                    ollama_url=os_mod.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                                    database=database or "neo4j"
                                )
                            finally:
                                sqlite_conn_tmp.close()
                        except Exception as e:
                            import logging
                            logging.warning(f"Schema intelligence failed: {e}")
                            schema_context = get_schema_context(driver, database=database or "neo4j")
                        base_prompt = "You are a research data assistant for SciDK. Answer questions about the knowledge graph and scientific data."

                        response_text = provider_obj.complete(
                            user_message=message_with_context,
                            system_prompt=base_prompt,
                            schema_context=schema_context
                        )

                        elapsed_ms = int((time.time() - start_time_lookup) * 1000)
                        response_data = {
                            "status": "ok",
                            "reply": response_text,
                            "engine": "reasoning_fallback",
                            "metadata": {
                                "note": "Could not generate valid Cypher, used reasoning instead",
                                "execution_time_ms": elapsed_ms
                            }
                        }
                    else:
                        # Step 3: Execute Cypher
                        with driver.session(database=database) if database else driver.session() as session:
                            try:
                                result = session.run(cypher_query)
                                records = [record.data() for record in result]
                                result_count = len(records)

                                # Phase 1: Log query usage (never fails)
                                try:
                                    chat_service = _get_chat_service()
                                    sqlite_conn = chat_service._get_conn()
                                    try:
                                        from ...services.schema_intelligence import log_query_usage
                                        log_query_usage(cypher_query, session_id, sqlite_conn, source='chat')
                                    finally:
                                        sqlite_conn.close()
                                except Exception:
                                    pass  # Logging must never fail a query

                            except Exception as query_error:
                                # Cypher execution failed - return error with query for debugging
                                elapsed_ms = int((time.time() - start_time_lookup) * 1000)
                                return jsonify({
                                    "status": "error",
                                    "error": f"Query execution failed: {str(query_error)}",
                                    "cypher_query": cypher_query,
                                    "metadata": {
                                        "execution_time_ms": elapsed_ms
                                    }
                                }), 500

                        # Step 4: Synthesize natural language answer from results
                        synthesis_prompt = f"""You are a research data assistant. A user asked a question and we ran a database query.

Context and Question:
{message_with_context}

Query Results: {records[:10]}  # Limit to first 10 for context window
Result Count: {result_count}

Provide a clear, concise natural language answer based on these results.
If there are many results, summarize the key findings.
If there are no results, say so clearly."""

                        answer = provider_obj.complete(
                            user_message="Synthesize the answer from the query results above.",
                            system_prompt=synthesis_prompt,
                            schema_context=None
                        )

                        elapsed_ms = int((time.time() - start_time_lookup) * 1000)

                        response_data = {
                            "status": "ok",
                            "reply": answer,
                            "engine": "lookup",
                            "cypher_query": cypher_query,
                            "metadata": {
                                "result_count": result_count,
                                "execution_time_ms": elapsed_ms
                            }
                        }

                except Exception as e:
                    # Provider error - return error response
                    elapsed_ms = int((time.time() - start_time_lookup) * 1000)
                    return jsonify({
                        "status": "error",
                        "error": f"LOOKUP path failed: {str(e)}",
                        "metadata": {
                            "execution_time_ms": elapsed_ms
                        }
                    }), 500

            elif intent == Intent.SUMMARIZE:
                # SUMMARIZE path: Run count queries and synthesize narrative overview
                from ...ai.summarization import generate_summary
                from ...ai.provider_factory import LLMProviderFactory

                # Build settings dict from environment/config
                settings = {
                    'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                    'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                    'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                    'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                    'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                }

                provider_obj = LLMProviderFactory.from_settings(settings)

                # Generate summary with count queries
                result = generate_summary(driver, database or "neo4j", provider_obj, neo4j_schema)

                if result.get('status') == 'error':
                    return jsonify(result), 500

                response_data = result

            elif intent == Intent.REACT:
                # REACT path: Multi-step reasoning loop with query execution
                from ...ai.react_loop import run_react_loop
                from ...ai.schema_context import get_schema_context
                from ...ai.provider_factory import LLMProviderFactory
                from ...ai.chat_graph import retrieve_relevant_context, format_context_for_prompt
                from ...services.chat_neo4j_client import get_chat_neo4j_client

                # Get schema context with semantic retrieval
                try:
                    from ...services.schema_intelligence import get_relevant_schema_context
                    chat_service_tmp = _get_chat_service()
                    sqlite_conn_tmp = chat_service_tmp._get_conn()
                    try:
                        schema_context = get_relevant_schema_context(
                            user_query=message_with_context,
                            sqlite_conn=sqlite_conn_tmp,
                            neo4j_driver=driver,
                            ollama_url=os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                            database=database or "neo4j"
                        )
                    finally:
                        sqlite_conn_tmp.close()
                except Exception as e:
                    logger.warning(f"Schema intelligence failed: {e}")
                    schema_context = get_schema_context(driver, database=database or "neo4j")

                # Build settings dict - override model for REACT path
                # REACT requires stronger reasoning to avoid hallucination
                react_model = os.environ.get('SCIDK_REACT_MODEL', 'qwen2.5:72b')

                settings = {
                    'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER', 'ollama'),
                    'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                    'chat_ollama_model': react_model,  # Use REACT-specific model
                    'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                    'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                }

                provider_obj = LLMProviderFactory.from_settings(settings)

                # Get chat Neo4j client for context retrieval
                chat_driver = get_chat_neo4j_client()

                # Retrieve relevant past context (if chat Neo4j available)
                retrieved_history = ""
                session_id = data.get('session_id', 'default')  # Get from request or use default

                if chat_driver:
                    try:
                        relevant_messages = retrieve_relevant_context(
                            current_query=message,
                            session_id=session_id,
                            chat_driver=chat_driver,
                            research_driver=driver,
                            embedding_model=os.environ.get('SCIDK_CHAT_EMBEDDING_MODEL', 'nomic-embed-text'),
                            top_k=int(os.environ.get('SCIDK_CHAT_CONTEXT_RETRIEVAL_TOP_K', 3))
                        )
                        retrieved_history = format_context_for_prompt(relevant_messages)
                    except Exception as e:
                        # Context retrieval failure shouldn't block the query
                        import logging
                        logging.warning(f"Context retrieval failed: {e}")

                # Run ReAct loop
                result = run_react_loop(
                    user_query=message_with_context,
                    session_id=session_id,
                    provider=provider_obj,
                    research_driver=driver,
                    chat_driver=chat_driver,
                    schema_context=schema_context,
                    retrieved_history=retrieved_history,
                    max_steps=int(os.environ.get('SCIDK_CHAT_REACT_MAX_STEPS', 4))
                )

                if result.get('status') == 'error':
                    return jsonify(result), 500

                response_data = result

            else:
                # REASONING path: Use existing /v2 provider architecture
                # This gives full LLM reasoning with schema context
                from ...ai.schema_context import get_schema_context
                from ...ai.provider_factory import LLMProviderFactory

                try:
                    from ...services.schema_intelligence import get_relevant_schema_context
                    chat_service_tmp = _get_chat_service()
                    sqlite_conn_tmp = chat_service_tmp._get_conn()
                    try:
                        schema_context = get_relevant_schema_context(
                            user_query=message_with_context,
                            sqlite_conn=sqlite_conn_tmp,
                            neo4j_driver=driver,
                            ollama_url=os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                            database=database or "neo4j"
                        )
                    finally:
                        sqlite_conn_tmp.close()
                except Exception as e:
                    logger.warning(f"Schema intelligence failed: {e}")
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
                    user_message=message_with_context,
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

            # Save messages to SQLite for conversation context
            try:
                # Ensure session exists (create if needed using INSERT OR IGNORE)
                existing_session = chat_service.get_session(session_id)
                if not existing_session:
                    # Directly insert with the provided session_id
                    conn = chat_service._get_conn()
                    try:
                        import time as time_module
                        now = time_module.time()
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO chat_sessions (id, name, created_at, updated_at, message_count, metadata)
                            VALUES (?, ?, ?, ?, 0, NULL)
                            """,
                            (session_id, f"Chat {session_id[:8]}", now, now)
                        )
                        conn.commit()
                        print(f"DEBUG: Created new session {session_id}")
                    finally:
                        conn.close()

                # Save user message and assistant response
                chat_service.add_message(session_id, "user", message)
                chat_service.add_message(session_id, "assistant", response_data.get('reply', ''))
                print(f"DEBUG: Saved messages to SQLite for session {session_id}")
            except Exception as e:
                # Non-fatal - conversation context won't work but query still succeeds
                print(f"DEBUG: Failed to save messages to SQLite: {e}")
                import traceback
                traceback.print_exc()

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

            # Log to chat Neo4j (background, non-blocking)
            # This logs the final answer + all ReAct steps for full audit trail
            try:
                from ...services.chat_neo4j_client import get_chat_neo4j_client
                chat_driver = get_chat_neo4j_client()

                if chat_driver and intent in (Intent.REACT, Intent.LOOKUP, Intent.SUMMARIZE):
                    import threading

                    def log_to_chat_neo4j():
                        try:
                            from ...ai.chat_graph import log_chat_message

                            # Generate a unique sqlite_id (in real impl, this would be from chat_service)
                            import uuid
                            sqlite_id = str(uuid.uuid4())
                            session_id = data.get('session_id', 'default')

                            # For REACT, log each step as a separate record
                            if intent == Intent.REACT and 'step_log' in response_data:
                                for step in response_data['step_log']:
                                    step_sqlite_id = f"{sqlite_id}_step_{step.get('step_num')}"
                                    log_chat_message(
                                        chat_driver=chat_driver,
                                        research_driver=driver,
                                        sqlite_id=step_sqlite_id,
                                        session_id=session_id,
                                        role="assistant",
                                        intent=intent.value,
                                        content_summary=f"ReAct Step {step.get('step_num')}: {step.get('action_type')}",
                                        finding_text=step.get('content', '')[:150],
                                        finding_type="REACT_STEP",
                                        cypher_used=step.get('content', '') if step.get('action_type') == 'QUERY' else None,
                                        referenced_labels=[],  # Could parse from Cypher
                                        embedding=None
                                    )

                            # Log final answer
                            log_chat_message(
                                chat_driver=chat_driver,
                                research_driver=driver,
                                sqlite_id=sqlite_id,
                                session_id=session_id,
                                role="assistant",
                                intent=intent.value,
                                content_summary=response_data.get('reply', '')[:200],
                                finding_text=response_data.get('reply', '')[:150],
                                finding_type="COUNT" if intent == Intent.SUMMARIZE else "RELATIONAL",
                                cypher_used=response_data.get('cypher_query'),
                                referenced_labels=[],  # Could extract from schema/query
                                embedding=None
                            )

                        except Exception as e:
                            import logging
                            logging.error(f"Chat Neo4j logging failed: {e}")

                    # Run in background thread to avoid blocking response
                    thread = threading.Thread(target=log_to_chat_neo4j)
                    thread.daemon = True
                    thread.start()

            except Exception as e:
                # Logging failure shouldn't break the response
                pass

            # Add history to response
            response_data["history"] = store['history']

            return jsonify(response_data), 200
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500


@bp.post('/chat/graphrag/stream')
def api_chat_graphrag_stream():
    """
    GraphRAG with Server-Sent Events (SSE) streaming for live ReAct step updates.

    Critical: Uses POST + fetch() ReadableStream (not EventSource GET) to support
    long messages with attached Cypher queries that exceed GET param limits.

    SSE Message Format:
        data: {"type": "step", "step_num": 1, "action": "THINK", "content": "...", "observation": ""}
        data: {"type": "step", "step_num": 2, "action": "QUERY", "content": "MATCH...", "observation": "..."}
        data: {"type": "done", "reply": "...", "engine": "react", "metadata": {...}}
        data: {"type": "error", "error": "..."}

    Connection Limiting:
        Max 12 concurrent SSE connections to prevent worker pool exhaustion.
        Returns 429 Too Many Requests if limit exceeded.

    Intent Routing:
        - REACT: Stream each step as it happens
        - LOOKUP/SUMMARIZE/REASONING: Buffer and send all at once, then close stream
    """
    global _active_sse_connections

    # Check connection limit before processing
    with _sse_connection_lock:
        if _active_sse_connections >= MAX_SSE_CONNECTIONS:
            return jsonify({
                "status": "error",
                "error": "Too many active streaming connections. Please try again shortly.",
                "code": "SSE_CAPACITY_EXCEEDED"
            }), 429

        # Reserve slot
        _active_sse_connections += 1
        current_count = _active_sse_connections

    print(f"DEBUG: SSE connection opened. Active: {current_count}/{MAX_SSE_CONNECTIONS}")

    # GraphRAG enabled check
    enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
    if not enabled:
        with _sse_connection_lock:
            _active_sse_connections -= 1
        from ...services.graphrag_schema import normalize_error
        return jsonify(normalize_error(status="disabled", error="GraphRAG disabled", code="GR_DISABLED", hint="Set SCIDK_GRAPHRAG_ENABLED=1")), 501

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        with _sse_connection_lock:
            _active_sse_connections -= 1
        return jsonify({"status": "error", "error": "message required"}), 400

    # Capture app for thread context
    _app = current_app._get_current_object()

    def generate_stream():
        """SSE generator with connection cleanup."""
        global _active_sse_connections

        # Push app context for entire generator - needed for _get_chat_service() and chat_service methods
        with _app.app_context():
            try:
                # Get session context - chat_service needs app context
                session_id = data.get('session_id', 'default')
                print(f"DEBUG: Stream session_id: {session_id}")

                chat_service = _get_chat_service()
                conversation_context = chat_service.get_recent_turns(session_id, n=4)
                message_with_context = f"{conversation_context}\n{message}" if conversation_context else message

                # Get Neo4j connection
                try:
                    from ...services.neo4j_client import get_neo4j_params
                    uri, user, pwd, database, auth_mode = get_neo4j_params(_app)
                except Exception:
                    uri = user = pwd = database = auth_mode = None

                if not uri:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Neo4j not configured'})}\n\n"
                    return

                from neo4j import GraphDatabase
                auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
                driver = GraphDatabase.driver(uri, auth=auth)

                # Get schema and classify intent
                from ...services.graphrag_schema import parse_ttl, filter_schema
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

                # Classify intent using Concept Graph or fallback to hard-coded classifier
                from ...services.graphrag.intent_classifier import classify, Intent
                concept_driver = _get_ext().get('concept_driver')
                traversal_log = None

                try:
                    if concept_driver is not None:
                        # Use Concept Graph for intent classification and planning
                        from ...services.concept_graph_service import (
                            classify_intent, plan_execution, build_traversal_log,
                            ConceptGraphUnavailableError
                        )
                        from ...services.schema_intelligence import get_relevant_schema_context

                        # Get SQLite connection
                        chat_service_tmp = _get_chat_service()
                        sqlite_conn_tmp = chat_service_tmp._get_conn()

                        try:
                            ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')

                            # Get relevant schema context (for semantic retrieval)
                            schema_context = get_relevant_schema_context(
                                message_with_context, sqlite_conn_tmp, driver,
                                ollama_url, database=database or "neo4j"
                            )
                            relevant_labels = schema_context.get('labels', [])

                            # Classify intent using concept graph
                            # Use raw message (not context) for intent - context pollutes classification
                            intent_name, intent_confidence = classify_intent(
                                message, concept_driver, sqlite_conn_tmp, ollama_url
                            )
                            print(f"DEBUG STREAM concept_graph: intent_name={intent_name}, confidence={intent_confidence}")

                            # Plan execution
                            plan = plan_execution(intent_name, relevant_labels, concept_driver)
                            print(f"DEBUG STREAM concept_graph: plan={plan}")

                            # Build traversal log
                            traversal_log = build_traversal_log(
                                query=message,
                                intent_matched=intent_name,
                                intent_confidence=intent_confidence,
                                plan=plan,
                                labels_considered=list(schema_context.get('labels', []))
                            )

                            # Map concept intent to legacy Intent enum
                            intent = _map_concept_intent_to_legacy(intent_name)
                            print(f"DEBUG STREAM concept_graph: mapped to legacy intent={intent}, value={intent.value}")

                            # Log traversal to SQLite
                            sqlite_conn_tmp.execute(
                                "INSERT INTO usage_event (event_type, label_name, session_id, "
                                "source, traversal_json) VALUES (?, ?, ?, ?, ?)",
                                ('concept_graph_plan', '', data.get('session_id', 'default'),
                                 'chat', json.dumps(traversal_log))
                            )
                            sqlite_conn_tmp.commit()

                        finally:
                            sqlite_conn_tmp.close()

                    else:
                        # Fallback to hard-coded classifier
                        intent = classify(message_with_context)

                except Exception as e:
                    # Concept graph error — fall back to hard-coded classifier
                    import logging
                    logging.warning(f"Concept graph classification failed (streaming): {e}")
                    intent = classify(message_with_context)
                    traversal_log = None

                print(f"DEBUG: Stream intent: {intent.value}")

                # Route based on intent
                if intent == Intent.REACT:
                    # REACT path: Stream steps in real-time
                    from ...ai.react_loop import run_react_loop
                    from ...ai.schema_context import get_schema_context
                    from ...ai.provider_factory import LLMProviderFactory
                    from ...ai.chat_graph import retrieve_relevant_context, format_context_for_prompt
                    from ...services.chat_neo4j_client import get_chat_neo4j_client

                    try:
                        from ...services.schema_intelligence import get_relevant_schema_context
                        chat_service_tmp = _get_chat_service()
                        sqlite_conn_tmp = chat_service_tmp._get_conn()
                        try:
                            schema_context = get_relevant_schema_context(
                                user_query=message,
                                sqlite_conn=sqlite_conn_tmp,
                                neo4j_driver=driver,
                                ollama_url=os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                                database=database or "neo4j"
                            )
                        finally:
                            sqlite_conn_tmp.close()
                    except Exception as e:
                        import logging
                        logging.warning(f"Schema intelligence failed: {e}")
                        schema_context = get_schema_context(driver, database=database or "neo4j")

                    react_model = os.environ.get('SCIDK_REACT_MODEL', 'qwen2.5:72b')
                    settings = {
                        'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER', 'ollama'),
                        'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                        'chat_ollama_model': react_model,
                        'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                        'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                    }

                    provider_obj = LLMProviderFactory.from_settings(settings)
                    chat_driver = get_chat_neo4j_client()

                    # Retrieve context
                    retrieved_history = ""
                    if chat_driver:
                        try:
                            relevant_messages = retrieve_relevant_context(
                                current_query=message,
                                session_id=session_id,
                                chat_driver=chat_driver,
                                research_driver=driver,
                                embedding_model=os.environ.get('SCIDK_CHAT_EMBEDDING_MODEL', 'nomic-embed-text'),
                                top_k=int(os.environ.get('SCIDK_CHAT_CONTEXT_RETRIEVAL_TOP_K', 3))
                            )
                            retrieved_history = format_context_for_prompt(relevant_messages)
                        except Exception as e:
                            import logging
                            logging.warning(f"Context retrieval failed: {e}")

                    # Define step callback for streaming
                    def step_callback(step_dict):
                        """Stream step updates as SSE events."""
                        sse_data = {
                            "type": "step",
                            "step_num": step_dict["step_num"],
                            "action": step_dict["action_type"],
                            "content": step_dict["content"],
                            "observation": step_dict.get("observation", "")
                        }
                        # Must use nonlocal or return value - can't yield from nested function
                        # Instead, we'll collect steps and check them in the main loop
                        # For now, print for debugging
                        print(f"DEBUG: Step callback fired: {sse_data['action']} step {sse_data['step_num']}")

                    # We need to refactor this - can't yield from callback
                    # Solution: Use queues to communicate between callback and generator
                    import queue
                    step_queue = queue.Queue()
                    token_queue = queue.Queue()

                    def streaming_step_callback(step_dict):
                        step_queue.put(step_dict)

                    def token_callback(token, step_num):
                        """Called by provider.stream() - enqueue tokens for SSE transmission."""
                        token_queue.put({"type": "token", "token": token, "step": step_num})

                    # Run ReAct in separate thread so we can yield steps as they arrive
                    result_container = {}
                    def run_react_thread():
                        # Push app context for Flask operations - use captured app object
                        with _app.app_context():
                            result = run_react_loop(
                                user_query=message_with_context,
                                session_id=session_id,
                                provider=provider_obj,
                                research_driver=driver,
                                chat_driver=chat_driver,
                                schema_context=schema_context,
                                retrieved_history=retrieved_history,
                                max_steps=int(os.environ.get('SCIDK_CHAT_REACT_MAX_STEPS', 4)),
                                on_step_callback=streaming_step_callback,
                                on_token_callback=token_callback
                            )
                            result_container['result'] = result
                            step_queue.put(None)  # Sentinel to signal completion

                    react_thread = threading.Thread(target=run_react_thread)
                    react_thread.start()

                    # Stream loop - drain BOTH queues (tokens + steps)
                    import time as time_module
                    while True:
                        # Drain token queue first (non-blocking)
                        while not token_queue.empty():
                            try:
                                token_event = token_queue.get_nowait()
                                yield f"data: {json.dumps(token_event)}\n\n"
                            except queue.Empty:
                                break

                        # Then check for step events (blocking with timeout)
                        try:
                            step_dict = step_queue.get(timeout=0.05)  # 50ms poll

                            if step_dict is None:
                                # Thread completed - drain remaining tokens
                                while not token_queue.empty():
                                    try:
                                        token_event = token_queue.get_nowait()
                                        yield f"data: {json.dumps(token_event)}\n\n"
                                    except queue.Empty:
                                        break
                                break

                            # After receiving step, pause briefly and drain remaining tokens for this step
                            time_module.sleep(0.05)  # let token_queue drain
                            while not token_queue.empty():
                                try:
                                    token_event = token_queue.get_nowait()
                                    yield f"data: {json.dumps(token_event)}\n\n"
                                except queue.Empty:
                                    break

                            # Now yield the step event
                            sse_data = {
                                "type": "step",
                                "step_num": step_dict["step_num"],
                                "action": step_dict["action_type"],
                                "content": step_dict["content"],
                                "observation": step_dict.get("observation", "")
                            }
                            yield f"data: {json.dumps(sse_data)}\n\n"

                        except queue.Empty:
                            # No step yet - continue draining tokens
                            continue

                    react_thread.join()
                    result = result_container.get('result', {})

                    if result.get('status') == 'error':
                        yield f"data: {json.dumps({'type': 'error', 'error': result.get('reply', 'Unknown error')})}\n\n"
                        return

                    # Send completion
                    done_data = {
                        "type": "done",
                        "reply": result.get('reply', ''),
                        "engine": result.get('engine', 'react'),
                        "metadata": result.get('metadata', {}),
                        "traversal_log": traversal_log
                    }
                    yield f"data: {json.dumps(done_data)}\n\n"

                    # Save to SQLite
                    try:
                        existing_session = chat_service.get_session(session_id)
                        if not existing_session:
                            conn = chat_service._get_conn()
                            try:
                                import time as time_module
                                now = time_module.time()
                                conn.execute(
                                    "INSERT OR IGNORE INTO chat_sessions (id, name, created_at, updated_at, message_count, metadata) VALUES (?, ?, ?, ?, 0, NULL)",
                                    (session_id, f"Chat {session_id[:8]}", now, now)
                                )
                                conn.commit()
                            finally:
                                conn.close()

                        chat_service.add_message(session_id, "user", message)
                        chat_service.add_message(session_id, "assistant", result.get('reply', ''))
                    except Exception as e:
                        print(f"DEBUG: Failed to save messages: {e}")

                elif intent == Intent.LOOKUP:
                    # LOOKUP path: Generate Cypher, execute, synthesize answer with streaming
                    from ...ai.cypher_utils import build_cypher_system_prompt, extract_cypher
                    from ...ai.provider_factory import LLMProviderFactory
                    from ...ai.schema_context import get_schema_context

                    settings = {
                        'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                        'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                        'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                        'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                        'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                    }

                    provider_obj = LLMProviderFactory.from_settings(settings)
                    start_time = time.time()

                    # Generate Cypher query
                    cypher_prompt = build_cypher_system_prompt(neo4j_schema)
                    cypher_response = provider_obj.complete(
                        user_message=message_with_context,
                        system_prompt=cypher_prompt,
                        schema_context=None
                    )
                    cypher_query = extract_cypher(cypher_response)

                    if cypher_query is None:
                        # Fallback to reasoning if no valid Cypher
                        try:
                            from ...services.schema_intelligence import get_relevant_schema_context
                            chat_service_tmp = _get_chat_service()
                            sqlite_conn_tmp = chat_service_tmp._get_conn()
                            try:
                                schema_context = get_relevant_schema_context(
                                    user_query=message_with_context,
                                    sqlite_conn=sqlite_conn_tmp,
                                    neo4j_driver=driver,
                                    ollama_url=os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                                    database=database or "neo4j"
                                )
                            finally:
                                sqlite_conn_tmp.close()
                        except Exception as e:
                            import logging
                            logging.warning(f"Schema intelligence failed: {e}")
                            schema_context = get_schema_context(driver, database=database or "neo4j")
                        base_prompt = "You are a research data assistant for SciDK."

                        final_answer = ''
                        for token in provider_obj.stream(
                            user_message=message_with_context,
                            system_prompt=base_prompt,
                            schema_context=schema_context
                        ):
                            final_answer += token
                            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                        elapsed_ms = int((time.time() - start_time) * 1000)
                        yield f"data: {json.dumps({'type': 'done', 'reply': final_answer, 'engine': 'reasoning_fallback', 'metadata': {'execution_time_ms': elapsed_ms, 'note': 'Could not generate valid Cypher'}, 'traversal_log': traversal_log})}\n\n"
                    else:
                        # Execute Cypher query
                        try:
                            with driver.session(database=database) if database else driver.session() as session:
                                result = session.run(cypher_query)
                                records = [record.data() for record in result]
                                result_count = len(records)
                        except Exception as query_error:
                            elapsed_ms = int((time.time() - start_time) * 1000)
                            yield f"data: {json.dumps({'type': 'error', 'error': f'Query execution failed: {str(query_error)}', 'cypher_query': cypher_query, 'metadata': {'execution_time_ms': elapsed_ms}})}\n\n"
                            return

                        # Synthesize answer with streaming
                        synthesis_prompt = f"""You are a research data assistant. A user asked a question and we ran a database query.

Context and Question:
{message_with_context}

Query Results: {records[:10]}
Result Count: {result_count}

Provide a clear, concise natural language answer based on these results."""

                        final_answer = ''
                        for token in provider_obj.stream(
                            user_message="Synthesize the answer from the query results above.",
                            system_prompt=synthesis_prompt,
                            schema_context=None
                        ):
                            final_answer += token
                            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                        elapsed_ms = int((time.time() - start_time) * 1000)
                        result_metadata = {
                            'cypher_query': cypher_query,
                            'result_count': result_count,
                            'execution_time_ms': elapsed_ms
                        }
                        yield f"data: {json.dumps({'type': 'done', 'reply': final_answer, 'engine': 'lookup', 'metadata': result_metadata, 'traversal_log': traversal_log})}\n\n"

                        # Save messages
                        chat_service.add_message(session_id, "user", message)
                        chat_service.add_message(session_id, "assistant", final_answer)

                elif intent == Intent.SUMMARIZE:
                    # SUMMARIZE path: Generate summary with streaming
                    from ...ai.summarization import generate_summary
                    from ...ai.provider_factory import LLMProviderFactory

                    settings = {
                        'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                        'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                        'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                        'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                        'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                    }

                    provider_obj = LLMProviderFactory.from_settings(settings)

                    # Note: generate_summary currently returns complete result, not streaming
                    # For now, get result and stream it out token by token
                    # TODO: Refactor generate_summary to support streaming internally
                    result = generate_summary(driver, database or "neo4j", provider_obj, neo4j_schema)

                    if result.get('status') == 'error':
                        yield f"data: {json.dumps({'type': 'error', 'error': result.get('error', 'Unknown error')})}\n\n"
                    else:
                        # Stream the summary text token by token (simulate streaming for now)
                        summary_text = result.get('reply', '')
                        # Split into words for pseudo-streaming
                        import time as time_module
                        words = summary_text.split()
                        streamed_text = ''
                        for i, word in enumerate(words):
                            token = word if i == 0 else f" {word}"
                            streamed_text += token
                            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                            time_module.sleep(0.01)  # Small delay to simulate streaming

                        yield f"data: {json.dumps({'type': 'done', 'reply': streamed_text, 'engine': 'summarize', 'metadata': result.get('metadata', {}), 'traversal_log': traversal_log})}\n\n"

                        # Save messages
                        chat_service.add_message(session_id, "user", message)
                        chat_service.add_message(session_id, "assistant", streamed_text)

                else:
                    # REASONING path: Default streaming response with schema grounding
                    from ...ai.schema_context import get_schema_context
                    from ...ai.provider_factory import LLMProviderFactory

                    try:
                        from ...services.schema_intelligence import get_relevant_schema_context
                        chat_service_tmp = _get_chat_service()
                        sqlite_conn_tmp = chat_service_tmp._get_conn()
                        try:
                            schema_context = get_relevant_schema_context(
                                user_query=message_with_context,
                                sqlite_conn=sqlite_conn_tmp,
                                neo4j_driver=driver,
                                ollama_url=os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                                database=database or "neo4j"
                            )
                        finally:
                            sqlite_conn_tmp.close()
                    except Exception as e:
                        import logging
                        logging.warning(f"Schema intelligence failed: {e}")
                        schema_context = get_schema_context(driver, database=database or "neo4j")

                    settings = {
                        'chat_llm_provider': data.get('provider') or os.environ.get('SCIDK_CHAT_LLM_PROVIDER'),
                        'chat_ollama_endpoint': os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT'),
                        'chat_ollama_model': os.environ.get('SCIDK_CHAT_OLLAMA_MODEL'),
                        'chat_claude_api_key': os.environ.get('SCIDK_CHAT_CLAUDE_API_KEY'),
                        'chat_openai_api_key': os.environ.get('SCIDK_CHAT_OPENAI_API_KEY'),
                    }

                    provider = LLMProviderFactory.from_settings(settings)
                    base_prompt = "You are a research data assistant for SciDK."

                    start_time = time.time()
                    final_answer = ''
                    for token in provider.stream(
                        user_message=message_with_context,
                        system_prompt=base_prompt,
                        schema_context=schema_context
                    ):
                        final_answer += token
                        yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                    elapsed_ms = int((time.time() - start_time) * 1000)
                    provider_info = provider.health_check()
                    yield f"data: {json.dumps({'type': 'done', 'reply': final_answer, 'metadata': {'provider': provider_info.get('provider'), 'model': provider_info.get('model'), 'execution_time_ms': elapsed_ms}, 'engine': 'reasoning', 'traversal_log': traversal_log})}\n\n"

                    # Save messages
                    chat_service.add_message(session_id, "user", message)
                    chat_service.add_message(session_id, "assistant", final_answer)

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            finally:
                # Always release connection slot
                with _sse_connection_lock:
                    _active_sse_connections -= 1
                    remaining = _active_sse_connections
                print(f"DEBUG: SSE connection closed. Active: {remaining}/{MAX_SSE_CONNECTIONS}")

    return Response(
        generate_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'X-Stream-Capacity': f'{_active_sse_connections}/{MAX_SSE_CONNECTIONS}'
        }
    )


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
            uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)
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
        try:
            from ...services.schema_intelligence import get_relevant_schema_context
            chat_service_tmp = _get_chat_service()
            sqlite_conn_tmp = chat_service_tmp._get_conn()
            try:
                schema_context = get_relevant_schema_context(
                    user_query=message,
                    sqlite_conn=sqlite_conn_tmp,
                    neo4j_driver=driver,
                    ollama_url=os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                    database=database or "neo4j"
                )
            finally:
                sqlite_conn_tmp.close()
        except Exception as e:
            logger.warning(f"Schema intelligence failed: {e}")
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
            data: {"type": "token", "token": "..."}
            data: {"type": "done", "reply": "...", "metadata": {...}}
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
            try:
                from ...services.schema_intelligence import get_relevant_schema_context
                from ...services.chat_service import get_chat_service
                import os as os_mod
                db_path = os_mod.environ.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
                chat_service_tmp = get_chat_service(db_path=db_path)
                sqlite_conn_tmp = chat_service_tmp._get_conn()
                try:
                    schema_context = get_relevant_schema_context(
                        user_query=message,
                        sqlite_conn=sqlite_conn_tmp,
                        neo4j_driver=driver,
                        ollama_url=os_mod.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434'),
                        database=database or "neo4j"
                    )
                finally:
                    sqlite_conn_tmp.close()
            except Exception as e:
                import logging
                logging.warning(f"Schema intelligence failed: {e}")
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
            final_answer = ''
            for token in provider.stream(
                user_message=message,
                system_prompt=base_prompt,
                schema_context=schema_context
            ):
                final_answer += token
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Send completion metadata with engine field for UI badge
            provider_info = provider.health_check()
            yield f"data: {json.dumps({'type': 'done', 'reply': final_answer, 'metadata': {'provider': provider_info.get('provider'), 'model': provider_info.get('model'), 'execution_time_ms': elapsed_ms, 'engine': 'reasoning'}, 'traversal_log': None})}\n\n"

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


# ============================================================================
# Schema Intelligence Layer API (Phases 1-3 + 6)
# ============================================================================

@bp.post('/chat/schema/refresh-embeddings')
def api_chat_schema_refresh_embeddings():
    """
    Refresh schema embeddings (Phase 6).

    Re-embeds all labels and relationship types from live Neo4j schema.
    Called manually from Settings, or automatically after imports/description edits.

    Returns:
        200: {embedded: int, failed: int}
        500: {status: error, error: str}
    """
    enabled = (os.environ.get('SCIDK_GRAPHRAG_ENABLED') or '').strip().lower() in ('1','true','yes','on','y')
    if not enabled:
        return jsonify({
            "status": "disabled",
            "error": "GraphRAG disabled",
            "hint": "Set SCIDK_GRAPHRAG_ENABLED=1"
        }), 501

    try:
        from ...services.neo4j_client import get_neo4j_params
        from neo4j import GraphDatabase
        uri, user, pwd, database, auth_mode = get_neo4j_params(current_app)

        if not uri:
            return jsonify({
                "status": "error",
                "error": "Neo4j not configured"
            }), 500

        auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
        driver = GraphDatabase.driver(uri, auth=auth)

        # Get SQLite connection
        chat_service = _get_chat_service()
        sqlite_conn = chat_service._get_conn()

        try:
            from ...services.schema_intelligence import refresh_schema_embeddings
            ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
            result = refresh_schema_embeddings(
                neo4j_driver=driver,
                sqlite_conn=sqlite_conn,
                ollama_url=ollama_url,
                database=database or "neo4j"
            )
            return jsonify(result), 200
        finally:
            sqlite_conn.close()
            driver.close()

    except Exception as e:
        logger.error(f"Schema embedding refresh failed: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@bp.get('/chat/schema/status')
def api_chat_schema_status():
    """
    Get schema intelligence layer status.

    Returns statistics about:
    - Embedded labels/relationships
    - Last embedding update timestamp
    - Property ranking coverage
    - Usage event counts

    Returns:
        200: {labels_embedded, relationships_embedded, last_embedding_update, ...}
    """
    try:
        chat_service = _get_chat_service()
        sqlite_conn = chat_service._get_conn()

        try:
            cursor = sqlite_conn.cursor()

            label_count = cursor.execute(
                "SELECT COUNT(*) FROM label_profile WHERE embedding IS NOT NULL"
            ).fetchone()[0]

            rel_count = cursor.execute(
                "SELECT COUNT(*) FROM relationship_profile WHERE embedding IS NOT NULL"
            ).fetchone()[0]

            last_updated = cursor.execute(
                "SELECT MAX(embedded_at) FROM label_profile WHERE embedding IS NOT NULL"
            ).fetchone()[0]

            ranking_count = cursor.execute(
                "SELECT COUNT(DISTINCT label_name) FROM property_ranking"
            ).fetchone()[0]

            event_count = cursor.execute(
                "SELECT COUNT(*) FROM usage_event"
            ).fetchone()[0]

            return jsonify({
                'labels_embedded': label_count,
                'relationships_embedded': rel_count,
                'last_embedding_update': last_updated,
                'labels_with_rankings': ranking_count,
                'total_usage_events': event_count
            }), 200
        finally:
            sqlite_conn.close()

    except Exception as e:
        logger.error(f"Schema status check failed: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@bp.get('/chat/schema/label/<label_name>')
def api_chat_schema_label(label_name):
    """
    Get intelligence profile for a specific label.

    Returns:
        200: {
            description, chat_context_mode, chat_context_n,
            always_include, never_include,
            embedding_status: 'embedded' | 'pending' | 'none',
            property_rankings: [{property, query_count, rank}, ...]
        }
    """
    try:
        chat_service = _get_chat_service()
        sqlite_conn = chat_service._get_conn()

        try:
            from ...services.schema_intelligence import get_label_profile
            profile = get_label_profile(label_name, sqlite_conn)

            # Check embedding status
            cursor = sqlite_conn.cursor()
            row = cursor.execute(
                "SELECT embedding, embedded_at FROM label_profile WHERE label_name = ?",
                (label_name,)
            ).fetchone()

            embedding_status = 'none'
            if row and row[0]:
                embedding_status = 'embedded'
            elif row:
                embedding_status = 'pending'

            # Get property rankings
            rankings = cursor.execute(
                "SELECT property_name, query_count, rank "
                "FROM property_ranking WHERE label_name = ? "
                "ORDER BY rank DESC",
                (label_name,)
            ).fetchall()

            property_rankings = [
                {'property': r[0], 'query_count': r[1], 'rank': r[2]}
                for r in rankings
            ]

            return jsonify({
                **profile,
                'embedding_status': embedding_status,
                'property_rankings': property_rankings
            }), 200
        finally:
            sqlite_conn.close()

    except Exception as e:
        logger.error(f"Failed to get label profile for {label_name}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@bp.put('/chat/schema/label/<label_name>')
def api_chat_schema_label_update(label_name):
    """
    Update intelligence profile for a label.

    Request body:
    {
        description: str (optional),
        chat_context_mode: 'top_n' | 'all' | 'exclude',
        chat_context_n: int,
        always_include: [str, ...],
        never_include: [str, ...]
    }

    Side effect: Re-embeds label if description changed.

    Returns:
        200: {success: true}
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        chat_service = _get_chat_service()
        sqlite_conn = chat_service._get_conn()

        try:
            from ...services.schema_intelligence import get_label_profile, embed_text
            cursor = sqlite_conn.cursor()

            # Get existing profile to check if description changed
            old_profile = get_label_profile(label_name, sqlite_conn)
            description = data.get('description', old_profile.get('description'))
            description_changed = description != old_profile.get('description')

            # Update or insert profile
            cursor.execute("""
                INSERT INTO label_profile
                (label_name, description, chat_context_mode, chat_context_n, always_include, never_include)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(label_name) DO UPDATE SET
                    description = excluded.description,
                    chat_context_mode = excluded.chat_context_mode,
                    chat_context_n = excluded.chat_context_n,
                    always_include = excluded.always_include,
                    never_include = excluded.never_include
            """, (
                label_name,
                description,
                data.get('chat_context_mode', old_profile.get('chat_context_mode', 'top_n')),
                data.get('chat_context_n', old_profile.get('chat_context_n', 5)),
                json.dumps(data.get('always_include', old_profile.get('always_include', []))),
                json.dumps(data.get('never_include', old_profile.get('never_include', [])))
            ))
            sqlite_conn.commit()

            # Re-embed if description changed
            if description_changed and description:
                ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
                embedding = embed_text(description, ollama_url)
                if embedding:
                    from ...services.schema_intelligence import _vector_to_blob
                    cursor.execute("""
                        UPDATE label_profile
                        SET embedding = ?, embedded_at = ?
                        WHERE label_name = ?
                    """, (_vector_to_blob(embedding), datetime.utcnow(), label_name))
                    sqlite_conn.commit()

            return jsonify({'success': True}), 200
        finally:
            sqlite_conn.close()

    except Exception as e:
        logger.error(f"Failed to update label profile for {label_name}: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@bp.get('/chat/schema/export')
def api_chat_schema_export():
    """
    Export schema intelligence layer as JSON.

    Returns:
        200: JSON download with label profiles and property rankings
    """
    try:
        chat_service = _get_chat_service()
        sqlite_conn = chat_service._get_conn()

        try:
            from ...services.schema_intelligence import export_schema_layer
            layer = export_schema_layer(sqlite_conn)

            response = jsonify(layer)
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            response.headers['Content-Disposition'] = f'attachment; filename=scidk_schema_layer_{timestamp}.json'
            return response, 200
        finally:
            sqlite_conn.close()

    except Exception as e:
        logger.error(f"Schema export failed: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@bp.post('/chat/schema/import')
def api_chat_schema_import():
    """
    Import schema intelligence layer from JSON.

    Request body: {layer JSON}

    Returns:
        200: {
            imported_labels: int,
            updated_labels: int,
            skipped: int,
            embeddings_triggered: int
        }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        chat_service = _get_chat_service()
        sqlite_conn = chat_service._get_conn()

        try:
            from ...services.schema_intelligence import import_schema_layer
            result = import_schema_layer(data, sqlite_conn)
            return jsonify(result), 200
        finally:
            sqlite_conn.close()

    except Exception as e:
        logger.error(f"Schema import failed: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


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


@bp.post('/chat/concept-graph/feedback')
def api_concept_graph_feedback():
    """
    Receive feedback on concept graph classification outcomes.

    Called by frontend after query completion (fire-and-forget).
    Updates SATISFIES edge weights in concept graph based on success/failure.

    Request body:
        {
            "intent": "data_lookup",
            "tool": "run_safe_cypher",
            "success": true,
            "session_id": "abc123"
        }

    Returns:
        200: {"status": "ok"}
        400: {"status": "error", "error": "..."}
        501: {"status": "disabled", "error": "Concept graph not available"}
    """
    data = request.get_json(force=True, silent=True) or {}

    intent_name = data.get('intent')
    tool_name = data.get('tool')
    success = data.get('success')

    if not intent_name or not tool_name or success is None:
        return jsonify({
            "status": "error",
            "error": "Missing required fields: intent, tool, success"
        }), 400

    # Get concept driver
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "error": "Concept graph not available"
        }), 501

    # Update weights
    from ...services.concept_graph_service import update_traversal_weights
    result = update_traversal_weights(intent_name, tool_name, bool(success), concept_driver)

    if result:
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({
            "status": "error",
            "error": "Failed to update weights"
        }), 500


# ========== Concept Graph Editor Endpoints ==========


@bp.get('/chat/concept-graph/intents')
def api_concept_graph_intents():
    """Get all intents with their top tool + edge weights."""
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "error": "Concept graph not available"
        }), 501

    try:
        with concept_driver.session() as session:
            result = session.run("""
                MATCH (i:Concept_Intent)-[r:SATISFIES]->(t:Concept_Tool)
                WITH i, t, r
                ORDER BY r.weight DESC
                WITH i, COLLECT({tool: t.name, weight: r.weight, usage_count: r.usage_count})[0] AS top_tool,
                     i.description AS description,
                     i.examples AS examples
                RETURN i.name AS name,
                       description,
                       examples,
                       top_tool.tool AS top_tool,
                       top_tool.weight AS weight,
                       top_tool.usage_count AS usage_count
                ORDER BY i.name
            """).data()

            return jsonify({"status": "ok", "intents": result}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.put('/chat/concept-graph/intent/<intent_name>')
def api_concept_graph_intent_update(intent_name):
    """Update intent description/examples + re-embed."""
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "error": "Concept graph not available"
        }), 501

    data = request.get_json(force=True, silent=True) or {}
    description = data.get('description', '').strip()
    examples = data.get('examples', [])

    if not description:
        return jsonify({"status": "error", "error": "description required"}), 400
    if not isinstance(examples, list):
        return jsonify({"status": "error", "error": "examples must be a list"}), 400

    try:
        # Update intent node
        with concept_driver.session() as session:
            session.run("""
                MATCH (i:Concept_Intent {name: $name})
                SET i.description = $description,
                    i.examples = $examples
            """, name=intent_name, description=description, examples=examples)

        # Re-embed this intent
        ollama_endpoint = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
        from ...services.concept_graph_service import _embed_text
        import json

        # Build embedding text from description + examples
        embed_text = f"{description}\n" + "\n".join(examples)
        embedding = _embed_text(embed_text, ollama_endpoint)

        if embedding:
            with concept_driver.session() as session:
                session.run("""
                    MATCH (i:Concept_Intent {name: $name})
                    SET i.embedding = $embedding
                """, name=intent_name, embedding=embedding)

        return jsonify({"status": "ok", "re_embedded": embedding is not None}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.get('/chat/concept-graph/tools')
def api_concept_graph_tools():
    """Get all tools with active status + retrieves labels."""
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "error": "Concept graph not available"
        }), 501

    try:
        with concept_driver.session() as session:
            result = session.run("""
                MATCH (t:Concept_Tool)
                OPTIONAL MATCH (t)-[:RETRIEVES]->(l:Concept_Label)
                WITH t, COLLECT(l.name) AS retrieves
                RETURN t.name AS name,
                       t.description AS description,
                       COALESCE(t.active, true) AS active,
                       t.source AS source,
                       retrieves
                ORDER BY t.name
            """).data()

            return jsonify({"status": "ok", "tools": result}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.post('/chat/concept-graph/tool/<tool_name>/toggle')
def api_concept_graph_tool_toggle(tool_name):
    """Toggle tool active/inactive."""
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "error": "Concept graph not available"
        }), 501

    try:
        with concept_driver.session() as session:
            result = session.run("""
                MATCH (t:Concept_Tool {name: $name})
                SET t.active = NOT COALESCE(t.active, true)
                RETURN t.active AS active
            """, name=tool_name).single()

            if result is None:
                return jsonify({"status": "error", "error": "Tool not found"}), 404

            return jsonify({"status": "ok", "name": tool_name, "active": result["active"]}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.get('/chat/concept-graph/status')
def api_concept_graph_status():
    """Get concept graph status."""
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "connected": False,
            "intents": 0,
            "tools": 0,
            "satisfies_edges": 0
        }), 501

    try:
        with concept_driver.session() as session:
            stats = session.run("""
                MATCH (i:Concept_Intent)
                WITH COUNT(i) AS intents
                MATCH (t:Concept_Tool)
                WITH intents, COUNT(t) AS tools
                MATCH ()-[r:SATISFIES]->()
                RETURN intents, tools, COUNT(r) AS satisfies_edges
            """).single()

            # Get last_seeded from a timestamp property if it exists
            # For now, return None (could be added to concept graph metadata)
            return jsonify({
                "status": "ok",
                "connected": True,
                "intents": stats["intents"],
                "tools": stats["tools"],
                "satisfies_edges": stats["satisfies_edges"],
                "last_seeded": None  # TODO: track seeding timestamp
            }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "connected": False,
            "error": str(e)
        }), 500


@bp.post('/chat/concept-graph/reseed')
def api_concept_graph_reseed():
    """Re-seed full concept graph."""
    concept_driver = _get_ext().get('concept_driver')
    if concept_driver is None:
        return jsonify({
            "status": "disabled",
            "error": "Concept graph not available"
        }), 501

    try:
        from ...services.concept_graph_service import seed_intents_from_yaml, seed_tools_from_yaml, sync_labels_from_research_graph

        ollama_endpoint = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
        intents_file = Path(__file__).parent.parent.parent / 'concept_graph' / 'intents.yaml'

        # Seed intents
        intent_result = seed_intents_from_yaml(concept_driver, str(intents_file), ollama_endpoint)

        # Seed tools
        tool_result = seed_tools_from_yaml(concept_driver, str(intents_file))

        # Sync labels
        research_driver = _get_ext().get('driver')
        if research_driver:
            label_result = sync_labels_from_research_graph(concept_driver, research_driver)
        else:
            label_result = {"synced": 0}

        return jsonify({
            "status": "ok",
            "intents_seeded": intent_result.get('embedded', 0),
            "tools_seeded": tool_result.get('seeded', 0),
            "labels_synced": label_result.get('synced', 0)
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
