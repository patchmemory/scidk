# SciDK MCP Server Setup

The SciDK MCP (Model Context Protocol) server exposes core SciDK functionality to external AI agents like Claude Desktop.

## Features

The MCP server provides 5 core tools:

1. **`query_knowledge_graph`** — Execute safe read-only Cypher queries against the Neo4j knowledge graph
2. **`get_schema`** — Retrieve the current database schema (labels, relationships, properties)
3. **`summarize_dataset`** — Generate statistical summaries of labels/relationships
4. **`get_label_profile`** — Get detailed Schema Intelligence profiles for specific labels
5. **`list_labels`** — List all labels with node counts

All tools return structured JSON responses and enforce read-only safety (no CREATE/MERGE/DELETE operations).

## Installation

### 1. Install MCP SDK

```bash
pip install mcp>=1.0.0
```

This is already included in `requirements.txt`.

### 2. Configure Claude Desktop

Add the following to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "scidk": {
      "command": "python3",
      "args": ["-m", "scidk.mcp_server"],
      "cwd": "/path/to/scidk",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "neo4jiscool",
        "NEO4J_DATABASE": "neo4j"
      }
    }
  }
}
```

**Important**: Replace `/path/to/scidk` with the absolute path to your SciDK installation.

### 3. Restart Claude Desktop

After updating the config, restart Claude Desktop completely. The MCP server will start automatically when you open a new conversation.

## Testing

### Manual Test

You can test the MCP server directly from the command line:

```bash
# Start the server (it uses stdio transport)
python3 -m scidk.mcp_server
```

The server will connect to Neo4j and wait for MCP protocol messages on stdin.

### Test in Claude Desktop

Once configured, open Claude Desktop and try these queries:

1. **List available labels:**
   ```
   Use the list_labels tool to show me all labels in the database
   ```

2. **Get schema:**
   ```
   Use get_schema to show me the database structure
   ```

3. **Query the graph:**
   ```
   Use query_knowledge_graph to run: MATCH (f:File) RETURN f.name LIMIT 5
   ```

4. **Get label profile:**
   ```
   Use get_label_profile to analyze the File label
   ```

## Tool Usage Examples

### 1. query_knowledge_graph

Execute a read-only Cypher query:

```json
{
  "cypher": "MATCH (f:File) WHERE f.mime_type CONTAINS 'image' RETURN f.name, f.path LIMIT 10",
  "limit": 10
}
```

Returns:
```json
{
  "status": "success",
  "rows": [
    {"f.name": "image1.png", "f.path": "/data/images/image1.png"},
    ...
  ],
  "row_count": 10,
  "error": null
}
```

### 2. get_schema

Retrieve database schema:

```json
{
  "max_labels": 50,
  "max_props_per_label": 5
}
```

Returns:
```json
{
  "status": "success",
  "schema": {
    "labels": ["File", "Folder", "Scan", "Sample", "SampleType"],
    "relationships": ["CONTAINS", "DERIVED_FROM", "SCANNED_IN"],
    "properties": {
      "File": ["name", "path", "mime_type", "size", "created"],
      "Folder": ["name", "path", "host", "host_id"]
    },
    "label_counts": {
      "File": 1523,
      "Folder": 342,
      ...
    }
  },
  "error": null
}
```

### 3. list_labels

Get all labels with counts:

```json
{}
```

Returns:
```json
{
  "status": "success",
  "labels": [
    {"name": "File", "count": 1523},
    {"name": "Folder", "count": 342},
    {"name": "Scan", "count": 89},
    {"name": "Sample", "count": 45},
    {"name": "SampleType", "count": 12}
  ],
  "error": null
}
```

### 4. get_label_profile

Get detailed profile for a label:

```json
{
  "label": "File"
}
```

Returns:
```json
{
  "status": "success",
  "profile": {
    "label": "File",
    "node_count": 1523,
    "properties": [
      {"name": "name", "frequency": 1523},
      {"name": "path", "frequency": 1523},
      {"name": "mime_type", "frequency": 1521},
      {"name": "size", "frequency": 1520},
      {"name": "created", "frequency": 1518}
    ],
    "relationships": [
      {"type": "CONTAINS", "target": "Folder", "frequency": 1523},
      {"type": "DERIVED_FROM", "target": "Sample", "frequency": 342}
    ]
  },
  "error": null
}
```

### 5. summarize_dataset

Generate statistical summary:

```json
{
  "label": "File"
}
```

Returns:
```json
{
  "status": "success",
  "summary": "Dataset summary: {'node_count': 1523, 'label': 'File'}",
  "error": null
}
```

## Safety Features

The MCP server enforces strict safety rules:

- **Read-only queries**: Blocks CREATE, MERGE, DELETE, SET, DROP, DETACH keywords
- **Automatic LIMIT**: Adds `LIMIT 50` to queries without explicit limits
- **Error handling**: Returns structured error messages instead of crashing
- **Connection pooling**: Uses Neo4j driver connection pooling for efficiency

## Troubleshooting

### MCP server not appearing in Claude Desktop

1. Check the Claude Desktop config file path
2. Verify JSON syntax is valid (use a JSON validator)
3. Check that the `cwd` path is correct
4. Restart Claude Desktop completely (quit and reopen)

### Connection errors

1. Verify Neo4j is running: `docker ps | grep neo4j`
2. Test connection manually: `python3 -m scidk.mcp_server`
3. Check environment variables in config
4. Verify Neo4j credentials are correct

### Tools not working

1. Check the Claude Desktop logs (varies by platform)
2. Verify the MCP server can import scidk modules
3. Test tools directly via Python:
   ```python
   from scidk.ai import mcp_tools
   from neo4j import GraphDatabase

   driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4jiscool"))
   result = mcp_tools.list_labels(driver, "neo4j")
   print(result)
   ```

## Next Steps

Once the MCP server is working, these tools can be integrated into the Concept Graph Phase 3 as `:Concept_Tool` nodes. The Concept Graph will then route user intents to MCP tools alongside native SciDK tools, creating a unified planning layer.

See the [SciDK Architecture Vision](SciDK_Architecture_Vision.md) for the full integration plan.
