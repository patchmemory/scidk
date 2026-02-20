"""
Test fixtures for Plugin contract validation.

These fixtures test various edge cases and contract requirements
for plugin scripts (base contract).
"""

# Valid minimal plugin that passes all contract tests
VALID_PLUGIN = '''
"""Minimal valid plugin for testing."""

def run(context: dict) -> dict:
    """
    Basic plugin that returns valid dict.

    Args:
        context: Input context dictionary

    Returns:
        Dict with status and data keys
    """
    return {
        'status': 'success',
        'data': {
            'message': 'Plugin executed successfully',
            'input_keys': list(context.keys())
        }
    }
'''

# Returns list instead of dict - violates base contract
RETURNS_LIST_NOT_DICT = '''
"""Plugin that returns list instead of dict."""

def run(context: dict) -> list:
    """Returns list - violates contract."""
    return ['item1', 'item2', 'item3']
'''

# Returns None - violates contract
RETURNS_NONE = '''
"""Plugin that returns None."""

def run(context: dict):
    """Returns None - violates contract."""
    # Missing return statement
    print("Processing...")
'''

# Has syntax errors
SYNTAX_ERROR = '''
"""Plugin with syntax errors."""

def run(context: dict) -> dict:
    """Missing closing brace."""
    return {
        'status': 'success'
'''

# Plugin that uses disallowed import (subprocess)
DISALLOWED_IMPORT = '''
"""Plugin that tries to import subprocess."""
import subprocess

def run(context: dict) -> dict:
    """Uses subprocess - should be blocked."""
    result = subprocess.run(['ls'], capture_output=True)
    return {'status': 'success', 'data': {'output': result.stdout}}
'''

# Plugin that uses relative import
RELATIVE_IMPORT = '''
"""Plugin that tries relative import."""
from . import helper_module

def run(context: dict) -> dict:
    """Uses relative import - should be blocked."""
    return helper_module.process(context)
'''

# Valid plugin with proper error handling
PLUGIN_WITH_ERROR_HANDLING = '''
"""Plugin with comprehensive error handling."""

def run(context: dict) -> dict:
    """Plugin that handles errors gracefully."""
    try:
        required_key = context.get('required_param')

        if not required_key:
            return {
                'status': 'error',
                'data': {'error': 'Missing required_param in context'}
            }

        # Process data
        result = process_data(required_key)

        return {
            'status': 'success',
            'data': {'result': result}
        }

    except Exception as e:
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }


def process_data(data):
    """Helper function."""
    return f"Processed: {data}"
'''

# Plugin that takes too long (for timeout testing)
SLOW_PLUGIN = '''
"""Plugin that takes a long time to execute."""
import time

def run(context: dict) -> dict:
    """Sleeps for 15 seconds - should timeout."""
    time.sleep(15)
    return {'status': 'success', 'data': {}}
'''

# Valid data transformation plugin (realistic use case)
DATA_NORMALIZER_PLUGIN = '''
"""Plugin that normalizes data format."""
import json

def run(context: dict) -> dict:
    """Normalizes input data to standard format."""
    try:
        raw_data = context.get('data', [])

        if not isinstance(raw_data, list):
            return {
                'status': 'error',
                'data': {'error': 'Input data must be a list'}
            }

        normalized = []
        for item in raw_data:
            if isinstance(item, dict):
                normalized.append({
                    'id': item.get('id', ''),
                    'value': str(item.get('value', '')).strip().lower(),
                    'metadata': item.get('metadata', {})
                })

        return {
            'status': 'success',
            'data': {
                'normalized': normalized,
                'count': len(normalized)
            }
        }

    except Exception as e:
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }
'''

# Valid statistical plugin (realistic use case)
STATS_CALCULATOR_PLUGIN = '''
"""Plugin that calculates statistics on data."""
import statistics

def run(context: dict) -> dict:
    """Calculates basic statistics on numeric data."""
    try:
        values = context.get('values', [])

        if not values:
            return {
                'status': 'error',
                'data': {'error': 'No values provided'}
            }

        # Convert to floats
        numeric_values = [float(v) for v in values]

        return {
            'status': 'success',
            'data': {
                'mean': statistics.mean(numeric_values),
                'median': statistics.median(numeric_values),
                'stdev': statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0,
                'min': min(numeric_values),
                'max': max(numeric_values),
                'count': len(numeric_values)
            }
        }

    except ValueError as e:
        return {
            'status': 'error',
            'data': {'error': f'Invalid numeric data: {e}'}
        }
    except Exception as e:
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }
'''

# Test context data for plugins
TEST_CONTEXT = {
    'project_id': 'test-project-123',
    'user': 'test_user',
    'parameters': {'param1': 'value1', 'param2': 'value2'}
}

TEST_DATA_CONTEXT = {
    'data': [
        {'id': '1', 'value': '  ALICE  ', 'metadata': {'age': 30}},
        {'id': '2', 'value': 'Bob', 'metadata': {'age': 25}},
        {'id': '3', 'value': '  charlie  '}
    ]
}

TEST_STATS_CONTEXT = {
    'values': [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
}

EMPTY_CONTEXT = {}
