"""
Calculate interpretation success rates by file type.

category: analyses
language: python
"""


def run(context):
    """Analyze interpreter success rates per file extension."""

    # Query interpretation stats
    results = context.neo4j.query("""
        MATCH (f:File)
        WHERE f.interpreter_used IS NOT NULL
        RETURN
            f.extension as extension,
            count(*) as total,
            sum(CASE WHEN f.interpreted = true THEN 1 ELSE 0 END) as successful
        ORDER BY total DESC
    """)

    # Calculate success rates
    for row in results:
        if row['total'] > 0:
            row['success_rate'] = f"{(row['successful'] / row['total'] * 100):.1f}%"
        else:
            row['success_rate'] = "N/A"

    # Register table panel
    context.register_panel(
        panel_type='table',
        title='Interpretation Success Rates',
        data=results
    )
