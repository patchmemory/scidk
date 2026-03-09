#!/usr/bin/env python3
"""Apply schema constraints to the Concept Graph."""
from neo4j import GraphDatabase

uri = "bolt://localhost:7689"
auth = ("neo4j", "concept-graph-password")

driver = GraphDatabase.driver(uri, auth=auth)

with open('scidk/concept_graph/schema.cypher', 'r') as f:
    schema_cypher = f.read()

# Split by semicolon and execute each statement
statements = [s.strip() for s in schema_cypher.split(';') if s.strip() and not s.strip().startswith('//')]

with driver.session() as session:
    for stmt in statements:
        if stmt:
            try:
                print(f"Executing: {stmt[:60]}...")
                session.run(stmt)
                print("  ✓ Success")
            except Exception as e:
                print(f"  ✗ Error: {e}")

driver.close()
print("\n✓ Schema constraints applied to Concept Graph")
