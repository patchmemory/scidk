# SciDK Quickstart: Fresh Install to First RO-Crate

**Goal**: Get from zero to your first RO-Crate in under 30 minutes.

**Prerequisites**: Python 3.10+, git, and 5 minutes.

---

## 1. Install (5 minutes)

```bash
# Clone the repository
git clone https://github.com/yourusername/scidk.git
cd scidk

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # bash/zsh
# or: source .venv/bin/activate.fish  # fish shell

# Install SciDK in editable mode
pip install -e .

# Initialize environment (optional but recommended)
source scripts/init_env.sh
```

**Verify installation**:
```bash
scidk-serve --help
# Should show: usage: scidk-serve ...
```

---

## 2. Start the Server (1 minute)

```bash
# Start SciDK
scidk-serve
# or: python3 -m scidk.app
```

Server starts at: **http://127.0.0.1:5000**

Open in your browser and you should see the SciDK home page.

---

## 3. Scan Your First Directory (3 minutes)

### Via UI:
1. Navigate to **Files** page (http://127.0.0.1:5000/datasets)
2. Select provider: **Local Filesystem**
3. Enter a path (e.g., `/home/user/Documents` or use the repository root)
4. Check "Recursive" if you want subdirectories
5. Click **Scan Files**
6. Wait for scan to complete (progress shown in Background Tasks)

### Via API (alternative):
```bash
curl -X POST http://127.0.0.1:5000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/your/data", "recursive": true}'
```

---

## 4. Browse Scanned Files (2 minutes)

After scanning completes:

1. **Files page** shows all discovered datasets
2. Click any dataset to see details:
   - File metadata (size, type, timestamps)
   - Interpreted content (for Python, CSV, JSON, YAML, IPYNB, XLSX)
   - Import dependencies (for code files)

**API alternative**:
```bash
# List all scanned datasets
curl http://127.0.0.1:5000/api/datasets

# Get specific dataset details
curl http://127.0.0.1:5000/api/datasets/<dataset-id>
```

---

## 5. Select Files for RO-Crate (5 minutes)

Currently manual selection via browsing. For programmatic selection:

```bash
# Use search to find specific file types
curl "http://127.0.0.1:5000/api/search?q=csv"

# Filter by interpreter
curl "http://127.0.0.1:5000/api/search?q=python_code"
```

Mark interesting datasets mentally or via notes—RO-Crate packaging is next.

---

## 6. Create RO-Crate (5 minutes)

### Quick RO-Crate Generation:

For a scanned directory, generate a minimal RO-Crate:

```bash
# Generate RO-Crate JSON-LD for a directory
curl "http://127.0.0.1:5000/api/rocrate?path=/path/to/scanned/dir" > ro-crate-metadata.json
```

The RO-Crate will include:
- Root Dataset entity
- File/Folder entities (depth=1 by default)
- Contextual metadata per RO-Crate spec

### Via UI (if viewer embedding is enabled):
1. Set environment variable: `export SCIDK_FILES_VIEWER=rocrate`
2. Restart server
3. Files page will show **"Open in RO-Crate Viewer"** button
4. Click to view embedded crate metadata

---

## 7. Export RO-Crate as ZIP (5 minutes)

Create a complete RO-Crate package with data files:

```bash
# Using demo script (recommended)
./scripts/demo_rocrate_export.sh /path/to/scanned/dir ./my-crate.zip

# Manual steps:
# 1. Generate ro-crate-metadata.json (step 6)
# 2. Copy data files into crate directory
# 3. Zip the complete package
mkdir -p my-crate
curl "http://127.0.0.1:5000/api/rocrate?path=/path/to/dir" > my-crate/ro-crate-metadata.json
cp -r /path/to/dir/* my-crate/
zip -r my-crate.zip my-crate/
```

**Result**: `my-crate.zip` is a valid RO-Crate package containing:
- `ro-crate-metadata.json` (JSON-LD metadata)
- Data files from your scanned directory

---

## Verify Your RO-Crate (2 minutes)

```bash
# Unzip and inspect
unzip -l my-crate.zip
cat my-crate/ro-crate-metadata.json | jq '.@graph[] | select(.["@type"] == "Dataset")'

# Validate with ro-crate-py (optional)
pip install rocrate
python3 -c "from rocrate.rocrate import ROCrate; c = ROCrate('my-crate'); print(c.root_dataset)"
```

---

## Troubleshooting

### Port already in use
```bash
# Check what's using port 5000
lsof -i :5000

# Change port
export SCIDK_PORT=5001
scidk-serve
```

### Scan not finding files
- Verify the path exists and is readable
- Check recursive flag if scanning subdirectories
- Install `ncdu` for faster scanning: `brew install ncdu` (macOS) or `sudo apt install ncdu` (Linux)

### RO-Crate endpoint returns 404
- Ensure you're running the latest code from main branch
- Check that `/api/rocrate` endpoint is implemented (planned for v0.1.0)
- See `dev/features/ui/feature-rocrate-viewer-embedding.md` for implementation status

---

## Next Steps

**Explore more features**:
- **Map page** (http://127.0.0.1:5000/map): Visualize knowledge graph schema
- **Labels & Links**: Annotate files with custom labels and relationships
- **Providers**: Connect remote sources via rclone (S3, Google Drive, etc.)
- **Neo4j**: Enable persistent graph storage (see README § Neo4j integration)

**Documentation**:
- Full README: `/README.md`
- Development workflow: `dev/README-planning.md`
- RO-Crate feature spec: `dev/features/ui/feature-rocrate-viewer-embedding.md`

**Community**:
- Report issues: https://github.com/yourusername/scidk/issues
- Contributing: `CONTRIBUTING.md`

---

**Total time**: ~25 minutes from clone to packaged RO-Crate

**You're ready!** You've now:
- ✅ Installed SciDK
- ✅ Scanned a directory
- ✅ Browsed files and metadata
- ✅ Generated RO-Crate JSON-LD
- ✅ Exported a complete RO-Crate ZIP package

Happy crate-ing! 🎉
