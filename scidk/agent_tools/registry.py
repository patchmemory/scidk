"""The agent tool registry: every SciDK tool, defined once.

Moved from scidk/ai/mcp_tools.py (which re-exports it). Each entry is plain data
(name, description, input_schema, category); handlers live in ``_HANDLERS`` so
the definitions stay JSON-serialisable for /api/platform/tools and seeding.

``run_tool`` checks the current disclosure authority before execution. Legacy
unscoped handlers are suspended; only a future explicitly scoped template may
release records. Scoped knowledge tools use the shared authenticated boundary;
``openai_functions`` returns only permitted runtime definitions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import tools_graph, tools_sql
from .disclosure import SharingPolicy

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry — the single source of truth for what SciDK exposes as a tool.
#
# Three consumers read this list and nothing else defines a tool:
#   1. the MCP server's `list_tools` handler (scidk/mcp_server.py)
#   2. Concept Graph seeding (concept_graph_service.seed_mcp_tools), which embeds
#      `description` and stores `input_schema` on the :Concept_Tool node
#   3. GET /api/platform/tools (scidk/web/routes/api_platform.py), the in-app
#      "what this platform can do" display
#   4. the agent adapters (Parley Task 5): run_tool(), openai_functions(), the
#      HTTP routes in api_agent.py. Every one of them goes through run_tool, so
#      every result passes disclosure.filter_for_agent
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
TOOL_CATEGORIES = ('data_query', 'schema', 'summarization', 'files')


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
    },
    {
        "name": "count_nodes",
        "description": "Count nodes with one label in the knowledge graph, optionally only those whose properties equal given values (e.g. label 'ImagingSession', where {'modality': 'MRI'}). Cheaper and more reliable than writing a count query.",
        "category": "summarization",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Node label to count, e.g. 'Subject'"},
                "where": {"type": "object", "description": "Optional property equality filters, e.g. {\"modality\": \"MRI\"}"}
            },
            "required": ["label"]
        }
    },
    {
        "name": "scan_summary",
        "description": "List the file scans in SciDK's file index (newest first): root folder, status, file and folder counts, whether committed to the graph. Pass scan_id for one scan's top file extensions, total bytes and host. Works without the knowledge graph; use it for questions about what storage has been scanned.",
        "category": "files",
        "input_schema": {
            "type": "object",
            "properties": {
                "scan_id": {"type": "string", "description": "Optional scan id from a previous scan_summary result"}
            }
        }
    },
    {
        "name": "list_collections",
        "description": "List collections: datasets grouped by deepest folder with a single profile family, with inferred owner, lab and project and their confidence. Optional equality filters on collection fields (e.g. {\"owner\": \"Anderson Scott\"}). Returns at most 50 plus the total.",
        "category": "files",
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object", "description": "Optional field equality filters"}
            }
        }
    },
    {
        "name": "get_collection",
        "description": "Get one collection by its id (from list_collections), with all its fields. Cite this id when answering.",
        "category": "files",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Collection id"}},
            "required": ["id"]
        }
    },
    {
        "name": "search_datasets",
        "description": "Search candidate and confirmed datasets found by Profile (e.g. a microCT reconstruction, an MRI session) by free text over path and profile name, by profile, owner, project or creation date (epoch seconds). Returns at most 50 plus the total.",
        "category": "files",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free text matched against path, profile name and id"},
                "profile": {"type": "string", "description": "Profile (pattern) name, e.g. 'bruker_microct'"},
                "owner": {"type": "string"},
                "project": {"type": "string"},
                "date_from": {"type": "number", "description": "Earliest created_at, epoch seconds"},
                "date_to": {"type": "number", "description": "Latest created_at, epoch seconds"}
            }
        }
    },
    {
        "name": "unclaimed_summary",
        "description": "For one scan (default: the latest), count the files no dataset claims, by extension with bytes. Use it to say how much of the storage SciDK recognises, and what a new profile should cover.",
        "category": "files",
        "input_schema": {
            "type": "object",
            "properties": {"scan_id": {"type": "string", "description": "Optional scan id"}}
        }
    }
]


for _definition in TOOL_DEFINITIONS:
    _definition['description'] = ('Currently suspended: Resource-scoped disclosure is required; '
                                  'this legacy tool refuses execution. ' + _definition['description'])


# Static catalog for trusted internal consumers. Runtime discovery is filtered.
from .knowledge import DEFINITIONS as KNOWLEDGE_DEFINITIONS, NAMES as KNOWLEDGE_NAMES
TOOL_DEFINITIONS.extend(KNOWLEDGE_DEFINITIONS)


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


#: Tools only SciDK's own chat offers (e.g. building a dashboard tab). None yet;
#: the HTTP, functions.json and MCP adapters exclude these.
CHAT_ONLY: frozenset = frozenset()

_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    'query_knowledge_graph': tools_graph.agent_query_graph,
    'get_schema': tools_graph.agent_get_schema,
    'summarize_dataset': tools_graph.agent_summarize_dataset,
    'get_label_profile': tools_graph.agent_get_label_profile,
    'list_labels': tools_graph.agent_list_labels,
    'count_nodes': tools_graph.agent_count_nodes,
    'scan_summary': tools_sql.scan_summary,
    'list_collections': tools_sql.list_collections,
    'get_collection': tools_sql.get_collection,
    'search_datasets': tools_sql.search_datasets,
    'unclaimed_summary': tools_sql.unclaimed_summary,
}
from .knowledge import dispatch as _knowledge_dispatch
_HANDLERS.update({name: _knowledge_dispatch for name in KNOWLEDGE_NAMES})
_BY_NAME = {t['name']: t for t in TOOL_DEFINITIONS}


@dataclass
class ToolContext:
    """What a tool may read. ``driver`` is None when no Neo4j is configured."""
    driver: Any = None
    database: Optional[str] = None
    files_db: Optional[str] = None
    settings_db: Optional[str] = None
    user: Optional[str] = None
    policy: SharingPolicy = field(default_factory=SharingPolicy)
    identity: Any = None
    profile: str = 'overview'
    knowledge: Any = None
    knowledge_enabled: bool = False
    proposal_enabled: bool = False


def tool_names(include_chat_only: bool = False) -> List[str]:
    return [t['name'] for t in TOOL_DEFINITIONS if include_chat_only or t['name'] not in CHAT_ONLY]


def run_tool(name: str, arguments: Optional[Dict[str, Any]], ctx: ToolContext) -> Dict[str, Any]:
    """Agent boundary. Legacy unscoped handlers are suspended, never executed."""
    if name in KNOWLEDGE_NAMES:
        return _run_knowledge(name, arguments, ctx)
    if name not in _HANDLERS:
        return {"status": "error", "error": f"Unknown tool: {name}"}
    if arguments is not None and not isinstance(arguments, dict):
        return {"status": "error", "error": "Tool arguments must be a JSON object"}
    args = dict(arguments or {})
    schema = _BY_NAME[name]['input_schema']
    unexpected = sorted(set(args) - set(schema.get('properties', {})))
    if unexpected:
        return {"status": "error", "error": f"Unexpected argument(s) for {name}: {', '.join(unexpected)}"}
    missing = [k for k in schema.get('required', []) if args.get(k) in (None, '')]
    if missing:
        return {"status": "error", "error": f"Missing required argument(s) for {name}: {', '.join(missing)}"}
    from .security import PolicyStore, REFUSAL
    try:
        with PolicyStore(ctx.settings_db).resolve(ctx.identity):
            # Every legacy handler queries an unscoped graph or file-index view.
            # Scoped tools use the separate branch above. Refuse these legacy
            # handlers even for an otherwise approved principal/destination.
            return dict(REFUSAL)
    except Exception:
        return dict(REFUSAL)


def openai_functions(include_chat_only: bool = False, *, ctx=None) -> List[Dict[str, Any]]:
    """The registry as OpenAI-style tool definitions (what the chat sends to Parley)."""
    return [{"type": "function",
             "function": {"name": t['name'], "description": t['description'],
                          "parameters": t['input_schema']}}
            for t in available_tool_definitions(ctx) if include_chat_only or t['name'] not in CHAT_ONLY]


def available_tool_definitions(ctx=None):
    """Runtime discovery only. No identity/capability/backend implies no tools."""
    from copy import deepcopy
    from .security import PolicyStore
    from .capabilities import permitted_tools
    from .knowledge import KnowledgeServices
    try:
        if not ctx or not ctx.knowledge_enabled or not isinstance(ctx.knowledge, KnowledgeServices):
            return []
        with PolicyStore(ctx.settings_db).resolve(ctx.identity) as policy:
            names = permitted_tools(policy, ctx.profile)
            return deepcopy([t for t in TOOL_DEFINITIONS if t['name'] in names and ctx.knowledge.ready(t['name'])
                             and (t['name'] != 'submit_assertion' or ctx.proposal_enabled)])
    except Exception:
        return []


def _run_knowledge(name, arguments, ctx):
    from jsonschema import Draft202012Validator
    from .security import PolicyStore, REFUSAL, DisclosureDenied
    from .capabilities import permitted_tools
    from .knowledge import KnowledgeServices
    from ..curation.contracts import canonical
    try:
        if (not ctx.knowledge_enabled or not isinstance(ctx.knowledge, KnowledgeServices) or not ctx.knowledge.ready(name)
                or (name == 'submit_assertion' and not ctx.proposal_enabled)):
            raise DisclosureDenied()
        with PolicyStore(ctx.settings_db).resolve(ctx.identity) as policy:
            if name not in permitted_tools(policy, ctx.profile):
                raise DisclosureDenied()
            args = {} if arguments is None else arguments
            if len(canonical(args).encode()) > 65536 or not Draft202012Validator(_BY_NAME[name]['input_schema']).is_valid(args):
                return {'status': 'error', 'error': 'Invalid tool arguments.'}
            return _knowledge_dispatch(name, args, ctx, policy)
    except Exception:
        return dict(REFUSAL)
