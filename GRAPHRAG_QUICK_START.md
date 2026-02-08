# GraphRAG Quick Start Guide

## Enable GraphRAG in SciDK

### 1. Set Environment Variable
```bash
export SCIDK_GRAPHRAG_ENABLED=1
```

### 2. Optional: Add Anthropic API Key (Better Entity Extraction)
```bash
export SCIDK_ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Start SciDK
```bash
python3 -m scidk
```

### 4. Navigate to Chat
Open browser: `http://localhost:5000/chat`

---

## Example Queries

### Schema-Agnostic Examples (Works with ANY Neo4j Database)

```
How many nodes are in the database?

Find all File nodes

Show me recent scans

List all folders

What types of nodes exist?

Find files with name=test.txt

Count all relationships
```

### For File-Based Graphs (SciDK Default Schema)
```
Find all files in my project

Show recent file scans

How many Python files are there?

List all folders containing CSV files

Find files modified this week
```

---

## UI Features

### Basic Mode (Default)
- Type natural language queries
- Get conversational responses
- Chat history saved automatically

### Verbose Mode (Toggle Checkbox)
- See extracted entities (IDs, labels, properties)
- View execution time
- See result counts
- Colored entity badges

### Actions
- **Send:** Submit query (or press Enter)
- **Clear History:** Delete all messages
- **Verbose Toggle:** Show/hide technical details

---

## API Usage

### Query Endpoint
```bash
curl -X POST http://localhost:5000/api/chat/graphrag \
  -H "Content-Type: application/json" \
  -d '{"message": "How many files are there?"}'
```

### Response Format
```json
{
  "status": "ok",
  "reply": "Found 42 files in the database.",
  "metadata": {
    "entities": {
      "identifiers": [],
      "labels": ["File"],
      "properties": {},
      "intent": "count"
    },
    "execution_time_ms": 1234,
    "result_count": 1
  }
}
```

---

## Configuration Reference

### Required
```bash
SCIDK_GRAPHRAG_ENABLED=1          # Turn on GraphRAG
```

### Optional
```bash
SCIDK_ANTHROPIC_API_KEY=...       # Better entity extraction
SCIDK_GRAPHRAG_VERBOSE=true       # Always show metadata
SCIDK_GRAPHRAG_SCHEMA_CACHE_TTL_SEC=300  # Schema cache duration
```

### Privacy Controls
```bash
SCIDK_GRAPHRAG_ALLOW_LABELS=File,Folder  # Only query these labels
SCIDK_GRAPHRAG_DENY_LABELS=User,Secret   # Never query these labels
```

---

## Troubleshooting

### "GraphRAG disabled"
**Solution:** Set `SCIDK_GRAPHRAG_ENABLED=1`

### "Neo4j is not configured"
**Solution:** Set Neo4j connection:
```bash
export NEO4J_URI=neo4j://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your_password
```

### "neo4j-graphrag not installed"
**Solution:** Install dependency:
```bash
pip install neo4j-graphrag>=0.3.0
```

### Queries return "No results"
**Possible causes:**
1. Empty database → Run a scan first
2. Wrong node labels → Check schema with "What types of nodes exist?"
3. Query too specific → Try broader query

---

## Testing

### Run Pytest
```bash
python3 -m pytest tests/test_graphrag_*_simple.py -v
```

### Run E2E Tests
```bash
npm run e2e -- chat-graphrag.spec.ts
```

---

## Architecture

```
User Query
    ↓
Entity Extractor (extract IDs, labels, properties, intent)
    ↓
Neo4j Schema Discovery (CALL db.labels(), db.relationshipTypes())
    ↓
neo4j-graphrag Text2CypherRetriever (generate Cypher)
    ↓
Neo4j Execution
    ↓
Result Formatting
    ↓
Response to User
```

**Key Feature:** Schema-agnostic - works with ANY Neo4j database!

---

## Learn More

- **Implementation:** `scidk/services/graphrag/`
- **Tests:** `tests/test_graphrag_*_simple.py`
- **E2E Tests:** `e2e/chat-graphrag.spec.ts`
- **Session Summary:** `dev/sessions/2026-02-07-graphrag-integration-summary.md`
