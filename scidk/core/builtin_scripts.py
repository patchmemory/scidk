"""
Built-in scripts for the Scripts page.

Built-in scripts are now loaded from files in scripts/analyses/builtin/.
This module provides compatibility methods to load them.

Provides 7 core scripts:
1. File Distribution by Extension
2. Scan Timeline & Volume
3. Largest Files
4. Interpretation Success Rates
5. Neo4j Node/Relationship Counts
6. Orphaned Files
7. Schema Drift Detection
"""
from pathlib import Path
from typing import List
from .scripts import Script
from .script_loader import ScriptFileLoader


def get_builtin_scripts() -> List[Script]:
    """
    Return all built-in scripts loaded from files.

    Scripts are loaded from scripts/analyses/builtin/ directory.
    Falls back to in-memory versions if files don't exist.
    """
    scripts = []

    # Find builtin scripts directory
    import scidk
    project_root = Path(scidk.__file__).parent.parent
    builtin_dir = project_root / 'scripts' / 'analyses' / 'builtin'

    if not builtin_dir.exists():
        # Fall back to in-memory versions
        return _get_fallback_builtin_scripts()

    # Load all .py and .cypher files
    for pattern in ['*.py', '*.cypher']:
        for file_path in builtin_dir.glob(pattern):
            try:
                metadata, code = ScriptFileLoader.parse_file(file_path)
                script = Script(
                    id=metadata['id'],
                    name=metadata['name'],
                    language=metadata['language'],
                    category=metadata['category'],
                    code=code,
                    description=metadata.get('description', ''),
                    parameters=metadata.get('parameters', []),
                    tags=metadata.get('tags', [])
                )
                scripts.append(script)
            except Exception as e:
                print(f"Warning: Failed to load builtin script {file_path}: {e}")

    return scripts


def _get_fallback_builtin_scripts() -> List[Script]:
    """Fallback to in-memory built-in scripts if files don't exist."""
    return [
        get_file_distribution_script(),
        get_scan_timeline_script(),
        get_largest_files_script(),
        get_interpretation_rates_script(),
        get_neo4j_stats_script(),
        get_orphaned_files_script(),
        get_schema_drift_script()
    ]


def get_file_distribution_script():
    """Script 1: File Distribution by Extension."""
    return Script(
        id='builtin-file-distribution',
        name='File Distribution by Extension',
        description='Analyze file types across all scans. Shows count of files per extension as a table and bar chart.',
        language='cypher',
        category='builtin',
        code="""MATCH (f:File)
RETURN f.extension as extension,
       count(*) as count
ORDER BY count DESC
LIMIT $limit""",
        parameters=[
            {
                'name': 'limit',
                'type': 'integer',
                'default': 100,
                'label': 'Max results',
                'required': False
            }
        ],
        tags=['files', 'statistics', 'distribution']
    )


def get_scan_timeline_script():
    """Script 2: Scan Timeline & Volume."""
    return Script(
        id='builtin-scan-timeline',
        name='Scan Timeline & Volume',
        description='Show scan history with file counts and timestamps. Useful for tracking data ingestion over time.',
        language='cypher',
        category='builtin',
        code="""MATCH (s:Scan)
RETURN s.id as scan_id,
       s.started as started,
       s.completed as completed,
       s.root as path,
       s.file_count as file_count
ORDER BY s.started DESC
LIMIT $limit""",
        parameters=[
            {
                'name': 'limit',
                'type': 'integer',
                'default': 50,
                'label': 'Max scans',
                'required': False
            }
        ],
        tags=['scans', 'timeline', 'history']
    )


def get_largest_files_script():
    """Script 3: Largest Files."""
    return Script(
        id='builtin-largest-files',
        name='Largest Files',
        description='Find the largest files in the knowledge graph by size. Helps identify storage-heavy files.',
        language='cypher',
        category='builtin',
        code="""MATCH (f:File)
WHERE f.size_bytes IS NOT NULL
RETURN f.path as path,
       f.size_bytes as size_bytes,
       f.extension as extension,
       f.modified as modified
ORDER BY f.size_bytes DESC
LIMIT $limit""",
        parameters=[
            {
                'name': 'limit',
                'type': 'integer',
                'default': 50,
                'label': 'Max files',
                'required': False
            }
        ],
        tags=['files', 'size', 'storage']
    )


def get_interpretation_rates_script():
    """Script 4: Interpretation Success Rates."""
    return Script(
        id='builtin-interpretation-rates',
        name='Interpretation Success Rates',
        description='Analyze interpreter performance by type. Shows success vs failure rates for each interpreter.',
        language='cypher',
        category='builtin',
        code="""MATCH (f:File)
WHERE f.interpreter_type IS NOT NULL
WITH f.interpreter_type as interpreter,
     count(*) as total,
     sum(CASE WHEN f.interpretation_success = true THEN 1 ELSE 0 END) as successes
RETURN interpreter,
       total,
       successes,
       total - successes as failures,
       round(100.0 * successes / total, 2) as success_rate
ORDER BY total DESC""",
        parameters=[],
        tags=['interpreters', 'statistics', 'quality']
    )


def get_neo4j_stats_script():
    """Script 5: Neo4j Node/Relationship Counts."""
    return Script(
        id='builtin-neo4j-stats',
        name='Neo4j Node & Relationship Counts',
        description='Database statistics showing counts of all node labels and relationship types.',
        language='cypher',
        category='builtin',
        code="""// Node counts
CALL {
    MATCH (n)
    UNWIND labels(n) as label
    RETURN label, count(*) as count
    ORDER BY count DESC
}
RETURN label, count, 'node' as type

UNION ALL

// Relationship counts
CALL {
    MATCH ()-[r]->()
    RETURN type(r) as label, count(*) as count
    ORDER BY count DESC
}
RETURN label, count, 'relationship' as type""",
        parameters=[],
        tags=['neo4j', 'statistics', 'schema']
    )


def get_orphaned_files_script():
    """Script 6: Orphaned Files (Scanned but Not Committed)."""
    return Script(
        id='builtin-orphaned-files',
        name='Orphaned Files',
        description='Find files that were scanned but never committed to Neo4j. Uses SQL on local SQLite index.',
        language='python',
        category='builtin',
        code="""# Query SQLite for files not in Neo4j
import sqlite3
from scidk.core import path_index_sqlite as pix

conn = pix.connect()
cur = conn.cursor()

# Files in scans but not committed
query = \"\"\"
SELECT path, size, modified_time, file_extension
FROM files
WHERE checksum NOT IN (
    SELECT DISTINCT file_checksum
    FROM scan_items
    WHERE scan_id IN (
        SELECT scan_id
        FROM scans
        WHERE status = 'completed'
    )
)
LIMIT 100
\"\"\"

rows = cur.fetchall()
conn.close()

# Convert to list of dicts
results = []
for row in rows:
    results.append({
        'path': row[0],
        'size': row[1],
        'modified': row[2],
        'extension': row[3]
    })
""",
        parameters=[],
        tags=['files', 'quality', 'sync']
    )


def get_schema_drift_script():
    """Script 7: Schema Drift Detection."""
    return Script(
        id='builtin-schema-drift',
        name='Schema Drift Detection',
        description='Compare defined labels in SciDK with actual labels in Neo4j. Identifies missing or extra labels.',
        language='python',
        category='builtin',
        code="""# Compare defined vs actual schema
import sqlite3
from scidk.core import path_index_sqlite as pix

# Get defined labels from SQLite
conn = pix.connect()
cur = conn.cursor()
defined_labels = set()
for row in cur.execute("SELECT name FROM label_definitions"):
    defined_labels.add(row[0])
conn.close()

# Get actual labels from Neo4j
actual_labels = set()
if neo4j_driver:
    with neo4j_driver.session() as session:
        result = session.run("CALL db.labels()")
        for record in result:
            actual_labels.add(record[0])

# Compare
missing_in_neo4j = defined_labels - actual_labels
extra_in_neo4j = actual_labels - defined_labels
matching = defined_labels & actual_labels

# Build results
results = []
for label in sorted(missing_in_neo4j):
    results.append({'label': label, 'status': 'defined_not_in_neo4j', 'drift_type': 'missing'})
for label in sorted(extra_in_neo4j):
    results.append({'label': label, 'status': 'in_neo4j_not_defined', 'drift_type': 'extra'})
for label in sorted(matching):
    results.append({'label': label, 'status': 'matching', 'drift_type': 'none'})
""",
        parameters=[],
        tags=['schema', 'neo4j', 'quality', 'drift']
    )


# Initialize built-in scripts on module load
BUILTIN_SCRIPTS = get_builtin_scripts()
