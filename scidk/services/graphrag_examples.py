from __future__ import annotations

# Minimal curated examples to guide Text2CypherRetriever
# Format expected by neo4j_graphrag: list of dicts with 'question' and 'cypher' keys

examples = [
    {
        "question": "Show all files connected to the Smith collaboration",
        "cypher": (
            "MATCH (c:Collaboration {name: 'Smith'})-[:INVOLVES]->(:Project)-[:HAS_FILE]->(f:File) "
            "RETURN f.path AS path, f.filename AS filename LIMIT 50"
        )
    },
    {
        "question": "Datasets related to protein interactions from 2023",
        "cypher": (
            "MATCH (d:Dataset)-[:ABOUT]->(t:Topic {name:'protein interactions'}) "
            "WHERE coalesce(d.year, d.createdYear) = 2023 "
            "RETURN d.id AS id, d.name AS name LIMIT 50"
        )
    },
    {
        "question": "Projects linked to collaboration X",
        "cypher": (
            "MATCH (c:Collaboration {name:$name})-[:INVOLVES]->(p:Project) "
            "RETURN p.id AS id, p.name AS name"
        )
    },
]
