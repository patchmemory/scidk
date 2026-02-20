# Script Contracts Guide - Quick Reference

This guide explains the requirements for each type of script in SciDK.

## Quick Links
- [Plugins](#plugins-base-contract)
- [Interpreters](#interpreters)
- [Links](#links)
- [Validation Workflow](#validation-workflow)

---

## Plugins (Base Contract)

**Purpose:** Reusable code modules that can be called by other scripts

**Requirements:**
- ✅ Valid Python syntax
- ✅ Executes without errors
- ✅ Returns wrappable data (dict, list, or pandas DataFrame)
- 💡 Convention: Define a `run(context: dict)` function

**Data Contract:**
Plugins must return one of:
- `dict` (most common) - JSON-serializable dictionary
- `list` - JSON-serializable list
- `pandas.DataFrame` - Will be auto-converted

The `load_plugin()` function auto-wraps your return value in a `SciDKData` object, providing consistent `.to_dict()`, `.to_list()`, and `.to_dataframe()` methods for downstream consumers.

**Minimal Valid Example (Casual User):**
```python
"""
Plugin that processes data.

Usage:
  from scidk.core.script_plugin_loader import load_plugin
  result = load_plugin('plugin-id', manager, {'key': 'value'})
  data = result.to_dict()  # Extract as dict
"""

def run(context: dict) -> dict:
    """
    Execute plugin logic.

    Args:
        context: Input parameters as dict

    Returns:
        Dict, list, or DataFrame (auto-wrapped in SciDKData)
    """
    # Your plugin logic here

    # Simple return - auto-wrapped by load_plugin()
    return {
        'status': 'success',
        'data': {
            'message': 'Plugin executed',
            'result': context.get('key')
        }
    }
```

**Advanced Example (Explicit SciDKData):**
```python
"""
Advanced plugin using explicit SciDKData wrapper.
"""
from scidk.core.data_types import SciDKData

def run(context: dict) -> SciDKData:
    """Return explicitly wrapped data."""
    import pandas as pd

    # Create DataFrame
    df = pd.DataFrame({
        'gene': ['BRCA1', 'TP53'],
        'count': [42, 37]
    })

    # Explicit wrap (optional - load_plugin auto-wraps)
    result = SciDKData().from_dataframe(df)
    return result
```

---

## Interpreters

**Purpose:** Read files and extract structured data (e.g., parse CSV, analyze images)

**Required Function:**
```python
def interpret(file_path: Path) -> dict:
```

**Contract Tests:**
1. ✅ Has `interpret()` function
2. ✅ Function accepts `file_path` parameter
3. ✅ Returns dict type
4. ✅ Dict has 'status' key ('success' or 'error')
5. ✅ Handles missing files gracefully (returns error dict, doesn't crash)

**Minimal Valid Example:**
```python
"""
Interpreter that extracts basic file information.

Contract: Interpret files and return structured data
"""
from pathlib import Path

def interpret(file_path: Path) -> dict:
    """
    Interpret a file and extract data.

    Args:
        file_path: Path to file to interpret

    Returns:
        Dict with 'status' and 'data' keys:
        - status: 'success' or 'error'
        - data: Extracted data (dict)
    """
    # REQUIRED: Check if file exists
    if not file_path.exists():
        return {
            'status': 'error',
            'data': {'error': 'File not found'}
        }

    try:
        # Your parsing logic here
        content = file_path.read_text()

        # Extract/process data
        data = {
            'file_path': str(file_path),
            'file_name': file_path.name,
            'size_bytes': len(content),
            'lines': len(content.splitlines()),
            # Add your extracted data here
        }

        return {
            'status': 'success',
            'data': data
        }

    except Exception as e:
        # REQUIRED: Handle errors gracefully
        return {
            'status': 'error',
            'data': {'error': str(e)}
        }
```

**Common Failures & Fixes:**

| Error | Fix |
|-------|-----|
| Missing `interpret()` function | Add `def interpret(file_path: Path) -> dict:` |
| Doesn't accept parameter | Add `file_path` parameter to function |
| Returns list/string instead of dict | Change return to `{'status': ..., 'data': ...}` |
| Missing 'status' key | Add 'status': 'success' or 'error' to return dict |
| Crashes on missing file | Add `if not file_path.exists(): return {'status': 'error', ...}` |

---

## Links

**Purpose:** Analyze nodes and create relationships between them

**Required Function:**
```python
def create_links(source_nodes: list, target_nodes: list) -> list:
```

**Contract Tests:**
1. ✅ Has `create_links()` function
2. ✅ Accepts 2 parameters (source_nodes, target_nodes)
3. ✅ Returns list type
4. ✅ Handles empty inputs gracefully (returns empty list, doesn't crash)

**Return Format:**
```python
[
    (source_id, target_id, relationship_type, properties_dict),
    (source_id, target_id, relationship_type, properties_dict),
    ...
]
```

**Minimal Valid Example:**
```python
"""
Link script that creates relationships between nodes.

Contract: Create relationships between source and target nodes
"""

def create_links(source_nodes: list, target_nodes: list) -> list:
    """
    Create relationships between nodes.

    Args:
        source_nodes: List of source node dicts (each has 'id' key)
        target_nodes: List of target node dicts (each has 'id' key)

    Returns:
        List of tuples: (source_id, target_id, rel_type, properties)
    """
    links = []

    # REQUIRED: Handle empty inputs
    if not source_nodes or not target_nodes:
        return links

    # Your link creation logic here
    for source in source_nodes:
        for target in target_nodes:
            # Your matching/scoring logic
            should_link = True  # Your condition here

            if should_link:
                links.append((
                    source.get('id'),
                    target.get('id'),
                    'RELATED_TO',  # Change to your relationship type
                    {
                        'confidence': 1.0,  # Your properties
                        'method': 'your_algorithm'
                    }
                ))

    return links
```

**Common Failures & Fixes:**

| Error | Fix |
|-------|-----|
| Missing `create_links()` function | Add `def create_links(source_nodes, target_nodes) -> list:` |
| Only accepts 1 parameter | Add second parameter: `target_nodes: list` |
| Returns dict/string instead of list | Change return to `[]` or list of tuples |
| Crashes on empty input | Add `if not source_nodes or not target_nodes: return []` |
| Relationship type is None | Use a string like 'RELATED_TO', not None |

---

## Validation Workflow

### Step 1: Write Script
```python
# Write your script in the Scripts page editor
```

### Step 2: Validate
```
Click "Validate" button → Runs contract tests
```

**Results show:**
- ✅ Passed tests (green)
- ❌ Failed tests (red) with 💡 fix hints

Example output:
```
❌ Validation Failed: 3 of 5 tests passed

✅ Valid Python syntax
✅ Executes without errors
❌ Returns dict with 'status' key
   💡 Return dict must include 'status' key: {'status': 'success', 'data': {...}}
```

### Step 3: Fix Issues
Use the fix hints to correct your code, then validate again.

### Step 4: Activate
Once validation passes:
```
Click "Activate" → Script becomes available system-wide
```

**Active scripts:**
- Appear in Settings dropdowns
- Can be called by other scripts via `load_plugin()`
- Are used by the system for file interpretation and link creation

---

## Execution Context

All scripts run with these variables available:

```python
parameters = {}        # Parameters passed to script
neo4j_driver = None   # Database driver (if available)
results = []          # Output list for Scripts page
__file__              # File path (set automatically)

# Pre-imported modules
import json
import pandas as pd
from pathlib import Path
import sys
```

---

## Using Plugins in Other Scripts

**From Interpreters or Links:**

```python
from scidk.core.script_plugin_loader import load_plugin

def interpret(file_path: Path) -> dict:
    """Interpreter that uses a plugin."""

    # Load and execute plugin
    result = load_plugin(
        plugin_id='my-plugin-id',
        manager=manager,  # Available in context
        context={'file_path': str(file_path)},
        timeout=10
    )

    if result['status'] == 'success':
        return {
            'status': 'success',
            'data': result['data']
        }
    else:
        return {
            'status': 'error',
            'data': {'error': result.get('message', 'Plugin failed')}
        }
```

**Security:** Only validated + active plugins can be loaded.

---

## Allowed Imports

**Data & Utilities:**
- json, csv, pandas, numpy
- re, pathlib, datetime, time, ast, typing
- collections, itertools, functools, math, statistics

**File System:**
- os, shutil

**System:**
- sys, pickle

**Database:**
- sqlite3

**CLI:**
- argparse, click

**Framework:**
- scidk (core framework access)

**Blocked:** subprocess, requests, socket, urllib, http, email, smtplib

---

## Security & Permissions

**Admin-Only Operations:**
- Create scripts
- Edit scripts
- Delete scripts
- Activate scripts
- Deactivate scripts

**All Users Can:**
- View scripts
- Run scripts
- Validate scripts (safe, read-only)

**Warning:** Scripts have full system access (filesystem, databases). Only activate scripts from trusted sources.

---

## Tips for Success

1. **Start with templates** - Copy a minimal valid example above
2. **Validate early and often** - Fix issues as you go
3. **Read the fix hints** - They tell you exactly what to change
4. **Handle errors gracefully** - Always check inputs and catch exceptions
5. **Test with edge cases** - Missing files, empty lists, invalid data
6. **Use docstrings** - Document what your script does
7. **Keep it simple** - Start small, add features incrementally

---

## Need Help?

- Check validation error messages and fix hints
- Review minimal valid examples in this guide
- Look at test fixtures in `tests/fixtures/` directory
- See `SECURITY_HARDENING_RECOMMENDATIONS.md` for security info

---

*For more details on the validation system and plugin architecture, see `IMPLEMENTATION_COMPLETION_GUIDE.md`*
