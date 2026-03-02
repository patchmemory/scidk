"""
Analyze file type distribution across all scans.

category: analyses
language: python
"""


def run(context):
    """Count files by extension and display as table with chart."""

    # Query file distribution
    results = context.neo4j.query("""
        MATCH (f:File)
        RETURN f.extension as extension, count(*) as count
        ORDER BY count DESC
        LIMIT 20
    """)

    # Register table panel with bar chart visualization
    context.register_panel(
        panel_type='table',
        title='File Distribution by Extension',
        data=results,
        visualization='bar_chart'
    )

    # Write aggregate stats to KG
    total_files = sum(row['count'] for row in results)
    context.neo4j.write_node(
        label='FileStats',
        properties={
            'total_files': total_files,
            'extension_count': len(results),
            'analyzed_at': context.ran_at
        }
    )
