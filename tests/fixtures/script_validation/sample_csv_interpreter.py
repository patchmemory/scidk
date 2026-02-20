"""
Sample CSV interpreter for testing validation framework.

This script demonstrates the correct contract for an Interpreter:
- Has interpret(file_path: Path) function
- Returns dict with 'status' key
- Handles missing files gracefully
- Handles corrupt/empty files gracefully
"""
from pathlib import Path
from typing import Dict
import csv


def interpret(file_path: Path) -> Dict:
    """
    Interpret a CSV file and return metadata.

    Args:
        file_path: Path to CSV file

    Returns:
        Dict with 'status' and 'data' keys
    """
    # Handle missing file
    if not file_path.exists():
        return {
            'status': 'error',
            'data': {
                'error': 'File not found',
                'path': str(file_path)
            }
        }

    # Try to read CSV
    try:
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

            # Handle empty file
            if len(rows) == 0:
                return {
                    'status': 'success',
                    'data': {
                        'type': 'csv',
                        'row_count': 0,
                        'headers': [],
                        'message': 'Empty CSV file'
                    }
                }

            # Handle headers only
            if len(rows) == 1:
                return {
                    'status': 'success',
                    'data': {
                        'type': 'csv',
                        'row_count': 0,
                        'headers': rows[0],
                        'message': 'Headers only, no data rows'
                    }
                }

            # Normal case
            return {
                'status': 'success',
                'data': {
                    'type': 'csv',
                    'row_count': len(rows) - 1,  # Exclude header
                    'headers': rows[0],
                    'column_count': len(rows[0])
                }
            }

    except Exception as e:
        return {
            'status': 'error',
            'data': {
                'error': f'Failed to parse CSV: {str(e)}',
                'path': str(file_path)
            }
        }
