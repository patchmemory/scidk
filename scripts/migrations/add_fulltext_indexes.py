"""
Add Neo4j full-text indexes for key string properties.

This script creates full-text indexes on text-based properties across all labels,
enabling fast keyword search without embedding overhead.

Usage:
    python scripts/migrations/add_fulltext_indexes.py

Features:
- Auto-discovers labels and string properties
- Creates label-specific full-text indexes
- Skips existing indexes
- Safe to re-run (idempotent)
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from neo4j import GraphDatabase
from typing import List, Dict, Set


def get_neo4j_connection():
    """Get Neo4j connection from environment."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USER', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')

    return GraphDatabase.driver(uri, auth=(user, password))


def get_existing_fulltext_indexes(session) -> Set[str]:
    """Get names of existing full-text indexes."""
    result = session.run("SHOW INDEXES YIELD name, type WHERE type = 'FULLTEXT' RETURN name")
    return {record['name'] for record in result}


def get_text_properties_per_label(session, label: str) -> List[str]:
    """
    Get string properties for a label that are good candidates for full-text search.

    Heuristics:
    - String type
    - Not IDs or timestamps
    - Commonly used (present in >50% of nodes)
    """
    # Simplified: just get all string properties, filter by heuristics
    query = f"""
    MATCH (n:`{label}`)
    UNWIND keys(n) AS prop
    WITH DISTINCT prop, n[prop] AS value
    WHERE value IS NOT NULL
      AND (value IS :: STRING)
      AND NOT prop =~ '(?i).*(id|uuid|timestamp|created|updated|date).*'
    RETURN DISTINCT prop
    LIMIT 5
    """

    try:
        result = session.run(query)
        return [record['prop'] for record in result]
    except Exception as e:
        print(f"  ⚠️  Could not analyze properties for {label}: {e}")
        return []


def create_fulltext_index(session, label: str, properties: List[str], existing_indexes: Set[str]) -> bool:
    """
    Create a full-text index for the given label and properties.

    Returns True if created, False if skipped.
    """
    if not properties:
        return False

    # Index name follows Neo4j convention
    index_name = f"{label.lower()}_fulltext_idx"

    if index_name in existing_indexes:
        print(f"  ⏭️  Skipping {label} (index already exists)")
        return False

    # Build property list for query
    props_str = ', '.join([f'n.{prop}' for prop in properties])

    query = f"""
    CREATE FULLTEXT INDEX {index_name}
    FOR (n:`{label}`)
    ON EACH [{props_str}]
    OPTIONS {{indexConfig: {{`fulltext.analyzer`: 'standard'}}}}
    """

    try:
        session.run(query)
        print(f"  ✅ Created {index_name} on properties: {', '.join(properties)}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to create {index_name}: {e}")
        return False


def main():
    """Main migration logic."""
    print("🔍 Adding Neo4j full-text indexes...")
    print()

    driver = get_neo4j_connection()

    try:
        with driver.session() as session:
            # Get all labels
            result = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [record['label'] for record in result]

            print(f"Found {len(labels)} labels in database")
            print()

            # Get existing indexes
            existing_indexes = get_existing_fulltext_indexes(session)
            if existing_indexes:
                print(f"Existing full-text indexes: {', '.join(existing_indexes)}")
                print()

            # Process each label
            created_count = 0
            skipped_count = 0

            for label in labels:
                print(f"Processing {label}...")

                # Find text properties suitable for indexing
                text_props = get_text_properties_per_label(session, label)

                if not text_props:
                    print(f"  ⏭️  No suitable text properties found")
                    skipped_count += 1
                    continue

                # Create index
                if create_fulltext_index(session, label, text_props, existing_indexes):
                    created_count += 1
                else:
                    skipped_count += 1

            print()
            print(f"✨ Complete! Created {created_count} indexes, skipped {skipped_count}")

            # Show usage example
            if created_count > 0:
                print()
                print("📖 Usage example:")
                print(f"   CALL db.index.fulltext.queryNodes(")
                print(f"     '{labels[0].lower()}_fulltext_idx',")
                print(f"     'search terms'")
                print(f"   ) YIELD node, score")
                print(f"   RETURN node, score")
                print(f"   ORDER BY score DESC")

    finally:
        driver.close()


if __name__ == '__main__':
    main()
