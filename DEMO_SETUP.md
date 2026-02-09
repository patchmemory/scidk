# SciDK Demo Setup Guide

Quick reference for running and testing the SciDK application.

## Prerequisites

- Python 3.9+ installed
- Node.js (for E2E tests)
- Docker (for Neo4j, optional but recommended)
- Rclone (optional, for remote provider testing)

## Quick Start

### 1. Start Neo4j (Optional but Recommended)

```bash
# Start Neo4j in Docker
docker-compose -f docker-compose.neo4j.yml up -d

# Neo4j will be available at:
# - Browser: http://localhost:7474
# - Bolt: bolt://localhost:7687
# - Default credentials: neo4j / your-password-here
```

### 2. Activate Python Environment

```bash
# Activate virtual environment
source .venv/bin/activate

# Or on some systems:
. .venv/bin/activate

# Verify activation (should show .venv path)
which python
```

### 3. Start the Application

```bash
# RECOMMENDED: Use the scidk-serve command
scidk-serve

# Alternative: Run as module (also works after the fix)
python -m scidk

# Server starts at: http://127.0.0.1:5000
```

**Note**: Use `scidk-serve` or `python -m scidk` (not `python -m scidk.app`) to avoid import path issues with test stubs.

### 4. Access the Application

Open your browser and navigate to: **http://127.0.0.1:5000**

## Page Navigation Quick Reference

| Page | URL | Purpose |
|------|-----|---------|
| **Home** | `/` | Landing page, search, filters, quick chat |
| **Chat** | `/chat` | Full chat interface (multi-user) |
| **Files** | `/datasets` | Browse files, scans, snapshots, data cleaning |
| **Map** | `/map` | Graph visualization (Neo4j + local schema) |
| **Labels** | `/labels` | Graph schema management (3-column layout) |
| **Links** | `/links` | Link definition wizard |
| **Extensions** | `/extensions` | Plugin/extension management |
| **Integrations** | `/integrations` | External service integrations |
| **Settings** | `/settings` | Neo4j, interpreters, rclone, chat, plugins |
| **Login** | `/login` | User authentication |

## Creating Test Data

### Option 1: Scan Local Directory

1. Navigate to **Files** page (`/datasets`)
2. Select "Provider Browser" tab
3. Choose provider: `filesystem`
4. Select or enter a directory path (e.g., `/home/user/Documents`)
5. Check "Recursive" if needed
6. Click **"Go"** to browse
7. Click **"Scan"** to index files

### Option 2: Use Test Data Script

```bash
# Run a test scan on the project itself
python -c "
from scidk.core import filesystem
from scidk.app import create_app

app = create_app()
with app.app_context():
    ext = app.extensions['scidk']
    # Scan the docs folder
    result = ext['graph'].scan_source(
        provider='filesystem',
        root_id='/',
        path='docs',
        recursive=True
    )
    print(f'Scanned {len(result.get(\"checksums\", []))} files')
"
```

### Option 3: Use Existing Test Fixtures

The test suite creates temporary test data. You can reference `tests/conftest.py` for fixture patterns.

## Common Demo Workflows

### Workflow 1: File Discovery & Viewing

1. **Scan** a directory (Files page)
2. **Browse** snapshot results
3. **Click** on a file to view details
4. **View** interpretations (CSV table, JSON tree, etc.)
5. **Navigate** back to files list

### Workflow 2: Graph Visualization

#### Option A: Using Local Labels
1. **Navigate** to Labels page (`/labels`)
2. **Create** a new label (e.g., "Project")
3. **Add** properties (e.g., name: string, budget: number)
4. **Define** relationships (e.g., "HAS_FILE" → File)
5. **Save** the label
6. **Navigate** to Map page (`/map`)
7. **Select** "Local Labels" from Source dropdown
8. **View** schema visualization (nodes appear in red = definition only, no instances)
9. **Observe** relationships shown as edges

#### Option B: Using Neo4j Schema
1. **Navigate** to Settings (`/settings`)
2. **Connect** to Neo4j (configure URI, username, password)
3. **Test** connection to verify it works
4. **Navigate** to Labels page (`/labels`)
5. **Click** "Pull from Neo4j" to sync schema
6. **Navigate** to Map page (`/map`)
7. **Select** "Neo4j Schema" from Source dropdown
8. **View** schema pulled from database (nodes in green)

#### Option C: Combined View (Default)
1. **Scan** files and commit to Neo4j (Files page)
2. **Navigate** to Map page (`/map`)
3. **Source** defaults to "All Sources"
4. **View** combined graph with color-coded nodes:
   - **Blue**: In-memory graph (actual scanned data)
   - **Red**: Local labels (definitions only, no instances)
   - **Green**: Neo4j schema (pulled from database)
   - **Orange/Purple/Teal/Yellow**: Mixed sources
5. **Filter** by labels/relationships (dropdowns populate dynamically)
6. **Adjust** layout and appearance
7. **Interact** with nodes (click, drag)

### Workflow 3: Schema Management

1. **Navigate** to Labels page
2. **Create** a new label (e.g., "Dataset")
3. **Add** properties (e.g., name: string, size: int)
4. **Define** relationships (e.g., "HAS_FILE")
5. **Push** schema to Neo4j

#### Import/Export with Arrows.app

**Import from Arrows.app:**
1. Design schema at https://arrows.app
2. Export JSON from Arrows (File → Export → JSON)
3. In scidk, navigate to Labels page
4. Click "Import from Arrows.app"
5. Paste JSON or upload file
6. Click "Import" to create labels

**Export to Arrows.app:**
1. Navigate to Labels page
2. Click "Export to Arrows.app"
3. Download JSON file
4. Open https://arrows.app
5. Import file (File → Import → From JSON)
6. View/edit schema in Arrows

### Workflow 4: Integration & Link Creation

**Option A: Configure External API Integration**
1. **Navigate** to Integrations page (`/integrations`)
2. **Configure** external service (API endpoint, auth)
3. **Test** connection to verify it works
4. **Save** integration configuration
5. **Navigate** to Links page to use the integration

**Option B: Direct Link Creation**
1. **Navigate** to Links page (`/links`)
2. **Create** new link definition
3. **Choose** data source (CSV, API, or Cypher)
4. **Configure** source and target labels
5. **Preview** link results
6. **Execute** link to create relationships
7. **View** in Map

### Workflow 5: Search & Chat

**Quick Chat (from Home):**
1. **Home page**: Enter search query OR use quick chat input
2. **View** results filtered by type
3. **Get** inline responses without leaving home

**Full Chat Interface:**
1. **Navigate** to Chat page (`/chat`)
2. **Login** if using multi-user mode
3. **Ask** questions about indexed files
4. **Get** context-aware responses with file references
5. **View** conversation history (persisted per user)

### Workflow 6: Data Cleaning

1. **Navigate** to Files page (`/datasets`)
2. **Browse** snapshot or search for files
3. **Select** files to delete (individual or bulk)
4. **Click** delete button
5. **Confirm** deletion
6. **System** automatically cleans up:
   - File nodes from graph
   - Associated relationships
   - Orphaned link records
7. **View** updated file list

## Configuration for Demo

### First-Time Setup: User Authentication

1. **Navigate** to Login page (`/login`) - or you'll be redirected on first visit
2. **Create** an account (if no users exist, first user becomes admin)
3. **Login** with username/password
4. **Note**: Multi-user mode supports:
   - Role-based access control (Admin/User)
   - Per-user chat history
   - Session management with auto-lock after inactivity

### Neo4j Connection

1. Navigate to **Settings** page (`/settings`)
2. Click **"Neo4j"** tab in settings
3. Enter Neo4j details:
   - URI: `bolt://localhost:7687`
   - Username: `neo4j`
   - Database: `neo4j`
   - Password: `[your password]`
4. Click **"Save Settings"**
5. Click **"Connect"** to test connection
6. Success message confirms connection

### Interpreter Configuration

1. On **Settings** page, click **"Interpreters"** tab
2. Enable desired interpreters:
   - CSV, JSON, YAML (common formats)
   - Python, Jupyter (code files)
   - Excel (workbooks)
3. Configure advanced settings:
   - Suggest threshold
   - Batch size
4. Click **"Save"** to apply changes

### Rclone Mounts (Optional)

1. On **Settings** page, click **"Rclone"** tab
2. Configure remote:
   - Remote: `myremote:`
   - Subpath: `/folder/path`
   - Name: `MyRemote`
   - Read-only: checked (recommended for demo)
3. Click **"Create Mount"**
4. Click **"Refresh Mounts"** to see updated list

### Chat Backend Configuration

1. On **Settings** page, click **"Chat"** tab
2. Configure chat backend:
   - LLM service endpoint
   - API key (if required)
   - Context settings
3. Click **"Save Settings"**
4. Test by sending a message from Home or Chat page

### External Service Integrations

1. Navigate to **Integrations** page (`/integrations`)
2. Select an integration to configure
3. Enter service-specific settings:
   - API endpoint URL
   - Authentication credentials (encrypted at rest)
   - JSONPath extraction (optional)
   - Target label mapping (optional)
4. Click **"Test Connection"** to verify
5. Click **"Save"** to enable integration

**OR** configure in Settings:
1. On **Settings** page, click **"Integrations"** tab
2. Scroll to "API Endpoint Mappings"
3. Configure endpoint:
   - **Name**: Descriptive name (e.g., "Users API")
   - **URL**: Full API endpoint (e.g., `https://api.example.com/users`)
   - **Auth Method**: None, Bearer Token, or API Key
   - **Auth Value**: Token/key if authentication required
   - **JSONPath**: Extract specific data (e.g., `$.data[*]`)
   - **Maps to Label**: Target label for imported data
4. Click **"Test Connection"** to verify
5. Click **"Save Endpoint"** to register

**Using Integrations in Links:**
- Registered endpoints appear in Links wizard
- Select an endpoint as a data source
- Field mappings auto-populate from endpoint config

**Security Notes:**
- Auth tokens encrypted at rest in settings database
- Set `SCIDK_API_ENCRYPTION_KEY` environment variable for production
- Without this variable, ephemeral key is generated (not persistent across restarts)

**Example: JSONPlaceholder Test API**
```
Name: JSONPlaceholder Users
URL: https://jsonplaceholder.typicode.com/users
Auth Method: None
JSONPath: $[*]
Maps to Label: User
```

### Configuration Backup & Restore

1. On **Settings** page, click **"General"** tab
2. Scroll to "Configuration Management"
3. **Export** settings:
   - Click **"Export Settings"**
   - Download JSON backup file
4. **Import** settings:
   - Click **"Import Settings"**
   - Select JSON backup file
   - Confirm import
   - Application restores all configurations

## Troubleshooting

### Application Won't Start

```bash
# Check if port 5000 is already in use
lsof -i :5000

# Use a different port
SCIDK_PORT=5001 scidk-serve
```

### Neo4j Connection Fails (502 Error)

**If you get a 502 error when connecting to Neo4j:**
- Make sure you're using `scidk-serve` or `python -m scidk` (not `python -m scidk.app`)
- The issue is caused by a local test stub shadowing the real neo4j package
- See "Technical Note: Import Path Issue" below for details

**Other Neo4j issues:**
- Verify Neo4j is running: `docker ps | grep neo4j`
- Check credentials match Settings page
- Ensure bolt port 7687 is accessible
- Check logs: `docker logs <neo4j-container-id>`

### No Files Showing

- Verify scan completed successfully
- Check database file exists: `ls -la *.db`
- Check console for errors
- Try scanning a small directory first

### Interpreter Not Working

- Verify interpreter enabled in Settings
- Check file extension matches interpreter
- Review Python console for import errors
- Ensure required packages installed (see `requirements.txt`)

### Map Page Empty

- Ensure Neo4j connected (Settings page)
- Verify schema committed (Labels page → Push to Neo4j)
- Verify files committed (Files page → Commit button)
- Check Neo4j browser: http://localhost:7474

## Demo Tips

### Before the Demo

- [ ] Start Neo4j before application
- [ ] Clear test/sensitive data from database
- [ ] Prepare interesting dataset (variety of file types)
- [ ] Pre-scan dataset so demo isn't waiting for scan
- [ ] Test Neo4j connection in Settings
- [ ] Have 2-3 example questions ready for Chat

### During the Demo

**Suggested Demo Flow:**
1. **Login**: Show authentication (multi-user support)
2. **Home Page**:
   - Demonstrate search with filters
   - Show summary cards (file count, scan count, extensions)
   - Try quick chat input (inline responses)
3. **Files Workflow**:
   - Browse → Scan → Snapshot → File Detail → Interpretation
   - Show data cleaning (delete files, auto-cleanup relationships)
4. **Labels Page**:
   - Show 3-column layout (list, editor, instance browser)
   - Create/edit label with properties
   - Define relationships
   - Show keyboard navigation (arrow keys, Enter, Escape)
   - Push schema to Neo4j
5. **Map Visualization**:
   - Show combined view (in-memory + local labels + Neo4j schema)
   - Demonstrate filters (labels, relationships)
   - Show color-coding (blue/red/green for different sources)
   - Adjust layout and appearance controls
6. **Integrations**:
   - Configure external API endpoint
   - Test connection
   - Show encrypted credential storage
7. **Links Creation**:
   - Quick wizard walkthrough
   - Use configured integration as data source
   - Preview and execute to create relationships
8. **Chat Interface**:
   - Ask context-aware questions about indexed files
   - Show conversation history (persisted per user)
   - Demonstrate file references in responses
9. **Settings**:
   - Show modular settings tabs (Neo4j, Interpreters, Rclone, Chat, etc.)
   - Demonstrate configuration backup/restore

### Known Limitations (to mention if asked)

- Scans are synchronous (page waits for completion)
- Very large files (>10MB) may have limited preview
- Chat requires external LLM service configuration
- Map rendering slows with 1000+ nodes
- Rclone features require rclone installed on system
- Session auto-locks after inactivity (configurable timeout)

## Testing the Application

### Run E2E Tests

```bash
# Ensure app is running on http://127.0.0.1:5000

# In a separate terminal:
npm run e2e
```

### Run Unit Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_scan_browse_indexed.py

# With coverage report
python -m coverage run -m pytest tests/
python -m coverage report
```

### Manual Testing

See **`dev/ux-testing-checklist.md`** for comprehensive page-by-page testing guide.

## Stopping the Application

### Stop Flask

Press `Ctrl+C` in the terminal running the Flask app

### Stop Neo4j

```bash
docker-compose -f docker-compose.neo4j.yml down
```

### Deactivate Python Environment

```bash
deactivate
```

## Environment Files

The application uses `.env` files for configuration:

- `.env` - Default/development settings (in use)
- `.env.example` - Template with all options
- `.env.dev`, `.env.beta`, `.env.stable` - Environment-specific

To switch environments:
```bash
cp .env.dev .env  # Use dev settings
```

## Database Files

SciDK uses SQLite databases:

- `scidk_path_index.db` - File index and scan history
- `scidk_settings.db` - Application settings (Neo4j, interpreters)
- `data/files.db` - Legacy/alternative file storage (if used)

To reset data:
```bash
# Backup first!
cp scidk_path_index.db scidk_path_index.db.backup

# Remove databases to start fresh
rm scidk_path_index.db scidk_settings.db

# Restart app (will recreate with schema)
python -m scidk.app
```

## Additional Resources

- **Feature Index**: `FEATURE_INDEX.md` (comprehensive feature list by page)
- **Development Protocols**: `dev/README-planning.md`
- **UX Testing Checklist**: `dev/ux-testing-checklist.md`
- **E2E Testing Guide**: `docs/e2e-testing.md`
- **API Documentation**: `docs/MVP_Architecture_Overview_REVISED.md`
- **Main README**: `README.md`

## Quick Commands Reference

```bash
# Start everything for demo
docker-compose -f docker-compose.neo4j.yml up -d  # Neo4j
source .venv/bin/activate                           # Python env
scidk-serve                                          # Flask app (RECOMMENDED)

# Run tests
npm run e2e          # E2E tests
pytest tests/        # Unit tests

# Check coverage
python -m coverage run -m pytest tests/
python -m coverage report
python -m coverage html  # HTML report in htmlcov/

# Stop everything
# Ctrl+C in Flask terminal
docker-compose -f docker-compose.neo4j.yml down
deactivate
```

---

## Technical Note: Import Path Issue

**Why use `scidk-serve` instead of `python -m scidk.app`?**

The repository contains a `neo4j/` directory with a test stub (`neo4j/__init__.py`) used for mocking in tests. When you run `python -m scidk.app`, Python adds the current directory to `sys.path[0]`, causing the local stub to shadow the real `neo4j` package from `.venv/lib/python3.x/site-packages/`. This results in:

- **Error**: `type object 'GraphDatabase' has no attribute 'driver'`
- **HTTP 502** when trying to connect to Neo4j in Settings

**Solutions** (in order of preference):
1. ✅ **Use `scidk-serve`** - Entry point doesn't add cwd to sys.path
2. ✅ **Use `python -m scidk`** - Now includes `__main__.py` that removes cwd from path
3. ❌ **Don't use `python -m scidk.app`** - Adds cwd to sys.path (causes issue)

The fix has been implemented with:
- `scidk/__main__.py` - Removes cwd from sys.path before importing
- `pyproject.toml` - Excludes `neo4j*` from package builds
- `.gitignore` - Documents the stub's purpose

**For developers**: The `neo4j/` stub should remain for test compatibility, but runtime execution should use methods 1 or 2 above.

---

**Ready to demo!** Follow the workflows above and refer to `dev/ux-testing-checklist.md` for detailed testing.
