# SciDKData Implementation Status

## ✅ Completed (Phase 1-3)

### 1. Core Architecture
**Files Created:**
- `scidk/core/data_types.py` - Universal `SciDKData` wrapper class

**Features Implemented:**
- Auto-wrapping of dict, list, pandas DataFrame at plugin boundary
- Consistent interface: `.to_dict()`, `.to_list()`, `.to_dataframe()`, `.to_json()`
- JSON-serializability validation at wrap time
- Improved duck typing for DataFrames (checks `.empty` and `.columns`)
- Type checking prevents false positives

### 2. Plugin Loader Integration
**File Modified:** `scidk/core/script_plugin_loader.py`

**Changes:**
- `load_plugin()` now returns `SciDKData` instead of raw dict
- Auto-wraps plugin output using `auto_wrap()` function
- Casual users don't need to import `SciDKData` - just return dict/list/DataFrame

**Example Usage (Downstream):**
```python
from scidk.core.script_plugin_loader import load_plugin

# Call plugin
result = load_plugin('my-plugin-id', manager, {'param': 'value'})

# Extract data in desired format
data_dict = result.to_dict()        # As dict
data_list = result.to_list()        # As list
data_df = result.to_dataframe()     # As pandas DataFrame
```

### 3. Validation System Update
**File Modified:** `scidk/core/script_validators.py`

**Changes:**
- Added `returns_wrappable_data` test to `BaseValidator`
- Only tests plugins with `run()` function (allows interpreter/link scripts to pass)
- Provides rich mock context to avoid false KeyError failures:
  ```python
  mock_context = {
      'mode': 'test',
      'limit': 10,
      'file_path': '/tmp/test.txt',
      'query': 'test query',
      'user_id': 1,
      'session_id': 'test-session',
  }
  ```
- Distinguishes between:
  - **KeyError** - Plugin needs specific context keys (acceptable, test passes)
  - **TypeError** - Plugin returns unsupported type (validation fails)

### 4. UI Updates
**File Modified:** `scidk/ui/templates/scripts.html`

**Changes:**
- Added description for `returns_wrappable_data` test
- Added fix hint: "Plugin run() must return dict, list, or pandas DataFrame (JSON-serializable)"

### 5. Documentation
**File Modified:** `SCRIPT_CONTRACTS_GUIDE.md`

**Updates:**
- Documented SciDKData contract and auto-wrapping behavior
- Provided casual user examples (simple return dict)
- Provided advanced user examples (explicit SciDKData wrap)
- Clarified supported types: dict, list, DataFrame

---

## 🚧 Remaining Work (Phase 4-5)

### Phase 4: Parameter System Design
**Status:** Not started

**Problem:**
Scripts like "Analyze Feedback" need user inputs (e.g., which analysis to run, limit count). Currently:
- CLI scripts use argparse (not compatible with GUI)
- No standard way to define parameters in script metadata
- No UI for parameter input in Scripts page

**Proposed Solution:**
1. Extend `Script` model with `parameters` field (JSON schema)
   ```python
   parameters = {
       'analysis_type': {
           'type': 'select',
           'options': ['stats', 'entities', 'queries', 'terminology'],
           'default': 'stats',
           'label': 'Analysis Type'
       },
       'limit': {
           'type': 'number',
           'default': 10,
           'min': 1,
           'max': 100,
           'label': 'Result Limit'
       }
   }
   ```

2. Add parameter editing UI in Scripts page
   - Parse `parameters` schema from script metadata
   - Render form inputs dynamically
   - Pass values to script execution as `parameters` dict

3. Update script execution to pass parameters
   - Already available in `global_namespace` for direct execution
   - Need to pass to plugins via `load_plugin(context={'parameters': ...})`

### Phase 5: Refactor Existing Scripts
**Status:** Not started

**Scripts Needing Updates:**
1. **Analyze Feedback** (`analyze_feedback`)
   - Remove argparse CLI interface
   - Add `run(context)` function that returns dict/list
   - Use `context.get('parameters', {})` for user inputs
   - Populate `results[]` array instead of printing
   - Return structured data compatible with SciDKData

2. **Other builtin scripts** (if any use CLI patterns)
   - Audit all builtin scripts for CLI dependencies
   - Refactor to use `run(context)` + `results[]` pattern

---

## 🧪 Testing Needed

### 1. Validation Testing
Test that plugins validate correctly:
- ✅ Plugin returning dict → passes `returns_wrappable_data`
- ✅ Plugin returning list → passes `returns_wrappable_data`
- ✅ Plugin returning DataFrame → passes `returns_wrappable_data`
- ❌ Plugin returning string → fails with clear error
- ❌ Plugin returning non-JSON-serializable dict → fails with clear error

### 2. Plugin Loading Testing
Test `load_plugin()` auto-wrapping:
- Dict input → SciDKData with `.to_dict()` working
- List input → SciDKData with `.to_list()` working
- DataFrame input → SciDKData with `.to_dataframe()` working
- Mixed conversions (dict → list, list → DataFrame, etc.)

### 3. KeyError Handling
Test validation with context-dependent plugins:
- Plugin that expects specific keys in context
- Should pass validation (KeyError is acceptable)
- Should work when called with correct context

### 4. Edge Cases
- Empty dict/list return → wrappable
- DataFrame with no rows → wrappable
- Plugin timeout during validation → handled gracefully

---

## 📝 Migration Guide for Existing Plugins

### Before (Old Pattern):
```python
def run(context):
    # Direct return - no validation
    return {'status': 'success', 'data': [1, 2, 3]}
```

### After (New Pattern - Still Works!):
```python
def run(context):
    # Same code - auto-wrapped by load_plugin()
    return {'status': 'success', 'data': [1, 2, 3]}
```

**No migration needed for existing plugins!** The SciDKData wrapper is applied automatically by `load_plugin()`. Plugins can continue returning dict/list/DataFrame directly.

### Advanced Users (Optional):
```python
from scidk.core.data_types import SciDKData

def run(context):
    # Explicit wrap for more control
    result = SciDKData().from_dict({'status': 'success'})
    return result
```

---

## 🔍 Architecture Decisions

### 1. Why auto-wrap at boundary?
- **Casual users** don't need to learn SciDKData - just return dict/list/DataFrame
- **Consistency** - all plugins have same return type from `load_plugin()`
- **Validation** - JSON-serializability checked once at wrap time

### 2. Why not require SciDKData in plugin signature?
- **Friction** - increases learning curve for plugin authors
- **Import dependency** - plugins would need `from scidk.core.data_types import SciDKData`
- **Compatibility** - breaks existing plugins that return dict directly

### 3. Why validate wrappability instead of specific types?
- **Flexibility** - plugins can return dict, list, or DataFrame
- **Future-proof** - easy to add more supported types
- **Clear errors** - validation tells you if return type is unsupported

### 4. Why rich mock context in validation?
Feedback from Claude Sonnet: Plugins may expect specific context keys (e.g., `file_path`, `query`). Using empty dict `{}` causes false failures when plugin does `context['file_path']`. Providing rich mock + catching KeyError separately distinguishes:
- Plugin needs specific keys → OK (will work with right context)
- Plugin returns wrong type → Error (needs fixing)

---

## 📚 Related Files

### Core Implementation:
- `scidk/core/data_types.py` - SciDKData class
- `scidk/core/script_plugin_loader.py` - Auto-wrapping
- `scidk/core/script_validators.py` - Wrappability tests

### Documentation:
- `SCRIPT_CONTRACTS_GUIDE.md` - User-facing guide
- `SECURITY_HARDENING_RECOMMENDATIONS.md` - Security analysis (separate concern)

### UI:
- `scidk/ui/templates/scripts.html` - Validation display

### Testing:
- `tests/fixtures/plugin_fixtures.py` - Plugin test fixtures (if exists)

---

## 🎯 Next Steps

1. **Test validation** with existing plugins (manually or automated)
2. **Design parameter system** (schema format, UI mockup, execution flow)
3. **Implement parameter editing UI** in Scripts page
4. **Refactor Analyze Feedback** to use new pattern
5. **Document parameter system** in SCRIPT_CONTRACTS_GUIDE.md
6. **Add tests** for SciDKData wrapper and validation

---

## 📞 Questions for User

1. Should we proceed with parameter system design, or test current implementation first?
2. What should parameter schema format look like? JSON Schema? Custom format?
3. Should parameters be validated before script execution (e.g., type checking, required fields)?
4. Do we need parameter presets/templates for common patterns?
