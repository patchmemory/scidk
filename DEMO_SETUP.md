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
| **Home** | `/` | Landing page, search, filters |
| **Chat** | `/chat` | Chat interface |
| **Files** | `/datasets` | Browse files, scans, snapshots |
| **Map** | `/map` | Graph visualization |
| **Labels** | `/labels` | Graph schema management |
| **Links** | `/links` | Link definition wizard |
| **Settings** | `/settings` | Neo4j, interpreters, rclone |

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

### Workflow 4: Link Creation

1. **Navigate** to Links page
2. **Create** new link definition
3. **Choose** data source (CSV, API, or Cypher)
4. **Configure** source and target labels
5. **Preview** link results
6. **Execute** link to create relationships
7. **View** in Map

### Workflow 5: Search & Chat

1. **Home page**: Enter search query
2. **View** results filtered by type
3. **Navigate** to Chat page
4. **Ask** about indexed files
5. **Get** responses with file references

## Configuration for Demo

### Neo4j Connection

1. Navigate to **Settings** page
2. Enter Neo4j details:
   - URI: `bolt://localhost:7687`
   - Username: `neo4j`
   - Database: `neo4j`
   - Password: `[your password]`
3. Click **"Save Settings"**
4. Click **"Connect"** to test

### Interpreter Configuration

1. On **Settings** page, scroll to "Interpreters"
2. Enable desired interpreters:
   - CSV, JSON, YAML (common formats)
   - Python, Jupyter (code files)
   - Excel (workbooks)
3. Changes save automatically

### Rclone Mounts (Optional)

1. On **Settings** page, scroll to "Rclone Mounts"
2. Configure remote:
   - Remote: `myremote:`
   - Subpath: `/folder/path`
   - Name: `MyRemote`
   - Read-only: checked (recommended for demo)
3. Click **"Create Mount"**

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

- **Start at Home**: Show search and summary cards
- **Show Files workflow**: Browse → Detail → Interpretation
- **Demonstrate Graph**: Map visualization with filters
- **Highlight Schema**: Show Labels and relationships
- **Show Link Creation**: Quick wizard walkthrough
- **End with Chat**: Ask questions about the data

### Known Limitations (to mention if asked)

- Scans are synchronous (page waits for completion)
- Very large files (>10MB) may have limited preview
- Chat requires external LLM service (if not configured)
- Map rendering slows with 1000+ nodes
- Rclone features require rclone installed

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
