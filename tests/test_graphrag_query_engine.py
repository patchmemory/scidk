"""
Tests for schema-agnostic GraphRAG query engine.
"""
import pytest
from unittest.mock import Mock
from scidk.services.graphrag.query_engine import QueryEngine


def test_initialization():
    """Test QueryEngine initialization."""
    driver = Mock()
    schema = {'labels': ['File'], 'relationships': []}
    
    engine = QueryEngine(
        driver=driver,
        neo4j_schema=schema,
        anthropic_api_key=None,
        verbose=False
    )
    
    assert engine.driver == driver
    assert engine.neo4j_schema == schema
    assert engine.verbose is False


def test_format_answer_single_result():
    """Test formatting single result."""
    driver = Mock()
    schema = {'labels': [], 'relationships': []}
    engine = QueryEngine(driver, schema)
    
    result_obj = type('Result', (), {'items': [{'name': 'test.txt'}]})
    answer = engine._format_answer(result_obj, "Find files")
    
    assert 'Found 1 result' in answer
    assert 'test.txt' in answer


def test_format_answer_multiple_results():
    """Test formatting multiple results."""
    driver = Mock()
    schema = {'labels': [], 'relationships': []}
    engine = QueryEngine(driver, schema)
    
    result_obj = type('Result', (), {
        'items': [{'name': f'file{i}.txt'} for i in range(3)]
    })
    answer = engine._format_answer(result_obj, "Find files")
    
    assert 'Found 3 results' in answer


def test_format_answer_no_results():
    """Test formatting empty results."""
    driver = Mock()
    schema = {'labels': [], 'relationships': []}
    engine = QueryEngine(driver, schema)

    result_obj = type('Result', (), {'items': []})
    answer = engine._format_answer(result_obj, "Find files")

    assert 'no results' in answer.lower()


def test_format_item_with_name():
    """Test formatting item with name field."""
    driver = Mock()
    schema = {'labels': [], 'relationships': []}
    engine = QueryEngine(driver, schema)
    
    item = {'name': 'test.txt', 'id': '123'}
    formatted = engine._format_item(item)
    
    assert formatted == 'test.txt'


def test_format_item_with_id():
    """Test formatting item with id field."""
    driver = Mock()
    schema = {'labels': [], 'relationships': []}
    engine = QueryEngine(driver, schema)
    
    item = {'id': '123'}
    formatted = engine._format_item(item)
    
    assert 'ID: 123' in formatted
