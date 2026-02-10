# SciDK API Reference

This document provides a comprehensive guide to the SciDK REST API, including authentication, common operations, and endpoint reference.

## Base URL

```
http://localhost:5000
```

For production deployments, replace with your domain:
```
https://your-domain.com
```

## API Documentation (Swagger/OpenAPI)

Interactive API documentation is available at:
```
http://localhost:5000/api/docs
```

This provides a complete, interactive reference with the ability to test endpoints directly from your browser.

## Authentication

SciDK supports multiple authentication methods depending on your configuration.

### Session-Based Authentication

For web UI access, log in through the login page:

**Endpoint**: `POST /api/auth/login`

**Request**:
```json
{
  "username": "admin",
  "password": "your_password"
}
```

**Response**:
```json
{
  "status": "success",
  "user": {
    "username": "admin",
    "role": "admin"
  }
}
```

The session cookie is automatically set and used for subsequent requests.

### Bearer Token Authentication

For API access, use Bearer tokens:

**Request Header**:
```
Authorization: Bearer YOUR_TOKEN_HERE
```

**Example**:
```bash
curl -H "Authorization: Bearer abc123..." \
  http://localhost:5000/api/health
```

### No Authentication (Development)

For development or testing, authentication can be disabled (not recommended for production):
```bash
export SCIDK_AUTH_DISABLED=true
```

## Common API Operations

### Health Check

Check application and database status:

```bash
curl http://localhost:5000/api/health
```

**Response**:
```json
{
  "status": "healthy",
  "sqlite": {
    "path": "/home/user/.scidk/db/files.db",
    "exists": true,
    "journal_mode": "wal",
    "wal_mode": true,
    "schema_version": 5,
    "select1": true
  }
}
```

### Graph Health

Check Neo4j connection and graph statistics:

```bash
curl http://localhost:5000/api/health/graph
```

**Response**:
```json
{
  "status": "connected",
  "nodes": {
    "File": 1245,
    "Folder": 89,
    "Scan": 12
  },
  "relationships": {
    "CONTAINS": 1334,
    "SCANNED_IN": 1245
  }
}
```

## File and Dataset Operations

### List Scans

```bash
curl http://localhost:5000/api/scans
```

**Response**:
```json
{
  "scans": [
    {
      "id": "scan_123",
      "path": "/data/project",
      "recursive": true,
      "timestamp": "2024-01-15T10:30:00Z",
      "file_count": 1245,
      "status": "completed"
    }
  ]
}
```

### Create New Scan

```bash
curl -X POST http://localhost:5000/api/scans \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": "local_fs",
    "path": "/data/project",
    "recursive": true
  }'
```

**Response**:
```json
{
  "status": "success",
  "scan_id": "scan_456",
  "message": "Scan started"
}
```

### Get Scan Status

```bash
curl http://localhost:5000/api/scans/scan_456/status
```

**Response**:
```json
{
  "scan_id": "scan_456",
  "status": "in_progress",
  "file_count": 523,
  "progress": 42
}
```

### List Files in Scan

```bash
curl http://localhost:5000/api/scans/scan_456/files?page=1&limit=50
```

**Response**:
```json
{
  "files": [
    {
      "id": "file_123",
      "name": "data.csv",
      "path": "/data/project/data.csv",
      "size": 1024000,
      "modified": "2024-01-15T09:00:00Z",
      "extension": ".csv"
    }
  ],
  "total": 1245,
  "page": 1,
  "per_page": 50
}
```

### Get File Details

```bash
curl http://localhost:5000/api/datasets/file_123
```

**Response**:
```json
{
  "id": "file_123",
  "name": "data.csv",
  "path": "/data/project/data.csv",
  "size": 1024000,
  "modified": "2024-01-15T09:00:00Z",
  "interpretations": [
    {
      "type": "csv",
      "rows": 100,
      "columns": 5,
      "preview": [...]
    }
  ]
}
```

### Delete File(s)

Delete single file:
```bash
curl -X DELETE http://localhost:5000/api/datasets/file_123
```

Bulk delete:
```bash
curl -X POST http://localhost:5000/api/datasets/bulk-delete \
  -H "Content-Type: application/json" \
  -d '{"file_ids": ["file_123", "file_456"]}'
```

## Graph and Label Operations

### List Labels

```bash
curl http://localhost:5000/api/labels
```

**Response**:
```json
{
  "labels": [
    {
      "name": "File",
      "properties": [
        {"name": "path", "type": "string"},
        {"name": "size", "type": "integer"}
      ],
      "relationships": [
        {
          "name": "SCANNED_IN",
          "target": "Scan"
        }
      ]
    }
  ]
}
```

### Create Label

```bash
curl -X POST http://localhost:5000/api/labels \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dataset",
    "properties": [
      {"name": "name", "type": "string"},
      {"name": "created", "type": "datetime"}
    ]
  }'
```

### Get Label Instances

```bash
curl http://localhost:5000/api/labels/File/instances?page=1&limit=10
```

**Response**:
```json
{
  "label": "File",
  "instances": [
    {
      "id": "file_123",
      "properties": {
        "path": "/data/project/data.csv",
        "size": 1024000
      }
    }
  ],
  "total": 1245,
  "page": 1
}
```

### Push Labels to Neo4j

```bash
curl -X POST http://localhost:5000/api/labels/File/push
```

### Pull Labels from Neo4j

```bash
curl -X POST http://localhost:5000/api/labels/pull
```

### Import Schema from Arrows.app

```bash
curl -X POST http://localhost:5000/api/labels/import/arrows \
  -H "Content-Type: application/json" \
  -d '{"schema": {...}}'
```

### Export Schema to Arrows.app

```bash
curl http://localhost:5000/api/labels/export/arrows
```

## Link Operations

### List Link Definitions

```bash
curl http://localhost:5000/api/links
```

**Response**:
```json
{
  "links": [
    {
      "id": "link_123",
      "name": "File to Dataset",
      "source_type": "csv",
      "target_label": "Dataset"
    }
  ]
}
```

### Create Link Definition

```bash
curl -X POST http://localhost:5000/api/links \
  -H "Content-Type: application/json" \
  -d '{
    "name": "File to Dataset",
    "source": {
      "type": "csv",
      "data": "...",
      "mapping": {...}
    },
    "target": {
      "label": "Dataset",
      "mapping": {...}
    }
  }'
```

### Execute Link

```bash
curl -X POST http://localhost:5000/api/links/link_123/execute
```

**Response**:
```json
{
  "status": "success",
  "job_id": "job_789",
  "message": "Link execution started"
}
```

### Get Link Execution Job Status

```bash
curl http://localhost:5000/api/integrations/jobs/job_789
```

**Response**:
```json
{
  "job_id": "job_789",
  "status": "completed",
  "relationships_created": 145,
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:05:00Z"
}
```

## Integration Operations

### List API Endpoints

```bash
curl http://localhost:5000/api/integrations
```

**Response**:
```json
{
  "endpoints": [
    {
      "id": "ep_123",
      "name": "External API",
      "url": "https://api.example.com/data",
      "auth_method": "bearer",
      "target_label": "ExternalData"
    }
  ]
}
```

### Create API Endpoint

```bash
curl -X POST http://localhost:5000/api/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "External API",
    "url": "https://api.example.com/data",
    "auth_method": "bearer",
    "auth_value": "token_here",
    "jsonpath": "$.data[*]",
    "target_label": "ExternalData"
  }'
```

### Test Endpoint Connection

```bash
curl -X POST http://localhost:5000/api/integrations/ep_123/preview
```

## Settings Operations

### Export Configuration

```bash
curl -X GET http://localhost:5000/api/settings/export \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o scidk-config.json
```

### Import Configuration

```bash
curl -X POST http://localhost:5000/api/settings/import \
  -H "Content-Type: application/json" \
  -d @scidk-config.json
```

### Get Neo4j Settings

```bash
curl http://localhost:5000/api/settings/neo4j
```

**Response**:
```json
{
  "uri": "bolt://localhost:7687",
  "user": "neo4j",
  "database": "neo4j",
  "connected": true
}
```

### Update Neo4j Settings

```bash
curl -X POST http://localhost:5000/api/settings/neo4j \
  -H "Content-Type: application/json" \
  -d '{
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "password",
    "database": "neo4j"
  }'
```

## Alert Operations

### List Alerts

```bash
curl http://localhost:5000/api/settings/alerts
```

**Response**:
```json
{
  "alerts": [
    {
      "id": "alert_import_failed",
      "name": "Import Failed",
      "enabled": true,
      "recipients": "admin@example.com",
      "threshold": null
    }
  ]
}
```

### Update Alert Configuration

```bash
curl -X PUT http://localhost:5000/api/settings/alerts/alert_import_failed \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "recipients": "admin@example.com,ops@example.com"
  }'
```

### Test Alert

```bash
curl -X POST http://localhost:5000/api/settings/alerts/alert_import_failed/test
```

### Get Alert History

```bash
curl http://localhost:5000/api/settings/alerts/history?limit=50
```

**Response**:
```json
{
  "history": [
    {
      "alert_id": "alert_import_failed",
      "triggered_at": "2024-01-15T12:30:00Z",
      "condition": "Import failed for scan_456",
      "sent": true
    }
  ]
}
```

## Chat Operations

### Send Chat Message

```bash
curl -X POST http://localhost:5000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What files are in /data/project?",
    "context": true
  }'
```

**Response**:
```json
{
  "response": "I found 1,245 files in /data/project...",
  "sources": [
    {"scan_id": "scan_123", "file_count": 1245}
  ]
}
```

### Get Chat History

```bash
curl http://localhost:5000/api/chat/history?limit=50
```

## Error Response Format

All API errors follow a consistent format:

```json
{
  "status": "error",
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {}
}
```

### Common Error Codes

| HTTP Code | Meaning | Example |
|-----------|---------|---------|
| 400 | Bad Request | Invalid JSON or missing required fields |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Duplicate resource or constraint violation |
| 500 | Internal Server Error | Unexpected server error |
| 502 | Bad Gateway | Neo4j connection failed |
| 503 | Service Unavailable | Service temporarily unavailable |

### Example Error Response

```json
{
  "status": "error",
  "error": "File not found",
  "code": "FILE_NOT_FOUND",
  "details": {
    "file_id": "file_999"
  }
}
```

## Rate Limiting

API rate limiting may be configured in production deployments. Check response headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1673798400
```

## Pagination

List endpoints support pagination:

**Query Parameters**:
- `page`: Page number (default: 1)
- `limit`: Items per page (default: 50, max: 1000)

**Response Headers**:
```
X-Total-Count: 1245
X-Page: 1
X-Per-Page: 50
```

## Filtering and Sorting

Many list endpoints support filtering and sorting:

**Query Parameters**:
- `filter[field]`: Filter by field value
- `sort`: Sort field (prefix with `-` for descending)

**Example**:
```bash
curl "http://localhost:5000/api/scans?filter[status]=completed&sort=-timestamp"
```

## WebSocket Support (Future)

WebSocket support for real-time updates is planned for future releases.

## SDK and Client Libraries

Official client libraries:
- **Python**: `pip install scidk-client` (planned)
- **JavaScript**: `npm install @scidk/client` (planned)

## Examples

### Complete Workflow Example

```bash
# 1. Check health
curl http://localhost:5000/api/health

# 2. Start a scan
SCAN_ID=$(curl -X POST http://localhost:5000/api/scans \
  -H "Content-Type: application/json" \
  -d '{"path": "/data", "recursive": true}' \
  | jq -r '.scan_id')

# 3. Check scan status
curl http://localhost:5000/api/scans/$SCAN_ID/status

# 4. List files from scan
curl http://localhost:5000/api/scans/$SCAN_ID/files

# 5. Commit to Neo4j
curl -X POST http://localhost:5000/api/scans/$SCAN_ID/commit

# 6. Query graph
curl http://localhost:5000/api/health/graph
```

### Python Example

```python
import requests

base_url = "http://localhost:5000"

# Start scan
response = requests.post(f"{base_url}/api/scans", json={
    "path": "/data/project",
    "recursive": True
})
scan_id = response.json()["scan_id"]

# Wait for completion (polling)
import time
while True:
    status = requests.get(f"{base_url}/api/scans/{scan_id}/status").json()
    if status["status"] == "completed":
        break
    time.sleep(5)

# Get files
files = requests.get(f"{base_url}/api/scans/{scan_id}/files").json()
print(f"Found {len(files['files'])} files")
```

## Additional Resources

- **Interactive API Docs**: http://localhost:5000/api/docs
- **Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Operations Manual**: [OPERATIONS.md](OPERATIONS.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Security**: [SECURITY.md](SECURITY.md)
