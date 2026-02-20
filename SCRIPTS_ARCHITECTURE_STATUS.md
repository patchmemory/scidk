# Scripts Architecture Status

**Date:** 2026-02-20
**Status:** ✅ Complete - Validation & Execution Aligned

---

## Overview

The Scripts system now has **complete alignment** between validation contracts and execution contexts. Scripts are properly categorized as **Plugins**, **Interpreters**, or **Links**, and each category has:

1. **Specific validation tests** (contract enforcement)
2. **Specific execution contexts** (proper function calls)
3. **Clear documentation** (SCRIPT_CONTRACTS_GUIDE.md)

---

## Architecture Summary

### Three Script Categories

| Category | Purpose | Function Signature | Return Type |
|----------|---------|-------------------|-------------|
| **Plugin** | Reusable analysis/processing modules | `run(context)` | dict/list/DataFrame |
| **Interpreter** | Parse files and extract data | `interpret(file_path)` | `{'status': ..., 'data': ...}` |
| **Link** | Create relationships between nodes | `create_links(source, target)` | list of tuples |

---

## Validation System ✅

**Location:** `scidk/core/script_validators.py`

### BaseValidator (for Plugins)
Tests:
- ✅ Valid Python syntax
- ✅ Executes without errors
- ✅ Returns wrappable data (dict, list, DataFrame)

### InterpreterValidator (extends Base)
Additional tests:
- ✅ Has `interpret()` function
- ✅ Function accepts `file_path` parameter
- ✅ Returns dict with 'status' key
- ✅ Handles missing files gracefully

### LinkValidator (extends Base)
Additional tests:
- ✅ Has `create_links()` function
- ✅ Accepts two parameters (source_nodes, target_nodes)
- ✅ Returns list type
- ✅ Handles empty inputs gracefully

**Routing:** `get_validator_for_category(category)` selects appropriate validator

---

## Execution System ✅

**Location:** `scidk/core/scripts.py:_execute_python()`

### Category Detection
```python
category = script.category.lower()
if 'interpreter' in category:
    # Call interpret(file_path)
elif 'link' in category:
    # Call create_links(source_nodes, target_nodes)
else:
    # Call run(context) or use results[]
```

### Interpreter Execution
```python
# Extract file path from parameters
file_path = Path(parameters.get('file_path', '/tmp/test.txt'))

# Call interpreter function
result = interpret(file_path)

# Expect: {'status': 'success|error', 'data': {...}}
```

### Link Execution
```python
# Extract node lists from parameters
source_nodes = parameters.get('source_nodes', [])
target_nodes = parameters.get('target_nodes', [])

# Call link function
links = create_links(source_nodes, target_nodes)

# Expect: [(source_id, target_id, rel_type, props), ...]
# Convert to: [{'source_id': ..., 'target_id': ..., ...}, ...]
```

### Plugin Execution
```python
# Build context
context = {
    'parameters': parameters,
    'neo4j_driver': neo4j_driver
}

# Call plugin function
result = run(context)

# Expect: dict with 'data' key, or list, or DataFrame
```

---

## Parameter System ✅

**Location:** `scidk/ui/templates/scripts.html`

### Current Features
- ✅ Parameter schema definition (JSON format)
- ✅ Dynamic form rendering based on schema
- ✅ Client-side validation
- ✅ Parameter types: text, number, boolean, select, textarea
- ✅ Parameter editor modal for defining schemas
- ✅ Save/delete script functionality

### Category-Specific Parameters

**Plugins** (flexible):
```json
[
  {"name": "mode", "type": "select", "options": ["test", "prod"]},
  {"name": "limit", "type": "number", "min": 1, "max": 1000}
]
```

**Interpreters** (file-focused):
```json
[
  {"name": "file_path", "type": "text", "label": "File Path"}
]
```
*Future: Replace text input with file picker*

**Links** (node-focused):
```json
[
  {"name": "source_nodes", "type": "textarea", "label": "Source Nodes (JSON)"},
  {"name": "target_nodes", "type": "textarea", "label": "Target Nodes (JSON)"}
]
```
*Future: Replace textarea with node selector UI*

---

## Documentation ✅

### SCRIPT_CONTRACTS_GUIDE.md
- ✅ Contract specifications for all three categories
- ✅ Minimal valid examples for each
- ✅ Common failures and fixes
- ✅ Validation workflow
- ✅ Execution context details (updated!)

### IMPLEMENTATION_COMPLETION_GUIDE.md
- ✅ Validation & Plugin Architecture (100% complete)
- ✅ Backend, UI, JavaScript all implemented
- ✅ Testing checklist

---

## What Works Today

### ✅ Validation
- Click "Validate" on any script
- System detects category and runs appropriate tests
- Shows pass/fail for each contract requirement
- Updates validation status (draft → validated/failed)

### ✅ Activation
- Validated scripts can be activated
- Active scripts appear in settings dropdowns
- Can be called by other scripts via `load_plugin()`

### ✅ Plugin Execution
- Run scripts from Scripts page with parameters
- Supports `run(context)` pattern
- Supports legacy `results[]` pattern
- Parameter form renders with validation

### ✅ Interpreter Execution
- Executes with `interpret(file_path)` pattern
- Extracts file_path from parameters
- Returns structured data

### ✅ Link Execution
- Executes with `create_links(source_nodes, target_nodes)` pattern
- Extracts node lists from parameters
- Formats tuples as displayable dicts

---

## Future Enhancements (Optional)

### UI Improvements
1. **File Picker for Interpreters**
   - Replace text input with file browser
   - Show only scanned files from Files page
   - Auto-populate file_path parameter

2. **Node Selector for Links**
   - Query Neo4j for existing nodes
   - Multi-select UI for source and target nodes
   - Preview node properties before selecting

3. **Category-Specific Templates**
   - Pre-populated code templates for each category
   - "New Interpreter" button → template with interpret() stub
   - "New Link" button → template with create_links() stub

### Testing Improvements
1. **Server-side Parameter Validation**
   - Validate parameters before execution
   - Prevent injection attacks
   - Return clear error messages

2. **Integration Tests**
   - E2E tests for each category
   - Test validation → activation → execution flow
   - Test parameter system with all types

3. **Test Data Fixtures**
   - Sample files for interpreter testing
   - Sample node sets for link testing
   - Mock Neo4j data for plugin testing

---

## Key Files

| File | Purpose |
|------|---------|
| `scidk/core/scripts.py` | Script execution engine with category dispatch |
| `scidk/core/script_validators.py` | Validation system with category-specific tests |
| `scidk/core/script_sandbox.py` | Sandboxed execution for validation |
| `scidk/core/script_plugin_loader.py` | Plugin loading with security checks |
| `scidk/ui/templates/scripts.html` | UI for script management, validation, parameters |
| `scidk/web/routes/api_scripts.py` | API endpoints for CRUD, validation, activation |
| `SCRIPT_CONTRACTS_GUIDE.md` | User-facing documentation |
| `IMPLEMENTATION_COMPLETION_GUIDE.md` | Implementation status and checklist |

---

## Success Criteria

- [x] **Validation aligns with contracts** - Each category has appropriate tests
- [x] **Execution respects contracts** - Each category calls correct function signature
- [x] **Documentation is complete** - Users know how to write each type
- [x] **Backward compatible** - Existing scripts continue to work
- [x] **Parameter system functional** - Users can define and fill parameters
- [x] **Save/delete works** - Users can persist changes
- [x] **UI is polished** - Professional, compact parameter forms
- [x] **No major bugs** - Test script executes successfully

---

## Summary

**Scripts architecture is production-ready.** The system correctly:
1. Validates scripts against category contracts
2. Executes scripts with category-appropriate contexts
3. Documents contracts and patterns for users
4. Provides UI for managing scripts, parameters, and validation

**Next focus areas** should be on the broader roadmap items (Analyses page, Integrations layout, etc.) rather than additional Scripts work, unless specific use cases require interpreter or link script creation.
