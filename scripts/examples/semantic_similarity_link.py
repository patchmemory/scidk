"""
---
id: semantic-similarity-link
name: Semantic Document Similarity
category: examples
language: python
description: Creates SIMILAR_TO relationships between documents based on content similarity (demo stub with hardcoded examples)
parameters:
  - name: similarity_threshold
    type: number
    default: 0.7
    description: Minimum similarity score (0-1) to create link
---
"""
from typing import List, Dict, Tuple


def create_links(source_nodes: List[Dict], target_nodes: List[Dict]) -> List[Tuple]:
    """
    Create SIMILAR_TO relationships between similar documents.

    Demo stub: Returns hardcoded examples showing semantic similarity.
    Production: Would use embedding model (OpenAI, sentence-transformers).

    Args:
        source_nodes: List of source node dicts with 'id' and 'type'
        target_nodes: List of target node dicts with 'id' and 'type'

    Returns:
        List of tuples: (source_id, rel_type, target_id, properties)
    """
    if not source_nodes or not target_nodes:
        return []

    links = []

    # Demo: Hardcoded similarity pairs (realistic for demo)
    # In production: compute cosine similarity between document embeddings
    similarity_pairs = [
        ('doc-1', 'doc-5', 0.87, 'Both discuss Python testing frameworks'),
        ('doc-2', 'doc-8', 0.91, 'Both cover React component patterns'),
        ('doc-3', 'doc-12', 0.74, 'Both reference Neo4j query optimization'),
        ('file-123', 'file-456', 0.82, 'Similar code structure and patterns'),
        ('readme-1', 'readme-3', 0.79, 'Similar documentation style'),
        ('paper-a', 'paper-b', 0.88, 'Both discuss machine learning pipelines'),
        ('article-1', 'article-5', 0.76, 'Both analyze data visualization'),
        ('code-main', 'code-utils', 0.83, 'Shared utility functions'),
    ]

    # Map node IDs from source and target sets
    source_ids = {n.get('id') for n in source_nodes if n.get('type') in ['Document', 'File', 'Paper', 'Article', 'Code']}
    target_ids = {n.get('id') for n in target_nodes if n.get('type') in ['Document', 'File', 'Paper', 'Article', 'Code']}

    # Create links for pairs where both nodes exist in our sets
    for src_id, tgt_id, score, reason in similarity_pairs:
        if src_id in source_ids and tgt_id in target_ids:
            links.append((
                src_id,
                'SIMILAR_TO',
                tgt_id,
                {
                    'similarity_score': score,
                    'reason': reason,
                    'method': 'embedding_cosine',
                    'model': 'text-embedding-3-small (demo stub)',
                    'created_by': 'semantic-similarity-link'
                }
            ))

    return links
