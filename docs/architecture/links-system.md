# Links System Architecture

## Design Philosophy

Two complementary tools for different use cases, unified UI, independent maintenance.

The Links system provides two approaches to creating relationships in the knowledge graph:
- **Wizard Links**: Declarative, form-based (simple property matching)
- **Script Links**: Imperative, code-based (complex logic, ML, inference)

They coexist by design and are not mutually exclusive.

---

## Wizard Links (Declarative)

**Storage:** `link_definitions` table (SQLite)
**Use Cases:** Property matching, CSV imports, fuzzy matching, API lookups
**Interface:** Visual form in Links page
**Execution:** `LinkService.execute_link_job()` → Cypher batch writes
**Best For:** Non-developers, straightforward mappings

### Example Use Cases
- Connect Person nodes to Document nodes where `person.email == document.author_email`
- Import author→file relationships from CSV
- Fuzzy match organization names between systems
- Lookup entity relationships from external API

### Match Strategies
- `property`: Match on exact property equality
- `fuzzy`: Match on string similarity (Levenshtein distance)
- `table_import`: Import from CSV/Excel files
- `api_endpoint`: Fetch relationships from external REST API

### Execution Flow
1. User fills out wizard form (source label, target label, match strategy)
2. `LinkService.preview()` shows sample matches
3. User clicks Execute → `LinkService.execute_link_job()`
4. Service fetches source and target node sets
5. Applies match strategy to find pairs
6. Batch creates relationships in Neo4j

---

## Script Links (Imperative)

**Storage:** `scripts` table (category='links'), or file-based in `scripts/links/`
**Use Cases:** Complex logic, embeddings, inference, external APIs, computation
**Interface:** Python code editor in Scripts page
**Execution:** `ScriptsManager.execute_script()` → `create_links()` function
**Best For:** Developers, custom algorithms, ML-based linking

### Example Use Cases
- Connect documents with >0.8 embedding similarity (semantic search)
- Infer CO_AUTHORED from shared document patterns
- Create INFLUENCES relationships via citation analysis
- Link entities using custom scoring algorithms
- Integrate with ML models (classification, clustering)

### Contract Requirements
Script links must implement the link contract (see `scripts/contracts/LINKS.md`):

```python
def create_links(source_nodes: List[Dict], target_nodes: List[Dict]) -> List[Tuple]:
    """
    Args:
        source_nodes: Source node dicts with 'id' and 'type'
        target_nodes: Target node dicts with 'id' and 'type'

    Returns:
        List of tuples: (source_id, rel_type, target_id, properties_dict)
    """
```

### Execution Flow
1. User writes Python script with `create_links()` function
2. Clicks Validate → Contract tests verify signature, return type, empty input handling
3. If validated → Script can be executed
4. User provides source/target node parameters (or uses defaults)
5. `ScriptsManager.execute_script()` calls `create_links()`
6. Returns list of relationship tuples
7. System creates relationships in Neo4j

---

## Integration Points

### 1. Unified List View

**Function:** `LinkService.list_all_links()`

```python
def list_all_links(self) -> List[Dict[str, Any]]:
    # Get wizard links from link_definitions table
    wizard_links = self.list_link_definitions()

    # Get script links from scripts table (category='links')
    from ..core.scripts import ScriptsManager
    scripts_mgr = ScriptsManager()
    script_links = scripts_mgr.list_scripts(category='links')

    # Normalize to common schema
    # ...
```

**UI:** Links page shows both types with filter tabs (All/Wizard/Script)

**Common Schema:**
```javascript
{
  id: string,
  name: string,
  type: 'wizard' | 'script',
  created_at: number,
  updated_at: number,

  // Wizard-specific
  source_label?: string,
  target_label?: string,
  match_strategy?: string,

  // Script-specific
  description?: string,
  validation_status?: 'draft' | 'validated' | 'failed',
  is_active?: boolean
}
```

### 2. Execution Paths

**Wizard Path:**
```
User clicks Execute
  ↓
/api/links/{id}/execute
  ↓
LinkService.execute_link_job()
  ↓
_fetch_source_data() + _match_with_targets()
  ↓
Batch Cypher: CREATE (a)-[r:REL_TYPE]->(b)
  ↓
_validate_relationship_type() prevents injection
```

**Script Path:**
```
User clicks Execute (with confirmation)
  ↓
/api/scripts/{id}/execute
  ↓
ScriptsManager.execute_script()
  ↓
Calls create_links(source_nodes, target_nodes)
  ↓
Returns [(src, rel_type, tgt, props), ...]
  ↓
Creates relationships in Neo4j
```

**Shared Protection:** Both validate relationship types via regex `^[A-Za-z_][A-Za-z0-9_]*$` to prevent Cypher injection.

### 3. UI Routing

- **Wizard links:** Edit in Links page wizard form
- **Script links:** Redirect to Scripts page for code editing
- **Script links:** Execute/Preview from Links page (if validated)
- **Create new wizard:** Links page "New Link" → "Wizard Link" option
- **Create new script:** Links page "New Link" → "Script Link" option → Redirects to Scripts page with `?new=link`

### 4. Validation

**Wizard Links:**
- Form validation (required fields, label existence checks)
- Preview before execution
- No code validation needed

**Script Links:**
- Contract testing (function signature, return type, empty input handling)
- Sandbox execution with test data
- Must pass validation before activation
- Re-validation required after code changes

---

## Maintenance Guidelines

### Independent Systems

✅ **Separate storage** - Different tables, no foreign keys
✅ **Separate services** - LinkService vs ScriptsManager
✅ **Separate execution** - No shared execution logic
✅ **Independent changes** - Editing wizard logic doesn't affect scripts and vice versa

### Shared Components

⚠️ **Frontend rendering** - Unified link list branches by `type` field
⚠️ **Security** - Both use `_validate_relationship_type()` for Cypher injection prevention
⚠️ **API normalization** - `/api/links` returns normalized schema for both

### When to Use Which

**Choose Wizard Link if:**
- Matching logic is simple (property equality, fuzzy match, CSV lookup)
- Non-developer creating the link
- No computation or external APIs needed
- Form-based interface is sufficient

**Choose Script Link if:**
- Matching requires computation (embeddings, scores, inference)
- Need to integrate external APIs or ML models
- Custom algorithms beyond basic property matching
- Dynamic relationship types based on logic
- Complex multi-step reasoning

### Migration Strategy

**Don't migrate wizard → script**. They serve different needs and coexist by design.

Only convert if:
1. Wizard strategy is insufficient (e.g., need ML embeddings)
2. Custom logic required (e.g., graph algorithms)
3. External API integration needed

---

## Security

### Cypher Injection Protection

Both wizard and script links validate relationship types using regex:

```python
def _validate_relationship_type(rel_type: str) -> str:
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', rel_type):
        raise ValueError(f"Invalid relationship type '{rel_type}'")
    return rel_type
```

**Protects against:**
- SQL injection patterns: `'; DROP TABLE users;--`
- Cypher injection: `TEST]->(n) DELETE n//`
- Path traversal: `../../../etc/passwd`
- Code execution attempts: `REL{code:exec()}`

**Applied in:**
- `LinkService._execute_job_impl()` (line 762)
- `LinkService._execute_job_impl_with_progress()` (line 878)

### XSS Protection

All user-provided content is escaped via `escapeHtml()` helper in the frontend:

```javascript
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}
```

### Confirmation Dialog

Execute button requires user confirmation to prevent accidental writes:

```javascript
const confirmed = confirm(
  `Execute "${scriptLink.name}"?\n\n` +
  `This will create relationships in your Neo4j knowledge graph.\n\n` +
  `Tip: Use Preview first to see what will be created.`
);
```

Preview button remains direct (read-only, safe).

---

## Demo Flow

1. **Open Links page** → See 4 wizard + 2 script links
2. **Filter tabs** → Click "All (6)", "Wizard (4)", "Script (2)"
3. **Click script link** → Detail view shows Execute/Preview buttons
4. **Click Preview** → See "X relationships would be created" with samples
5. **Click Execute** → Confirmation dialog → Success message with count
6. **Click Edit** → Redirect to Scripts page with script open
7. **New Link dropdown** → Choose "Script Link" → Opens Scripts page with category='links'

**Key Message:** Two tools for different jobs, working together seamlessly.

---

## Testing

Run integration tests:
```bash
pytest tests/test_links_integration.py -v
```

**Test coverage:**
- ✅ Unified list returns both types
- ✅ Script links have validation fields
- ✅ Wizard links have label fields
- ✅ Cypher injection protection on both paths
- ✅ API returns normalized schema
- ✅ File-based scripts are discovered

---

## Future Enhancements

### Possible Improvements
- **Batch execution progress bar** for large link jobs
- **Relationship property editor** in UI
- **Dry-run mode** for script links (preview without Neo4j query)
- **Link templates** for common patterns
- **Visual diff** showing before/after graph state
- **Scheduled link execution** (cron-style)
- **Link versioning** (track changes over time)

### Anti-Patterns to Avoid
❌ **Don't create wizard/script hybrid** - Keep systems separate
❌ **Don't inline script code in wizard form** - Use Scripts page
❌ **Don't share execution logic** - Maintain independence
❌ **Don't skip validation** - Always validate script links before activation

---

## Questions?

- **Link contract details:** See `scripts/contracts/LINKS.md`
- **Sample scripts:** See `scripts/links/` directory
- **API docs:** See `/api/links` and `/api/scripts` endpoints
- **Tests:** See `tests/test_links_integration.py`
