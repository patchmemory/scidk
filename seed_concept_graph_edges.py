#!/usr/bin/env python3
"""
Seed missing edges in the concept graph.

Seeds RETRIEVES, REQUIRES, CONNECTED_VIA, and CONNECTS_TO edges
to eliminate planning query warnings and complete the concept graph schema.
"""
from neo4j import GraphDatabase
import os

uri = os.environ.get('SCIDK_CONCEPT_NEO4J_URI', 'bolt://localhost:7689')
user, pwd = os.environ.get(
    'SCIDK_CONCEPT_NEO4J_AUTH', 'neo4j/concept-graph-password'
).split('/', 1)
d = GraphDatabase.driver(uri, auth=(user, pwd))

with d.session() as s:
    print("Seeding RETRIEVES edges...")
    # RETRIEVES edges: run_safe_cypher can retrieve any label
    # (primary=False means general-purpose)
    for label in ['Sample', 'File', 'Folder', 'Scan', 'SampleType']:
        s.run("""
            MATCH (t:Concept_Tool {name: 'run_safe_cypher'})
            MATCH (l:Concept_Label {name: $label})
            MERGE (t)-[:RETRIEVES {primary: false}]->(l)
        """, label=label)

    # generate_summary retrieves all labels (primary=false)
    for label in ['Sample', 'File', 'Folder', 'Scan', 'SampleType']:
        s.run("""
            MATCH (t:Concept_Tool {name: 'generate_summary'})
            MATCH (l:Concept_Label {name: $label})
            MERGE (t)-[:RETRIEVES {primary: false}]->(l)
        """, label=label)

    print("Seeding REQUIRES edges...")
    # REQUIRES edges: react_loop requires run_safe_cypher
    s.run("""
        MATCH (t1:Concept_Tool {name: 'react_loop'})
        MATCH (t2:Concept_Tool {name: 'run_safe_cypher'})
        MERGE (t1)-[:REQUIRES {order: 1}]->(t2)
    """)

    print("Seeding CONNECTED_VIA and CONNECTS_TO edges...")
    # CONNECTED_VIA edges: mirror actual research graph relationships
    rels = [
        ('File', 'SCANNED_IN', 'Scan'),
        ('Folder', 'SCANNED_IN', 'Scan'),
        ('Folder', 'CONTAINS', 'File'),
        ('Sample', 'OF_TYPE', 'SampleType'),
        ('Sample', 'DERIVED_FROM', 'Sample'),
    ]
    for source, rel_type, target in rels:
        s.run("""
            MERGE (r:Concept_Relationship {type: $rel_type})
            WITH r
            MATCH (src:Concept_Label {name: $source})
            MATCH (tgt:Concept_Label {name: $target})
            MERGE (src)-[:CONNECTED_VIA]->(r)
            MERGE (r)-[:CONNECTS_TO]->(tgt)
        """, rel_type=rel_type, source=source, target=target)

    print("\n✓ Edges seeded.")
    print("\nEdge counts:")
    result = s.run("MATCH ()-[r]->() RETURN type(r) as rel_type, count(r) as count ORDER BY count DESC").data()
    for row in result:
        print(f"  {row['rel_type']}: {row['count']}")

d.close()
