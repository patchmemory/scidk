"""Declarative assistant contexts over the shared registry, not chat engines."""
from types import MappingProxyType

#: Read-only graph tools. Granted per user through CapabilityStore; they run only on
#: the connection the user holds a graph_management_read grant for.
GRAPH_AGENT_TOOLS = frozenset({'list_labels', 'count_nodes', 'get_schema', 'query_knowledge_graph'})

PROFILES = MappingProxyType({
    'overview': frozenset({'get_system_context', 'get_ontology_context', 'explain_fact'}) | GRAPH_AGENT_TOOLS,
    'review': frozenset({'get_system_context', 'get_ontology_context', 'explain_fact',
                         'get_assertion', 'submit_assertion'}),
})

# Read-only Cypher for AI tools is approved policy (Oct 30): the overview profile may be
# granted the four graph tools above. No profile can grant graph writes or Python execution.
