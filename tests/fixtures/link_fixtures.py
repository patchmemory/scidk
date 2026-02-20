"""
Test fixtures for Link contract validation.

These fixtures test various edge cases and contract requirements
for link scripts.
"""

# Valid minimal link script that passes all contract tests
VALID_LINK = '''
"""Minimal valid link script for testing."""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """
    Basic link creation that returns proper format.

    Args:
        source_nodes: List of source node dicts
        target_nodes: List of target node dicts

    Returns:
        List of tuples: (source_id, target_id, rel_type, properties)
    """
    links = []

    if not source_nodes or not target_nodes:
        return links

    # Simple example: link all sources to all targets
    for source in source_nodes:
        for target in target_nodes:
            links.append((
                source.get('id'),
                target.get('id'),
                'RELATED_TO',
                {'confidence': 1.0}
            ))

    return links
'''

# Missing create_links() function - fails contract
MISSING_CREATE_LINKS_FUNCTION = '''
"""Link script missing required function."""

def make_connections(source_nodes: list, target_nodes: list) -> list:
    """Wrong function name - should be create_links()."""
    return []
'''

# Wrong number of parameters (only one instead of two)
WRONG_PARAMETER_COUNT = '''
"""Link script with wrong parameter count."""

def create_links(nodes: list) -> list:
    """Takes only one parameter - violates contract."""
    return []
'''

# Returns wrong type (dict instead of list)
RETURNS_WRONG_TYPE = '''
"""Link script that returns dict instead of list."""

def create_links(source_nodes: list, target_nodes: list) -> dict:
    """Returns dict - violates contract."""
    return {'links': []}
'''

# Returns None as relationship type - edge case
RETURNS_NONE_RELATIONSHIP = '''
"""Link script that returns None as relationship type."""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """Returns None as rel_type - edge case that should be caught."""
    links = []

    for source in source_nodes:
        for target in target_nodes:
            links.append((
                source.get('id'),
                target.get('id'),
                None,  # Invalid! Rel type should be a string
                {}
            ))

    return links
'''

# Doesn't handle empty inputs gracefully - crashes
CRASHES_ON_EMPTY_INPUT = '''
"""Link script that crashes on empty input."""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """Assumes non-empty lists - will crash on empty input."""
    # This will crash if lists are empty
    first_source = source_nodes[0]
    first_target = target_nodes[0]

    return [(first_source['id'], first_target['id'], 'LINKED', {})]
'''

# Handles empty inputs correctly
HANDLES_EMPTY_CORRECTLY = '''
"""Link script that properly handles empty inputs."""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """Gracefully handles all edge cases."""
    if not source_nodes or not target_nodes:
        return []

    links = []
    for source in source_nodes:
        for target in target_nodes:
            # Check for required 'id' field
            if 'id' not in source or 'id' not in target:
                continue

            links.append((
                source['id'],
                target['id'],
                'RELATED_TO',
                {}
            ))

    return links
'''

# Advanced: Returns multiple relationship types based on logic
MULTI_RELATIONSHIP_TYPES = '''
"""Link script that returns different relationship types."""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """Creates different rel types based on node properties."""
    if not source_nodes or not target_nodes:
        return []

    links = []

    for source in source_nodes:
        for target in target_nodes:
            # Determine relationship type based on node properties
            if source.get('type') == target.get('type'):
                rel_type = 'SAME_TYPE_AS'
            else:
                rel_type = 'DIFFERENT_FROM'

            links.append((
                source.get('id'),
                target.get('id'),
                rel_type,
                {'source_type': source.get('type'), 'target_type': target.get('type')}
            ))

    return links
'''

# Fuzzy string matching link (realistic use case)
FUZZY_MATCH_LINK = '''
"""Link script using fuzzy string matching."""
from difflib import SequenceMatcher

def create_links(source_nodes: list, target_nodes: list) -> list:
    """Links nodes with similar names using fuzzy matching."""
    if not source_nodes or not target_nodes:
        return []

    links = []
    threshold = 0.8  # 80% similarity

    for source in source_nodes:
        for target in target_nodes:
            source_name = source.get('name', '')
            target_name = target.get('name', '')

            if not source_name or not target_name:
                continue

            # Calculate similarity ratio
            ratio = SequenceMatcher(None, source_name.lower(), target_name.lower()).ratio()

            if ratio >= threshold:
                links.append((
                    source.get('id'),
                    target.get('id'),
                    'SIMILAR_NAME',
                    {'similarity': ratio, 'threshold': threshold}
                ))

    return links
'''

# Has syntax errors
SYNTAX_ERROR = '''
"""Link script with syntax errors."""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """Missing closing bracket."""
    return [
        ('source1', 'target1', 'LINKED', {}
    ]
'''

# Test data for link scripts
TEST_SOURCE_NODES = [
    {'id': 'source1', 'name': 'Alice', 'type': 'Person'},
    {'id': 'source2', 'name': 'Bob', 'type': 'Person'},
    {'id': 'source3', 'name': 'Project Alpha', 'type': 'Project'}
]

TEST_TARGET_NODES = [
    {'id': 'target1', 'name': 'Alicia', 'type': 'Person'},
    {'id': 'target2', 'name': 'Charlie', 'type': 'Person'},
    {'id': 'target3', 'name': 'Project Beta', 'type': 'Project'}
]

EMPTY_NODES = []
