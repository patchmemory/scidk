# Parameter System Design

## Overview

Scripts need a way to accept user inputs from the GUI. This design adds:
1. Parameter schema definition in script metadata
2. UI for parameter input in Scripts page
3. Parameter validation before execution
4. Parameter passing to script execution context

---

## 1. Parameter Schema Format

Scripts define parameters using a JSON schema stored in `Script.parameters`:

```python
script.parameters = [
    {
        'name': 'analysis_type',
        'type': 'select',
        'label': 'Analysis Type',
        'description': 'Type of analysis to perform',
        'options': ['stats', 'entities', 'queries', 'terminology'],
        'default': 'stats',
        'required': True
    },
    {
        'name': 'limit',
        'type': 'number',
        'label': 'Result Limit',
        'description': 'Maximum number of results to return',
        'default': 10,
        'min': 1,
        'max': 100,
        'required': False
    },
    {
        'name': 'include_details',
        'type': 'boolean',
        'label': 'Include Details',
        'description': 'Show detailed information',
        'default': False,
        'required': False
    },
    {
        'name': 'query',
        'type': 'text',
        'label': 'Search Query',
        'description': 'Text to search for',
        'placeholder': 'Enter search terms...',
        'required': False
    }
]
```

### Supported Parameter Types

| Type | HTML Input | Attributes |
|------|-----------|-----------|
| `text` | `<input type="text">` | placeholder, default, required, maxLength |
| `number` | `<input type="number">` | default, min, max, step, required |
| `boolean` | `<input type="checkbox">` | default, required |
| `select` | `<select>` | options (list), default, required |
| `textarea` | `<textarea>` | placeholder, default, required, rows |

### Parameter Schema Fields

- **`name`** (string, required) - Parameter key passed to script
- **`type`** (string, required) - One of: text, number, boolean, select, textarea
- **`label`** (string, required) - Human-readable label for UI
- **`description`** (string, optional) - Help text shown in UI
- **`default`** (any, optional) - Default value
- **`required`** (boolean, optional) - Whether parameter is required (default: false)
- **Type-specific fields**:
  - `options` (list, for select) - List of valid options
  - `min`, `max`, `step` (number, for number)
  - `placeholder` (string, for text/textarea)
  - `rows` (number, for textarea)
  - `maxLength` (number, for text/textarea)

---

## 2. Script Execution Context

Parameters are passed to scripts via the `parameters` dict in execution context:

### Python Scripts (Direct Execution)
```python
# Already available in global_namespace
parameters = {
    'analysis_type': 'stats',
    'limit': 10,
    'include_details': True
}

# Script can access directly
analysis_type = parameters.get('analysis_type', 'stats')
limit = parameters.get('limit', 10)
```

### Plugins (via load_plugin)
```python
# Context passed to run() function
def run(context):
    params = context.get('parameters', {})
    analysis_type = params.get('analysis_type', 'stats')
    limit = params.get('limit', 10)

    # ... plugin logic ...

    return {'status': 'success', 'data': results}
```

---

## 3. UI Implementation

### 3.1 Parameter Form Rendering

When a script is selected, the Scripts page:
1. Parses `script.parameters` JSON schema
2. Renders form inputs dynamically based on type
3. Shows validation errors inline
4. Populates defaults on load

**UI Location:** Below script editor, in a collapsible "Parameters" panel

### 3.2 Parameter Panel HTML Structure

```html
<div class="parameters-panel">
  <div class="panel-header" onclick="toggleParameters()">
    <h4>Parameters</h4>
    <span class="toggle-icon">▼</span>
  </div>

  <div class="panel-body" id="parameters-form">
    <!-- Dynamically rendered based on script.parameters -->

    <div class="parameter-field">
      <label for="param-analysis_type">
        Analysis Type
        <span class="required">*</span>
        <span class="info-icon" title="Type of analysis to perform">ⓘ</span>
      </label>
      <select id="param-analysis_type" name="analysis_type" required>
        <option value="stats" selected>stats</option>
        <option value="entities">entities</option>
        <option value="queries">queries</option>
        <option value="terminology">terminology</option>
      </select>
      <div class="field-description">Type of analysis to perform</div>
      <div class="field-error" style="display:none;"></div>
    </div>

    <div class="parameter-field">
      <label for="param-limit">Result Limit</label>
      <input type="number" id="param-limit" name="limit"
             value="10" min="1" max="100" />
      <div class="field-description">Maximum number of results to return</div>
    </div>

  </div>
</div>
```

### 3.3 JavaScript Implementation

```javascript
// Render parameter form based on schema
function renderParameterForm(parameters) {
  const container = document.getElementById('parameters-form');

  if (!parameters || parameters.length === 0) {
    container.innerHTML = '<p class="no-parameters">No parameters defined</p>';
    return;
  }

  container.innerHTML = parameters.map(param => {
    return renderParameterField(param);
  }).join('');
}

// Render individual parameter field
function renderParameterField(param) {
  const fieldId = `param-${param.name}`;
  const required = param.required ? '<span class="required">*</span>' : '';
  const description = param.description ?
    `<div class="field-description">${escapeHtml(param.description)}</div>` : '';

  let inputHtml = '';

  switch (param.type) {
    case 'text':
      inputHtml = `<input type="text" id="${fieldId}" name="${param.name}"
                   value="${param.default || ''}"
                   placeholder="${param.placeholder || ''}"
                   ${param.required ? 'required' : ''}
                   ${param.maxLength ? `maxlength="${param.maxLength}"` : ''} />`;
      break;

    case 'number':
      inputHtml = `<input type="number" id="${fieldId}" name="${param.name}"
                   value="${param.default || ''}"
                   ${param.min !== undefined ? `min="${param.min}"` : ''}
                   ${param.max !== undefined ? `max="${param.max}"` : ''}
                   ${param.step !== undefined ? `step="${param.step}"` : ''}
                   ${param.required ? 'required' : ''} />`;
      break;

    case 'boolean':
      inputHtml = `<input type="checkbox" id="${fieldId}" name="${param.name}"
                   ${param.default ? 'checked' : ''} />`;
      break;

    case 'select':
      const options = param.options.map(opt => {
        const selected = opt === param.default ? 'selected' : '';
        return `<option value="${escapeHtml(opt)}" ${selected}>${escapeHtml(opt)}</option>`;
      }).join('');
      inputHtml = `<select id="${fieldId}" name="${param.name}"
                   ${param.required ? 'required' : ''}>${options}</select>`;
      break;

    case 'textarea':
      inputHtml = `<textarea id="${fieldId}" name="${param.name}"
                   rows="${param.rows || 4}"
                   placeholder="${param.placeholder || ''}"
                   ${param.required ? 'required' : ''}
                   ${param.maxLength ? `maxlength="${param.maxLength}"` : ''}
                   >${param.default || ''}</textarea>`;
      break;
  }

  return `
    <div class="parameter-field">
      <label for="${fieldId}">
        ${escapeHtml(param.label)}
        ${required}
      </label>
      ${inputHtml}
      ${description}
      <div class="field-error" style="display:none;"></div>
    </div>
  `;
}

// Collect parameter values from form
function collectParameterValues() {
  const form = document.getElementById('parameters-form');
  const fields = form.querySelectorAll('.parameter-field');
  const values = {};

  fields.forEach(field => {
    const input = field.querySelector('input, select, textarea');
    if (!input) return;

    const name = input.name;

    if (input.type === 'checkbox') {
      values[name] = input.checked;
    } else if (input.type === 'number') {
      values[name] = input.value ? parseFloat(input.value) : null;
    } else {
      values[name] = input.value;
    }
  });

  return values;
}

// Validate parameter values
function validateParameters(parameters, values) {
  const errors = [];

  parameters.forEach(param => {
    const value = values[param.name];

    // Check required
    if (param.required && (value === null || value === undefined || value === '')) {
      errors.push({
        field: param.name,
        message: `${param.label} is required`
      });
    }

    // Type-specific validation
    if (value !== null && value !== undefined && value !== '') {
      if (param.type === 'number') {
        if (param.min !== undefined && value < param.min) {
          errors.push({
            field: param.name,
            message: `${param.label} must be at least ${param.min}`
          });
        }
        if (param.max !== undefined && value > param.max) {
          errors.push({
            field: param.name,
            message: `${param.label} must be at most ${param.max}`
          });
        }
      }

      if (param.type === 'select') {
        if (!param.options.includes(value)) {
          errors.push({
            field: param.name,
            message: `${param.label} must be one of: ${param.options.join(', ')}`
          });
        }
      }
    }
  });

  return errors;
}

// Display validation errors
function displayParameterErrors(errors) {
  // Clear previous errors
  document.querySelectorAll('.field-error').forEach(el => {
    el.style.display = 'none';
    el.textContent = '';
  });

  // Show new errors
  errors.forEach(error => {
    const fieldId = `param-${error.field}`;
    const field = document.getElementById(fieldId)?.closest('.parameter-field');
    if (field) {
      const errorEl = field.querySelector('.field-error');
      errorEl.textContent = error.message;
      errorEl.style.display = 'block';
    }
  });
}
```

### 3.4 Integration with Script Execution

Update the "Run Script" button handler:

```javascript
async function runScript() {
  const currentScript = getCurrentScript();
  if (!currentScript) return;

  // Collect parameters
  const parameterValues = collectParameterValues();

  // Validate parameters
  const errors = validateParameters(currentScript.parameters || [], parameterValues);
  if (errors.length > 0) {
    displayParameterErrors(errors);
    return;
  }

  // Execute script with parameters
  const response = await fetch(`/api/scripts/scripts/${currentScript.id}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parameters: parameterValues,
      neo4j_driver_config: { /* ... */ }
    })
  });

  // ... handle response ...
}
```

---

## 4. Backend Implementation

### 4.1 Parameter Storage

Parameters are already stored as JSON in the `scripts` table:
```sql
CREATE TABLE scripts (
    -- ... existing fields ...
    parameters TEXT,  -- JSON array of parameter schemas
    -- ... existing fields ...
);
```

No schema changes needed!

### 4.2 Parameter Passing to Execution

Update `ScriptsManager.run_script()` to accept parameters:

```python
def run_script(
    self,
    script_id: str,
    user_id: str,
    parameters: Optional[Dict[str, Any]] = None,
    neo4j_driver=None,
    neo4j_database: Optional[str] = None
) -> ScriptResult:
    """
    Run script with parameters.

    Args:
        script_id: Script ID
        user_id: User executing script
        parameters: Parameter values (validated by frontend)
        neo4j_driver: Neo4j driver instance
        neo4j_database: Neo4j database name
    """
    parameters = parameters or {}

    # ... existing execution logic ...
```

Already implemented! Just need to pass `parameters` from API route.

### 4.3 API Route Update

Update `/api/scripts/scripts/<id>/run` endpoint:

```python
@api_scripts_bp.route('/scripts/<script_id>/run', methods=['POST'])
@require_auth
def run_script_endpoint(script_id):
    """Run a script with parameters."""
    data = request.json or {}
    parameters = data.get('parameters', {})

    # ... existing code ...

    result = scripts_manager.run_script(
        script_id=script_id,
        user_id=user_id,
        parameters=parameters,  # Pass parameters
        neo4j_driver=neo4j_driver,
        neo4j_database=neo4j_database
    )

    # ... return result ...
```

---

## 5. Parameter Editor UI

Add a parameter editor in script edit mode:

### 5.1 Parameter Editor Panel

```html
<div class="parameters-editor">
  <h4>Parameter Definition</h4>
  <button onclick="addParameter()">+ Add Parameter</button>

  <div id="parameter-list">
    <!-- Parameter editor items -->
    <div class="parameter-editor-item">
      <input type="text" placeholder="name" name="param-name" />
      <select name="param-type">
        <option value="text">Text</option>
        <option value="number">Number</option>
        <option value="boolean">Boolean</option>
        <option value="select">Select</option>
        <option value="textarea">Textarea</option>
      </select>
      <input type="text" placeholder="Label" name="param-label" />
      <button onclick="removeParameter(this)">Remove</button>

      <!-- Expand for more options -->
      <div class="parameter-options" style="display:none;">
        <input type="text" placeholder="Description" name="param-description" />
        <input type="text" placeholder="Default" name="param-default" />
        <label><input type="checkbox" name="param-required" /> Required</label>
        <!-- Type-specific fields shown/hidden based on type -->
      </div>
    </div>
  </div>
</div>
```

### 5.2 Alternative: JSON Editor

For power users, provide a JSON editor:

```html
<div class="parameters-editor">
  <div class="editor-tabs">
    <button class="active" onclick="switchToFormEditor()">Form</button>
    <button onclick="switchToJsonEditor()">JSON</button>
  </div>

  <div id="form-editor" class="editor-view">
    <!-- Form-based parameter editor -->
  </div>

  <div id="json-editor" class="editor-view" style="display:none;">
    <textarea id="parameters-json" rows="10"></textarea>
    <button onclick="validateParametersJson()">Validate</button>
  </div>
</div>
```

---

## 6. Migration Path

### 6.1 Existing Scripts

Scripts without `parameters` field continue to work:
- `script.parameters` defaults to `[]`
- No parameter form shown in UI
- Scripts receive empty `parameters` dict

### 6.2 Example Migration

**Before (CLI with argparse):**
```python
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()

    # ... use args.limit ...

if __name__ == '__main__':
    main()
```

**After (with parameter system):**
```python
# Define parameters in script metadata
# parameters = [
#     {'name': 'limit', 'type': 'number', 'label': 'Limit', 'default': 10}
# ]

def run(context):
    """Run script with parameters from context."""
    params = context.get('parameters', {})
    limit = params.get('limit', 10)

    # ... use limit ...

    return {'status': 'success', 'data': results}
```

---

## 7. Testing Plan

1. **Unit Tests**
   - Parameter validation logic
   - Type coercion (string → number, etc.)
   - Required field validation
   - Min/max validation

2. **Integration Tests**
   - Parameter form rendering
   - Parameter collection
   - Script execution with parameters
   - Error handling

3. **Manual Tests**
   - Create script with parameters
   - Edit parameter schema
   - Run script with various parameter values
   - Validate error messages

---

## 8. Example: Analyze Feedback Script

**Parameter Schema:**
```json
[
  {
    "name": "analysis_type",
    "type": "select",
    "label": "Analysis Type",
    "description": "Type of feedback analysis to perform",
    "options": ["stats", "entities", "queries", "terminology"],
    "default": "stats",
    "required": true
  },
  {
    "name": "limit",
    "type": "number",
    "label": "Result Limit",
    "description": "Maximum number of results to show",
    "default": 10,
    "min": 1,
    "max": 1000,
    "required": false
  },
  {
    "name": "export_format",
    "type": "select",
    "label": "Export Format",
    "description": "Format for exported data",
    "options": ["json", "csv", "table"],
    "default": "table",
    "required": false
  }
]
```

**Script Code:**
```python
def run(context):
    """Analyze GraphRAG feedback with configurable parameters."""
    from scidk.services.graphrag_feedback_service import get_graphrag_feedback_service

    # Get parameters
    params = context.get('parameters', {})
    analysis_type = params.get('analysis_type', 'stats')
    limit = params.get('limit', 10)
    export_format = params.get('export_format', 'table')

    # Get service
    service = get_graphrag_feedback_service()

    # Perform analysis based on type
    if analysis_type == 'stats':
        data = service.get_feedback_stats()
    elif analysis_type == 'entities':
        data = service.get_entity_corrections(limit=limit)
    elif analysis_type == 'queries':
        data = service.get_query_reformulations(limit=limit)
    elif analysis_type == 'terminology':
        data = service.get_terminology_mappings()

    # Format based on export_format
    if export_format == 'json':
        return {'status': 'success', 'data': data, 'format': 'json'}
    elif export_format == 'csv':
        # Convert to CSV-friendly format
        return {'status': 'success', 'data': data, 'format': 'csv'}
    else:  # table
        return {'status': 'success', 'data': data, 'format': 'table'}
```

---

## 9. Future Enhancements

1. **Parameter Presets** - Save common parameter combinations
2. **Conditional Parameters** - Show/hide parameters based on other values
3. **Parameter Validation Rules** - Custom validation beyond type checking
4. **Parameter Groups** - Organize related parameters into sections
5. **Parameter Dependencies** - Link parameters (e.g., max depends on min)
6. **Rich Input Types** - File upload, date picker, color picker
7. **Parameter History** - Remember last used values per script
8. **Auto-completion** - Suggest values based on data schema

---

## Summary

The parameter system enables:
- ✅ GUI-driven script execution (no CLI needed)
- ✅ Type-safe parameter validation
- ✅ Discoverable script capabilities (via parameter schema)
- ✅ Consistent UX across all scripts
- ✅ No breaking changes (backward compatible)

**Implementation Priority:**
1. Basic parameter types (text, number, boolean, select)
2. Parameter form rendering in Scripts page
3. Parameter passing to execution
4. Refactor Analyze Feedback script as example
5. (Future) Parameter editor for script authors
