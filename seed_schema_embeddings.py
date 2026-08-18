#!/usr/bin/env python3
"""
Seed schema embeddings for Schema Intelligence Layer.
Runs within Flask app context to bypass auth middleware.
"""
import os
import sys

# Add scidk to path
sys.path.insert(0, os.path.dirname(__file__))

from scidk.app import create_app
from scidk.services.schema_intelligence import refresh_schema_embeddings
from scidk.services.chat_service import get_chat_service
from scidk.services.neo4j_client import get_neo4j_params
from neo4j import GraphDatabase

def main():
    print("Initializing Flask app...")
    app = create_app()

    with app.app_context():
        print("Getting Neo4j connection parameters...")
        uri, user, pwd, database, auth_mode = get_neo4j_params(app)

        if not uri:
            print("ERROR: Neo4j is not configured")
            return 1

        auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
        driver = GraphDatabase.driver(uri, auth=auth)
        print(f"Connected to Neo4j at {uri}")

        # Get SQLite connection
        db_path = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        print(f"Using SQLite database: {db_path}")
        chat_service = get_chat_service(db_path=db_path)
        sqlite_conn = chat_service._get_conn()

        try:
            ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')
            print(f"Using Ollama at: {ollama_url}")
            print("\nRefreshing schema embeddings...")

            result = refresh_schema_embeddings(
                neo4j_driver=driver,
                sqlite_conn=sqlite_conn,
                ollama_url=ollama_url,
                database=database or "neo4j"
            )

            print(f"\n✓ Success!")
            print(f"  - Embedded: {result['embedded']}")
            print(f"  - Failed: {result['failed']}")

            # Check status
            cursor = sqlite_conn.cursor()
            label_count = cursor.execute(
                "SELECT COUNT(*) FROM label_profile WHERE embedding IS NOT NULL"
            ).fetchone()[0]
            rel_count = cursor.execute(
                "SELECT COUNT(*) FROM relationship_profile WHERE embedding IS NOT NULL"
            ).fetchone()[0]

            print(f"\nCurrent status:")
            print(f"  - Labels with embeddings: {label_count}")
            print(f"  - Relationship types with embeddings: {rel_count}")

            return 0

        except Exception as e:
            print(f"\n✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            sqlite_conn.close()
            driver.close()

if __name__ == '__main__':
    sys.exit(main())
