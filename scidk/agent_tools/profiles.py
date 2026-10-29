"""Declarative assistant contexts over the shared registry, not chat engines."""
from types import MappingProxyType

PROFILES = MappingProxyType({
    'overview': frozenset({'get_system_context', 'get_ontology_context', 'explain_fact'}),
    'review': frozenset({'get_system_context', 'get_ontology_context', 'explain_fact',
                         'get_assertion', 'submit_assertion'}),
})

# Suggestions such as dataset discovery remain unavailable until a scoped query
# template exists. No profile can grant legacy queries, review or graph writes.
