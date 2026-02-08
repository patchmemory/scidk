"""
Tests for schema-agnostic entity extractor.
"""
import pytest
from scidk.services.graphrag.entity_extractor import EntityExtractor


def test_extract_identifiers():
    """Test extracting IDs."""
    extractor = EntityExtractor(anthropic_api_key=None)
    result = extractor.extract("Find files for NHP123 and A001")
    assert 'NHP123' in result['identifiers']
    assert 'A001' in result['identifiers']


def test_detect_intents():
    """Test detecting different intents."""
    extractor = EntityExtractor()
    
    assert extractor.extract("Find some files")['intent'] == 'find'
    assert extractor.extract("How many files?")['intent'] == 'count'
    assert extractor.extract("List all scans")['intent'] == 'list'
    assert extractor.extract("Show files")['intent'] == 'show'


def test_match_schema_labels():
    """Test matching labels from schema."""
    extractor = EntityExtractor()
    schema = {'labels': ['File', 'Folder'], 'relationships': []}
    
    result = extractor.extract("Find all files", schema)
    assert 'File' in result['labels']


def test_extract_properties():
    """Test extracting property filters."""
    extractor = EntityExtractor()
    
    result = extractor.extract("Find files with name=test.txt")
    assert result['properties'].get('name') == 'test.txt'


def test_no_api_key_uses_patterns():
    """Test pattern matching without API key."""
    extractor = EntityExtractor(anthropic_api_key=None)
    assert extractor.use_llm is False
    
    result = extractor.extract("Find TEST_001")
    assert 'TEST_001' in result['identifiers']
