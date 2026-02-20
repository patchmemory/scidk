# Plugin Contract

## Purpose

Plugins are reusable components that return valid SciDK data objects. They serve as building blocks that can be used by Interpreters, Links, and other scripts. Think of them as utility functions or data transformers.

## Base Contract

Plugins have the most flexible contract - they just need to:

1. **Return a valid data object** (dict, list, tuple, or primitive)
2. **Never return None** (use empty dict/list instead)
3. **Handle errors gracefully** (return error dict, don't crash)
4. **Have clear documentation** (docstring explaining purpose and return type)

## Common Plugin Types

### 1. Data Validators

Validate and normalize data structures:

```python
"""
---
id: csv-validator
name: CSV Validator
category: plugins
language: python
description: Validates CSV structure and returns normalized data
---
"""
from typing import Dict, List

def validate_csv_data(rows: List[List[str]]) -> Dict:
    """
    Validate CSV rows and return normalized structure.

    Args:
        rows: List of CSV rows (each row is list of strings)

    Returns:
        Dict with 'valid', 'errors', and 'data' keys
    """
    if not rows:
        return {
            'valid': False,
            'errors': ['Empty CSV data'],
            'data': []
        }

    # Check all rows have same column count
    col_count = len(rows[0])
    invalid_rows = [
        i for i, row in enumerate(rows)
        if len(row) != col_count
    ]

    if invalid_rows:
        return {
            'valid': False,
            'errors': [f'Inconsistent columns at rows: {invalid_rows}'],
            'data': rows
        }

    return {
        'valid': True,
        'errors': [],
        'data': rows
    }
```

### 2. Data Transformers

Transform data from one format to another:

```python
"""
---
id: json-to-nodes
name: JSON to Nodes Transformer
category: plugins
language: python
description: Converts JSON objects to SciDK node format
---
"""
from typing import List, Dict

def json_to_nodes(json_data: List[Dict], node_type: str) -> List[Dict]:
    """
    Transform JSON array into SciDK node format.

    Args:
        json_data: List of JSON objects
        node_type: Node label/type to assign

    Returns:
        List of node dicts with 'id', 'type', and properties
    """
    if not json_data:
        return []

    nodes = []
    for idx, item in enumerate(json_data):
        node = {
            'id': item.get('id', f'{node_type}-{idx}'),
            'type': node_type,
            **item  # Spread all other properties
        }
        nodes.append(node)

    return nodes
```

### 3. Utility Functions

Common operations used by multiple scripts:

```python
"""
---
id: fuzzy-matcher
name: Fuzzy String Matcher
category: plugins
language: python
description: Fuzzy match strings with configurable threshold
---
"""
from typing import List, Tuple

def fuzzy_match(query: str, candidates: List[str], threshold: float = 0.8) -> List[Tuple[str, float]]:
    """
    Find fuzzy matches for query string in candidates.

    Args:
        query: String to match
        candidates: List of candidate strings
        threshold: Minimum similarity score (0.0 to 1.0)

    Returns:
        List of (candidate, score) tuples, sorted by score desc
    """
    # Simple example using basic string similarity
    import re

    if not query or not candidates:
        return []

    matches = []
    query_lower = query.lower()

    for candidate in candidates:
        candidate_lower = candidate.lower()

        # Simple similarity: count common words
        query_words = set(re.findall(r'\w+', query_lower))
        candidate_words = set(re.findall(r'\w+', candidate_lower))

        if not query_words:
            continue

        common = query_words & candidate_words
        score = len(common) / len(query_words)

        if score >= threshold:
            matches.append((candidate, score))

    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)

    return matches
```

## Contract Tests

Plugins are tested for:

1. ✅ **Valid syntax** - Code must parse without errors
2. ✅ **Executes without crashing** - Must run in sandbox
3. ✅ **Returns valid type** - Returns dict, list, tuple, or primitive (not None)
4. ✅ **Has documentation** - Docstring explaining purpose

## Using Plugins in Other Scripts

Once validated, plugins can be imported in other scripts:

```python
"""
My interpreter using a validator plugin
"""
from scidk.plugins import load_plugin

# Load validated plugin
validator = load_plugin('csv-validator')

def interpret(file_path):
    # ... read CSV rows ...

    # Use plugin to validate
    validation = validator.validate_csv_data(rows)

    if not validation['valid']:
        return {
            'status': 'error',
            'data': {'errors': validation['errors']}
        }

    return {
        'status': 'success',
        'data': validation['data']
    }
```

## Best Practices

1. **Single Responsibility** - Each plugin should do one thing well
2. **Type Hints** - Always use type hints for clarity
3. **Docstrings** - Document parameters and return types
4. **No Side Effects** - Plugins should be pure functions (no file writes, network calls)
5. **Error Handling** - Return error dicts, don't raise exceptions
6. **Test Independently** - Write unit tests for your plugin

## Common Pitfalls

❌ **Don't return None**
```python
def my_plugin(data):
    if not data:
        return None  # Bad! Return empty dict/list instead
```

❌ **Don't have side effects**
```python
def my_plugin(data):
    # Bad! Don't write files or make network calls
    with open('output.txt', 'w') as f:
        f.write(str(data))
```

❌ **Don't crash on invalid input**
```python
def my_plugin(data):
    return data[0]  # Bad! Crashes if data is empty
```

## Discoverability

Validated plugins appear in the **Plugin Palette** in the Scripts page:

```
📦 Available Plugins
┌──────────────────────────┐
│ csv-validator            │ ← Click to copy import
│ Validates CSV structure  │
├──────────────────────────┤
│ json-to-nodes            │
│ Convert JSON to nodes    │
└──────────────────────────┘
```

Click any plugin to copy this to clipboard:
```python
from scidk.plugins import load_plugin
csv_validator = load_plugin('csv-validator')
```

## Integration

Once validated:
- ✅ Appears in Plugin Palette (Scripts page)
- ✅ Importable via `load_plugin()`
- ✅ Usable by Interpreters, Links, and other Plugins
- ✅ Documented in Settings panels

## Validation Process

1. Write plugin in Scripts page
2. Click "Validate"
3. Tests run in sandbox
4. If passed: ✅ Available in Plugin Palette
5. If failed: ❌ Fix errors and retry

## Questions?

See examples in `tests/fixtures/script_validation/` directory
