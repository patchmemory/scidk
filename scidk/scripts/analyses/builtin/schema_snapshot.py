"""
Capture current knowledge graph schema state.

category: analyses
language: python
"""


def run(context):
    """Capture and display current KG schema as a table."""

    # Query all node labels with counts
    schema = context.neo4j.query("""
        MATCH (n)
        RETURN labels(n)[0] as label, count(*) as count
        ORDER BY count DESC
    """)

    # Register table panel
    context.register_panel(
        panel_type='table',
        title='Knowledge Graph Schema Snapshot',
        data=schema
    )

    # Optionally write summary node to KG
    total_nodes = sum(row['count'] for row in schema)
    context.neo4j.write_node(
        label='SchemaSnapshot',
        properties={
            'total_nodes': total_nodes,
            'label_count': len(schema),
            'snapshot_at': context.ran_at
        }
    )
