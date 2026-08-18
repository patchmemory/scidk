"""
MCP Tool Implementations for SciDK.

This module contains the actual tool logic that's exposed via the MCP server.
Keeping tools separate from the server allows them to be:
- Tested independently
- Reused in other contexts (web API, CLI, etc.)
- Documented with their schemas in one place
"""
import logging
import os
import re
import sqlite3
from typing import Dict, Any, List, Optional, Set
from neo4j import Driver

from .schema_context import get_schema_context

logger = logging.getLogger(__name__)


# Clauses that mutate the graph. Checked as whole tokens, never as substrings —
# `created_at`, `dataset`, and `OFFSET` all contain a forbidden keyword as a
# substring and are perfectly valid in a read query.
FORBIDDEN_KEYWORDS = frozenset(
    {'CREATE', 'MERGE', 'DELETE', 'REMOVE', 'SET', 'DROP', 'DETACH'}
)


# Guard for identifiers that must be interpolated into Cypher rather than
# passed as parameters. Same pattern as canvas_service._LABEL_RE / _REL_RE,
# which guards the write path; kept local so importing this module does not
# pull in the services layer (the MCP server runs as its own process).
#
# Interpolation rather than `WHERE $label IN labels(n)` is deliberate here.
# Parameterizing the label removes it from the node pattern, so Neo4j can no
# longer use the label index and each of these reads degrades into a scan of
# the entire graph. The pattern below admits no backtick, whitespace, or
# operator character, so a label that passes it cannot escape the quoting.
_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _validate_identifier(value: Any, kind: str) -> Optional[str]:
    """Return an error message if ``value`` is unsafe to interpolate, else None.

    Args:
        value: The caller-supplied label or relationship type.
        kind: What the value names, for the error message ("label"/"relationship").
    """
    if not isinstance(value, str) or not value:
        return f"Invalid {kind}: expected a non-empty string, got {value!r}."
    if not _IDENTIFIER_RE.match(value):
        return (
            f"Invalid {kind} {value!r}: must start with a letter or underscore "
            "and contain only letters, digits, and underscores."
        )
    return None


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


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry — the single source of truth for what SciDK exposes as a tool.
#
# Three consumers read this list and nothing else defines a tool:
#   1. the MCP server's `list_tools` handler (scidk/mcp_server.py)
#   2. Concept Graph seeding (concept_graph_service.seed_mcp_tools), which embeds
#      `description` and stores `input_schema` on the :Concept_Tool node
#   3. GET /api/platform/tools (scidk/web/routes/api_platform.py), the in-app
#      "what this platform can do" display
#
# Until Cycle 6 there were two lists — MCP_TOOL_DEFINITIONS for seeding, this one
# for MCP — and they had already drifted. The seeding copy carried a `parameters`
# pseudo-schema (`{"cypher": "string"}`) that omitted query_knowledge_graph's
# `parameters` argument and claimed get_schema took none, while the functions
# below accept both; that copy is gone. Its *prose* was the better of the two and
# has been kept, so descriptions here are longer than they were on the MCP side.
#
# Entry shape: {name, description, input_schema, category}. `input_schema` is
# snake_case to match the `input_schema` property on :Concept_Tool nodes and the
# key `seed_tools_from_yaml` reads from intents.yaml; mcp_server.py maps it to
# MCP's `inputSchema` at the protocol boundary, so the wire format is unchanged.
# ─────────────────────────────────────────────────────────────────────────────

#: Categories a registry entry may declare. Drives the UI filter on
#: GET /api/platform/tools; a tool naming anything else is a bug, not a new
#: category, so `get_tool_definitions` rejects unknown values rather than
#: answering with an empty list.
TOOL_CATEGORIES = ('data_query', 'schema', 'summarization')


TOOL_DEFINITIONS = [
    {
        "name": "query_knowledge_graph",
        "description": "Execute a read-only Cypher query against the SciDK research knowledge graph. Returns structured results. Automatically blocks all write operations (CREATE/MERGE/DELETE). Use this to retrieve data, count nodes, or explore relationships.",
        "category": "data_query",
        "input_schema": {
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
        "description": "Return the current schema of the knowledge graph including all node labels, relationship types, and key properties per label. Essential for understanding what data is available before querying.",
        "category": "schema",
        "input_schema": {
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
        "description": "Generate a statistical summary of the knowledge graph, or of a single label or relationship type when one is named: node counts per label and relationship counts per type. Useful for a dataset overview before querying in detail.",
        "category": "summarization",
        "input_schema": {
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
        "description": "Return the Schema Intelligence profile for a specific node label: node count, description, chat context mode, always/never include pins, properties in usage-rank order from the Schema Intelligence Layer, and relationship patterns.",
        "category": "schema",
        "input_schema": {
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
        "description": "List all node labels in the knowledge graph with their node counts, sorted by count descending. Quick overview of what types of data exist.",
        "category": "schema",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


def get_tool_definitions(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the canonical tool registry, optionally narrowed to one category.

    Args:
        category: One of ``TOOL_CATEGORIES``, or None for the whole registry.

    Returns:
        A new list of the matching registry entries. The entry dicts themselves
        are the module-level ones, not copies — read them, do not mutate them.

    Raises:
        ValueError: if ``category`` is not a known category. An unrecognised
            category is a caller mistake; answering it with ``[]`` would read as
            "no tool does that", which is a different and wrong statement.
    """
    if category is None:
        return list(TOOL_DEFINITIONS)
    if category not in TOOL_CATEGORIES:
        raise ValueError(
            f"Unknown category {category!r}: expected one of "
            f"{', '.join(TOOL_CATEGORIES)}."
        )
    return [tool for tool in TOOL_DEFINITIONS if tool['category'] == category]


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
    # Same interpolation guard as get_label_profile: both identifiers land
    # inside backticks in the patterns below, and both come from the caller.
    invalid = (
        _validate_identifier(label, 'label') if label
        else _validate_identifier(relationship, 'relationship') if relationship
        else None
    )
    if invalid:
        return {"status": "error", "summary": None, "error": invalid}

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


# Ceiling on the property keys pulled from Neo4j before ranking is applied.
# Ranking can only reorder what this query returned, so the cap is generous
# rather than presentational; a label carrying more distinct keys than this has
# the rest dropped, and `properties_truncated` says so in the response.
MAX_PROPERTY_KEYS = 200


def _settings_db_path(explicit: Optional[str] = None) -> str:
    """Resolve scidk_settings.db the way scidk.app._resolve_settings_db_path does.

    The MCP server runs as its own process with no Flask app, so app.config is
    not available here — the env var and the cwd default are.
    """
    return explicit or os.environ.get('SCIDK_SETTINGS_DB') or 'scidk_settings.db'


def _open_settings_db(path: str) -> Optional[sqlite3.Connection]:
    """Open the settings DB, or return None if it is not there.

    Deliberately does not create the file: sqlite3.connect() on a missing path
    would leave an empty database behind in whatever directory the MCP server
    happened to start in, and an empty database is indistinguishable from a real
    one with no Schema Intelligence rows. Nothing here writes to it.
    """
    if not os.path.exists(path):
        return None
    try:
        return sqlite3.connect(path)
    except Exception:
        return None


def get_label_profile(
    driver: Driver,
    label: str,
    database: str = "neo4j",
    sqlite_conn=None,
    settings_db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get the Schema Intelligence profile for a specific label.

    Neo4j supplies the facts about the graph — node count, which property keys
    exist and how often, outgoing relationships. The Schema Intelligence layer
    in scidk_settings.db supplies how that label should be *presented*: its
    description, its chat context mode, the always/never include pins, and the
    usage-weighted property ranking. Properties come back in rank order with
    never_include dropped and always_include pinned to the front, which is the
    same shaping the chat path gets from get_enriched_schema_context.

    Falls back to raw frequency order when the settings database or the SI
    tables are unreachable, and to SI defaults when the label simply has no
    label_profile row. Either way `schema_intelligence` in the response says
    which happened.

    Args:
        driver: Neo4j driver instance
        label: Label name to get profile for
        database: Database name (default "neo4j")
        sqlite_conn: Open connection to scidk_settings.db. When omitted, one is
            opened from settings_db_path and closed before returning.
        settings_db_path: Override for the settings DB location. Defaults to
            $SCIDK_SETTINGS_DB, then scidk_settings.db in the cwd.

    Returns:
        {
            "status": "success" | "error",
            "profile": {
                "label": str,
                "node_count": int,
                "description": str | null,
                "chat_context_mode": "top_n" | "all" | "exclude",
                "chat_context_n": int,
                "always_include": [str],
                "never_include": [str],
                "properties": [{"name": str, "frequency": int}],
                "properties_truncated": bool,
                "chat_context_properties": [str],
                "relationships": [...],
                "schema_intelligence": "applied" | "unavailable"
            } | null,
            "error": str | null
        }
    """
    # The label is interpolated into the node patterns below to keep the label
    # index in play, so it must be validated first — a backtick would otherwise
    # escape the quoting, and the write-keyword filter does not cover this path.
    invalid = _validate_identifier(label, 'label')
    if invalid:
        return {"status": "error", "profile": None, "error": invalid}

    try:
        # Get node count
        count_query = f"MATCH (n:`{label}`) RETURN count(n) as count"

        with driver.session(database=database) as session:
            count_result = session.run(count_query)
            count_record = count_result.single()
            node_count = count_record['count'] if count_record else 0

            # Get properties with frequency. Frequency order is only the input
            # to ranking below, not the order returned to the caller.
            props_query = f"""
            MATCH (n:`{label}`)
            UNWIND keys(n) AS prop
            WITH prop, count(*) as freq
            RETURN prop, freq
            ORDER BY freq DESC
            LIMIT {MAX_PROPERTY_KEYS}
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

        # Shape the Neo4j facts through the Schema Intelligence layer. Done
        # outside the driver session — it reads SQLite, not Neo4j.
        si = _apply_schema_intelligence(
            label, properties, sqlite_conn, settings_db_path
        )

        return {
            "status": "success",
            "profile": {
                "label": label,
                "node_count": node_count,
                "properties_truncated": len(properties) >= MAX_PROPERTY_KEYS,
                "relationships": relationships,
                **si,
            },
            "error": None
        }

    except Exception as e:
        return {
            "status": "error",
            "profile": None,
            "error": str(e)
        }


def _apply_schema_intelligence(
    label: str,
    properties: List[Dict[str, Any]],
    sqlite_conn=None,
    settings_db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Reorder `properties` by usage rank and attach the label's SI profile.

    `properties` arrives in Neo4j frequency order. Returns the profile fields
    plus a `properties` list reordered by ``get_ranked_properties`` — pinned
    first, then ranked, then unranked — with ``never_include`` dropped.

    Never raises: on any failure the caller keeps frequency order and the
    response reports ``schema_intelligence: 'unavailable'``.
    """
    frequencies = {p['name']: p['frequency'] for p in properties}
    fallback = {
        'description': None,
        'chat_context_mode': 'top_n',
        'chat_context_n': 5,
        'always_include': [],
        'never_include': [],
        'properties': properties,
        'chat_context_properties': [p['name'] for p in properties[:5]],
        'schema_intelligence': 'unavailable',
    }

    conn = sqlite_conn
    opened_here = False
    if conn is None:
        conn = _open_settings_db(_settings_db_path(settings_db_path))
        if conn is None:
            return fallback
        opened_here = True

    try:
        # Imported here rather than at module scope: schema_intelligence pulls in
        # numpy and requests for the embedding phases, and the MCP server should
        # not pay for those on import.
        from ..services import schema_intelligence as si

        profile = si.get_label_profile(label, conn)
        all_names = list(frequencies.keys())

        ranked = si.get_ranked_properties(
            label_name=label,
            sqlite_conn=conn,
            all_properties=all_names,
            top_n=0,  # 0 = no truncation; this tool reports the whole label
            always_include=profile['always_include'],
            never_include=profile['never_include'],
        )

        # What the chat path would actually put in the prompt for this label.
        # Mirrors get_enriched_schema_context, including its handling of
        # chat_context_mode: 'exclude' drops the label, and every other mode
        # truncates to chat_context_n.
        if profile['chat_context_mode'] == 'exclude':
            chat_context = []
        else:
            chat_context = si.get_ranked_properties(
                label_name=label,
                sqlite_conn=conn,
                all_properties=all_names,
                top_n=profile['chat_context_n'],
                always_include=profile['always_include'],
                never_include=profile['never_include'],
            )

        return {
            **profile,
            'properties': [
                {'name': name, 'frequency': frequencies.get(name, 0)}
                for name in ranked
            ],
            'chat_context_properties': chat_context,
            'schema_intelligence': 'applied',
        }

    except Exception as e:  # noqa: BLE001
        # A missing table, a locked database, an import failure — the graph facts
        # are still worth returning, so degrade instead of failing the tool.
        logger.warning(
            "Schema Intelligence unavailable for label %r, "
            "falling back to frequency order: %s", label, e
        )
        return fallback
    finally:
        if opened_here:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


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
