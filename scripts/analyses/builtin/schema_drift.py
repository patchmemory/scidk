"""
---
id: builtin-schema-drift
name: Schema Drift Detection
description: Compare defined labels in SciDK with actual labels in Neo4j. Identifies missing or extra labels.
language: python
category: analyses/builtin
tags: [schema, neo4j, quality, drift]
---
"""
# Compare defined vs actual schema
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
