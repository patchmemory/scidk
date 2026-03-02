"""
Sample Link script for testing validation framework.

This script demonstrates the correct contract for a Link:
- Has create_links(source_nodes, target_nodes) function
- Returns list of tuples/dicts (triples)
- Handles empty inputs gracefully
- Returns valid relationship types
"""
from typing import List, Dict, Tuple, Any


def create_links(source_nodes: List[Dict], target_nodes: List[Dict]) -> List[Tuple[str, str, str, Dict]]:
    """
    Create links between source and target nodes.

    Args:
        source_nodes: List of source node dicts with 'id', 'name', 'type'
        target_nodes: List of target node dicts with 'id', 'name', 'type'

    Returns:
        List of tuples: (source_id, rel_type, target_id, properties)
    """
    # Handle empty inputs
    if not source_nodes or not target_nodes:
        return []

    # Create links based on simple logic
    # Example: Connect each Person to each Project with WORKS_ON relationship
    links = []

    for source in source_nodes:
        if source.get('type') == 'Person':
            for target in target_nodes:
                if target.get('type') == 'Project':
                    links.append((
                        source['id'],
                        'WORKS_ON',
                        target['id'],
                        {
                            'created_by': 'sample_link_script',
                            'confidence': 0.95
                        }
                    ))

    return links
