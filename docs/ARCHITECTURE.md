# SciDK Architecture Documentation

This document provides a comprehensive overview of SciDK's system design, technology choices, component interactions, data flow, and scalability considerations.

## System Overview

SciDK is a scientific data knowledge management system that bridges filesystem data with graph-based knowledge representation. The architecture is designed for:

- **Flexibility**: Support multiple data sources (local, cloud, API)
- **Extensibility**: Plugin-based interpreter system
- **Scalability**: Efficient indexing and querying of large datasets
- **Maintainability**: Clean separation of concerns with modular design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Web Browser                          │
│                    (User Interface Layer)                     │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼────────────────────────────────────┐
│                      Flask Web Server                        │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ UI Routes   │  │ API Routes   │  │  Authentication  │  │
│  │ (Jinja2)    │  │ (REST/JSON)  │  │  & Authorization │  │
│  └─────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Core Services Layer                       │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐ │
│  │ Filesystem   │  │  Interpreter  │  │   Config        │ │
│  │ Manager      │  │  Registry     │  │   Manager       │ │
│  └──────────────┘  └───────────────┘  └─────────────────┘ │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐ │
│  │ Backup       │  │  Alert        │  │   Plugin        │ │
│  │ Manager      │  │  Manager      │  │   Loader        │ │
│  └──────────────┘  └───────────────┘  └─────────────────┘ │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     Data Layer                               │
│  ┌──────────────┐                    ┌──────────────────┐  │
│  │   SQLite     │                    │     Neo4j        │  │
│  │   Database   │                    │  Graph Database  │  │
│  │              │                    │   (Optional)     │  │
│  │ • Files      │                    │ • Nodes          │  │
│  │ • Scans      │                    │ • Relationships  │  │
│  │ • Settings   │                    │ • Schema         │  │
│  │ • Users      │                    │ • Instances      │  │
│  │ • Audit Log  │                    │                  │  │
│  └──────────────┘                    └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Core Technologies

**Backend Framework**: Flask 3.0+
- **Why Flask**: Lightweight, flexible, extensive ecosystem
- **Advantages**: Easy to extend, well-documented, Python ecosystem integration
- **Alternatives Considered**: FastAPI (async support), Django (too heavyweight)

**Primary Database**: SQLite 3
- **Why SQLite**:
  - Zero-configuration, embedded database
  - ACID compliant
  - WAL mode for concurrent access
  - Single-file portability
- **Use Cases**:
  - File index and metadata
  - Scan history
  - User accounts and settings
  - Audit logs
  - Configuration storage
- **Limitations**:
  - Not ideal for high-concurrency writes (mitigated with WAL mode)
  - No built-in graph queries (use Neo4j for this)

**Graph Database**: Neo4j 5.x (Optional but active in production)
- **Why Neo4j**:
  - Industry-leading graph database
  - Cypher query language
  - ACID transactions
  - Built-in graph algorithms
- **Use Cases**:
  - Knowledge graph storage
  - Relationship queries
  - Graph visualization
  - Schema management
- **Deployment**: Docker container or standalone instance

### Supporting Technologies

**Python Libraries**:
- **ijson**: Streaming JSON parsing for large files
- **openpyxl**: Excel file interpretation
- **PyYAML**: YAML file parsing
- **pandas**: Data analysis and CSV handling
- **bcrypt**: Password hashing
- **cryptography**: Symmetric encryption for sensitive data
- **APScheduler**: Background job scheduling
- **flasgger**: OpenAPI/Swagger documentation

**Frontend**:
- **Jinja2**: Server-side templating
- **JavaScript**: Interactive UI components
- **Cytoscape.js**: Graph visualization (alternative: vis.js)
- **Bootstrap**: UI framework (responsive design)

**External Tools** (Optional):
- **ncdu/gdu**: Fast filesystem enumeration
- **rclone**: Cloud storage integration
- **nginx**: Reverse proxy and SSL termination

## Component Architecture

### Web Layer

**Blueprint Structure** (~27 blueprints, 300+ routes). Blueprints are registered via `register_blueprints()` in `scidk/web/routes/__init__.py`:

```python
scidk/web/routes/
├── ui.py                    # User interface (HTML) routes
├── api_files.py             # File, scan, and dataset operations
├── api_graph.py             # Graph schema, instances, RO-Crate export
├── api_maps.py              # Map/visualization data
├── api_labels.py            # Schema/label management
├── api_links.py             # Link definitions and execution
├── api_links_v2.py          # Link registry (v2)
├── api_integrations.py      # External API integrations
├── api_neo4j.py             # Neo4j connection and operations
├── api_providers.py         # Filesystem/rclone providers and mounts
├── api_tasks.py             # Background task management
├── api_scripts.py           # Analysis scripts
├── api_results.py           # Analysis result panels
├── api_queries.py           # Saved Cypher query library
├── api_chat.py              # Chat / GraphRAG interface
├── api_annotations.py       # Annotations
├── api_plugins.py           # Plugin management and instances
├── api_interpreters.py      # Interpreter configuration
├── api_settings.py          # Settings and configuration
├── api_auth.py              # Authentication endpoints
├── api_users.py             # User management
├── api_audit.py             # Audit log access
├── api_alerts.py            # Alert configuration
├── api_logs.py              # Application logs
├── api_admin.py             # Health / metrics / admin
└── api_system.py            # System info
```

**Advantages**:
- Clean separation of concerns
- Easy to add new features
- Improved testability
- Lean application factory: `create_app()` lives in `scidk/app.py` (~314 lines); route definitions live in the per-area blueprint modules above

### Core Services

**FilesystemManager**:
- Orchestrates file scanning and indexing
- Manages multiple provider backends (local, mounted, rclone)
- Coordinates with interpreter registry
- Handles batch processing

**InterpreterRegistry**:
- Plugin-based system for file interpretation
- Extensible architecture for new file types
- Built-in interpreters:
  - CSV (tabular data)
  - JSON (structured data)
  - YAML (configuration files)
  - Python (code analysis: imports, functions, classes)
  - Excel (multi-sheet workbooks)
  - Jupyter notebooks (.ipynb)
  - Generic text

**GraphBackend**:
- Abstract interface for graph operations
- Implementations:
  - InMemoryGraph (default, no external dependencies)
  - Neo4jGraph (persistent, production-ready)
- Supports:
  - Node and relationship creation
  - Schema management
  - Cypher query execution
  - Commit operations with verification

**ConfigManager**:
- Centralized configuration management
- Export/import functionality
- Encrypted credential storage
- Version tracking
- Automatic backups before changes

**BackupManager**:
- Scheduled backup operations
- Configurable retention policies
- Backup verification
- Alert integration on failure

**AlertManager**:
- Event-driven notification system
- SMTP email delivery
- Alert history tracking
- Configurable thresholds
- Pre-configured alerts:
  - Import failures
  - High discrepancies
  - Backup failures
  - Neo4j connection loss
  - Disk space critical

### Data Flow

#### File Scanning Flow

```
User Initiates Scan
        │
        ▼
┌───────────────────┐
│ API: POST /scans  │
└────────┬──────────┘
         │
         ▼
┌──────────────────────────┐
│ FilesystemManager        │
│ • Validate path          │
│ • Select provider        │
│ • Create scan record     │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Provider Backend         │
│ (LocalFS/Rclone)         │
│ • Enumerate files        │
│ • Collect metadata       │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ InterpreterRegistry      │
│ • Match file types       │
│ • Run interpreters       │
│ • Generate metadata      │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ SQLite: Batch Insert     │
│ • Store file metadata    │
│ • Store interpretations  │
│ • Update scan status     │
└────────┬─────────────────┘
         │
         ▼
   Scan Complete
```

#### Commit to Graph Flow

```
User Commits Scan
        │
        ▼
┌──────────────────────────┐
│ API: POST /scans/commit  │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Load Scan Data from DB   │
│ • Fetch files            │
│ • Fetch folders          │
│ • Build hierarchy        │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ GraphBackend             │
│ • Create/merge nodes     │
│ • Create relationships   │
│ • Set properties         │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Post-Commit Verification │
│ • Count expected records │
│ • Query actual records   │
│ • Report discrepancies   │
└────────┬─────────────────┘
         │
         ▼
  Commit Verified
```

#### Label Management Flow

```
User Defines Label
        │
        ▼
┌──────────────────────────┐
│ API: POST /labels        │
│ • Name, properties       │
│ • Relationships          │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Local Label Storage      │
│ (SQLite)                 │
└────────┬─────────────────┘
         │
         ▼
User Pushes to Neo4j
         │
         ▼
┌──────────────────────────┐
│ GraphBackend.push_schema │
│ • Create constraints     │
│ • Create indexes         │
│ • Define relationships   │
└────────┬─────────────────┘
         │
         ▼
  Schema in Neo4j
```

## Database Schema

### SQLite Tables

**files** (see `scidk/core/path_index_sqlite.py`):
```sql
CREATE TABLE IF NOT EXISTS files (
    path TEXT NOT NULL,
    parent_path TEXT,
    name TEXT NOT NULL,
    depth INTEGER NOT NULL,
    type TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_time REAL,
    file_extension TEXT,
    mime_type TEXT,
    etag TEXT,
    hash TEXT,
    remote TEXT,
    scan_id TEXT,
    extra_json TEXT
);
-- interpreted_as TEXT and interpretation_json TEXT are added via ALTER TABLE on init.
-- Node identity is the composite (path, host); there is no surrogate `id` column.
```

**scans** (see `scidk/core/migrations.py`):
```sql
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    root TEXT,
    started REAL,
    completed REAL,
    status TEXT,
    extra_json TEXT
);
-- Per-scan detail (recursive flag, counts, provider, etc.) is stored in extra_json
-- and in companion tables (scan_items, scan_progress).
```

**auth_users** (see `scidk/core/auth.py`):
```sql
CREATE TABLE IF NOT EXISTS auth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    created_by TEXT,
    last_login REAL
);
```

**settings** (see `scidk/core/migrations.py`):
```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

**auth_audit_log** (see `scidk/core/auth.py`):
```sql
CREATE TABLE IF NOT EXISTS auth_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT
);
```

### Neo4j Schema

**Node Labels**:
- **File**: Individual files with properties (path, size, modified, extension)
- **Folder**: Directory nodes with properties (path, name)
- **Scan**: Scan session metadata (timestamp, path, recursive)
- **Custom Labels**: User-defined via Labels page

**Relationships** (see `scidk/services/neo4j_client.py`):
- **(File)-[:SCANNED_IN]->(Scan)**: Files belong to scans
- **(Folder)-[:SCANNED_IN]->(Scan)**: Folders belong to scans
- **(Folder)-[:CONTAINS]->(File)**: File hierarchy
- **(Folder)-[:CONTAINS]->(Folder)**: Folder hierarchy
- **(File)-[:INTERPRETED_AS]->(...)**: Interpretation results
- **Custom Relationships**: User-defined via Links page (e.g. `DERIVED_FROM`)

## Scalability Considerations

### Current Limitations

1. **File Count**: Tested with datasets up to 100,000 files
   - SQLite handles this well with proper indexing
   - Graph visualization limited to ~1,000 nodes for UI performance

2. **Concurrent Users**: Designed for 10-50 concurrent users
   - WAL mode supports concurrent reads
   - Single-writer model for SQLite

3. **Data Size**: Individual file size limits:
   - Preview generation: 10MB
   - Full interpretation: 100MB
   - Streaming for larger files

### Scaling Strategies

**Horizontal Scaling** (Future):
- Multiple app servers behind load balancer
- Shared PostgreSQL database (replace SQLite)
- Neo4j cluster for graph operations

**Vertical Scaling** (Current):
- Increase server resources (RAM, CPU)
- SSD for database storage
- Optimize indexes and queries

**Performance Optimization**:

1. **Database Optimizations**:
   ```sql
   -- Enable WAL mode (done automatically)
   PRAGMA journal_mode=WAL;

   -- Optimize query planner
   ANALYZE;

   -- Reclaim space
   VACUUM;
   ```

2. **Caching**:
   - In-memory caching for frequently accessed data
   - Redis for distributed caching (future)

3. **Batch Processing**:
   - Process files in batches (default: 10,000)
   - Commit to graph in batches
   - Background job processing

4. **Index Optimization**:
   - Composite indexes for common queries
   - Full-text search indexes
   - Neo4j relationship indexes

### Monitoring and Metrics

**Application Metrics**:
- Request rate and latency
- Error rates by endpoint
- Active user sessions
- Background job queue depth

**Database Metrics**:
- Query execution time
- Connection pool usage
- Database size and growth rate
- Index efficiency

**System Metrics**:
- CPU and memory usage
- Disk I/O
- Network bandwidth
- Disk space available

## Security Architecture

See [SECURITY.md](SECURITY.md) for detailed security architecture.

**Key Security Features**:
- Multi-user authentication with RBAC
- Session management with auto-lock
- Encrypted credential storage
- Comprehensive audit logging
- CSRF protection
- Input validation and sanitization

## Extensibility

### Plugin System

**Interpreter Plugins**:
```python
# Example custom interpreter
from scidk.core.registry import Interpreter

class MyInterpreter(Interpreter):
    name = "my_format"
    extensions = [".myext"]

    def interpret(self, file_path):
        # Custom interpretation logic
        return {
            "type": "my_format",
            "data": {...}
        }

# Register
registry.register(MyInterpreter())
```

**Provider Plugins**:
```python
# Example custom provider
class MyProvider:
    provider_id = "my_provider"

    def list_files(self, path):
        # Custom file listing logic
        return [...]

    def read_file(self, file_id):
        # Custom file reading logic
        return bytes
```

### API Extensibility

**Custom Endpoints**:
```python
from flask import Blueprint

custom_bp = Blueprint('custom', __name__, url_prefix='/api/custom')

@custom_bp.route('/my-endpoint', methods=['GET'])
def my_endpoint():
    return {"message": "Custom endpoint"}

# Register blueprint
app.register_blueprint(custom_bp)
```

## Design Decisions and Trade-offs

### Why SQLite?

**Advantages**:
- Zero configuration
- Single-file portability
- ACID compliance
- Built-in full-text search
- Python standard library support

**Trade-offs**:
- Limited concurrency for writes (mitigated with WAL)
- No network access (local or mounted filesystem)
- Not ideal for distributed systems

**When to Switch**: Consider PostgreSQL when:
- Need for multiple app servers
- High concurrent write load (>100 writes/sec)
- Distributed deployment required

### Why Neo4j (Optional but active in production)?

**Advantages**:
- Native graph queries (relationships are first-class)
- Cypher query language (declarative, powerful)
- Built-in graph algorithms
- Excellent visualization support

**Trade-offs**:
- Additional infrastructure requirement
- Memory-intensive for large graphs
- Commercial licensing for enterprise features

**When to Use**:
- Complex relationship queries
- Knowledge graph workflows
- Graph analytics requirements

### Why Flask over FastAPI?

**Flask Advantages**:
- Mature ecosystem
- Extensive documentation
- Synchronous model (simpler for most operations)
- Jinja2 integration for server-side rendering

**FastAPI Advantages** (not chosen):
- Async/await support
- Automatic OpenAPI generation
- Better performance for I/O-bound operations

**Decision**: Flask chosen for:
- Simpler synchronous model fits use case
- Rich plugin ecosystem
- Team expertise

## Future Architecture Considerations

### Planned Enhancements

1. **Microservices Architecture** (Long-term):
   - Separate scan service
   - Separate graph service
   - API gateway

2. **Event-Driven Architecture**:
   - Event bus (RabbitMQ, Kafka)
   - Async processing
   - Real-time updates via WebSockets

3. **Containerization**:
   - Docker images for all components
   - Kubernetes orchestration
   - Helm charts for deployment

4. **Distributed Caching**:
   - Redis for session storage
   - Cached query results
   - Distributed lock management

5. **Advanced Analytics**:
   - Machine learning integration
   - Anomaly detection
   - Predictive modeling

## Deployment Architectures

### Single Server (Current)

```
┌─────────────────────────────┐
│      Single Server          │
│  ┌──────────────────────┐  │
│  │   nginx (reverse     │  │
│  │   proxy)             │  │
│  └──────────┬───────────┘  │
│             │               │
│  ┌──────────▼───────────┐  │
│  │   SciDK Flask App    │  │
│  │   (systemd service)  │  │
│  └──────────┬───────────┘  │
│             │               │
│  ┌──────────▼───────────┐  │
│  │   SQLite + Neo4j     │  │
│  │   (local)            │  │
│  └──────────────────────┘  │
└─────────────────────────────┘
```

### High-Availability (Future)

```
┌──────────────┐
│ Load Balancer│
└──────┬───────┘
       │
   ┌───┴────┬────────┐
   │        │        │
┌──▼──┐ ┌──▼──┐ ┌──▼──┐
│App 1│ │App 2│ │App 3│
└──┬──┘ └──┬──┘ └──┬──┘
   │       │       │
   └───┬───┴───┬───┘
       │       │
  ┌────▼───┐ ┌▼──────────┐
  │ Postgres│ │Neo4j      │
  │ Cluster │ │Cluster    │
  └─────────┘ └───────────┘
```

## Additional Resources

- **Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Operations Manual**: [OPERATIONS.md](OPERATIONS.md)
- **API Reference**: [API.md](API.md)
- **Security Guide**: [SECURITY.md](SECURITY.md)
- **Feature Index**: [FEATURE_INDEX.md](../dev/features/FEATURE_INDEX.md)
- **Testing Documentation**: [testing.md](testing.md)
