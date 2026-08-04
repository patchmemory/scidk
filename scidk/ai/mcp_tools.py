"""
MCP Tool Implementations for SciDK.

This module contains the actual tool logic that's exposed via the MCP server.
Keeping tools separate from the server allows them to be:
- Tested independently
- Reused in other contexts (web API, CLI, etc.)
- Documented with their schemas in one place
"""
import re
from typing import Dict, Any, List, Optional, Set
from neo4j import Driver

from .schema_context import get_schema_context


# Clauses that mutate the graph. Checked as whole tokens, never as substrings —
# `created_at`, `dataset`, and `OFFSET` all contain a forbidden keyword as a
# substring and are perfectly valid in a read query.
FORBIDDEN_KEYWORDS = frozenset(
    {'CREATE', 'MERGE', 'DELETE', 'REMOVE', 'SET', 'DROP', 'DETACH'}
)


def _cypher_tokens(cypher: str) -> Set[str]:
    """Split Cypher into upper-cased word tokens for keyword matching.

    Splitting on ``\\W+`` isolates every keyword, because Cypher requires a
    non-word character (whitespace, parenthesis, colon, comma, operator) on
    both sides of a clause keyword. That holds for the operator spellings too:
    ``IS NULL`` and ``STARTS WITH`` split into their own word tokens, and
    punctuation-only operators like ``<>`` and ``->`` split into empty strings,
    which never match a keyword.

    The check stays deliberately conservative in one direction: string literals
    and comments are tokenized along with the query, so a read query containing
    the word ``set`` inside a quoted value is rejected. Stripping literals first
    would need to model quote escaping correctly, and getting that wrong would
    let a real write clause through — for a safety filter, a false rejection is
    the better failure.
    """
    return set(re.split(r'\W+', cypher.upper()))


# MCP tool definitions for Concept Graph seeding
# Simplified format for embedding into Concept Graph as :Concept_Tool nodes
MCP_TOOL_DEFINITIONS = [
    {
        "name": "query_knowledge_graph",
        "description": "Execute a read-only Cypher query against the SciDK research knowledge graph. Returns structured results. Automatically blocks all write operations (CREATE/MERGE/DELETE). Use this to retrieve data, count nodes, or explore relationships.",
        "parameters": {"cypher": "string", "limit": "integer"}
    },
    {
        "name": "get_schema",
        "description": "Return the current schema of the knowledge graph including all node labels, relationship types, and key properties per label. Essential for understanding what data is available before querying.",
        "parameters": {}
    },
    {
        "name": "summarize_dataset",
        "description": "Generate a statistical summary of the entire knowledge graph: node counts per label, relationship counts per type, and key property distributions. Useful for dataset overview.",
        "parameters": {"label": "string (optional)", "relationship": "string (optional)"}
    },
    {
        "name": "get_label_profile",
        "description": "Return the Schema Intelligence profile for a specific node label, including description, chat context mode, always/never include properties, and property usage rankings from the Schema Intelligence Layer.",
        "parameters": {"label": "string"}
    },
    {
        "name": "list_labels",
        "description": "List all node labels in the knowledge graph with their node counts, sorted by count descending. Quick overview of what types of data exist.",
        "parameters": {}
    },
]


# Tool definitions with full JSON schemas (for MCP server registration)
TOOL_DEFINITIONS = [
    {
        "name": "query_knowledge_graph",
        "description": "Execute a safe read-only Cypher query against the Neo4j knowledge graph. Returns structured results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cypher": {
                    "type": "string",
                    "description": "Cypher query string (read-only, no CREATE/MERGE/DELETE)"
                },
                "parameters": {
                    "type": "object",
                    "description": "Optional query parameters for parameterized queries"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of rows to return (default 50)"
                }
            },
            "required": ["cypher"]
        }
    },
    {
        "name": "get_schema",
        "description": "Get the current Neo4j schema including labels, relationships, and properties. Essential for understanding what data is available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_labels": {
                    "type": "integer",
                    "description": "Maximum number of labels to return (default 50)"
                },
                "max_props_per_label": {
                    "type": "integer",
                    "description": "Max properties per label (default 5)"
                }
            }
        }
    },
    {
        "name": "summarize_dataset",
        "description": "Generate statistical summary of the dataset or specific label/relationship. Provides counts, distributions, and patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Optional specific label to summarize"
                },
                "relationship": {
                    "type": "string",
                    "description": "Optional specific relationship to summarize"
                }
            }
        }
    },
    {
        "name": "get_label_profile",
        "description": "Get detailed Schema Intelligence profile for a specific label, including property rankings and relationship patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Label name to get profile for"
                }
            },
            "required": ["label"]
        }
    },
    {
        "name": "list_labels",
        "description": "Get all label names with their node counts, sorted by count descending.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


def query_knowledge_graph(
    driver: Driver,
    cypher: str,
    database: str = "neo4j",
    parameters: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = 50
) -> Dict[str, Any]:
    """
    Execute a safe read-only Cypher query against the Neo4j knowledge graph.

    Safety features:
    - Blocks write keywords (CREATE, MERGE, DELETE, etc.) as whole tokens, so
      read queries mentioning `created_at`, `dataset`, or `OFFSET` are allowed
    - Adds LIMIT if not present
    - Parameterized queries supported

    Args:
        driver: Neo4j driver instance
        cypher: Cypher query string (read-only)
        database: Database name (default "neo4j")
        parameters: Optional query parameters for parameterized queries
        limit: Max number of rows to return (default 50)

    Returns:
        {
            "status": "success" | "error",
            "rows": [...] | null,
            "row_count": int,
            "error": str | null
        }
    """
    # Safety check: block write operations. Token matching, not substring
    # matching — see _cypher_tokens.
    tokens = _cypher_tokens(cypher)
    found = tokens & FORBIDDEN_KEYWORDS

    if found:
        keyword = sorted(found)[0]
        return {
            "status": "error",
            "rows": None,
            "row_count": 0,
            "error": f"Forbidden keyword '{keyword}' detected. Only read-only queries allowed."
        }

    # Add LIMIT if not present. Also a token check: a query selecting a property
    # named `limit_value` has no LIMIT clause and still needs one appended.
    if 'LIMIT' not in tokens:
        cypher = f"{cypher.rstrip(';')} LIMIT {limit}"

    try:
        with driver.session(database=database) as session:
            result = session.run(cypher, parameters or {})
            rows = [dict(record) for record in result]

            return {
                "status": "success",
                "rows": rows,
                "row_count": len(rows),
                "error": None
            }

    except Exception as e:
        return {
            "status": "error",
            "rows": None,
            "row_count": 0,
            "error": str(e)
        }


def get_schema(
    driver: Driver,
    database: str = "neo4j",
    max_labels: int = 50,
    max_props_per_label: int = 5
) -> Dict[str, Any]:
    """
    Get the current Neo4j schema (labels, relationships, properties).

    Uses the Schema Intelligence layer's cached schema retrieval.

    Args:
        driver: Neo4j driver instance
        database: Database name (default "neo4j")
        max_labels: Maximum number of labels to return (default 50)
        max_props_per_label: Max properties per label (default 5)

    Returns:
        {
            "status": "success" | "error",
            "schema": {
                "labels": [...],
                "relationships": [...],
                "properties": {...},
                "label_counts": {...}
            } | null,
            "error": str | null
        }
    """
    try:
        schema = get_schema_context(
            driver,
            database=database,
            max_labels=max_labels,
            max_props_per_label=max_props_per_label
        )

        return {
            "status": "success",
            "schema": {
                "labels": schema.get("labels", []),
                "relationships": schema.get("relationships", []),
                "properties": schema.get("properties", {}),
                "label_counts": schema.get("label_counts", {})
            },
            "error": None
        }

    except Exception as e:
        return {
            "status": "error",
            "schema": None,
            "error": str(e)
        }


def summarize_dataset(
    driver: Driver,
    database: str = "neo4j",
    label: Optional[str] = None,
    relationship: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate statistical summary of the dataset or specific label/relationship.

    This is a basic implementation that returns node/relationship counts.
    Future enhancement: integrate with the full summarization pipeline.

    Args:
        driver: Neo4j driver instance
        database: Database name (default "neo4j")
        label: Optional specific label to summarize
        relationship: Optional specific relationship to summarize

    Returns:
        {
            "status": "success" | "error",
            "summary": str | null,
            "error": str | null
        }
    """
    try:
        if label:
            query = f"""
            MATCH (n:`{label}`)
            WITH count(n) as node_count, labels(n) as label_list
            RETURN node_count, label_list[0] as label
            """
        elif relationship:
            query = f"""
            MATCH ()-[r:`{relationship}`]->()
            RETURN count(r) as rel_count, type(r) as rel_type
            """
        else:
            query = """
            MATCH (n)
            WITH count(n) as total_nodes
            CALL db.labels() YIELD label
            RETURN total_nodes, count(label) as label_count
            """

        with driver.session(database=database) as session:
            result = session.run(query)
            record = result.single()

            if record:
                summary = f"Dataset summary: {dict(record)}"
            else:
                summary = "No data found"

            return {
                "status": "success",
                "summary": summary,
                "error": None
            }

    except Exception as e:
        return {
            "status": "error",
            "summary": None,
            "error": str(e)
        }


def get_label_profile(
    driver: Driver,
    label: str,
    database: str = "neo4j"
) -> Dict[str, Any]:
    """
    Get the Schema Intelligence profile for a specific label.

    Returns property rankings, usage statistics, and relationship patterns.

    Args:
        driver: Neo4j driver instance
        label: Label name to get profile for
        database: Database name (default "neo4j")

    Returns:
        {
            "status": "success" | "error",
            "profile": {
                "label": str,
                "node_count": int,
                "properties": [...],
                "relationships": [...]
            } | null,
            "error": str | null
        }
    """
    try:
        # Get node count
        count_query = f"MATCH (n:`{label}`) RETURN count(n) as count"

        with driver.session(database=database) as session:
            count_result = session.run(count_query)
            count_record = count_result.single()
            node_count = count_record['count'] if count_record else 0

            # Get properties with frequency
            props_query = f"""
            MATCH (n:`{label}`)
            UNWIND keys(n) AS prop
            WITH prop, count(*) as freq
            RETURN prop, freq
            ORDER BY freq DESC
            LIMIT 20
            """

            props_result = session.run(props_query)
            properties = [
                {"name": record["prop"], "frequency": record["freq"]}
                for record in props_result
            ]

            # Get relationships
            rels_query = f"""
            MATCH (n:`{label}`)-[r]->(m)
            WITH type(r) as rel_type, labels(m) as target_labels, count(*) as freq
            RETURN rel_type, target_labels[0] as target_label, freq
            ORDER BY freq DESC
            LIMIT 10
            """

            rels_result = session.run(rels_query)
            relationships = [
                {
                    "type": record["rel_type"],
                    "target": record["target_label"],
                    "frequency": record["freq"]
                }
                for record in rels_result
            ]

            return {
                "status": "success",
                "profile": {
                    "label": label,
                    "node_count": node_count,
                    "properties": properties,
                    "relationships": relationships
                },
                "error": None
            }

    except Exception as e:
        return {
            "status": "error",
            "profile": None,
            "error": str(e)
        }


def list_labels(
    driver: Driver,
    database: str = "neo4j"
) -> Dict[str, Any]:
    """
    Get all label names with their node counts.

    Args:
        driver: Neo4j driver instance
        database: Database name (default "neo4j")

    Returns:
        {
            "status": "success" | "error",
            "labels": [
                {"name": str, "count": int},
                ...
            ] | null,
            "error": str | null
        }
    """
    try:
        with driver.session(database=database) as session:
            # Get all labels
            labels_result = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [record["label"] for record in labels_result]

            # Get counts for each label
            label_data = []
            for label in labels:
                count_result = session.run(f"MATCH (n:`{label}`) RETURN count(n) as count")
                count_record = count_result.single()
                count = count_record['count'] if count_record else 0
                label_data.append({"name": label, "count": count})

            # Sort by count descending
            label_data.sort(key=lambda x: x["count"], reverse=True)

            return {
                "status": "success",
                "labels": label_data,
                "error": None
            }

    except Exception as e:
        return {
            "status": "error",
            "labels": None,
            "error": str(e)
        }
