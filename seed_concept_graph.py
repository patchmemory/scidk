#!/usr/bin/env python3
"""
Seed Concept Graph with intents, tools, and schema labels.

Runs within Flask app context to bypass auth middleware and access app configuration.
Follows the same pattern as seed_schema_embeddings.py.

Usage:
    python seed_concept_graph.py
"""
import os
import sys

# Add scidk to path
sys.path.insert(0, os.path.dirname(__file__))

from scidk.app import create_app


def main():
    print("Initializing Flask app...")
    app = create_app()

    with app.app_context():
        # Get concept graph driver
        concept_driver = app.extensions['scidk'].get('concept_driver')

        if not concept_driver:
            print("ERROR: Concept graph is not configured or unavailable")
            print("Check these environment variables:")
            print("  SCIDK_CONCEPT_NEO4J_URI (default: bolt://localhost:7689)")
            print("  SCIDK_CONCEPT_NEO4J_AUTH (default: neo4j/concept-graph-password)")
            print("  SCIDK_CONCEPT_GRAPH_ENABLED (default: 1)")
            return 1

        print(f"Connected to concept graph")

        # Get research graph driver for schema sync
        from scidk.services.neo4j_client import get_neo4j_params
        from neo4j import GraphDatabase

        uri, user, pwd, database, auth_mode = get_neo4j_params(app)

        if not uri:
            print("ERROR: Research graph (Neo4j) is not configured")
            print("Concept graph needs research graph schema for label sync")
            return 1

        auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
        research_driver = GraphDatabase.driver(uri, auth=auth)
        print(f"Connected to research graph at {uri}")

        # Get SQLite connection
        from scidk.services.chat_service import get_chat_service
        db_path = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        print(f"Using SQLite database: {db_path}")
        chat_service = get_chat_service(db_path=db_path)
        sqlite_conn = chat_service._get_conn()

        try:
            from scidk.services.concept_graph_service import (
                seed_intents_from_yaml,
                seed_tools_from_yaml,
                sync_labels_from_schema
            )

            ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
            yaml_path = os.path.join(os.path.dirname(__file__), 'scidk/concept_graph/intents.yaml')

            print(f"Using Ollama at: {ollama_url}")
            print(f"Loading intents from: {yaml_path}")

            # Step 1: Seed intents
            print("\n" + "="*60)
            print("STEP 1: Seeding intents...")
            print("="*60)
            result = seed_intents_from_yaml(concept_driver, yaml_path, ollama_url)
            print(f"✓ Intents embedded: {result['embedded']}")
            print(f"✗ Intents failed: {result['failed']}")

            # Step 2: Seed tools
            print("\n" + "="*60)
            print("STEP 2: Seeding tools...")
            print("="*60)
            result = seed_tools_from_yaml(concept_driver, yaml_path, ollama_url)
            print(f"✓ Tools embedded: {result['embedded']}")
            print(f"✗ Tools failed: {result['failed']}")

            # Step 3: Sync labels from research schema
            print("\n" + "="*60)
            print("STEP 3: Syncing labels from research schema...")
            print("="*60)
            result = sync_labels_from_schema(concept_driver, research_driver, sqlite_conn)
            print(f"✓ Labels synced: {result['labels']}")
            print(f"✓ Relationships synced: {result['relationships']}")
            print(f"✓ Edges created: {result['edges']}")

            # Verification
            print("\n" + "="*60)
            print("VERIFICATION")
            print("="*60)

            with concept_driver.session() as session:
                # Count nodes by label
                result = session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY label")
                print("\nNode counts:")
                for record in result:
                    print(f"  {record['label']}: {record['count']}")

                # Count SATISFIES edges
                result = session.run("MATCH ()-[r:SATISFIES]->() RETURN count(r) AS count")
                satisfies_count = result.single()['count']
                print(f"\nSATISFIES edges: {satisfies_count}")

                # Count RETRIEVES edges
                result = session.run("MATCH ()-[r:RETRIEVES]->() RETURN count(r) AS count")
                retrieves_count = result.single()['count']
                print(f"RETRIEVES edges: {retrieves_count}")

                # Count REFERENCES_LABEL edges
                result = session.run("MATCH ()-[r:REFERENCES_LABEL]->() RETURN count(r) AS count")
                references_count = result.single()['count']
                print(f"REFERENCES_LABEL edges: {references_count}")

            print("\n" + "="*60)
            print("✓ SUCCESS! Concept graph seeded successfully")
            print("="*60)
            print("\nNext steps:")
            print("  1. Restart gunicorn to load concept_driver:")
            print("     pkill -f gunicorn && gunicorn -w 16 -b 127.0.0.1:5000 --timeout 300 \"scidk.app:create_app()\"")
            print("  2. Verify in Neo4j Browser: http://localhost:7476/browser/")
            print("     Run: MATCH (n) RETURN labels(n), count(n)")
            print("  3. Test with a chat query")

            return 0

        except Exception as e:
            print(f"\n✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            sqlite_conn.close()
            research_driver.close()
            concept_driver.close()


if __name__ == '__main__':
    sys.exit(main())
