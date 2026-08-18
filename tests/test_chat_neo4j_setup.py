"""
Test chat Neo4j setup and connectivity.

Gate 2 verification tests:
- Chat Neo4j container is accessible
- Indexes can be created
- Messages can be written and retrieved
- Staleness detection works correctly
"""
import pytest
import time
import json

pytestmark = pytest.mark.integration

from scidk.services.chat_neo4j_client import ChatNeo4jClient, get_chat_neo4j_client
from scidk.ai.chat_graph import (
    get_label_snapshot,
    check_staleness,
    retrieve_relevant_context,
    format_context_for_prompt,
    log_chat_message
)


def test_chat_neo4j_connection():
    """Test: Can connect to chat Neo4j."""
    client = get_chat_neo4j_client()
    assert client is not None, "Chat Neo4j client should be created"

    connected = client.verify_connection()
    assert connected, "Chat Neo4j should be accessible"

    client.close()


def test_chat_neo4j_ensure_schema():
    """Test: Can create indexes in chat Neo4j."""
    client = get_chat_neo4j_client()
    assert client is not None

    # Create schema (idempotent)
    client.ensure_schema()

    # Verify indexes were created by querying them
    with client._session() as session:
        # Check if indexes exist (Neo4j 5.x syntax)
        result = session.run("SHOW INDEXES")
        indexes = [record["name"] for record in result]

        # Should have created these indexes
        expected_indexes = [
            "chat_message_session",
            "chat_message_timestamp",
            "chat_message_finding_type",
            "chat_session_id"
        ]

        for expected in expected_indexes:
            assert expected in indexes, f"Index {expected} should be created"

    client.close()


def test_write_and_retrieve_chat_message():
    """Test: Can write ChatMessage to chat Neo4j and retrieve it."""
    chat_client = get_chat_neo4j_client()
    assert chat_client is not None

    # Create a mock research driver that returns empty snapshot
    class MockResearchDriver:
        def session(self):
            class MockSession:
                def run(self, query):
                    class MockResult:
                        def __iter__(self):
                            return iter([])
                        def single(self):
                            return {"count": 0}
                    return MockResult()
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockSession()

    mock_research_driver = MockResearchDriver()

    # Log a test message
    test_session_id = f"test_session_{int(time.time())}"
    test_sqlite_id = f"test_msg_{int(time.time())}"

    log_chat_message(
        chat_driver=chat_client,
        research_driver=mock_research_driver,
        sqlite_id=test_sqlite_id,
        session_id=test_session_id,
        role="user",
        intent="LOOKUP",
        content_summary="Test query about samples",
        finding_text=None,
        finding_type="NONE",
        cypher_used=None,
        referenced_labels=[],
        embedding=None
    )

    # Retrieve the message
    result = chat_client.execute_read(
        """
        MATCH (m:ChatMessage {sqlite_id: $sqlite_id})
        RETURN m
        """,
        {"sqlite_id": test_sqlite_id}
    )

    assert len(result) == 1, "Should retrieve exactly one message"
    msg = result[0]["m"]
    assert msg["role"] == "user"
    assert msg["intent"] == "LOOKUP"
    assert msg["session_id"] == test_session_id

    # Cleanup
    chat_client.execute_write(
        "MATCH (m:ChatMessage {sqlite_id: $sqlite_id}) DETACH DELETE m",
        {"sqlite_id": test_sqlite_id}
    )
    chat_client.execute_write(
        "MATCH (s:ChatSession {session_id: $session_id}) DETACH DELETE s",
        {"session_id": test_session_id}
    )

    chat_client.close()


def test_staleness_detection():
    """Test: Staleness detection calculates correct percentage changes."""
    # Mock research driver that returns different counts
    class MockResearchDriver:
        def __init__(self, snapshot):
            self.snapshot = snapshot

        def session(self):
            class MockSession:
                def __init__(self, snapshot):
                    self.snapshot = snapshot

                def run(self, query):
                    if "db.labels()" in query:
                        class LabelsResult:
                            def __init__(self, labels):
                                self.labels = labels
                            def __iter__(self):
                                return iter([{"label": label} for label in self.labels])
                        return LabelsResult(list(self.snapshot.keys()))
                    else:
                        # Extract label from query
                        for label in self.snapshot.keys():
                            if label in query:
                                class CountResult:
                                    def __init__(self, count):
                                        self.count = count
                                    def single(self):
                                        return {"count": self.count}
                                return CountResult(self.snapshot[label])
                        class EmptyResult:
                            def single(self):
                                return {"count": 0}
                        return EmptyResult()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

            return MockSession(self.snapshot)

    # Test message with stored snapshot
    message = {
        "referenced_labels": ["Sample", "Treatment"],
        "snapshot": {"Sample": 1000, "Treatment": 50},
        "finding_type": "COUNT"
    }

    # Current snapshot shows significant changes
    current_snapshot = {"Sample": 1080, "Treatment": 50}  # 8% increase in Sample
    mock_driver = MockResearchDriver(current_snapshot)

    signals = check_staleness(message, mock_driver)

    assert len(signals) == 2, "Should return signals for both labels"

    # Find Sample signal
    sample_signal = next(s for s in signals if s["label"] == "Sample")
    assert sample_signal["stored_count"] == 1000
    assert sample_signal["current_count"] == 1080
    assert sample_signal["delta"] == 80
    assert 0.07 < sample_signal["pct_change"] < 0.09  # ~8%
    assert sample_signal["status"] == "moderate_change"
    assert sample_signal["should_flag"] is True  # COUNT finding with moderate change

    # Find Treatment signal
    treatment_signal = next(s for s in signals if s["label"] == "Treatment")
    assert treatment_signal["status"] == "unchanged"
    assert treatment_signal["should_flag"] is False


def test_format_context_for_prompt():
    """Test: Context formatting stays under token budget."""
    messages = [
        {
            "timestamp": time.time() - 86400,  # 1 day ago
            "intent": "LOOKUP",
            "content_summary": "How many samples are in the database?",
            "finding_text": "Found 9042 samples",
            "cypher_used": "MATCH (s:Sample) RETURN count(s)",
            "staleness_signals": [
                {"message": "Sample: 9847 now vs 9042 then (+805 nodes) ⚠️", "should_flag": True}
            ]
        },
        {
            "timestamp": time.time() - 172800,  # 2 days ago
            "intent": "SUMMARIZE",
            "content_summary": "What data do we have in the graph?",
            "finding_text": "Database contains 3 node types with 10k total nodes",
            "cypher_used": "",
            "staleness_signals": []
        }
    ]

    context = format_context_for_prompt(messages)

    assert len(context) > 0, "Context should be generated"
    assert "[PAST CONTEXT" in context, "Should have context header"
    assert "LOOKUP" in context, "Should include intent"
    assert "Finding:" in context, "Should include findings"
    assert "Staleness:" in context, "Should include staleness warnings"

    # Rough token check (~4 chars per token, target 800 tokens = 3200 chars)
    assert len(context) < 3500, f"Context should stay under token budget (got {len(context)} chars)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
