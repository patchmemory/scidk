"""
ReAct Loop - Reasoning and Acting for multi-step chat queries.

Implements a bounded ReAct (Reason + Act) loop that allows the chat agent to:
1. THINK: Reason about what information is needed
2. ACT: Execute a safe read-only Cypher query OR produce final answer
3. OBSERVE: Review results and decide next step

Safety is enforced via:
- Cypher inspection: Block WRITE/CREATE/MERGE/DELETE keywords
- Endpoint whitelist: Only safe read-only endpoints allowed
- Bounded steps: Max 4 steps to prevent infinite loops
- Token budget: ~3000 tokens per step
"""
from typing import Dict, Any, List, Optional
import time
import logging
import re

logger = logging.getLogger(__name__)


def build_react_system_prompt(schema_context: Dict[str, Any], retrieved_history: str) -> str:
    """
    Build system prompt for ReAct loop steps.

    Key design decisions:
    - Explicit output format (THINK/QUERY/FINAL ANSWER) to enable parsing
    - Safety rules: only use schema, don't invent data, stop after 4 steps
    - Full schema injection (no truncation) to prevent hallucination
    - Schema and history injected once (step 1 only) to save tokens
    - Clear termination criteria to avoid infinite loops

    Args:
        schema_context: Neo4j schema dict with labels, relationships, properties
        retrieved_history: Formatted context from past relevant messages

    Returns:
        Complete system prompt for ReAct step
    """
    # No truncation - inject full schema to prevent hallucination
    labels_str = ", ".join(schema_context.get("labels", []))
    rels_str = ", ".join(schema_context.get("relationships", []))

    # Format properties (show all labels, top 5 props each)
    props_lines = []
    properties = schema_context.get("properties", {})
    for label in schema_context.get("labels", []):
        props = properties.get(label, [])
        if props:
            props_lines.append(f"  - {label}: {', '.join(props[:5])}")

    props_str = "\n".join(props_lines) if props_lines else "  (No property info available)"

    # Build history section (empty if no relevant context)
    history_section = ""
    if retrieved_history and retrieved_history.strip():
        history_section = f"""
RELEVANT PAST CONTEXT:
{retrieved_history}

Use this context to:
- Avoid repeating queries you've already run
- Check if data has changed (staleness warnings)
- Build on previous findings
---
"""

    prompt = f"""You are a research data assistant with access to a Neo4j knowledge graph.
You reason step-by-step to answer research questions accurately.

At each step you must output EXACTLY ONE of:
    THINK: [your reasoning about what to do next]
    QUERY: [a single executable Cypher query, no explanation]
    FINAL ANSWER: [your complete answer to the researcher]

RULES (enforce strictly):
1. Only use node labels, relationship types, and properties from the schema below
2. Never invent or guess labels/properties - if schema doesn't have it, say so
3. Do NOT repeat a query you already ran in this session
4. After you output QUERY, the system executes it and returns an OBSERVATION. Wait for it before your next step.
5. Never fabricate an OBSERVATION — only reason from results the system actually returns.
6. If a QUERY returns an error, output THINK with your diagnosis of what went wrong before trying again. Do not repeat the identical query.
7. After 4 steps, you MUST produce FINAL ANSWER regardless
8. If you cannot answer confidently, say so in FINAL ANSWER
9. Use LIMIT clauses (default 50) unless user wants all results
10. For count questions, use COUNT() and return a single number
11. ⚠️  CRITICAL: You MUST execute queries to get data. NEVER answer from memory or make up folder/file names.

CORRECT BEHAVIOR (follow this pattern):
User: "Find CAC folders in Dropbox and SharePoint"

THINK: I need to query for Folder nodes filtered by host_id and name. I'll check Dropbox first.

QUERY: MATCH (f:Folder) WHERE f.host_id CONTAINS 'dropbox' AND f.name CONTAINS 'CAC' RETURN f.name, f.path LIMIT 20

OBSERVATION: 2 rows returned: [{{"name": "CAC_Archive", "path": "/data/CAC_Archive"}}, {{"name": "CAC_Reports_2024", "path": "/shared/CAC_Reports_2024"}}]

THINK: Found 2 Dropbox folders. Now checking SharePoint.

QUERY: MATCH (f:Folder) WHERE f.host_id CONTAINS 'sharepoint' AND f.name CONTAINS 'CAC' RETURN f.name, f.path LIMIT 20

OBSERVATION: No results returned

FINAL ANSWER: I found 2 CAC-related folders in Dropbox: "CAC_Archive" and "CAC_Reports_2024". No CAC folders were found in SharePoint.

INCORRECT BEHAVIOR (NEVER do this):
User: "Find CAC folders in Dropbox and SharePoint"

FINAL ANSWER: I found "CAC Documents", "Customer Account Center", and "CAC Data" folders across your services.
⚠️  WRONG: These folder names were invented without running queries!

AVAILABLE SCHEMA:
Node Labels: {labels_str}
Relationship Types: {rels_str}
Key Properties by Label:
{props_str}

{history_section}

REMEMBER: Output only THINK, QUERY, or FINAL ANSWER - nothing else. ALWAYS query before answering."""

    return prompt


def extract_action(response: str) -> tuple[str, str]:
    """
    Parse LLM response to extract action type and content.

    Args:
        response: Raw LLM response text

    Returns:
        (action_type, content) where action_type is "THINK", "QUERY", or "FINAL_ANSWER"
    """
    response = response.strip()

    # Check for explicit markers (prefer these)
    if response.startswith("THINK:"):
        # Check if there's an embedded QUERY: later in the response
        # Pattern: "THINK: reasoning...\n\nQUERY: MATCH..."
        # Prioritize the QUERY action over the THINK reasoning
        query_match = re.search(r'\n\s*QUERY:\s*(.+)', response, re.DOTALL | re.IGNORECASE)
        if query_match:
            # Extract the query portion (everything after "QUERY:")
            query_content = query_match.group(1).strip()
            # Strip markdown fences if present (both opening and closing)
            query_content = re.sub(r'^```(?:cypher)?\s*\n', '', query_content, flags=re.IGNORECASE)
            query_content = re.sub(r'\n```\s*$', '', query_content)  # Allow trailing whitespace
            query_content = re.sub(r'\n```\n', '\n', query_content)  # Remove fences in middle
            # Also strip any trailing THINK/FINAL ANSWER markers
            query_content = re.split(r'\n\s*(?:THINK|FINAL ANSWER):', query_content)[0].strip()

            # Strip trailing markdown fences and any text after them
            if '```' in query_content:
                query_content = query_content.split('```')[0].strip()
            # Also strip any remaining fence lines
            query_content = '\n'.join(
                line for line in query_content.splitlines()
                if not line.strip().startswith('```')
            ).strip()

            return ("QUERY", query_content)

        # No embedded QUERY, just return the THINK content
        content = response[6:].strip()
        return ("THINK", content)

    if response.startswith("QUERY:"):
        content = response[6:].strip()
        # Strip markdown fences if present (both opening and closing)
        content = re.sub(r'^```(?:cypher)?\s*\n', '', content, flags=re.IGNORECASE)
        content = re.sub(r'\n```\s*$', '', content)  # Allow trailing whitespace
        content = re.sub(r'\n```\n', '\n', content)  # Remove fences in middle

        # Strip trailing markdown fences and any text after them
        if '```' in content:
            content = content.split('```')[0].strip()
        # Also strip any remaining fence lines
        content = '\n'.join(
            line for line in content.splitlines()
            if not line.strip().startswith('```')
        ).strip()

        return ("QUERY", content)

    if response.startswith("FINAL ANSWER:"):
        content = response[13:].strip()
        return ("FINAL_ANSWER", content)

    # Detect degenerate case: LLM output just "THINK" or "QUERY" without colon
    # This causes infinite loops - treat as malformed and force termination
    if response.upper() in ["THINK", "QUERY", "FINAL ANSWER"]:
        logger.warning(f"LLM output malformed action without content: '{response}'. Forcing termination.")
        return ("FINAL_ANSWER", "I encountered an error in my reasoning process and cannot complete this query.")

    # Fallback: detect based on content
    # If starts with Cypher keywords, assume QUERY
    upper = response[:100].upper()
    if any(kw in upper for kw in ["MATCH", "RETURN", "WITH", "WHERE"]):
        return ("QUERY", response)

    # Otherwise assume THINK (reasoning)
    return ("THINK", response)


def is_safe_cypher(query: str) -> tuple[bool, Optional[str]]:
    """
    Check if Cypher query is safe (read-only).

    Blocks queries containing write operations:
    - CREATE, MERGE, DELETE, REMOVE, SET
    - CALL procedures that modify data

    Args:
        query: Cypher query string

    Returns:
        (is_safe, error_message) - error_message is None if safe
    """
    query_upper = query.upper()

    # Blocked keywords (write operations)
    dangerous_keywords = [
        "CREATE ",
        "MERGE ",
        "DELETE ",
        "REMOVE ",
        "SET ",
        "DETACH DELETE",
        "DROP ",
        "CALL APOC.REFACTOR",
        "CALL APOC.CREATE",
    ]

    for keyword in dangerous_keywords:
        if keyword in query_upper:
            return (False, f"Blocked: Query contains write operation '{keyword.strip()}'")

    return (True, None)


def format_step_history(steps: List[Dict[str, Any]]) -> str:
    """
    Format completed steps into compact history for next step's prompt.

    Each step: THINK → QUERY → OBSERVE (3 lines max per step)

    Args:
        steps: List of step dicts with keys: step_num, action_type, content, observation

    Returns:
        Formatted step history string (target: 150 tokens per step = ~600 chars)
    """
    if not steps:
        return ""

    lines = []
    for step in steps:
        step_num = step.get("step_num", 0)
        action_type = step.get("action_type", "UNKNOWN")
        content = step.get("content", "")
        observation = step.get("observation", "")

        # Truncate content to 200 chars
        if len(content) > 200:
            content = content[:197] + "..."

        # Build 3-line summary
        if action_type == "THINK":
            lines.append(f"Step {step_num} — Think: {content}")
        elif action_type == "QUERY":
            lines.append(f"Step {step_num} — Query: {content}")
            # Add observation (truncate to 150 chars)
            obs_truncated = observation[:147] + "..." if len(observation) > 150 else observation
            lines.append(f"Step {step_num} — Observe: {obs_truncated}")
        elif action_type == "FINAL_ANSWER":
            lines.append(f"Step {step_num} — Final Answer: {content[:150]}")

    return "\n".join(lines)


def run_react_loop(
    user_query: str,
    session_id: str,
    provider,
    research_driver,
    chat_driver,
    schema_context: Dict[str, Any],
    retrieved_history: str = "",
    max_steps: int = 4,
    on_step_callback: Optional[Any] = None,
    on_token_callback: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Run a bounded ReAct loop for multi-step reasoning queries.

    Each step:
        1. Think: LLM decides what to do next
        2. Act: either run a Cypher query OR produce final answer
        3. Observe: collect results, check for errors
        4. Loop or terminate

    Termination conditions (any one triggers final answer):
        - LLM outputs "FINAL ANSWER:" prefix
        - max_steps reached
        - Last step produced no new Cypher

    Token budget per step:
        System prompt:        ~500 tokens  (fixed)
        Schema context:       ~1000-2500 tokens  (injected once, step 1 only, full schema)
        Retrieved history:    ~800 tokens  (injected once, step 1 only)
        Step history:         ~150 tokens per step × max 4 = ~600
        Current observation:  ~300 tokens  (truncate results if needed)
        TOTAL TARGET:         ~3000-4000 tokens per step

    Args:
        user_query: The user's question
        session_id: Chat session ID
        provider: LLMProvider instance (e.g., OllamaProvider)
        research_driver: Neo4j driver for research database
        chat_driver: ChatNeo4jClient instance
        schema_context: Neo4j schema dict
        retrieved_history: Formatted past context (from retrieve_relevant_context)
        max_steps: Maximum number of reasoning steps (default 4)
        on_step_callback: Optional callback invoked after each step with step dict.
                         Errors are silently caught to prevent loop termination.
        on_token_callback: Optional callback invoked for each token during THINK steps.
                          Called as: on_token_callback(token, step_num)
                          Enables real-time token streaming for typewriter effect.

    Returns:
        Dict with:
            - status: 'ok' or 'error'
            - reply: Final answer text
            - metadata: {steps_taken, queries_executed, execution_time_ms}
            - step_log: List of all steps for debugging/audit
    """
    start_time = time.time()
    steps = []
    queries_executed = []

    try:
        # Build initial system prompt (includes schema + history)
        system_prompt = build_react_system_prompt(schema_context, retrieved_history)

        # DEBUG: Log ReAct loop entry
        print(f"DEBUG: Entering ReAct loop for query: {user_query[:100]}")
        print(f"DEBUG: Max steps: {max_steps}")

        for step_num in range(1, max_steps + 1):
            logger.info(f"ReAct step {step_num}/{max_steps} for session {session_id}")
            print(f"DEBUG: ReAct step {step_num}/{max_steps}")

            # Build step history (grows each iteration)
            step_history = format_step_history(steps)

            # Construct prompt for this step
            if step_num == 1:
                # First step: include full system prompt
                step_prompt = f"{system_prompt}\n\nUser Question: {user_query}\n\nBegin reasoning:"
            else:
                # Subsequent steps: MUST include format reminder to prevent "THINK" without content
                step_prompt = f"""Previous steps:
{step_history}

REMINDER - You must output EXACTLY ONE of these formats:
  THINK: [your reasoning about what to do next]
  QUERY: [a single executable Cypher query]
  FINAL ANSWER: [your complete answer]

What's your next step?"""

            # Get LLM response - use streaming if token callback provided
            llm_response = ""
            if on_token_callback:
                # Try streaming with token callback
                try:
                    for token in provider.stream(
                        user_message=step_prompt,
                        system_prompt="",  # Already in step_prompt for token efficiency
                        schema_context=None  # Already injected in system_prompt
                    ):
                        llm_response += token
                        # Invoke token callback (swallow errors silently)
                        try:
                            on_token_callback(token, step_num)
                        except Exception:
                            pass
                except Exception as stream_err:
                    # Streaming failed - fall back to complete()
                    logger.warning(f"Token streaming failed for step {step_num}, falling back: {stream_err}")
                    llm_response = provider.complete(
                        user_message=step_prompt,
                        system_prompt="",
                        schema_context=None
                    )
            else:
                # No token callback - use non-streaming complete()
                llm_response = provider.complete(
                    user_message=step_prompt,
                    system_prompt="",  # Already in step_prompt for token efficiency
                    schema_context=None  # Already injected in system_prompt
                )

            # Parse action
            action_type, content = extract_action(llm_response)

            # DEBUG: Log action
            print(f"DEBUG: Step {step_num} action_type: {action_type}")
            print(f"DEBUG: Step {step_num} content: {content[:200]}")

            # Handle action
            if action_type == "FINAL_ANSWER":
                # Termination: final answer produced
                elapsed_ms = int((time.time() - start_time) * 1000)
                step_dict = {
                    "step_num": step_num,
                    "action_type": "FINAL_ANSWER",
                    "content": content,
                    "observation": ""
                }
                steps.append(step_dict)

                # Invoke callback (swallow errors silently)
                if on_step_callback:
                    try:
                        on_step_callback(step_dict)
                    except Exception:
                        pass

                return {
                    "status": "ok",
                    "reply": content,
                    "engine": "react",
                    "metadata": {
                        "steps_taken": step_num,
                        "queries_executed": len(queries_executed),
                        "execution_time_ms": elapsed_ms
                    },
                    "step_log": steps
                }

            elif action_type == "QUERY":
                # Safety check
                is_safe, error_msg = is_safe_cypher(content)
                if not is_safe:
                    observation = f"ERROR: {error_msg}"
                    logger.warning(f"Blocked unsafe query in step {step_num}: {error_msg}")
                else:
                    # Execute query
                    try:
                        with research_driver.session() as session:
                            result = session.run(content)
                            records = [record.data() for record in result]
                            result_count = len(records)

                            queries_executed.append(content)

                            # Phase 1: Log query usage (never fails)
                            if chat_driver:
                                try:
                                    from ..services.chat_service import get_chat_service
                                    import os
                                    db_path = os.environ.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
                                    chat_service = get_chat_service(db_path=db_path)
                                    sqlite_conn = chat_service._get_conn()
                                    try:
                                        from ..services.schema_intelligence import log_query_usage
                                        log_query_usage(content, session_id, sqlite_conn, source='chat')
                                    finally:
                                        sqlite_conn.close()
                                except Exception:
                                    pass  # Logging must never fail a query

                            # Truncate results for observation (top 5 only)
                            if result_count == 0:
                                observation = (
                                    "Query returned 0 results. "
                                    "Do not invent data. Either try a different query or report no data found in FINAL ANSWER."
                                )
                            elif result_count <= 5:
                                observation = f"{result_count} rows: {records}"
                            else:
                                observation = f"{result_count} rows returned. Top 5: {records[:5]}"

                    except Exception as query_error:
                        observation = f"Query execution failed: {str(query_error)}"
                        logger.error(f"Query error in step {step_num}: {query_error}")
                        # Don't terminate - let agent diagnose and retry per rule 6

                step_dict = {
                    "step_num": step_num,
                    "action_type": "QUERY",
                    "content": content,
                    "observation": observation
                }
                steps.append(step_dict)

                # Invoke callback (swallow errors silently)
                if on_step_callback:
                    try:
                        on_step_callback(step_dict)
                    except Exception:
                        pass

            elif action_type == "THINK":
                # Pure reasoning step
                step_dict = {
                    "step_num": step_num,
                    "action_type": "THINK",
                    "content": content,
                    "observation": ""
                }
                steps.append(step_dict)

                # Invoke callback (swallow errors silently)
                if on_step_callback:
                    try:
                        on_step_callback(step_dict)
                    except Exception:
                        pass

            # Check if we've hit max steps
            if step_num >= max_steps:
                # Force final answer
                logger.info(f"Max steps reached, forcing final answer")
                final_prompt = f"""You've completed {max_steps} reasoning steps:
{step_history}

Provide your FINAL ANSWER to the user's question: {user_query}"""

                final_response = provider.complete(
                    user_message=final_prompt,
                    system_prompt="",
                    schema_context=None
                )

                elapsed_ms = int((time.time() - start_time) * 1000)
                return {
                    "status": "ok",
                    "reply": final_response,
                    "engine": "react",
                    "metadata": {
                        "steps_taken": step_num,
                        "queries_executed": len(queries_executed),
                        "execution_time_ms": elapsed_ms,
                        "max_steps_reached": True
                    },
                    "step_log": steps
                }

        # Shouldn't reach here, but handle gracefully
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "status": "ok",
            "reply": "I completed my reasoning but didn't arrive at a definitive answer.",
            "engine": "react",
            "metadata": {
                "steps_taken": len(steps),
                "queries_executed": len(queries_executed),
                "execution_time_ms": elapsed_ms
            },
            "step_log": steps
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"ReAct loop failed: {e}", exc_info=True)
        return {
            "status": "error",
            "reply": f"ReAct loop encountered an error: {str(e)}",
            "engine": "react",
            "metadata": {
                "steps_taken": len(steps),
                "queries_executed": len(queries_executed),
                "execution_time_ms": elapsed_ms
            },
            "step_log": steps
        }
