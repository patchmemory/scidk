# SciDK Feature Index

**Purpose**: Current application layout and feature inventory for product planning and demo preparation.

**Last Updated**: 2026-02-09

---

## Application Structure

### Navigation & Pages

| Page | Route | Primary Purpose |
|------|-------|----------------|
| Home | `/` | Landing page with search, filters, quick chat |
| Chat | `/chat` | Full chat interface (multi-user, database-persisted) |
| Files/Datasets | `/datasets` | Browse scans, manage file data, commit to Neo4j |
| File Detail | `/datasets/<id>` | View file metadata and interpretations |
| Workbook Viewer | `/datasets/<id>/workbook` | Excel sheet preview with navigation |
| Map | `/map` | Interactive graph visualization (Neo4j + local schema) |
| Labels | `/labels` | Graph schema management (properties, relationships) |
| Links | `/links` | Link definition wizard (create relationships) |
| Extensions | `/extensions` | Plugin/extension management |
| Integrations | `/integrations` | External service integrations |
| Settings | `/settings` | Neo4j, interpreters, rclone, chat, plugins, integrations |
| Login | `/login` | User authentication (multi-user with RBAC) |

---

## Feature Groups by Page

### 1. Home Page (`/`)

**Search & Discovery**
- Full-text file search with query input
- Filter by file extension
- Filter by interpreter type
- Provider/path-based filtering
- Recursive path toggle
- Reset filters option

**Dashboard & Summary**
- File count display
- Scan count summary
- Extension breakdown
- Interpreter type summary
- Recent scans list

**Quick Actions**
- Inline chat input (quick queries without leaving home)
- Direct navigation to all main pages

---

### 2. Chat Page (`/chat`)

**Conversation Interface**
- Full-featured chat UI with message history
- Context-aware responses (references indexed files/graph)
- Markdown rendering in responses
- Timestamped messages
- Scrollable history

**Multi-User & Security** (Recent: PR #40)
- User authentication system
- Role-based access control (RBAC)
- Database-persisted chat history
- Per-user conversation isolation
- Admin role for system management

**Session Management** (Recent: PR #44)
- Auto-lock after inactivity timeout
- Configurable timeout settings
- Session expiration handling

---

### 3. Files/Datasets Page (`/datasets`)

**Provider Browser Tab**
- Provider dropdown (filesystem, rclone remotes)
- Path selection and manual entry
- Recursive scan toggle
- Fast list mode (skip detailed metadata)
- Max depth control
- Browse before scan (preview file tree)
- Initiate scan with progress tracking

**Snapshot Browser Tab**
- Scan dropdown (view historical scans)
- Snapshot file list with pagination
- Path prefix filter
- Extension/type filter
- Custom extension input
- Page size controls
- Previous/Next pagination
- "Use Live" switch (latest data)

**Snapshot Search**
- Query input for snapshot data
- Extension-based search
- Prefix-based search
- Clear and reset options

**Data Management**
- Commit snapshot to Neo4j
- Commit progress/status indicators
- Recent scans management
- Refresh scans list

**RO-Crate Integration**
- Open RO-Crate viewer modal
- Display RO-Crate metadata
- Export capability

**Data Cleaning Workflow** (Recent: PR #46)
- Delete individual files from dataset
- Bulk delete multiple files
- Bidirectional relationship cleanup (removes orphaned links)
- Confirmation prompts for destructive actions
- Real-time UI updates after deletion

---

### 4. File Detail Page (`/datasets/<id>`)

**Metadata Display**
- Filename, full path
- File size, last modified
- Checksum/ID
- Provider information

**Interpretation Viewer**
- Multiple interpretation tabs (CSV, JSON, YAML, Python, etc.)
- CSV: Table preview
- JSON: Formatted/collapsible tree
- Python: Syntax-highlighted code
- YAML: Structured display
- Excel: Sheet selector (links to workbook viewer)

**Actions**
- Back navigation
- Copy path/ID to clipboard
- View raw content
- Navigate to related files

---

### 5. Workbook Viewer (`/datasets/<id>/workbook`)

**Sheet Navigation**
- Sheet selector dropdown
- Switch between sheets
- Active sheet indicator

**Table Preview**
- Rendered table with headers
- Formatted cell values
- Horizontal/vertical scrolling
- Row/column count display
- Preview limit indicator (first N rows)

**Navigation**
- Back to file detail
- Back to files list
- Breadcrumb navigation

---

### 6. Map/Graph Visualization (`/map`)

**Graph Display**
- Interactive node/edge rendering
- Auto-layout on load
- Node labels and colors
- Relationship edges
- Color-coded sources:
  - Blue: In-memory graph (scanned data)
  - Red: Local labels (definitions only)
  - Green: Neo4j schema (pulled from database)
  - Mixed colors: Combined sources

**Data Source Selection**
- "All Sources" (combined view, default)
- "In-Memory Graph" (scanned files only)
- "Local Labels" (schema definitions)
- "Neo4j Schema" (pulled from database)

**Filtering**
- Label type filter dropdown
- Relationship type filter
- Multiple filter combinations
- Clear filters option

**Layout Controls**
- Layout mode selector (force-directed, circular, etc.)
- Save positions button
- Load saved positions
- Re-layout on demand

**Appearance Controls**
- Node size slider
- Edge width slider
- Font size slider
- High contrast toggle
- Immediate visual updates

**Interaction**
- Click and drag nodes
- Pan graph canvas
- Zoom in/out (mousewheel)
- Click nodes for details
- Click edges for relationship info

**Export & Instance Preview**
- Download CSV (graph data export)
- Instance preview selector
- "Preview Instances" button
- Formatted instance data display

---

### 7. Labels Page (`/labels`)

**Schema Definition** (Recent: PR #38 - Three-column layout with instance browser)
- Three-column layout:
  - Left: Label list sidebar (resizable, 200px-50% width)
  - Center: Label editor/wizard
  - Right: Instance browser (shows actual nodes for selected label)
- Create new labels
- Edit existing labels
- Define label properties (name, type: string/int/float/etc.)
- Add/remove properties
- Property type dropdown

**Relationship Management**
- Add relationships to labels
- Define relationship name
- Select target label
- Define relationship properties (optional)
- Remove relationships

**Neo4j Synchronization**
- Push to Neo4j (local → database)
- Pull from Neo4j (database → local)
- Success/failure feedback
- Sync status indicators

**Arrows.app Integration**
- Import schema from Arrows.app (JSON)
- Export schema to Arrows.app
- Paste JSON or upload file
- Bidirectional workflow support

**Label Operations**
- Delete label (with confirmation)
- Save label changes
- Validation feedback

**Keyboard Navigation** (Recent: PR #37)
- Arrow Up/Down: Navigate label list
- Home/End: Jump to first/last
- PageUp/PageDown: Navigate 10 items at a time
- Enter: Open selected label in editor
- Escape: Return focus to sidebar
- Visual focus indicators
- Auto-scroll to focused item

**Instance Browser** (Recent: PR #38)
- View actual nodes for selected label
- Instance count display
- Property values preview
- Pagination for large instance sets
- Link to node details

**Resizable Layout** (Recent: PR #38)
- Draggable divider between sidebar and editor
- Min/max width constraints (200px - 50%)
- Resize cursor indicator
- Persistent layout preferences

---

### 8. Links Page (`/links`)

**Link Definition Wizard**
- Multi-step wizard interface
- Link name input
- Data source selection:
  - CSV data source (paste CSV)
  - API endpoint source (URL + JSONPath)
  - Cypher query source (direct Neo4j query)
- Target label configuration
- Field mapping (source → target properties)
- Relationship type definition
- Relationship property mapping
- Preview sample links
- Save definition

**Link Management**
- List of saved definitions
- Select/view/edit definitions
- Delete definition (with confirmation)
- Duplicate definition names prevented

**Execution**
- Execute link button (per definition)
- Execution progress indicator
- Success message (# relationships created)
- Error handling and feedback

**Jobs & History**
- Link execution jobs list
- Job status (pending, running, completed, failed)
- View job details (logs, errors)
- Re-run failed jobs (if supported)

**Keyboard Navigation**
- Arrow Up/Down: Navigate link definitions
- Home/End: Jump to first/last
- PageUp/PageDown: Navigate 10 items at a time
- Enter: Open selected link in wizard
- Escape: Return focus to sidebar
- Visual focus indicators
- Auto-scroll to focused item

**Resizable Layout**
- Draggable divider between sidebar and wizard
- Min/max width constraints (200px - 50%)
- Matches Labels page structure
- Resize cursor indicator
- Highlight during resize

---

### 9. Extensions Page (`/extensions`)

**Plugin Management**
- View installed extensions
- Enable/disable extensions
- Extension metadata display
- Configuration options (per extension)

---

### 10. Integrations Page (`/integrations`)

**External Service Configuration**
- List of available integrations
- Configure integration settings
- Test connections
- Enable/disable integrations

---

### 11. Settings Page (`/settings`)

**Modular Settings Structure** (Recent: PR #43 - Template partials)
Settings organized into separate template files for maintainability:

**General Settings** (`_general.html`)
- Application-wide configurations
- Session timeout settings
- UI preferences

**Neo4j Configuration** (`_neo4j.html`)
- URI input (default: bolt://localhost:7687)
- Username input (default: neo4j)
- Database name input (default: neo4j)
- Password input with show/hide toggle
- Save settings button
- Connect/disconnect buttons
- Connection test with feedback
- Test graph operations button

**Interpreter Configuration** (`_interpreters.html`)
- List of available interpreters
- Enable/disable toggle per interpreter
- File extension associations display
- Advanced settings:
  - Suggest threshold input
  - Batch size input
- Save button for interpreter settings

**Rclone Mounts Configuration** (`_rclone.html`)
- Remote input field
- Subpath input field
- Mount name input
- Read-only checkbox
- Create mount button
- Mount list display
- Refresh mounts button
- Remove mount option

**Chat Settings** (`_chat.html`)
- Chat backend configuration
- LLM service settings
- Context settings

**Plugin Settings** (`_plugins.html`)
- Plugin-specific configurations
- Plugin enable/disable controls

**Integrations Settings** (`_integrations.html`)
- Integration service configurations
- API endpoint mappings:
  - Name, URL, Auth Method (None/Bearer/API Key)
  - Auth value (encrypted at rest)
  - JSONPath extraction
  - Maps to Label (optional)
  - Test connection button
  - Save endpoint button
- Encrypted credential storage
- Test endpoint connections

**Alerts Settings** (`_alerts.html`) (Recent: task:ops/monitoring/alert-system)
- Alert/notification system for critical events
- SMTP Configuration:
  - Host, port, username, password (encrypted)
  - From address, TLS toggle
  - Test email button
  - Save configuration
- Alert Definitions:
  - Pre-configured alerts:
    - Import Failed
    - High Discrepancies (threshold: 50)
    - Backup Failed
    - Neo4j Connection Lost
    - Disk Space Critical (threshold: 95%)
  - Enable/disable toggles
  - Recipient configuration (comma-separated emails)
  - Threshold adjustment (where applicable)
  - Test alert button (sends test notification)
  - Update button
- Alert History:
  - Recent alert trigger history
  - Success/failure status
  - Condition details
  - Timestamp tracking
- Backend integration:
  - Backup manager triggers backup_failed alerts
  - Extensible for scan/import, reconciliation, health checks
  - Alert trigger logging and tracking

**Configuration Backup/Restore** (Recent: PR #41)
- Export all settings to JSON
- Import settings from JSON backup
- Secure authentication for backup operations
- Validation on import
- Success/error feedback

---

### 12. Login Page (`/login`)

**Authentication** (Recent: PR #40)
- Username/password form
- Session creation
- Redirect to home after login
- Error handling

**Security Features**
- Password hashing (bcrypt)
- Session management
- CSRF protection
- Role-based permissions check

---

## Cross-Cutting Features

### Security & Access Control (Recent: PR #40)
- Multi-user authentication system
- Role-based access control (RBAC):
  - Admin: Full system access
  - User: Standard access to features
- Session-based authentication
- Password encryption (bcrypt)
- Database-persisted user accounts
- Permissions checks on endpoints
- Auto-lock after inactivity (PR #44)

### Data Cleaning (Recent: PR #46)
- Delete files from datasets (individual or bulk)
- Bidirectional relationship cleanup:
  - Remove File nodes
  - Remove associated relationships
  - Clean up orphaned link records
- Confirmation prompts
- Real-time UI updates
- Error handling and rollback

### Configuration Management (Recent: PR #41)
- Export/import all settings (JSON format)
- Backup and restore workflows
- Secure credential handling (encrypted at rest)
- Validation on import
- Test authentication before backup operations

### Session Management (Recent: PR #44)
- Configurable inactivity timeout
- Auto-lock and redirect to login
- Session expiration handling
- Persistent session state

### Template Modularization (Recent: PR #43)
- Settings page broken into template partials:
  - `_general.html`, `_neo4j.html`, `_interpreters.html`
  - `_rclone.html`, `_chat.html`, `_plugins.html`, `_integrations.html`
- Improved maintainability
- Easier to add new settings sections

---

## Technical Capabilities

### Data Sources
- Local filesystem scanning
- Rclone remote providers
- API endpoints (with auth: Bearer, API Key)
- CSV/JSON data import
- Direct Neo4j Cypher queries

### File Interpretation
- CSV (table preview)
- JSON (formatted tree)
- YAML (structured display)
- Python (syntax-highlighted)
- Jupyter notebooks
- Excel workbooks (multi-sheet)
- Generic text files
- Binary file handling (hex preview)

### Graph Database Integration
- Neo4j connection (Bolt protocol)
- Schema push/pull synchronization
- Node and relationship creation
- Cypher query execution
- Graph visualization
- Instance browsing

### Search & Indexing
- Full-text search (SQLite FTS)
- Extension-based filtering
- Interpreter-based filtering
- Path-based filtering
- Provider-based filtering
- Recursive/non-recursive scans

### Export & Integration
- CSV export (graph data)
- RO-Crate metadata export
- Arrows.app schema import/export
- Configuration backup/restore (JSON)
- API endpoint integration

---

## Architecture Notes

### Database Stack
- **SQLite**: File index, scan history, settings, chat history, user accounts
- **Neo4j**: Graph database (optional, for visualization and relationships)

### Frontend
- **Flask**: Python web framework
- **Jinja2**: Template engine (modular partials)
- **JavaScript**: Interactive UI (graph rendering, drag/drop, keyboard nav)

### Authentication
- **Flask-Login**: Session management
- **Bcrypt**: Password hashing
- **RBAC**: Role-based permissions

### Testing
- **Playwright E2E**: TypeScript tests (`e2e/*.spec.ts`)
- **Pytest**: Python unit/integration tests
- **98.3% interactive element coverage** (117/119 elements)

---

## Demo-Ready Features

### Critical Path Working
✅ Scan a folder (local filesystem)
✅ Browse scanned files
✅ View file interpretations
✅ Commit to Neo4j
✅ Visualize graph in Map
✅ Search files
✅ Chat interface (with multi-user support)

### Recent Improvements (Feb 2026)
✅ Multi-user authentication with RBAC (PR #40)
✅ Configuration backup/restore (PR #41)
✅ Modular settings templates (PR #43)
✅ Auto-lock after inactivity (PR #44)
✅ Data cleaning with bidirectional relationship management (PR #46)
✅ Three-column Labels layout with instance browser (PR #38)
✅ Comprehensive keyboard navigation (PR #37)

---

## Usage Patterns

### Common Workflows

**1. File Discovery & Interpretation**
Home → Files → Scan → Browse Snapshot → File Detail → View Interpretations

**2. Graph Visualization**
Settings → Connect Neo4j → Labels → Define Schema → Push to Neo4j → Files → Commit → Map → Visualize

**3. Schema Design with Arrows.app**
Arrows.app → Export JSON → Labels → Import → Edit/Refine → Push to Neo4j → Map

**4. Link Creation**
Labels → Define Labels → Links → Create Definition → Configure Source/Target → Preview → Execute → Map

**5. Search & Chat**
Home → Search Query → View Results → Chat → Ask Questions → Get Context-Aware Responses

**6. Data Cleaning**
Files → Browse Snapshot → Select Files → Delete (individual or bulk) → Confirm → Refresh

**7. Configuration Management**
Settings → Configure All Services → Export Settings → (Later) Import Settings to Restore

---

## Known Limitations

- Scans are synchronous (page waits for completion)
- Very large files (>10MB) may have limited preview
- Chat requires external LLM service (if not configured)
- Map rendering slows with 1000+ nodes
- Rclone features require rclone installed on system

---

## References

- **UX Testing Checklist**: `dev/ux-testing-checklist.md`
- **Demo Setup Guide**: `DEMO_SETUP.md`
- **Dev Protocols**: `dev/README-planning.md`
- **E2E Testing Guide**: `docs/e2e-testing.md`
- **Test Coverage Index**: `dev/test-coverage-index.md`
