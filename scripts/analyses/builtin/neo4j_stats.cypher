"""
---
id: builtin-neo4j-stats
name: Neo4j Node & Relationship Counts
description: Database statistics showing counts of all node labels and relationship types.
language: cypher
category: analyses/builtin
tags: [neo4j, statistics, schema]
---
"""
// Node counts
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
RETURN label, count, 'relationship' as type
