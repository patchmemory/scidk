"""
---
id: builtin-orphaned-files
name: Orphaned Files
description: Find files that were scanned but never committed to Neo4j. Uses SQL on local SQLite index.
language: python
category: builtin
tags: [files, quality, sync]
---
"""
# Query SQLite for files not in Neo4j
import sqlite3
from scidk.core import path_index_sqlite as pix

conn = pix.connect()
cur = conn.cursor()

# Files in scans but not committed
query = """
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
"""

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
