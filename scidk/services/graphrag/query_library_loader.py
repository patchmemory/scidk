"""
Query library loader for SciDK GraphRAG.

Loads curated Cypher examples from YAML file and converts them to the format
expected by neo4j-graphrag's Text2CypherRetriever.

The query library provides few-shot examples that guide the LLM to generate
correct Cypher queries for common SciDK data patterns.
"""
import os
import yaml
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path


def load_query_library(library_path: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Load query library from YAML file.

    Args:
        library_path: Path to query library YAML file.
                     If None, uses SCIDK_QUERY_LIBRARY_PATH env var,
                     or defaults to query_library/scidk_queries.yaml

    Returns:
        List of dicts with 'question' and 'cypher' keys (neo4j-graphrag format).
        Returns empty list if file not found or parsing fails.

    Format expected by neo4j-graphrag:
        [
            {"question": "...", "cypher": "..."},
            {"question": "...", "cypher": "..."},
            ...
        ]
    """
    logger = logging.getLogger(__name__)

    # Determine library path
    if not library_path:
        library_path = os.environ.get('SCIDK_QUERY_LIBRARY_PATH')

    if not library_path:
        # Default: query_library/scidk_queries.yaml relative to project root
        # Project root is 2 levels up from this file (scidk/services/graphrag/)
        project_root = Path(__file__).parent.parent.parent.parent
        library_path = project_root / "query_library" / "scidk_queries.yaml"

    library_path = Path(library_path)

    # Check if file exists
    if not library_path.exists():
        logger.warning(f"Query library not found at {library_path}, using empty library")
        return []

    try:
        # Load YAML
        with open(library_path, 'r') as f:
            queries = yaml.safe_load(f) or []

        if not isinstance(queries, list):
            logger.error(f"Query library must be a list, got {type(queries)}")
            return []

        # Convert to neo4j-graphrag format
        examples = []
        for query in queries:
            # Skip queries marked as deprecated
            if query.get('status') == 'deprecated':
                continue

            # Extract first example question as the representative question
            example_questions = query.get('example_questions', [])
            if not example_questions:
                logger.warning(f"Query {query.get('id')} has no example questions, skipping")
                continue

            cypher = query.get('cypher', '').strip()
            if not cypher:
                logger.warning(f"Query {query.get('id')} has no Cypher, skipping")
                continue

            # Use first example question as the representative
            question = example_questions[0]

            examples.append({
                "question": question,
                "cypher": cypher
            })

        logger.info(f"Loaded {len(examples)} query examples from {library_path}")
        return examples

    except yaml.YAMLError as e:
        logger.error(f"Failed to parse query library YAML: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to load query library: {e}")
        return []


def get_query_by_id(query_id: str, library_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get a specific query entry by ID.

    Args:
        query_id: The 'id' field of the query to retrieve
        library_path: Optional path to query library YAML

    Returns:
        Full query dict from YAML, or None if not found.
    """
    logger = logging.getLogger(__name__)

    if not library_path:
        library_path = os.environ.get('SCIDK_QUERY_LIBRARY_PATH')
        if not library_path:
            project_root = Path(__file__).parent.parent.parent.parent
            library_path = project_root / "query_library" / "scidk_queries.yaml"

    library_path = Path(library_path)

    if not library_path.exists():
        return None

    try:
        with open(library_path, 'r') as f:
            queries = yaml.safe_load(f) or []

        for query in queries:
            if query.get('id') == query_id:
                return query

        return None

    except Exception as e:
        logger.error(f"Failed to load query by ID: {e}")
        return None
