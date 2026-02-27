"""
Neo4j Schema Grounding for Chat.

Prevents LLM hallucination by injecting actual database schema into prompts.
This is THE differentiator: generic Neo4j chatbots hallucinate labels/relationships.

Performance: Schema caching with 5-min TTL is critical to reduce prefill time.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import time


class SchemaCache:
    """
    Simple in-memory cache for Neo4j schema with TTL.

    Critical for performance: Avoids repeated Neo4j queries and reduces LLM prefill time.
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize schema cache.

        Args:
            ttl_seconds: Time-to-live in seconds (default 5 minutes)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached schema if not expired."""
        if key not in self._cache:
            return None

        # Check expiration
        if time.time() - self._timestamps[key] > self.ttl_seconds:
            # Expired - remove from cache
            del self._cache[key]
            del self._timestamps[key]
            return None

        return self._cache[key]

    def set(self, key: str, value: Dict[str, Any]):
        """Store schema in cache with current timestamp."""
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def clear(self):
        """Clear all cached schemas."""
        self._cache.clear()
        self._timestamps.clear()


# Global schema cache (shared across requests)
_schema_cache = SchemaCache(ttl_seconds=300)  # 5 minutes


def get_schema_context(neo4j_driver, database: str = "neo4j", max_labels: int = 50, max_props_per_label: int = 5) -> Dict[str, Any]:
    """
    Query Neo4j for schema information and return structured context.

    Optimized for lean context to reduce LLM prefill time:
    - Limit to top 50 labels (truncate large schemas)
    - Limit to 5 most common properties per label
    - Cache results for 5 minutes

    Args:
        neo4j_driver: Neo4j driver instance
        database: Database name (default "neo4j")
        max_labels: Maximum number of labels to include (default 50)
        max_props_per_label: Max properties per label (default 5)

    Returns:
        Dict with keys:
            - labels: List[str]
            - relationships: List[str]
            - properties: Dict[label, List[str]]
            - label_counts: Dict[label, int] (optional, for ranking)
            - cached: bool (whether result came from cache)
            - cached_at: float (timestamp if cached)
    """
    cache_key = f"schema:{database}"

    # Check cache first
    cached = _schema_cache.get(cache_key)
    if cached:
        cached['cached'] = True
        return cached

    # Query Neo4j for schema
    with neo4j_driver.session(database=database) as session:
        # Get labels
        labels_result = session.run("CALL db.labels() YIELD label RETURN label")
        all_labels = [record["label"] for record in labels_result]

        # Get label counts to rank by usage (most-used labels first)
        label_counts = {}
        for label in all_labels[:max_labels]:  # Limit to avoid long query
            try:
                count_result = session.run(f"MATCH (n:`{label}`) RETURN count(n) as count")
                label_counts[label] = count_result.single()["count"]
            except Exception:
                # Skip labels that cause errors (invalid syntax, etc.)
                label_counts[label] = 0

        # Sort labels by usage, take top N
        sorted_labels = sorted(label_counts.keys(), key=lambda l: label_counts[l], reverse=True)
        labels = sorted_labels[:max_labels]

        # Get relationship types
        rels_result = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        relationships = [record["relationshipType"] for record in rels_result]

        # Get property keys per label (limit to top N most common)
        properties = {}
        for label in labels:
            try:
                props_result = session.run(
                    f"""
                    MATCH (n:`{label}`)
                    UNWIND keys(n) AS key
                    RETURN key, count(*) as freq
                    ORDER BY freq DESC
                    LIMIT {max_props_per_label}
                    """
                )
                properties[label] = [record["key"] for record in props_result]
            except Exception:
                # Skip labels with query issues
                properties[label] = []

    schema = {
        "labels": labels,
        "relationships": relationships,
        "properties": properties,
        "label_counts": label_counts,
        "cached": False,
        "cached_at": None
    }

    # Cache result
    _schema_cache.set(cache_key, schema)
    schema['cached_at'] = time.time()

    return schema


def build_system_prompt(schema: Dict[str, Any], base_prompt: Optional[str] = None) -> str:
    """
    Build LLM system prompt with injected Neo4j schema.

    Keeps context LEAN to minimize prefill time.

    Args:
        schema: Schema dict from get_schema_context()
        base_prompt: Optional base instructions (default: generic assistant)

    Returns:
        Complete system prompt with schema context
    """
    if base_prompt is None:
        base_prompt = """You are a research data assistant for SciDK, a scientific data management platform.
You help researchers find, understand, and query data stored in Neo4j knowledge graphs.

Guidelines:
- Answer concisely for factual questions (1-3 sentences)
- Be thorough for complex queries requiring reasoning
- Never fabricate data, labels, relationships, or results
- If context doesn't contain needed information, say so clearly"""

    # Format schema for injection
    labels_str = ", ".join(schema["labels"])
    rels_str = ", ".join(schema["relationships"])

    # Format properties (show only top 3 per label for brevity)
    props_lines = []
    for label in schema["labels"][:20]:  # Show props for top 20 labels only
        props = schema["properties"].get(label, [])
        if props:
            props_lines.append(f"  - {label}: {', '.join(props[:3])}")

    props_str = "\n".join(props_lines) if props_lines else "  (No property info available)"

    # Schema context section
    schema_context = f"""
Connected Neo4j Database Schema:
- Node Labels: {labels_str}
- Relationship Types: {rels_str}
- Key Properties by Label:
{props_str}

CRITICAL RULES FOR CYPHER GENERATION:
1. ONLY use labels and relationship types listed above
2. Never invent or guess labels/relationships
3. Use LIMIT clauses unless user wants all results
4. Prefer MATCH + WHERE over complex subqueries
5. If query can't be answered with available schema, explain what's missing
"""

    return f"{base_prompt}\n{schema_context}"


def refresh_schema_cache():
    """
    Force refresh of schema cache.

    Useful for /api/chat/context/refresh endpoint or after schema changes.
    """
    _schema_cache.clear()


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for observability.

    Returns:
        Dict with cache size, keys, timestamps
    """
    return {
        "size": len(_schema_cache._cache),
        "keys": list(_schema_cache._cache.keys()),
        "timestamps": {k: datetime.fromtimestamp(v).isoformat() for k, v in _schema_cache._timestamps.items()},
        "ttl_seconds": _schema_cache.ttl_seconds
    }
