# Link Contract

## Purpose

Links define relationship types between node sets based on rules or computation. They enable SciDK to create connections in the knowledge graph by analyzing node properties, external data, or custom logic.

## Required Signature

```python
def create_links(source_nodes: List[Dict], target_nodes: List[Dict]) -> List[Tuple]:
    """
    Create relationship links between source and target nodes.

    Args:
        source_nodes: List of source node dicts
        target_nodes: List of target node dicts

    Returns:
        List of tuples: (source_id, rel_type, target_id, properties)
    """
```

## Return Type

```python
[
    (
        "source_node_id",      # str: ID of source node
        "RELATIONSHIP_TYPE",   # str: Relationship type (e.g., WORKS_ON, CONTAINS)
        "target_node_id",      # str: ID of target node
        {                      # dict: Optional relationship properties
            'confidence': 0.95,
            'created_by': 'link_script_name',
            'weight': 1.0
        }
    ),
    # ... more triples
]
```

## Contract Tests

Your link script will be tested against these requirements:

1. ✅ **Has create_links() function** - Must define a function named `create_links`
2. ✅ **Accepts two parameters** - Function must accept source_nodes and target_nodes
3. ✅ **Returns list** - Must return a list object
4. ✅ **Handles empty inputs** - Must return `[]` when given empty source or target lists
5. ✅ **Returns valid triples** - Each item must be a tuple with 4 elements
6. ✅ **Valid relationship types** - Relationship type (2nd element) must be a non-empty string
7. ✅ **Handles null gracefully** - Must not crash on None values

## Example Implementation

```python
"""
---
id: person-project-link
name: Person to Project Links
category: links
language: python
description: Links people to projects they work on based on role or department
---
"""
from typing import List, Dict, Tuple

def create_links(source_nodes: List[Dict], target_nodes: List[Dict]) -> List[Tuple]:
    """
    Create WORKS_ON links between Person nodes and Project nodes.

    Logic: Connect if person's department matches project's department
    """

    # Handle empty inputs
    if not source_nodes or not target_nodes:
        return []

    links = []

    for source in source_nodes:
        # Only link Person nodes
        if source.get('type') != 'Person':
            continue

        source_dept = source.get('department', '')

        for target in target_nodes:
            # Only link to Project nodes
            if target.get('type') != 'Project':
                continue

            target_dept = target.get('department', '')

            # Create link if departments match
            if source_dept and source_dept == target_dept:
                links.append((
                    source['id'],
                    'WORKS_ON',
                    target['id'],
                    {
                        'matched_on': 'department',
                        'department': source_dept,
                        'confidence': 1.0,
                        'created_by': 'person-project-link'
                    }
                ))

    return links
```

## Node Structure

Nodes are dictionaries with at least:
- `id`: Unique identifier (string)
- `type`: Node label/type (string)
- Additional properties vary by node type

Example node:
```python
{
    'id': 'person-123',
    'type': 'Person',
    'name': 'Alice Smith',
    'department': 'Engineering',
    'email': 'alice@example.com'
}
```

## Best Practices

1. **Always check node types** - Use `node.get('type')` to filter relevant nodes
2. **Handle empty inputs** - Return `[]` for empty source or target lists
3. **Use meaningful relationship types** - Follow Neo4j conventions (UPPERCASE_WITH_UNDERSCORES)
4. **Add relationship properties** - Include metadata like confidence, source, timestamp
5. **Be efficient** - Use O(n*m) or better algorithms for large node sets
6. **Document your logic** - Explain why links are created

## Relationship Types

Common patterns:
- **WORKS_ON**: Person → Project
- **CONTAINS**: Folder → File
- **DEPENDS_ON**: Package → Package
- **AUTHORED_BY**: Document → Person
- **SIMILAR_TO**: Node → Node (semantic similarity)
- **PART_OF**: Component → System

## Common Pitfalls

❌ **Don't crash on empty inputs**
```python
def create_links(source_nodes, target_nodes):
    # Will crash if lists are empty!
    first_source = source_nodes[0]
```

❌ **Don't return invalid structures**
```python
# Bad: returning dicts instead of tuples
return [{'source': 'a', 'target': 'b'}]
```

❌ **Don't use None as relationship type**
```python
# Bad: None is not a valid relationship type
return [('a', None, 'b', {})]
```

## Advanced Features

### Dynamic Relationship Types

You can return unique relationship types per triple:

```python
def create_links(source_nodes, target_nodes):
    links = []
    for source in source_nodes:
        for target in target_nodes:
            # Different rel type based on data
            if source['role'] == 'manager':
                rel_type = 'MANAGES'
            elif source['role'] == 'contributor':
                rel_type = 'CONTRIBUTES_TO'
            else:
                rel_type = 'ASSOCIATED_WITH'

            links.append((source['id'], rel_type, target['id'], {}))
    return links
```

### External Data Integration

Links can incorporate any accessible data:

```python
def create_links(source_nodes, target_nodes):
    # Load mapping from CSV
    import csv
    from pathlib import Path

    mapping_file = Path('/path/to/mapping.csv')
    mappings = {}

    with open(mapping_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            mappings[row['source_id']] = row['target_id']

    # Create links based on mapping
    links = []
    for source in source_nodes:
        if source['id'] in mappings:
            target_id = mappings[source['id']]
            links.append((source['id'], 'MAPPED_TO', target_id, {}))

    return links
```

## Integration

Once validated, your link script will:
- Appear in **Links Settings** → Available Scripts
- Be selectable when defining new relationship types
- Run on-demand or via scheduled jobs
- Create relationships in Neo4j graph

## Testing Your Link Script

Before validation, test manually:

```python
from my_link_script import create_links

# Test cases
test_source = [
    {'id': '1', 'type': 'Person', 'name': 'Alice'},
    {'id': '2', 'type': 'Person', 'name': 'Bob'}
]

test_target = [
    {'id': '10', 'type': 'Project', 'name': 'Project A'}
]

# Should return list of tuples
links = create_links(test_source, test_target)
print(f"Created {len(links)} links")

# Test empty inputs
empty_links = create_links([], test_target)
assert empty_links == [], "Should return empty list for empty inputs"
```

## Validation Process

1. Click "Validate" in Scripts page
2. Sandbox tests with sample node sets
3. Contract tests verify:
   - Function signature
   - Return type (list)
   - Empty input handling
   - Valid triple structure
4. If passed: ✅ **Validated** → Available in Links settings
5. If failed: ❌ **Failed** → Fix errors and retry

## Questions?

See examples in `tests/fixtures/script_validation/sample_link_script.py`
