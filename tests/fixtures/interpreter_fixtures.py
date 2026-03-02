"""
Test fixtures for Interpreter contract validation.

These fixtures test various edge cases and contract requirements
for interpreter scripts.
"""

# Valid minimal interpreter that passes all contract tests
VALID_INTERPRETER = '''
"""Minimal valid interpreter for testing."""
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """
    Basic interpreter that handles files correctly.

    Args:
        file_path: Path to file to interpret

    Returns:
        Dict with status and data keys
    """
    if not file_path.exists():
        return {
            'status': 'error',
            'data': {'error': 'File not found'}
        }

    try:
        content = file_path.read_text()
        return {
            'status': 'success',
            'data': {
                'file_path': str(file_path),
                'size': len(content),
                'lines': len(content.splitlines())
            }
        }
    except Exception as e:
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }
'''

# Missing interpret() function - fails contract
MISSING_INTERPRET_FUNCTION = '''
"""Interpreter missing required function."""
from pathlib import Path

def process_file(file_path: Path) -> dict:
    """Wrong function name - should be interpret()."""
    return {'status': 'success', 'data': {}}
'''

# Doesn't handle missing files gracefully
MISSING_FILE_HANDLING = '''
"""Interpreter that crashes on missing files."""
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """Doesn't check if file exists."""
    # This will crash if file doesn't exist
    content = file_path.read_text()
    return {
        'status': 'success',
        'data': {'content': content}
    }
'''

# Returns wrong type (list instead of dict)
RETURNS_WRONG_TYPE = '''
"""Interpreter that returns list instead of dict."""
from pathlib import Path

def interpret(file_path: Path) -> list:
    """Returns list - violates contract."""
    return ['some', 'data']
'''

# Missing status key in return dict
MISSING_STATUS_KEY = '''
"""Interpreter missing 'status' key in return dict."""
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """Returns dict but missing 'status' key."""
    if not file_path.exists():
        return {'error': 'File not found'}

    return {'data': {'file': str(file_path)}}
'''

# Has syntax errors
SYNTAX_ERROR = '''
"""Interpreter with syntax errors."""
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """Missing closing parenthesis."""
    if not file_path.exists(:
        return {'status': 'error'}
'''

# Handles corrupt CSV edge case correctly
CSV_INTERPRETER_ROBUST = '''
"""CSV interpreter that handles corrupt files."""
import csv
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """Robust CSV interpreter with error handling."""
    if not file_path.exists():
        return {'status': 'error', 'data': {'error': 'File not found'}}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return {
                'status': 'success',
                'data': {'rows': 0, 'columns': 0, 'warning': 'Empty CSV'}
            }

        return {
            'status': 'success',
            'data': {
                'rows': len(rows),
                'columns': len(rows[0]) if rows else 0,
                'headers': rows[0] if rows else []
            }
        }
    except csv.Error as e:
        return {
            'status': 'error',
            'data': {'error': f'CSV parsing error: {e}'}
        }
    except Exception as e:
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }
'''

# FASTQ interpreter that handles edge case: valid headers but no sequences
FASTQ_INTERPRETER_EDGE_CASE = '''
"""FASTQ interpreter that handles empty sequence edge case."""
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """Interprets FASTQ files, handles edge cases."""
    if not file_path.exists():
        return {'status': 'error', 'data': {'error': 'File not found'}}

    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        # FASTQ format: 4 lines per sequence (@header, seq, +, quality)
        if len(lines) == 0:
            return {
                'status': 'success',
                'data': {'sequences': 0, 'warning': 'Empty file'}
            }

        # Edge case: has header line but no actual sequences
        if len(lines) < 4:
            return {
                'status': 'success',
                'data': {
                    'sequences': 0,
                    'warning': 'Incomplete FASTQ - header present but no sequences'
                }
            }

        num_sequences = len(lines) // 4
        return {
            'status': 'success',
            'data': {
                'sequences': num_sequences,
                'total_lines': len(lines)
            }
        }
    except Exception as e:
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }
'''

# Test data files (content as strings to be written to temp files during tests)
CORRUPT_CSV_CONTENT = '''name,age,city
Alice,30,NYC
Bob,25,"Unmatched quote
Charlie,35,Boston'''  # Unmatched quote causes CSV error

EMPTY_FASTQ_CONTENT = '''@HEADER1
'''  # Has header but no sequence data

VALID_CSV_CONTENT = '''name,age,city
Alice,30,NYC
Bob,25,LA
Charlie,35,Boston'''

EMPTY_CSV_CONTENT = ''  # Completely empty file
