# Interpreter Contract

## Purpose

Interpreters take a file path and return metadata about that file. They enable SciDK to understand and extract information from various file formats (CSV, JSON, YAML, images, scientific data files, etc.).

## Required Signature

```python
def interpret(file_path: Path) -> Dict:
    """
    Interpret a file and return metadata.

    Args:
        file_path: Path to file to interpret

    Returns:
        Dict with 'status' and 'data' keys
    """
```

## Return Type

```python
{
    'status': 'success' | 'error',
    'data': {
        # For success: metadata about the file
        'type': str,           # File type (csv, json, image, etc.)
        'row_count': int,      # Optional: number of rows/records
        'column_count': int,   # Optional: number of columns/fields
        # ... any other metadata

        # For error: error details
        'error': str,          # Error message
        'path': str            # Path that failed
    }
}
```

## Contract Tests

Your interpreter will be tested against these requirements:

1. ✅ **Has interpret() function** - Must define a function named `interpret`
2. ✅ **Accepts Path parameter** - Function must accept at least one parameter (file_path)
3. ✅ **Returns dict** - Must return a dictionary object
4. ✅ **Returns 'status' key** - Dict must contain a 'status' key
5. ✅ **Handles missing file** - Must return `{'status': 'error', 'data': {...}}` for non-existent files
6. ✅ **Handles corrupt file** - Must return `{'status': 'error', 'data': {...}}` or handle gracefully
7. ✅ **Handles empty file** - Must return `{'status': 'success', 'data': {...}}` with appropriate metadata

## Example Implementation

```python
"""
---
id: csv-interpreter
name: CSV Interpreter
category: interpreters
language: python
description: Interprets CSV files and extracts metadata
---
"""
from pathlib import Path
from typing import Dict
import csv

def interpret(file_path: Path) -> Dict:
    """Interpret a CSV file."""

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
                        'headers': []
                    }
                }

            # Normal case
            return {
                'status': 'success',
                'data': {
                    'type': 'csv',
                    'row_count': len(rows) - 1,
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
```

## Best Practices

1. **Always check if file exists** before opening
2. **Handle exceptions gracefully** - return error status, don't crash
3. **Return consistent structure** - always include 'status' and 'data'
4. **Be efficient** - don't load entire large files into memory
5. **Document your output** - explain what metadata fields mean
6. **Use type hints** - helps users understand your interface

## Common Pitfalls

❌ **Don't crash on missing files**
```python
def interpret(file_path: Path) -> Dict:
    with open(file_path) as f:  # Will crash if file doesn't exist!
```

❌ **Don't return inconsistent types**
```python
# Bad: returns string on error, dict on success
return "Error: file not found"
```

❌ **Don't forget the 'status' key**
```python
# Bad: no status key
return {'data': {...}}
```

## Integration

Once validated, your interpreter will:
- Appear in **File Settings** → Interpreter dropdown
- Be available for selection when configuring file scanning
- Run automatically on matching file extensions
- Show results in Files page and graph commits

## Testing Your Interpreter

Before validation, test manually with:

```python
from pathlib import Path
from my_interpreter import interpret

# Test cases
test_files = [
    Path('/path/to/valid.csv'),
    Path('/nonexistent/file.txt'),  # Should return error
    Path('/path/to/empty.csv'),     # Should handle gracefully
]

for file in test_files:
    result = interpret(file)
    print(f"{file.name}: {result['status']}")
    if result['status'] == 'error':
        print(f"  Error: {result['data']['error']}")
```

## Validation Process

1. Click "Validate" in Scripts page
2. Sandbox runs your code with test inputs
3. Contract tests check all requirements
4. If passed: ✅ **Validated** → Available in Settings
5. If failed: ❌ **Failed** → See errors, fix and retry

## Questions?

See examples in `tests/fixtures/script_validation/sample_csv_interpreter.py`
