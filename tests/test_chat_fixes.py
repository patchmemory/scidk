"""
Tests for conversation context injection and REACT routing fixes.

Tests Fix 1: Conversation context from SQLite
Tests Fix 2: REACT pattern matching for cross-service queries
"""
import pytest
from scidk.services.chat_service import ChatService
from scidk.services.graphrag.intent_classifier import classify, Intent


def test_get_recent_turns_empty_session():
    """Test get_recent_turns with no messages returns empty string."""
    import tempfile
    import os

    # Use temp file instead of :memory: to ensure migrations run
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        chat_service = ChatService(db_path=db_path)

        # Create session with no messages
        session = chat_service.create_session("Test Session")

        # Should return empty string
        result = chat_service.get_recent_turns(session.id, n=4)
        assert result == ""
    finally:
        os.unlink(db_path)


def test_get_recent_turns_formats_correctly():
    """Test get_recent_turns formats messages as User/Assistant pairs."""
    import tempfile
    import os

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        chat_service = ChatService(db_path=db_path)

        # Create session with messages
        session = chat_service.create_session("Test Session")
        chat_service.add_message(session.id, "user", "How many files do you have?")
        chat_service.add_message(session.id, "assistant", "There are 1684 files.")
        chat_service.add_message(session.id, "user", "What about folders?")

        # Get recent turns
        result = chat_service.get_recent_turns(session.id, n=4)

        # Check formatting
        assert "[Previous turns]" in result
        assert "User: How many files do you have?" in result
        assert "Assistant: There are 1684 files." in result
        assert "User: What about folders?" in result
        assert "---" in result
    finally:
        os.unlink(db_path)


def test_get_recent_turns_limits_to_n():
    """Test get_recent_turns respects n parameter."""
    import tempfile
    import os

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        chat_service = ChatService(db_path=db_path)

        # Create session with many messages
        session = chat_service.create_session("Test Session")
        for i in range(10):
            chat_service.add_message(session.id, "user", f"Message {i}")
            chat_service.add_message(session.id, "assistant", f"Response {i}")

        # Get only last 2 turns (4 messages)
        result = chat_service.get_recent_turns(session.id, n=2)

        # Should only contain last 2 user messages and 2 assistant messages
        assert "Message 8" in result
        assert "Message 9" in result
        assert "Message 7" not in result  # Too old
    finally:
        os.unlink(db_path)


def test_get_recent_turns_truncates_long_messages():
    """Test get_recent_turns truncates messages longer than 150 chars."""
    import tempfile
    import os

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        chat_service = ChatService(db_path=db_path)

        # Create session with long message
        session = chat_service.create_session("Test Session")
        long_message = "A" * 200
        chat_service.add_message(session.id, "user", long_message)

        # Get recent turns
        result = chat_service.get_recent_turns(session.id, n=4)

        # Should be truncated with ellipsis
        assert "..." in result
        assert len(result) < 300  # Much shorter than original 200 char message
    finally:
        os.unlink(db_path)


# ========== Intent Classifier Tests for REACT Patterns ==========

def test_react_pattern_service_names():
    """Test REACT patterns match service names like Dropbox, SharePoint, Google."""
    queries = [
        "Find folders in Dropbox",
        "Show me SharePoint files",
        "List Google Drive items",
        "CAC folders in dropbox",  # lowercase
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_across_services():
    """Test REACT patterns match 'across services/sources/platforms'."""
    queries = [
        "Find CAC folders across all services",
        "Compare files across platforms",
        "Check redundancy across sources",
        "Show me data across 3 services",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_all_three():
    """Test REACT patterns match 'all three/2/3'."""
    queries = [
        "Check all three services",
        "Find folders in all 3 platforms",
        "Compare all 2 sources",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_each_service():
    """Test REACT patterns match 'each service/source/platform'."""
    queries = [
        "Count files in each service",
        "Show folders from each source",
        "Check each platform",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_redundancy():
    """Test REACT patterns match 'redundant/redundancy'."""
    queries = [
        "Are there redundant folders?",
        "Check for redundancy",
        "Find redundant files",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_compare_across():
    """Test REACT patterns match 'compare across/between'."""
    queries = [
        "Compare folders across services",
        "Compare data between platforms",
        "Compare files across all sources",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_multi_service():
    """Test REACT patterns match 'multi-service/multiple-service'."""
    queries = [
        "Run a multi-service query",
        "Do a multiple-platform search",
        "Multi-source analysis",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_check_all():
    """Test REACT patterns match 'check all/each/every' when combined with context."""
    queries = [
        "Check all folders for redundancy",  # Triggers redundancy pattern
        "Verify each service has CAC folders",  # Triggers 'each service' pattern
        "Check all three platforms",  # Triggers 'all three' pattern
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.REACT, f"Expected REACT for '{query}', got {intent}"


def test_react_pattern_complex_cross_service_query():
    """Test the exact query from the bug report routes to REACT."""
    query = "Find all base-level folders related to CAC in Dropbox, SharePoint, and Google Drive, and tell me if any are redundant"

    intent = classify(query)
    assert intent == Intent.REACT, f"Expected REACT for complex cross-service query, got {intent}"


def test_react_pattern_does_not_override_summarize():
    """Test REACT patterns don't override higher-priority SUMMARIZE."""
    # SUMMARIZE patterns should have higher priority
    query = "What do we have in the database?"  # Explicitly triggers SUMMARIZE pattern
    intent = classify(query)
    assert intent == Intent.SUMMARIZE


def test_simple_lookup_still_routes_to_lookup():
    """Test simple lookups don't get caught by new REACT patterns."""
    queries = [
        "How many files?",
        "List all folders",
        "Show me samples",
    ]

    for query in queries:
        intent = classify(query)
        assert intent == Intent.LOOKUP, f"Expected LOOKUP for '{query}', got {intent}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
