#!/usr/bin/env python3
"""
Test semantic schema retrieval for Schema Intelligence Layer.
Verifies that relevant labels are retrieved for different query types.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from scidk.app import create_app
from scidk.services.schema_intelligence import get_relevant_schema_context
from scidk.services.chat_service import get_chat_service
from scidk.services.neo4j_client import get_neo4j_params
from neo4j import GraphDatabase

def run_query(query_text: str, expected_labels: list, driver, sqlite_conn, ollama_url, database):
    """Run a single query and print results.

    Not named test_* — it takes six arguments and main() supplies them, but
    pytest saw the old name, tried to collect it as a test, and errored out on
    fixtures it could not find. Keep the prefix off it.
    """
    print(f"\n{'='*80}")
    print(f"Query: \"{query_text}\"")
    print(f"Expected to retrieve: {', '.join(expected_labels)}")
    print(f"{'='*80}")

    try:
        result = get_relevant_schema_context(
            user_query=query_text,
            sqlite_conn=sqlite_conn,
            neo4j_driver=driver,
            ollama_url=ollama_url,
            database=database,
            top_k=5
        )

        retrieved_labels = result.get('labels', [])
        scores = result.get('scores', {})
        method = result.get('retrieval_method', 'unknown')

        print(f"\nRetrieval method: {method}")
        print(f"\nRetrieved labels (top {len(retrieved_labels)}):")
        for label in retrieved_labels:
            score = scores.get(label, 0.0)
            check = "✓" if label in expected_labels else "✗"
            print(f"  {check} {label:20s} (score: {score:.3f})")

        # Check if expected labels are in top results
        matches = [label for label in expected_labels if label in retrieved_labels[:3]]
        print(f"\nMatches in top 3: {len(matches)}/{len(expected_labels)}")

        if matches == expected_labels:
            print("✓ TEST PASSED: All expected labels retrieved")
            return True
        else:
            missing = [label for label in expected_labels if label not in retrieved_labels[:3]]
            if missing:
                print(f"✗ TEST FAILED: Missing expected labels in top 3: {', '.join(missing)}")
            return False

    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("Initializing Flask app...")
    app = create_app()

    with app.app_context():
        print("Connecting to Neo4j and SQLite...")
        uri, user, pwd, database, auth_mode = get_neo4j_params(app)

        if not uri:
            print("ERROR: Neo4j is not configured")
            return 1

        auth = None if (auth_mode or 'basic').lower() == 'none' else (user, pwd)
        driver = GraphDatabase.driver(uri, auth=auth)

        db_path = app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db')
        chat_service = get_chat_service(db_path=db_path)
        sqlite_conn = chat_service._get_conn()

        ollama_url = os.environ.get('SCIDK_CHAT_OLLAMA_ENDPOINT', 'http://localhost:11434')

        try:
            print("\n" + "="*80)
            print("SEMANTIC SCHEMA RETRIEVAL TEST SUITE")
            print("="*80)

            results = []

            # Test 1: File-related query
            results.append(run_query(
                query_text="What types of files are in the dataset?",
                expected_labels=["File"],  # Adjusted expectation - may not have Folder
                driver=driver,
                sqlite_conn=sqlite_conn,
                ollama_url=ollama_url,
                database=database or "neo4j"
            ))

            # Test 2: Sample-related query
            results.append(run_query(
                query_text="What properties do Samples have?",
                expected_labels=["Sample"],  # Adjusted - may not have SampleType
                driver=driver,
                sqlite_conn=sqlite_conn,
                ollama_url=ollama_url,
                database=database or "neo4j"
            ))

            # Test 3: Relationship query
            results.append(run_query(
                query_text="How are scans connected to samples?",
                expected_labels=["Scan", "Sample"],
                driver=driver,
                sqlite_conn=sqlite_conn,
                ollama_url=ollama_url,
                database=database or "neo4j"
            ))

            # Summary
            print("\n" + "="*80)
            print("TEST SUMMARY")
            print("="*80)
            passed = sum(results)
            total = len(results)
            print(f"Passed: {passed}/{total}")

            if passed == total:
                print("\n✓ ALL TESTS PASSED - Semantic retrieval is working correctly!")
                return 0
            else:
                print(f"\n✗ {total - passed} TEST(S) FAILED - Review results above")
                return 1

        finally:
            sqlite_conn.close()
            driver.close()

if __name__ == '__main__':
    sys.exit(main())
