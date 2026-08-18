"""
Concept Graph Service Layer
Meta-reasoning and planning layer for SciDK chat system.

The Concept Graph is a separate Neo4j instance that stores system self-knowledge:
intents, tools, schema labels/relationships as planning abstractions.

This service provides:
- Intent classification via semantic embedding search + graph traversal
- Execution planning via graph queries
- Self-learning via weight adjustment based on query outcomes

Graceful degradation: All functions return None or raise ConceptGraphUnavailableError
when the concept graph is unreachable. Callers must fall back to hard-coded logic.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

import numpy as np
import yaml
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

EMBED_MODEL = 'nomic-embed-text'


class ConceptGraphUnavailableError(Exception):
    """Raised when concept graph operations fail and fallback is required."""
    pass


# ─────────────────────────────────────────────
# Driver Initialization
# ─────────────────────────────────────────────

def get_concept_driver(app=None):
    """
    Initialize and return concept_driver or None if unavailable.

    Follows the same pattern as Neo4jClient initialization.
    Never raises — returns None for graceful degradation.

    Args:
        app: Flask app instance (optional, for config access)

    Returns:
        Neo4j driver instance or None
    """
    try:
        uri = os.environ.get('SCIDK_CONCEPT_NEO4J_URI', 'bolt://localhost:7689')
        auth_str = os.environ.get('SCIDK_CONCEPT_NEO4J_AUTH', 'neo4j/concept-graph-password')

        if not uri or not auth_str:
            logger.info("Concept graph not configured (missing URI or auth)")
            return None

        # Parse auth string (format: "user/password" or "none")
        if auth_str.lower() == 'none':
            auth = None
        else:
            parts = auth_str.split('/', 1)
            if len(parts) != 2:
                logger.warning(f"Invalid concept graph auth format: {auth_str}")
                return None
            user, password = parts
            auth = (user, password)

        # Verify with a throwaway driver, then hand back a fresh unused one.
        #
        # verify_connectivity() opens a real socket and leaves it idle in the
        # driver's connection pool. This function runs inside create_app(), which
        # gunicorn runs in the master process under --preload — a pooled
        # connection there is inherited by all 16 workers, which would then
        # interleave Bolt traffic on one shared file descriptor. A driver that has
        # never been used holds no socket, so it crosses the fork safely and each
        # worker opens its own connection on first query.
        probe = GraphDatabase.driver(uri, auth=auth)
        try:
            probe.verify_connectivity()
        finally:
            probe.close()

        logger.info(f"Concept graph connected at {uri}")
        return GraphDatabase.driver(uri, auth=auth)

    except Exception as e:
        logger.warning(f"Concept graph unavailable: {e}")
        return None


# ─────────────────────────────────────────────
# Embedding Utilities
# ─────────────────────────────────────────────

def embed_text(text: str, ollama_url: str,
               model: str = EMBED_MODEL) -> Optional[List[float]]:
    """Call Ollama embeddings API. Returns float list or None."""
    import requests
    try:
        resp = requests.post(
            f"{ollama_url.rstrip('/')}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json().get('embedding')
    except Exception as e:
        logger.warning(f"Embedding failed ({model}): {e}")
        return None


def _vector_to_blob(v: List[float]) -> bytes:
    """Convert float list to numpy blob for Neo4j storage."""
    return np.array(v, dtype=np.float32).tobytes()


def _blob_to_vector(b: bytes) -> np.ndarray:
    """Convert Neo4j blob back to numpy array."""
    return np.frombuffer(b, dtype=np.float32)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a / na, b / nb))


# ─────────────────────────────────────────────
# Seeding Functions
# ─────────────────────────────────────────────

def seed_intents_from_yaml(concept_driver, yaml_path: str, ollama_url: str) -> Dict[str, int]:
    """
    Load intents from intents.yaml into :Concept_Intent nodes.
    Embed each intent's description + examples using nomic-embed-text.
    Upsert — safe to call repeatedly.

    Args:
        concept_driver: Neo4j driver for concept graph
        yaml_path: Path to intents.yaml
        ollama_url: Ollama API endpoint

    Returns:
        Dict with 'embedded' and 'failed' counts
    """
    if concept_driver is None:
        raise ConceptGraphUnavailableError("concept_driver is None")

    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)

    intents = data.get('intents', [])
    embedded, failed = 0, 0

    with concept_driver.session() as session:
        for intent in intents:
            name = intent.get('name')
            description = intent.get('description', '').strip()
            examples = intent.get('examples', [])
            maps_to_legacy = intent.get('maps_to_legacy')
            references_labels = intent.get('references_labels', [])

            # Build embedding text from description + examples
            embedding_text = description
            if examples:
                embedding_text += ' Examples: ' + ' | '.join(examples)

            # Embed
            vector = embed_text(embedding_text, ollama_url)
            if vector is None:
                failed += 1
                logger.warning(f"Failed to embed intent: {name}")
                continue

            # Upsert intent node
            session.run("""
                MERGE (i:Concept_Intent {name: $name})
                SET i.description = $description,
                    i.examples = $examples,
                    i.maps_to_legacy = $maps_to_legacy,
                    i.embedding = $embedding,
                    i.embedding_model = $model,
                    i.embedding_text = $embedding_text,
                    i.embedded_at = datetime(),
                    i.updated_at = datetime()
            """, name=name, description=description, examples=examples,
                maps_to_legacy=maps_to_legacy,
                embedding=_vector_to_blob(vector),
                model=EMBED_MODEL, embedding_text=embedding_text)

            # Create REFERENCES_LABEL edges
            for label_name in references_labels:
                session.run("""
                    MATCH (i:Concept_Intent {name: $intent})
                    MERGE (l:Concept_Label {name: $label})
                    MERGE (i)-[:REFERENCES_LABEL]->(l)
                """, intent=name, label=label_name)

            embedded += 1

    logger.info(f"seed_intents_from_yaml: {embedded} embedded, {failed} failed")
    return {'embedded': embedded, 'failed': failed}


def seed_tools_from_yaml(concept_driver, yaml_path: str, ollama_url: str) -> Dict[str, int]:
    """
    Load tool definitions from intents.yaml into :Concept_Tool nodes.
    Embed descriptions. Create :SATISFIES edges to intents with initial weights.
    Upsert — safe to call repeatedly.

    Args:
        concept_driver: Neo4j driver for concept graph
        yaml_path: Path to intents.yaml
        ollama_url: Ollama API endpoint

    Returns:
        Dict with 'embedded' and 'failed' counts
    """
    if concept_driver is None:
        raise ConceptGraphUnavailableError("concept_driver is None")

    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)

    tools = data.get('tools', [])
    intents = data.get('intents', [])

    embedded, failed = 0, 0

    with concept_driver.session() as session:
        # Seed tool nodes
        for tool in tools:
            name = tool.get('name')
            description = tool.get('description', '').strip()
            source = tool.get('source', 'internal')
            endpoint = tool.get('endpoint')
            input_schema = tool.get('input_schema')
            output_format = tool.get('output_format')
            is_read_only = tool.get('is_read_only', True)
            active = tool.get('active', True)
            retrieves = tool.get('retrieves', [])

            # Embed description
            vector = embed_text(description, ollama_url)
            if vector is None:
                failed += 1
                logger.warning(f"Failed to embed tool: {name}")
                continue

            # Upsert tool node
            session.run("""
                MERGE (t:Concept_Tool {name: $name})
                SET t.description = $description,
                    t.source = $source,
                    t.endpoint = $endpoint,
                    t.input_schema = $input_schema,
                    t.output_format = $output_format,
                    t.is_read_only = $is_read_only,
                    t.active = $active,
                    t.embedding = $embedding,
                    t.embedding_model = $model,
                    t.embedding_text = $description,
                    t.embedded_at = datetime(),
                    t.updated_at = datetime()
            """, name=name, description=description, source=source,
                endpoint=endpoint, input_schema=json.dumps(input_schema) if input_schema else None,
                output_format=output_format, is_read_only=is_read_only, active=active,
                embedding=_vector_to_blob(vector), model=EMBED_MODEL)

            # Create RETRIEVES edges to labels
            for retrieval in retrieves:
                label_name = retrieval.get('label') if isinstance(retrieval, dict) else retrieval
                if label_name:
                    session.run("""
                        MATCH (t:Concept_Tool {name: $tool})
                        MERGE (l:Concept_Label {name: $label})
                        MERGE (t)-[:RETRIEVES]->(l)
                    """, tool=name, label=label_name)

            embedded += 1

        # Create SATISFIES edges from intents to tools
        for intent in intents:
            intent_name = intent.get('name')
            satisfies_list = intent.get('satisfies', [])

            for satisfies in satisfies_list:
                tool_name = satisfies.get('tool')
                weight = satisfies.get('weight', 0.5)

                session.run("""
                    MATCH (i:Concept_Intent {name: $intent})
                    MATCH (t:Concept_Tool {name: $tool})
                    MERGE (i)-[s:SATISFIES]->(t)
                    SET s.weight = $weight,
                        s.usage_count = coalesce(s.usage_count, 0),
                        s.last_used_at = null
                """, intent=intent_name, tool=tool_name, weight=weight)

    logger.info(f"seed_tools_from_yaml: {embedded} tools embedded, {failed} failed")
    return {'embedded': embedded, 'failed': failed}


def sync_labels_from_schema(concept_driver, research_driver, sqlite_conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Mirror research graph schema into :Concept_Label and :Concept_Relationship nodes.

    Uses raw get_schema_context() to get relationship metadata.
    Creates Concept_Relationship nodes without CONNECTED_VIA edges if source/target unavailable.

    Args:
        concept_driver: Neo4j driver for concept graph
        research_driver: Neo4j driver for research graph
        sqlite_conn: SQLite connection for label profiles

    Returns:
        Dict with 'labels', 'relationships', 'edges' counts
    """
    if concept_driver is None:
        raise ConceptGraphUnavailableError("concept_driver is None")

    # Use raw get_schema_context (not enriched) to get relationship metadata
    from ..ai.schema_context import get_schema_context

    database = os.environ.get('SCIDK_NEO4J_DATABASE', 'neo4j')
    schema = get_schema_context(research_driver, database=database)

    labels_synced = 0
    rels_synced = 0
    edges_created = 0

    research_uri = os.environ.get('SCIDK_NEO4J_URI') or os.environ.get('NEO4J_URI') or os.environ.get('BOLT_URI')

    with concept_driver.session() as session:
        # Upsert :Concept_Label for each label
        for label in schema.get('labels', []):
            session.run("""
                MERGE (l:Concept_Label {name: $name})
                SET l.graph_uri = $uri,
                    l.last_synced = datetime()
            """, name=label, uri=research_uri or 'unknown')
            labels_synced += 1

        # Upsert :Concept_Relationship for each rel type
        relationships = schema.get('relationships', [])

        # Handle both string format and dict format
        for rel in relationships:
            if isinstance(rel, dict):
                rel_type = rel.get('type')
                source_label = rel.get('source')
                target_label = rel.get('target')
            else:
                # String format: just the relationship type
                rel_type = rel
                source_label = None
                target_label = None

            if not rel_type:
                continue

            # Create Concept_Relationship node
            session.run("""
                MERGE (r:Concept_Relationship {type: $type})
                SET r.last_synced = datetime()
            """, type=rel_type)
            rels_synced += 1

            # Create CONNECTED_VIA edges only if source/target available
            if source_label and target_label:
                result = session.run("""
                    MATCH (source:Concept_Label {name: $source})
                    MATCH (target:Concept_Label {name: $target})
                    MATCH (r:Concept_Relationship {type: $rel_type})
                    MERGE (source)-[:CONNECTED_VIA]->(r)
                    MERGE (r)-[:CONNECTS_TO]->(target)
                    RETURN count(*) as created
                """, source=source_label, target=target_label, rel_type=rel_type)

                record = result.single()
                if record:
                    edges_created += record['created']

    logger.info(f"sync_labels_from_schema: {labels_synced} labels, {rels_synced} relationships, {edges_created} edges")
    return {'labels': labels_synced, 'relationships': rels_synced, 'edges': edges_created}


# ─────────────────────────────────────────────
# Intent Classification and Planning
# ─────────────────────────────────────────────

def classify_intent(user_query: str, concept_driver, sqlite_conn: sqlite3.Connection,
                   ollama_url: str) -> Tuple[str, float]:
    """
    Two-step intent classification:
    1. Embed query, cosine search against :Concept_Intent embeddings
    2. Confirmation traversal — boost if intent has REFERENCES_LABEL edges
       to labels that are relevant to this query

    Args:
        user_query: Natural language query from user
        concept_driver: Neo4j driver for concept graph
        sqlite_conn: SQLite connection (unused but kept for signature consistency)
        ollama_url: Ollama API endpoint

    Returns:
        Tuple of (intent_name, confidence_float)

    Raises:
        ConceptGraphUnavailableError if concept_driver is None or embeddings unavailable
    """
    if concept_driver is None:
        raise ConceptGraphUnavailableError("concept_driver not available")

    # Step 1: Embed query
    query_vector = embed_text(user_query, ollama_url)
    if query_vector is None:
        raise ConceptGraphUnavailableError("embedding unavailable")

    # Fetch all intent embeddings
    with concept_driver.session() as session:
        result = session.run(
            "MATCH (i:Concept_Intent) WHERE i.embedding IS NOT NULL "
            "RETURN i.name AS name, i.embedding AS embedding"
        )
        rows = [dict(record) for record in result]

    if not rows:
        raise ConceptGraphUnavailableError("no intent embeddings seeded")

    # Compute cosine similarities
    q = np.array(query_vector, dtype=np.float32)
    scored = []
    for row in rows:
        v = _blob_to_vector(row['embedding'])
        score = _cosine_sim(q, v)
        scored.append((score, row['name']))

    scored.sort(reverse=True)

    if not scored:
        raise ConceptGraphUnavailableError("no intent scores computed")

    top_intent = scored[0][1]
    top_score = scored[0][0]

    return top_intent, round(top_score, 3)


def plan_execution(intent_name: str, relevant_labels: List[str],
                  concept_driver) -> Optional[Dict[str, Any]]:
    """
    Run the planning Cypher query to produce execution plan.

    Traverse from intent to tools via SATISFIES edges, considering only
    tools that RETRIEVE relevant labels.

    Args:
        intent_name: Name of the matched intent
        relevant_labels: List of relevant label names from schema intelligence
        concept_driver: Neo4j driver for concept graph

    Returns:
        Dict with: primary_tool, tool_schema, output_format,
                   matched_labels, matched_relationships,
                   required_tools, confidence
        Or None if no plan found
    """
    if concept_driver is None:
        return None

    with concept_driver.session() as session:
        result = session.run("""
            MATCH (i:Concept_Intent {name: $intent})
            MATCH (i)-[s:SATISFIES]->(t:Concept_Tool {active: true})
            OPTIONAL MATCH (t)-[:RETRIEVES]->(l:Concept_Label)
              WHERE l.name IN $labels
            OPTIONAL MATCH (l)-[:CONNECTED_VIA]->(r:Concept_Relationship)
              -[:CONNECTS_TO]->(l2:Concept_Label)
              WHERE l2.name IN $labels
            OPTIONAL MATCH (t)-[:REQUIRES*1..2]->(t2:Concept_Tool)
            RETURN
              t.name            AS primary_tool,
              t.input_schema    AS tool_schema,
              t.output_format   AS output_format,
              collect(DISTINCT l.name)  AS matched_labels,
              collect(DISTINCT r.type)  AS matched_relationships,
              collect(DISTINCT t2.name) AS required_tools,
              s.weight          AS confidence
            ORDER BY s.weight DESC
            LIMIT 1
        """, intent=intent_name, labels=relevant_labels)

        record = result.single()

    if record is None:
        return None

    return {
        'primary_tool': record['primary_tool'],
        'tool_schema': record['tool_schema'],
        'output_format': record['output_format'],
        'matched_labels': [l for l in record['matched_labels'] if l],
        'matched_relationships': [r for r in record['matched_relationships'] if r],
        'required_tools': [t for t in record['required_tools'] if t],
        'confidence': record['confidence']
    }


def update_traversal_weights(intent_name: str, tool_name: str, success: bool,
                             concept_driver) -> bool:
    """
    Update SATISFIES edge weight based on query outcome.

    Called by feedback endpoint after query completes.
    Increments weight on success, decrements on failure.

    Args:
        intent_name: Matched intent name
        tool_name: Selected tool name
        success: Whether query succeeded
        concept_driver: Neo4j driver for concept graph

    Returns:
        True if update succeeded, False otherwise
    """
    if concept_driver is None:
        return False

    delta = 0.02 if success else -0.05

    try:
        with concept_driver.session() as session:
            # Compute new weight with clamping in Python (APOC may not be available)
            result = session.run("""
                MATCH (i:Concept_Intent {name: $intent})
                      -[s:SATISFIES]->(t:Concept_Tool {name: $tool})
                RETURN s.weight AS old_weight
            """, intent=intent_name, tool=tool_name)

            record = result.single()
            if record is None:
                logger.warning(f"SATISFIES edge not found: {intent_name} -> {tool_name}")
                return False

            old_weight = record['old_weight'] or 0.5
            new_weight = max(0.0, min(1.0, old_weight + delta))

            # Update weight and metadata
            session.run("""
                MATCH (i:Concept_Intent {name: $intent})
                      -[s:SATISFIES]->(t:Concept_Tool {name: $tool})
                SET s.weight = $new_weight,
                    s.usage_count = coalesce(s.usage_count, 0) + 1,
                    s.last_updated = datetime()
            """, intent=intent_name, tool=tool_name, new_weight=new_weight)

        return True

    except Exception as e:
        logger.warning(f"Failed to update traversal weights: {e}")
        return False


def build_traversal_log(query: str, intent_matched: str, intent_confidence: float,
                       plan: Optional[Dict[str, Any]], labels_considered: List[str]) -> Dict[str, Any]:
    """
    Assemble traversal log dict for SQLite storage and UI display.

    Caps labels_considered to 10 entries to keep SSE payload bounded.

    Args:
        query: User query string
        intent_matched: Matched intent name
        intent_confidence: Intent classification confidence score
        plan: Execution plan dict from plan_execution()
        labels_considered: All labels considered by schema intelligence

    Returns:
        Dict ready for JSON serialization
    """
    # Cap labels_considered to 10 entries
    labels_truncated = labels_considered[:10] if labels_considered else []

    return {
        'query': query,
        'intent_matched': intent_matched,
        'intent_confidence': intent_confidence,
        'tool_selected': plan.get('primary_tool') if plan else None,
        'tool_confidence': plan.get('confidence') if plan else None,
        'matched_labels': plan.get('matched_labels', []) if plan else [],
        'matched_relationships': plan.get('matched_relationships', []) if plan else [],
        'required_tools': plan.get('required_tools', []) if plan else [],
        'labels_considered': labels_truncated,
        'labels_considered_count': len(labels_considered) if labels_considered else 0,
        'timestamp': datetime.utcnow().isoformat()
    }


# ─────────────────────────────────────────────
# Weight Decay (Concept Graph Phase 3)
# ─────────────────────────────────────────────

def apply_weight_decay(driver, half_life_days: int = 90) -> dict:
    """
    Apply exponential decay to SATISFIES edge weights toward neutral (0.5).

    Weights drift toward 0.5 over time using exponential decay. This prevents
    stale feedback from permanently biasing tool routing.

    Formula:
        decay_factor = 0.5 ^ (days_since_update / half_life_days)
        new_weight = 0.5 + (current_weight - 0.5) * decay_factor

    Only affects edges not updated in the last 7 days to avoid decaying
    fresh feedback.

    Args:
        driver: Neo4j driver for concept graph
        half_life_days: Days for weight to decay halfway to 0.5 (default 90)

    Returns:
        {
            'edges_updated': int,
            'edges_skipped': int,
            'half_life_days': int,
            'errors': List[str]
        }
    """
    from datetime import datetime, timedelta

    edges_updated = 0
    edges_skipped = 0
    errors = []

    try:
        with driver.session() as session:
            # Get all SATISFIES edges with their current state
            edges = session.run("""
                MATCH (i:Concept_Intent)-[r:SATISFIES]->(t:Concept_Tool)
                RETURN id(r) AS rel_id,
                       r.weight AS weight,
                       r.last_updated AS last_updated,
                       i.name AS intent,
                       t.name AS tool
            """).data()

            cutoff_date = datetime.utcnow() - timedelta(days=7)

            for edge in edges:
                last_updated = edge.get('last_updated')

                # Skip if no last_updated timestamp (shouldn't happen after Phase 2)
                if last_updated is None:
                    logger.debug(f"Skipping edge {edge['intent']}→{edge['tool']}: no last_updated")
                    edges_skipped += 1
                    continue

                # Parse datetime (Neo4j returns datetime objects or strings)
                if isinstance(last_updated, str):
                    try:
                        last_updated = datetime.fromisoformat(
                            last_updated.replace('Z', '+00:00')
                        )
                    except ValueError as e:
                        logger.warning(f"Could not parse last_updated for edge {edge['rel_id']}: {e}")
                        errors.append(f"Parse error: {edge['intent']}→{edge['tool']}")
                        edges_skipped += 1
                        continue

                # Convert Neo4j datetime to Python datetime if needed
                if hasattr(last_updated, 'to_native'):
                    last_updated = last_updated.to_native()

                # Make timezone-naive for comparison
                if hasattr(last_updated, 'tzinfo') and last_updated.tzinfo is not None:
                    last_updated = last_updated.replace(tzinfo=None)

                # Calculate days since last update
                days_since = (datetime.utcnow() - last_updated).days

                # Skip recently updated edges (last 7 days)
                if days_since < 7:
                    logger.debug(f"Skipping recent edge {edge['intent']}→{edge['tool']}: {days_since} days")
                    edges_skipped += 1
                    continue

                # Apply exponential decay
                current_weight = edge['weight']
                decay_factor = 0.5 ** (days_since / half_life_days)
                new_weight = 0.5 + (current_weight - 0.5) * decay_factor

                # Clamp to [0.0, 1.0]
                new_weight = max(0.0, min(1.0, new_weight))

                # Update edge weight
                try:
                    session.run("""
                        MATCH ()-[r:SATISFIES]->()
                        WHERE id(r) = $rel_id
                        SET r.weight = $new_weight,
                            r.decayed_at = datetime()
                    """, rel_id=edge['rel_id'], new_weight=new_weight)

                    logger.info(f"Decayed {edge['intent']}→{edge['tool']}: "
                               f"{current_weight:.3f} → {new_weight:.3f} "
                               f"(age: {days_since} days)")
                    edges_updated += 1

                except Exception as e:
                    logger.error(f"Failed to update edge {edge['rel_id']}: {e}")
                    errors.append(f"Update error: {edge['intent']}→{edge['tool']}")

    except Exception as e:
        logger.error(f"Weight decay failed: {e}")
        errors.append(f"Fatal error: {str(e)}")

    return {
        'edges_updated': edges_updated,
        'edges_skipped': edges_skipped,
        'half_life_days': half_life_days,
        'errors': errors
    }


# ─────────────────────────────────────────────
# MCP Tool Seeding (Concept Graph Phase 3)
# ─────────────────────────────────────────────

def seed_mcp_tools(driver, ollama_endpoint: str) -> dict:
    """
    Embed MCP tool descriptions and add them as Concept_Tool nodes with source='mcp'.

    Creates SATISFIES edges from relevant intents to MCP tools based on
    predefined intent→tool mappings.

    Args:
        driver: Neo4j driver for concept graph
        ollama_endpoint: Ollama API endpoint for embeddings

    Returns:
        {
            'seeded': int,
            'failed': int,
            'edges_created': int,
            'errors': List[str]
        }
    """
    # The canonical registry, shared with the MCP server and
    # GET /api/platform/tools. Before Cycle 6 this read a second, drifted list.
    from ..ai.mcp_tools import TOOL_DEFINITIONS

    seeded = 0
    failed = 0
    edges_created = 0
    errors = []

    try:
        with driver.session() as session:
            for tool in TOOL_DEFINITIONS:
                try:
                    # Embed tool description
                    embedding = embed_text(tool['description'], ollama_endpoint)

                    if embedding is None:
                        logger.warning(f"Failed to embed MCP tool {tool['name']}")
                        failed += 1
                        errors.append(f"Embedding failed: {tool['name']}")
                        continue

                    # Upsert tool node. `category` is the registry's own
                    # classification (TOOL_CATEGORIES) and rides along to the node
                    # so the graph can group tools the way the platform does.
                    session.run("""
                        MERGE (t:Concept_Tool {name: $name})
                        SET t.description = $description,
                            t.source = 'mcp',
                            t.active = true,
                            t.embedding = $embedding,
                            t.input_schema = $schema,
                            t.category = $category,
                            t.updated_at = datetime()
                    """,
                        name=tool['name'],
                        description=tool['description'],
                        embedding=embedding,
                        schema=json.dumps(tool.get('input_schema', {})),
                        category=tool.get('category')
                    )
                    seeded += 1
                    logger.info(f"Seeded MCP tool: {tool['name']}")

                except Exception as e:
                    failed += 1
                    errors.append(f"Failed to seed {tool['name']}: {str(e)}")
                    logger.error(f"Failed to seed MCP tool {tool['name']}: {e}")

        # Wire intent→tool SATISFIES edges for MCP tools
        # These mappings define which intents should route to which MCP tools
        mcp_intent_mappings = [
            ('data_lookup', 'query_knowledge_graph', 0.7),
            ('count_simple', 'query_knowledge_graph', 0.7),
            ('count_filtered', 'query_knowledge_graph', 0.7),
            ('summarize_dataset', 'summarize_dataset', 0.8),
            ('property_exploration', 'get_schema', 0.75),
            ('property_exploration', 'get_label_profile', 0.7),
        ]

        with driver.session() as session:
            for intent_name, tool_name, weight in mcp_intent_mappings:
                try:
                    session.run("""
                        MATCH (i:Concept_Intent {name: $intent})
                        MATCH (t:Concept_Tool {name: $tool})
                        MERGE (i)-[r:SATISFIES]->(t)
                        ON CREATE SET r.weight = $weight,
                                      r.usage_count = 0,
                                      r.last_updated = datetime()
                    """,
                        intent=intent_name,
                        tool=tool_name,
                        weight=weight
                    )
                    edges_created += 1
                except Exception as e:
                    errors.append(f"Failed to wire {intent_name}→{tool_name}: {str(e)}")
                    logger.error(f"Failed to wire edge {intent_name}→{tool_name}: {e}")

    except Exception as e:
        errors.append(f"Fatal error: {str(e)}")
        logger.error(f"MCP tool seeding failed: {e}")

    return {
        'seeded': seeded,
        'failed': failed,
        'edges_created': edges_created,
        'errors': errors
    }


# ─────────────────────────────────────────────
# Export/Import (Concept Graph Phase 3)
# ─────────────────────────────────────────────

def export_concept_graph(driver) -> dict:
    """
    Export complete Concept Graph state as portable JSON.

    Does NOT export embedding BLOBs - they are regenerated on import.

    Returns:
        {
            "scidk_concept_graph": "1.0",
            "exported_at": ISO timestamp,
            "source_instance": hostname,
            "intents": [...],
            "tools": [...],
            "satisfies_edges": [...],
            "retrieves_edges": [...]
        }
    """
    import socket

    try:
        with driver.session() as session:
            # Export intents (without embeddings)
            intents_result = session.run("""
                MATCH (i:Concept_Intent)
                RETURN i.name AS name,
                       i.description AS description,
                       i.examples AS examples,
                       CASE WHEN i.embedding IS NOT NULL THEN true ELSE false END AS embedding_present
                ORDER BY i.name
            """).data()

            # Export tools. `category` is null for tools seeded from intents.yaml,
            # which declares none; the MCP registry is the only source that sets it.
            tools_result = session.run("""
                MATCH (t:Concept_Tool)
                RETURN t.name AS name,
                       t.description AS description,
                       t.source AS source,
                       t.active AS active,
                       t.input_schema AS input_schema,
                       t.category AS category
                ORDER BY t.source, t.name
            """).data()

            # Export SATISFIES edges
            satisfies_result = session.run("""
                MATCH (i:Concept_Intent)-[r:SATISFIES]->(t:Concept_Tool)
                RETURN i.name AS intent,
                       t.name AS tool,
                       r.weight AS weight,
                       r.usage_count AS usage_count,
                       r.last_updated AS last_updated
                ORDER BY i.name, t.name
            """).data()

            # Convert Neo4j datetime to ISO string
            for edge in satisfies_result:
                if edge.get('last_updated'):
                    if hasattr(edge['last_updated'], 'isoformat'):
                        edge['last_updated'] = edge['last_updated'].isoformat()
                    elif hasattr(edge['last_updated'], 'to_native'):
                        edge['last_updated'] = edge['last_updated'].to_native().isoformat()

            # Export RETRIEVES edges
            retrieves_result = session.run("""
                MATCH (t:Concept_Tool)-[r:RETRIEVES]->(l:Concept_Label)
                RETURN t.name AS tool,
                       l.name AS label
                ORDER BY t.name, l.name
            """).data()

        return {
            "scidk_concept_graph": "1.0",
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "source_instance": socket.gethostname(),
            "intents": intents_result,
            "tools": tools_result,
            "satisfies_edges": satisfies_result,
            "retrieves_edges": retrieves_result
        }

    except Exception as e:
        logger.error(f"Concept graph export failed: {e}")
        raise


def import_concept_graph(driver, data: dict, ollama_endpoint: str) -> dict:
    """
    Import Concept Graph snapshot (non-destructive upsert).

    - Upserts intents and tools
    - Re-embeds intents whose descriptions changed
    - Upserts SATISFIES edges, preserving higher weight if conflict
    - Upserts RETRIEVES edges

    Args:
        driver: Neo4j driver for concept graph
        data: Exported concept graph JSON
        ollama_endpoint: Ollama API endpoint for re-embedding

    Returns:
        {
            'intents_imported': int,
            'tools_imported': int,
            'edges_imported': int,
            're_embedded': int,
            'errors': List[str]
        }
    """
    intents_imported = 0
    tools_imported = 0
    edges_imported = 0
    re_embedded = 0
    errors = []

    try:
        # Import intents
        with driver.session() as session:
            for intent in data.get('intents', []):
                try:
                    # Check if description changed
                    result = session.run("""
                        MATCH (i:Concept_Intent {name: $name})
                        RETURN i.description AS old_desc
                    """, name=intent['name']).single()

                    desc_changed = (result is None or
                                   result['old_desc'] != intent['description'])

                    # Upsert intent node
                    session.run("""
                        MERGE (i:Concept_Intent {name: $name})
                        SET i.description = $description,
                            i.examples = $examples
                    """,
                        name=intent['name'],
                        description=intent['description'],
                        examples=intent.get('examples', [])
                    )
                    intents_imported += 1

                    # Re-embed if description changed
                    if desc_changed and intent.get('embedding_present'):
                        embed_text_content = f"{intent['description']}\n" + "\n".join(intent.get('examples', []))
                        embedding = embed_text(embed_text_content, ollama_endpoint)
                        if embedding:
                            session.run("""
                                MATCH (i:Concept_Intent {name: $name})
                                SET i.embedding = $embedding
                            """, name=intent['name'], embedding=embedding)
                            re_embedded += 1

                except Exception as e:
                    errors.append(f"Failed to import intent {intent.get('name')}: {str(e)}")

        # Import tools
        with driver.session() as session:
            for tool in data.get('tools', []):
                try:
                    # Upsert tool node (do not overwrite embeddings).
                    #
                    # `category` goes through coalesce rather than a plain SET: in
                    # Cypher `SET t.category = null` *removes* the property, so a
                    # snapshot taken before Cycle 8 — which carries no category at
                    # all — would strip it off every tool it touched. Falling back
                    # to the node's own value keeps the import non-destructive,
                    # which is what this function promises.
                    session.run("""
                        MERGE (t:Concept_Tool {name: $name})
                        SET t.description = $description,
                            t.source = $source,
                            t.active = $active,
                            t.input_schema = $input_schema,
                            t.category = coalesce($category, t.category)
                    """,
                        name=tool['name'],
                        description=tool.get('description'),
                        source=tool.get('source', 'internal'),
                        active=tool.get('active', True),
                        input_schema=tool.get('input_schema'),
                        category=tool.get('category')
                    )
                    tools_imported += 1

                except Exception as e:
                    errors.append(f"Failed to import tool {tool.get('name')}: {str(e)}")

        # Import SATISFIES edges (preserve higher weight)
        with driver.session() as session:
            for edge in data.get('satisfies_edges', []):
                try:
                    session.run("""
                        MATCH (i:Concept_Intent {name: $intent})
                        MATCH (t:Concept_Tool {name: $tool})
                        MERGE (i)-[r:SATISFIES]->(t)
                        ON CREATE SET r.weight = $weight,
                                      r.usage_count = $usage_count,
                                      r.last_updated = datetime($last_updated)
                        ON MATCH SET r.weight = CASE
                                        WHEN $weight > r.weight THEN $weight
                                        ELSE r.weight
                                     END,
                                     r.usage_count = $usage_count
                    """,
                        intent=edge['intent'],
                        tool=edge['tool'],
                        weight=edge.get('weight', 0.5),
                        usage_count=edge.get('usage_count', 0),
                        last_updated=edge.get('last_updated')
                    )
                    edges_imported += 1

                except Exception as e:
                    errors.append(f"Failed to import edge {edge.get('intent')}→{edge.get('tool')}: {str(e)}")

        # Import RETRIEVES edges
        with driver.session() as session:
            for edge in data.get('retrieves_edges', []):
                try:
                    session.run("""
                        MATCH (t:Concept_Tool {name: $tool})
                        MERGE (l:Concept_Label {name: $label})
                        MERGE (t)-[:RETRIEVES]->(l)
                    """,
                        tool=edge['tool'],
                        label=edge['label']
                    )

                except Exception as e:
                    errors.append(f"Failed to import RETRIEVES edge: {str(e)}")

    except Exception as e:
        errors.append(f"Fatal error: {str(e)}")
        logger.error(f"Concept graph import failed: {e}")

    return {
        'intents_imported': intents_imported,
        'tools_imported': tools_imported,
        'edges_imported': edges_imported,
        're_embedded': re_embedded,
        'errors': errors
    }
