"""
Chat Knowledge Graph - persistent chat history with semantic retrieval and staleness detection.

This module manages the chat Neo4j database, which stores:
- ChatMessage nodes: compressed summaries of chat interactions with embeddings
- ChatSession nodes: groupings of related messages
- ResearchEntity stubs: references to research data touched by queries

Key features:
- Semantic retrieval: Find relevant past messages via vector similarity
- Staleness detection: Track when research data has changed since a finding was generated
- Context compression: Keep full Cypher but summarize content to stay under token budgets
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import time
import json
import logging
import os

logger = logging.getLogger(__name__)


def get_label_snapshot(research_driver) -> Dict[str, int]:
    """
    Fast count of all node labels in the research graph.

    Uses Neo4j's internal stats - resolves in single-digit milliseconds even on large graphs.

    Args:
        research_driver: Neo4j driver for the research database

    Returns:
        Dict mapping label names to node counts, e.g.:
        {"Sample": 9042, "SampleType": 52, "Treatment": 384}
    """
    snapshot = {}

    try:
        with research_driver.session() as session:
            # Get all labels
            labels_result = session.run("CALL db.labels() YIELD label RETURN label")
            all_labels = [record["label"] for record in labels_result]

            # Count nodes for each label (fast - uses internal stats)
            for label in all_labels:
                try:
                    count_result = session.run(
                        f"MATCH (n:`{label}`) RETURN count(n) as count"
                    )
                    count_record = count_result.single()
                    if count_record:
                        snapshot[label] = count_record["count"]
                except Exception as e:
                    logger.warning(f"Failed to count label {label}: {e}")
                    snapshot[label] = 0

        return snapshot

    except Exception as e:
        logger.error(f"Failed to get label snapshot: {e}", exc_info=True)
        return {}


def check_staleness(message: Dict[str, Any], research_driver) -> List[Dict[str, Any]]:
    """
    Compare stored snapshot against current label counts to detect staleness.

    Returns a list of staleness signals, one per referenced label.

    Args:
        message: ChatMessage dict with keys: referenced_labels, snapshot, finding_type
        research_driver: Neo4j driver for the research database

    Returns:
        List of staleness signal dicts, each with:
        {
            "label": "Sample",
            "stored_count": 9042,
            "current_count": 9847,
            "delta": 805,
            "pct_change": 0.089,
            "status": "moderate_change",  # unchanged / minor / moderate / major
            "message": "Sample: 9847 now vs 9042 then (+805 nodes) ⚠️"
        }

    Thresholds:
        0%        → unchanged ✓
        0–5%      → minor change (note but don't flag)
        5–20%     → moderate change ⚠️ (flag for COUNT findings)
        >20%      → major change 🔴 (always flag)

    Finding type matters:
        COUNT findings:      flag at moderate change (5%)
        RELATIONAL findings: flag at major change only (20%)
        STRUCTURAL findings: flag at major change only (20%)
        SCHEMA findings:     never flag (schema changes are explicit)
    """
    referenced_labels = message.get("referenced_labels", [])
    stored_snapshot = message.get("snapshot", {})
    finding_type = message.get("finding_type", "NONE")

    if not referenced_labels:
        return []

    # Get current snapshot
    current_snapshot = get_label_snapshot(research_driver)

    signals = []
    for label in referenced_labels:
        stored_count = stored_snapshot.get(label, 0)
        current_count = current_snapshot.get(label, 0)
        delta = current_count - stored_count

        # Calculate percentage change (avoid division by zero)
        if stored_count == 0:
            pct_change = 1.0 if current_count > 0 else 0.0
        else:
            pct_change = abs(delta / stored_count)

        # Determine status based on thresholds
        if pct_change == 0:
            status = "unchanged"
            emoji = "✓"
        elif pct_change < 0.05:
            status = "minor_change"
            emoji = ""
        elif pct_change < 0.20:
            status = "moderate_change"
            emoji = "⚠️"
        else:
            status = "major_change"
            emoji = "🔴"

        # Build message
        sign = "+" if delta >= 0 else ""
        msg = f"{label}: {current_count:,} now vs {stored_count:,} then ({sign}{delta:,} nodes)"
        if emoji:
            msg += f" {emoji}"

        # Determine if this should be flagged based on finding type
        should_flag = False
        if finding_type == "COUNT" and status in ["moderate_change", "major_change"]:
            should_flag = True
        elif finding_type in ["RELATIONAL", "STRUCTURAL"] and status == "major_change":
            should_flag = True
        # SCHEMA findings never flagged

        signals.append({
            "label": label,
            "stored_count": stored_count,
            "current_count": current_count,
            "delta": delta,
            "pct_change": pct_change,
            "status": status,
            "message": msg,
            "should_flag": should_flag
        })

    return signals


def retrieve_relevant_context(
    current_query: str,
    session_id: str,
    chat_driver,
    research_driver,
    embedding_model: str = "nomic-embed-text",
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Retrieve the most relevant past messages for a new query.

    Uses TWO retrieval strategies, merged and deduplicated:

    Strategy 1 — Semantic similarity:
        Embed current_query with nomic-embed-text
        Vector search over ChatMessage.embedding
        Filter: m.timestamp > session.context_cleared_at (if set)
        Return top_k most similar

    Strategy 2 — Node overlap:
        Extract any entity references from current_query (label names)
        MATCH (m:ChatMessage)-[:REFERENCED_NODE]->(n)
        WHERE n.label IN {detected_labels}
        ORDER BY m.timestamp DESC
        Return top_k most recent that touched same node types

    For each retrieved message:
        Run check_staleness() against research_driver
        Attach staleness signals to the message

    Args:
        current_query: User's current question
        session_id: Chat session ID
        chat_driver: ChatNeo4jClient instance
        research_driver: Research Neo4j driver
        embedding_model: Ollama model for embeddings (default: nomic-embed-text)
        top_k: Number of messages to retrieve per strategy

    Returns:
        Merged list of messages with staleness signals attached,
        deduplicated by sqlite_id, max 6 total.
    """
    try:
        # Get session to check context_cleared_at
        context_cleared_at = None
        try:
            session_result = chat_driver.execute_read(
                """
                MATCH (s:ChatSession {session_id: $session_id})
                RETURN s.context_cleared_at AS cleared_at
                """,
                {"session_id": session_id}
            )
            if session_result:
                context_cleared_at = session_result[0].get("cleared_at")
        except Exception:
            pass

        # Strategy 1: Semantic similarity (if vector index available)
        semantic_messages = []
        try:
            # Generate embedding for current query using Ollama
            import requests
            ollama_endpoint = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
            embed_response = requests.post(
                f"{ollama_endpoint}/api/embeddings",
                json={"model": embedding_model, "prompt": current_query},
                timeout=10
            )
            if embed_response.status_code == 200:
                query_embedding = embed_response.json().get("embedding")

                if query_embedding:
                    # Vector search query
                    time_filter = ""
                    params = {
                        "session_id": session_id,
                        "query_embedding": query_embedding,
                        "top_k": top_k
                    }

                    if context_cleared_at:
                        time_filter = "AND m.timestamp > $cleared_at"
                        params["cleared_at"] = context_cleared_at

                    vector_query = f"""
                        MATCH (m:ChatMessage {{session_id: $session_id}})
                        WHERE m.embedding IS NOT NULL {time_filter}
                        WITH m, vector.similarity.cosine(m.embedding, $query_embedding) AS score
                        WHERE score > 0.5
                        RETURN m, score
                        ORDER BY score DESC
                        LIMIT $top_k
                    """

                    semantic_results = chat_driver.execute_read(vector_query, params)
                    semantic_messages = [r["m"] for r in semantic_results if r.get("m")]

        except Exception as e:
            logger.warning(f"Semantic retrieval failed (vector index may not be available): {e}")

        # Strategy 2: Node overlap (extract label names from query)
        node_overlap_messages = []
        try:
            # Simple heuristic: find capitalized words that might be label names
            # More sophisticated: use research graph labels as dictionary
            with research_driver.session() as session:
                labels_result = session.run("CALL db.labels() YIELD label RETURN label")
                all_labels = [r["label"] for r in labels_result]

            # Find labels mentioned in query (case-insensitive)
            query_lower = current_query.lower()
            detected_labels = [label for label in all_labels if label.lower() in query_lower]

            if detected_labels:
                time_filter = ""
                params = {
                    "session_id": session_id,
                    "labels": detected_labels,
                    "top_k": top_k
                }

                if context_cleared_at:
                    time_filter = "AND m.timestamp > $cleared_at"
                    params["cleared_at"] = context_cleared_at

                overlap_query = f"""
                    MATCH (m:ChatMessage {{session_id: $session_id}})-[:REFERENCED_NODE]->(n:ResearchEntity)
                    WHERE n.label IN $labels {time_filter}
                    WITH m, count(DISTINCT n) AS overlap_count
                    RETURN m, overlap_count
                    ORDER BY overlap_count DESC, m.timestamp DESC
                    LIMIT $top_k
                """

                overlap_results = chat_driver.execute_read(overlap_query, params)
                node_overlap_messages = [r["m"] for r in overlap_results if r.get("m")]

        except Exception as e:
            logger.warning(f"Node overlap retrieval failed: {e}")

        # Merge and deduplicate by sqlite_id
        seen_ids = set()
        merged_messages = []

        for msg in semantic_messages + node_overlap_messages:
            sqlite_id = msg.get("sqlite_id")
            if sqlite_id and sqlite_id not in seen_ids:
                seen_ids.add(sqlite_id)
                merged_messages.append(msg)

                if len(merged_messages) >= 6:  # Max total
                    break

        # Attach staleness signals to each message
        for msg in merged_messages:
            staleness_signals = check_staleness(msg, research_driver)
            msg["staleness_signals"] = staleness_signals

        return merged_messages

    except Exception as e:
        logger.error(f"Context retrieval failed: {e}", exc_info=True)
        return []


def format_context_for_prompt(messages: List[Dict[str, Any]]) -> str:
    """
    Format retrieved messages into a compact string for LLM injection.

    Total output must stay under 800 tokens regardless of input size.
    Truncates oldest messages first if over budget.

    Args:
        messages: List of ChatMessage dicts with staleness_signals attached

    Returns:
        Formatted context string for prompt injection

    Format per message:
        [PAST CONTEXT — {days_ago} days ago, {intent}]
        Q: {content_summary}
        Finding: {finding_text}
        Query used: {cypher_used} (if any)
        Staleness: {staleness signals, one line each}
        ---
    """
    if not messages:
        return ""

    formatted_lines = []
    now = time.time()

    for msg in messages:
        timestamp = msg.get("timestamp", now)
        intent = msg.get("intent", "UNKNOWN")
        content_summary = msg.get("content_summary", "")
        finding_text = msg.get("finding_text", "")
        cypher_used = msg.get("cypher_used", "")
        staleness_signals = msg.get("staleness_signals", [])

        # Calculate days ago
        days_ago = int((now - timestamp) / 86400)
        time_str = f"{days_ago} days ago" if days_ago > 0 else "today"

        # Build message block
        block = f"[PAST CONTEXT — {time_str}, {intent}]\n"
        block += f"Q: {content_summary[:200]}\n"  # Truncate summary to 200 chars

        if finding_text:
            block += f"Finding: {finding_text[:150]}\n"  # Truncate to 150 chars

        if cypher_used:
            # Truncate Cypher to 200 chars for display
            cypher_display = cypher_used[:200]
            if len(cypher_used) > 200:
                cypher_display += "..."
            block += f"Query used: {cypher_display}\n"

        # Add flagged staleness signals only
        flagged_signals = [s for s in staleness_signals if s.get("should_flag", False)]
        if flagged_signals:
            block += "Staleness: "
            block += ", ".join([s["message"] for s in flagged_signals[:3]])  # Max 3 signals
            block += "\n"

        block += "---\n"
        formatted_lines.append(block)

    # Join all blocks
    full_context = "\n".join(formatted_lines)

    # Rough token estimate: ~4 chars per token
    # Target: 800 tokens = ~3200 chars
    if len(full_context) > 3200:
        # Truncate from the beginning (oldest messages)
        # Keep last 3200 chars
        full_context = "...\n" + full_context[-3200:]

    return full_context


def log_chat_message(
    chat_driver,
    research_driver,
    sqlite_id: str,
    session_id: str,
    role: str,
    intent: str,
    content_summary: str,
    finding_text: Optional[str] = None,
    finding_type: Optional[str] = None,
    cypher_used: Optional[str] = None,
    referenced_labels: Optional[List[str]] = None,
    embedding: Optional[List[float]] = None
):
    """
    Log a chat message to the chat Neo4j graph.

    Creates ChatMessage node with full metadata, snapshot, and relationships.

    Args:
        chat_driver: ChatNeo4jClient instance
        research_driver: Research Neo4j driver (for snapshot)
        sqlite_id: Foreign key to SQLite chat_messages table
        session_id: Chat session ID
        role: "user" or "assistant"
        intent: LOOKUP / SUMMARIZE / REASONING / REACT
        content_summary: Compressed summary of message (under 200 tokens)
        finding_text: Key finding in one sentence (for assistant messages)
        finding_type: STRUCTURAL / RELATIONAL / COUNT / SCHEMA / NONE
        cypher_used: Exact Cypher executed (if any)
        referenced_labels: List of node labels touched by query
        embedding: nomic-embed-text vector (768 dimensions)
    """
    try:
        timestamp = time.time()
        snapshot = get_label_snapshot(research_driver) if referenced_labels else {}

        # Create or merge ChatSession
        chat_driver.execute_write(
            """
            MERGE (s:ChatSession {session_id: $session_id})
            ON CREATE SET s.started_at = $timestamp
            """,
            {"session_id": session_id, "timestamp": timestamp}
        )

        # Create ChatMessage
        message_params = {
            "sqlite_id": sqlite_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "role": role,
            "intent": intent,
            "content_summary": content_summary,
            "finding_text": finding_text or "",
            "finding_type": finding_type or "NONE",
            "cypher_used": cypher_used or "",
            "referenced_labels": referenced_labels or [],
            "snapshot": json.dumps(snapshot),
            "snapshot_taken_at": timestamp,
            "confidence": 1.0,  # Default confidence
            "embedding": embedding
        }

        chat_driver.execute_write(
            """
            CREATE (m:ChatMessage {
                sqlite_id: $sqlite_id,
                session_id: $session_id,
                timestamp: $timestamp,
                role: $role,
                intent: $intent,
                content_summary: $content_summary,
                finding_text: $finding_text,
                finding_type: $finding_type,
                cypher_used: $cypher_used,
                referenced_labels: $referenced_labels,
                snapshot: $snapshot,
                snapshot_taken_at: $snapshot_taken_at,
                confidence: $confidence,
                embedding: $embedding
            })
            WITH m
            MATCH (s:ChatSession {session_id: $session_id})
            MERGE (m)-[:IN_SESSION]->(s)
            """,
            message_params
        )

        # Create ResearchEntity stubs for referenced labels
        if referenced_labels:
            for label in referenced_labels:
                chat_driver.execute_write(
                    """
                    MERGE (e:ResearchEntity {label: $label})
                    WITH e
                    MATCH (m:ChatMessage {sqlite_id: $sqlite_id})
                    MERGE (m)-[:REFERENCED_NODE]->(e)
                    """,
                    {"label": label, "sqlite_id": sqlite_id}
                )

        logger.info(f"Logged ChatMessage {sqlite_id} to chat Neo4j (session: {session_id})")

    except Exception as e:
        logger.error(f"Failed to log chat message to Neo4j: {e}", exc_info=True)
        # Don't raise - logging failure shouldn't break chat functionality
