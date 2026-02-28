"""
---
id: author-collaboration-link
name: Author Collaboration Network
category: examples
language: python
description: Creates CO_AUTHORED relationships when authors share documents (inference-based, not explicit data)
parameters:
  - name: min_shared_docs
    type: number
    default: 2
    description: Minimum shared documents required to create collaboration link
---
"""
from typing import List, Dict, Tuple
from collections import defaultdict


def create_links(source_nodes: List[Dict], target_nodes: List[Dict]) -> List[Tuple]:
    """
    Infer CO_AUTHORED relationships based on shared document authorship.

    Logic: If two authors both contributed to N+ documents, they collaborated.
    This is INFERENCE - wizard links can't do this kind of reasoning.

    Args:
        source_nodes: List of Person nodes
        target_nodes: List of Person nodes (same set for N:N relationships)

    Returns:
        List of tuples: (author1_id, 'CO_AUTHORED', author2_id, properties)
    """
    if not source_nodes or not target_nodes:
        return []

    # Build author→documents mapping
    author_docs = defaultdict(set)

    # In production: Query Neo4j for (Person)-[:AUTHORED]->(Document) relationships
    # Demo: Use stub data from node properties or hardcode
    for author in source_nodes:
        if author.get('type') != 'Person':
            continue

        # Check if node has authored_docs property
        authored = author.get('authored_docs', [])
        if authored:
            author_docs[author['id']] = set(authored)

    # Demo fallback: Create hardcoded mappings if no data available
    if not author_docs:
        # Realistic demo data showing collaboration patterns
        author_docs = {
            'person-alice': {'doc-1', 'doc-2', 'doc-5', 'doc-12'},
            'person-bob': {'doc-2', 'doc-5', 'doc-8', 'doc-15'},
            'person-carol': {'doc-1', 'doc-3', 'doc-12', 'doc-20'},
            'person-dave': {'doc-5', 'doc-8', 'doc-9', 'doc-22'},
            'person-eve': {'doc-1', 'doc-12', 'doc-18'},
            'author-1': {'paper-a', 'paper-c', 'paper-f'},
            'author-2': {'paper-a', 'paper-b', 'paper-c'},
            'author-3': {'paper-c', 'paper-f', 'paper-g'},
        }

    # Find collaborations (authors who share documents)
    links = []
    authors = list(author_docs.keys())

    # For each pair of authors
    for i, author1 in enumerate(authors):
        for author2 in authors[i+1:]:  # Avoid duplicates, self-links
            # Find intersection of their document sets
            shared = author_docs[author1] & author_docs[author2]

            # Create link if they share enough documents (threshold check)
            if len(shared) >= 2:  # min_shared_docs parameter
                # Calculate collaboration strength (Jaccard-style)
                union = author_docs[author1] | author_docs[author2]
                strength = len(shared) / len(union) if union else 0

                links.append((
                    author1,
                    'CO_AUTHORED',
                    author2,
                    {
                        'shared_documents': len(shared),
                        'document_samples': sorted(list(shared))[:5],  # First 5 for display
                        'collaboration_strength': round(strength, 3),
                        'total_joint_work': len(shared),
                        'created_by': 'author-collaboration-link',
                        'inference_method': 'shared_authorship_count'
                    }
                ))

    return links
