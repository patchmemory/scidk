#!/usr/bin/env python3
"""
Command-line tool for analyzing GraphRAG feedback.

Usage:
    python scripts/analyze_feedback.py --stats
    python scripts/analyze_feedback.py --entities
    python scripts/analyze_feedback.py --queries
    python scripts/analyze_feedback.py --terminology
"""
import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scidk.services.graphrag_feedback_service import get_graphrag_feedback_service


def print_stats(service):
    """Print feedback statistics."""
    stats = service.get_feedback_stats()

    print("\n📊 GraphRAG Feedback Statistics")
    print("=" * 60)
    print(f"Total feedback entries:        {stats['total_feedback_count']}")
    print(f"  ✅ Answered question:         {stats['answered_yes_count']}")
    print(f"  ❌ Did not answer:            {stats['answered_no_count']}")
    print(f"  📈 Answer rate:               {stats['answer_rate']}%")
    print()
    print(f"Entity corrections provided:   {stats['entity_corrections_count']}")
    print(f"Query reformulations:          {stats['query_corrections_count']}")
    print(f"Terminology mappings:          {stats['terminology_corrections_count']}")
    print("=" * 60)


def print_entity_corrections(service, limit=10):
    """Print entity corrections for analysis."""
    corrections = service.get_entity_corrections(limit=limit)

    print(f"\n🔍 Entity Corrections (showing {len(corrections)})")
    print("=" * 60)

    for i, corr in enumerate(corrections, 1):
        print(f"\n{i}. Query: {corr['query']}")
        print(f"   Extracted: {corr['extracted']}")

        entity_corr = corr['corrections']
        if entity_corr.get('removed'):
            print(f"   ❌ Removed: {entity_corr['removed']}")
        if entity_corr.get('added'):
            print(f"   ✅ Added: {entity_corr['added']}")

    print("=" * 60)


def print_query_reformulations(service, limit=10):
    """Print query reformulations."""
    reformulations = service.get_query_reformulations(limit=limit)

    print(f"\n✏️  Query Reformulations (showing {len(reformulations)})")
    print("=" * 60)

    for i, reform in enumerate(reformulations, 1):
        print(f"\n{i}. Original:  {reform['original_query']}")
        print(f"   Corrected: {reform['corrected_query']}")
        if reform['entities_extracted']:
            print(f"   Entities:  {reform['entities_extracted']}")

    print("=" * 60)


def print_terminology_mappings(service):
    """Print schema terminology mappings."""
    mappings = service.get_terminology_mappings()

    print("\n📚 Schema Terminology Mappings")
    print("=" * 60)

    if not mappings:
        print("  (No terminology mappings found)")
    else:
        for user_term, schema_term in mappings.items():
            print(f"  '{user_term}' → '{schema_term}'")

    print("=" * 60)


def export_training_data(service, output_path):
    """Export feedback as training data for improving the system."""
    import json

    reformulations = service.get_query_reformulations(limit=1000)
    entity_corrections = service.get_entity_corrections(limit=1000)
    terminology = service.get_terminology_mappings()

    training_data = {
        'query_pairs': [
            {
                'input': r['original_query'],
                'output': r['corrected_query'],
                'metadata': {
                    'entities': r['entities_extracted'],
                    'timestamp': r['timestamp']
                }
            }
            for r in reformulations
        ],
        'entity_corrections': [
            {
                'query': ec['query'],
                'extracted': ec['extracted'],
                'corrections': ec['corrections']
            }
            for ec in entity_corrections
        ],
        'terminology_mappings': terminology
    }

    with open(output_path, 'w') as f:
        json.dump(training_data, f, indent=2)

    print(f"\n✅ Training data exported to: {output_path}")
    print(f"   Query pairs: {len(training_data['query_pairs'])}")
    print(f"   Entity corrections: {len(training_data['entity_corrections'])}")
    print(f"   Terminology mappings: {len(training_data['terminology_mappings'])}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze GraphRAG feedback',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --stats                    Show feedback statistics
  %(prog)s --entities --limit 20      Show 20 entity corrections
  %(prog)s --queries --limit 15       Show 15 query reformulations
  %(prog)s --terminology              Show terminology mappings
  %(prog)s --export training.json     Export training data
        """
    )

    parser.add_argument('--stats', action='store_true',
                       help='Show feedback statistics')
    parser.add_argument('--entities', action='store_true',
                       help='Show entity corrections')
    parser.add_argument('--queries', action='store_true',
                       help='Show query reformulations')
    parser.add_argument('--terminology', action='store_true',
                       help='Show terminology mappings')
    parser.add_argument('--export', metavar='PATH',
                       help='Export training data to JSON file')
    parser.add_argument('--limit', type=int, default=10,
                       help='Number of entries to show (default: 10)')
    parser.add_argument('--db', metavar='PATH',
                       help='Path to SQLite database (default: scidk_settings.db)')

    args = parser.parse_args()

    # Get feedback service
    service = get_graphrag_feedback_service(db_path=args.db)

    # Execute commands
    if args.stats:
        print_stats(service)

    if args.entities:
        print_entity_corrections(service, limit=args.limit)

    if args.queries:
        print_query_reformulations(service, limit=args.limit)

    if args.terminology:
        print_terminology_mappings(service)

    if args.export:
        export_training_data(service, args.export)

    # If no command specified, show stats by default
    if not any([args.stats, args.entities, args.queries, args.terminology, args.export]):
        print_stats(service)


if __name__ == '__main__':
    main()
