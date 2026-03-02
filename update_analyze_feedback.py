#!/usr/bin/env python3
"""
Update Analyze Feedback script with new parameter system and run() function.
"""
import json
from scidk.core.scripts import ScriptsManager


# New script code
SCRIPT_CODE = """\"\"\"
GraphRAG Feedback Analysis Script

Analyzes user feedback on GraphRAG query results.
\"\"\"
from scidk.services.graphrag_feedback_service import get_graphrag_feedback_service


def run(context):
    \"\"\"
    Analyze GraphRAG feedback with configurable parameters.

    Args:
        context: Execution context containing parameters

    Returns:
        Dict with analysis results (wrappable in SciDKData)
    \"\"\"
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
    \"\"\"Get feedback statistics as structured data.\"\"\"
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
    \"\"\"Get entity corrections as structured data.\"\"\"
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
    \"\"\"Get query reformulations as structured data.\"\"\"
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
    \"\"\"Get terminology mappings as structured data.\"\"\"
    mappings = service.get_terminology_mappings()

    # Transform dict into table structure
    rows = []
    for user_term, schema_term in mappings.items():
        rows.append({
            'user_term': user_term,
            'schema_term': schema_term
        })

    return rows
"""

# Parameter schema
PARAMETERS = [
    {
        'name': 'analysis_type',
        'type': 'select',
        'label': 'Analysis Type',
        'description': 'Type of feedback analysis to perform',
        'options': ['stats', 'entities', 'queries', 'terminology'],
        'default': 'stats',
        'required': True
    },
    {
        'name': 'limit',
        'type': 'number',
        'label': 'Result Limit',
        'description': 'Maximum number of results to show (for entities/queries/terminology)',
        'default': 10,
        'min': 1,
        'max': 1000,
        'required': False
    }
]


def main():
    manager = ScriptsManager()

    # Get existing script
    script = manager.get_script('analyze_feedback')
    if not script:
        print("❌ Script 'analyze_feedback' not found")
        return

    print("📝 Updating Analyze Feedback script...")

    # Update code and parameters
    script.code = SCRIPT_CODE
    script.parameters = PARAMETERS
    script.description = "Analyze GraphRAG feedback with configurable parameters"

    # Mark as edited (resets validation)
    script.mark_as_edited()

    # Save
    manager.update_script(script)

    print("✅ Script updated successfully!")
    print(f"\nParameters defined:")
    for param in PARAMETERS:
        print(f"  - {param['name']} ({param['type']}): {param['description']}")

    print("\n💡 Next steps:")
    print("  1. Reload the Scripts page")
    print("  2. Select 'Analyze Feedback' script")
    print("  3. Choose analysis type from dropdown")
    print("  4. Click 'Run' to see results")


if __name__ == '__main__':
    main()
