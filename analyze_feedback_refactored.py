"""
GraphRAG Feedback Analysis Script

Analyzes user feedback on GraphRAG query results.

Parameters:
- analysis_type: Type of analysis to perform (stats, entities, queries, terminology)
- limit: Maximum number of results to show
"""
from scidk.services.graphrag_feedback_service import get_graphrag_feedback_service


def run(context):
    """
    Analyze GraphRAG feedback with configurable parameters.

    Args:
        context: Execution context containing parameters

    Returns:
        Dict with analysis results (wrappable in SciDKData)
    """
    # Get parameters from context
    params = context.get('parameters', {})
    analysis_type = params.get('analysis_type', 'stats')
    limit = params.get('limit', 10)

    # Get feedback service
    service = get_graphrag_feedback_service()

    # Perform analysis based on type
    try:
        if analysis_type == 'stats':
            data = get_stats(service)
        elif analysis_type == 'entities':
            data = get_entity_corrections(service, limit)
        elif analysis_type == 'queries':
            data = get_query_reformulations(service, limit)
        elif analysis_type == 'terminology':
            data = get_terminology_mappings(service)
        else:
            return {
                'status': 'error',
                'error': f'Unknown analysis type: {analysis_type}',
                'data': []
            }

        return {
            'status': 'success',
            'analysis_type': analysis_type,
            'data': data
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'data': []
        }


def get_stats(service):
    """Get feedback statistics as structured data."""
    stats = service.get_feedback_stats()

    # Return as list of rows for table display
    return [
        {'metric': 'Total feedback entries', 'value': stats['total_feedback_count']},
        {'metric': 'Answered question', 'value': stats['answered_yes_count']},
        {'metric': 'Did not answer', 'value': stats['answered_no_count']},
        {'metric': 'Answer rate', 'value': f"{stats['answer_rate']}%"},
        {'metric': 'Entity corrections provided', 'value': stats['entity_corrections_count']},
        {'metric': 'Query reformulations', 'value': stats['query_corrections_count']},
        {'metric': 'Terminology mappings', 'value': stats['terminology_corrections_count']}
    ]


def get_entity_corrections(service, limit):
    """Get entity corrections as structured data."""
    corrections = service.get_entity_corrections(limit=limit)

    # Transform into flat table structure
    rows = []
    for corr in corrections:
        entity_corr = corr['corrections']
        rows.append({
            'query': corr['query'],
            'extracted': corr['extracted'],
            'removed': entity_corr.get('removed', ''),
            'added': entity_corr.get('added', '')
        })

    return rows


def get_query_reformulations(service, limit):
    """Get query reformulations as structured data."""
    reformulations = service.get_query_reformulations(limit=limit)

    # Transform into flat table structure
    rows = []
    for reform in reformulations:
        rows.append({
            'original_query': reform['original_query'],
            'corrected_query': reform['corrected_query'],
            'entities_extracted': reform['entities_extracted']
        })

    return rows


def get_terminology_mappings(service):
    """Get terminology mappings as structured data."""
    mappings = service.get_terminology_mappings()

    # Transform dict into table structure
    rows = []
    for user_term, schema_term in mappings.items():
        rows.append({
            'user_term': user_term,
            'schema_term': schema_term
        })

    return rows
