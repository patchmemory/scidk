# Demo Setup Guide

This guide explains how to set up and manage demo data for SciDK demonstrations and testing.

## Overview

SciDK includes a demo data seeding script (`scripts/seed_demo_data.py`) that creates a consistent set of sample data for demos and testing. This ensures every demo starts with the same baseline data.

## Quick Start

### Basic Demo Setup

```bash
# Seed demo data (preserves existing data)
python scripts/seed_demo_data.py

# Clean and reseed all data
python scripts/seed_demo_data.py --reset
```

### With Neo4j Graph Sync

```bash
# Seed with Neo4j labels and relationships
python scripts/seed_demo_data.py --neo4j --reset
```

## What Gets Created

### 👥 Demo Users

Three demo users are created with password `demo123`:

| Username | Password | Role | Use Case |
|----------|----------|------|----------|
| `admin` | `demo123` | Admin | Full system access, user management |
| `facility_staff` | `demo123` | User | Core facility operations |
| `billing_team` | `demo123` | User | Billing reconciliation workflows |

### 📁 Sample Files

Sample files are created in the `demo_data/` directory:

```
demo_data/
├── Project_A_Cancer_Research/
│   ├── experiments/
│   │   ├── exp001_cell_culture.xlsx
│   │   └── exp002_drug_treatment.xlsx
│   ├── results/
│   │   ├── microscopy/
│   │   │   ├── sample_001.tif
│   │   │   └── sample_002.tif
│   │   └── flow_cytometry/
│   │       └── analysis_20240115.fcs
│   ├── protocols/
│   │   └── cell_culture_protocol.pdf
│   └── README.md
├── Project_B_Proteomics/
│   ├── raw_data/
│   │   ├── mass_spec_run001.raw
│   │   └── mass_spec_run002.raw
│   ├── analysis/
│   │   ├── protein_identification.xlsx
│   │   └── go_enrichment.csv
│   ├── figures/
│   │   └── volcano_plot.png
│   └── README.md
└── Core_Facility_Equipment/
    ├── equipment_logs/
    │   ├── confocal_microscope_2024.xlsx
    │   └── flow_cytometer_2024.xlsx
    ├── maintenance/
    │   └── service_records.pdf
    ├── training/
    │   └── microscopy_training_slides.pdf
    └── README.md
```

### 🏷️ Sample Labels (Neo4j)

When run with `--neo4j` flag, the following labels are created:

**Projects**:
- Cancer Research - Project A (PI: Dr. Alice Smith)
- Proteomics Study - Project B (PI: Dr. Bob Jones)
- Core Facility Operations (PI: Dr. Carol Williams)

**Researchers**:
- Dr. Alice Smith (Oncology)
- Dr. Bob Jones (Biochemistry)
- Dr. Carol Williams (Core Facilities)

**Equipment**:
- Confocal Microscope LSM 880 (Microscopy Core)
- Flow Cytometer BD FACS Aria III (Flow Cytometry Core)
- Mass Spectrometer Orbitrap Fusion (Proteomics Core)

### 🔗 Sample Relationships

- Dr. Alice Smith → LEADS → Cancer Research - Project A
- Dr. Bob Jones → LEADS → Proteomics Study - Project B
- Dr. Carol Williams → MANAGES → Core Facility Operations

### 🧪 iLab Data (if plugin installed)

If the iLab Data Importer plugin is installed, sample iLab export files are copied to `demo_data/iLab_Exports/`:
- `ilab_equipment_sample.csv`
- `ilab_services_sample.csv`
- `ilab_pi_directory_sample.csv`

## Usage Scenarios

### Scenario 1: Fresh Demo Environment

Use this when setting up a new demo instance:

```bash
# Clean everything and start fresh
python scripts/seed_demo_data.py --reset --neo4j

# Start SciDK
python start.sh

# Login as admin / demo123
```

### Scenario 2: Preserving Existing Work

Use this to add demo data without deleting existing work:

```bash
# Add demo data alongside existing data
python scripts/seed_demo_data.py
```

### Scenario 3: Resetting After a Demo

Use this to clean up after a demo and prepare for the next one:

```bash
# Clean and reseed
python scripts/seed_demo_data.py --reset --neo4j
```

### Scenario 4: Testing Without Neo4j

Use this for quick testing without Neo4j graph sync:

```bash
# Seed users and files only
python scripts/seed_demo_data.py --reset
```

## Command-Line Options

### `--reset`

Cleans all existing demo data before seeding:
- Deletes demo users (admin, facility_staff, billing_team)
- Clears active sessions
- Removes demo labels from Neo4j (if `--neo4j` is used)
- Deletes `demo_data/` directory

**Use with caution**: This will delete data!

### `--neo4j`

Enables Neo4j graph database seeding:
- Creates sample labels (Projects, Researchers, Equipment)
- Creates sample relationships between entities
- All demo entities are tagged with `source: 'demo'` for easy cleanup

Requires Neo4j to be configured and running.

### `--db-path TEXT`

Specify custom path to settings database (default: `scidk_settings.db`).

### `--pix-path TEXT`

Specify custom path to path index database (default: `data/path_index.db`).

## Idempotency

The seeding script is designed to be idempotent:
- **Users**: Existing users are not overwritten
- **Files**: Existing files are not overwritten
- **Labels**: When using `--reset`, labels are cleaned first

Run the script multiple times without `--reset` to safely add demo data without affecting existing work.

## Demo Workflow

### Before a Demo

1. Clean and reseed data:
   ```bash
   python scripts/seed_demo_data.py --reset --neo4j
   ```

2. Start SciDK:
   ```bash
   python start.sh
   ```

3. Verify demo users work:
   - Login as `admin / demo123`
   - Verify `demo_data/` directory exists

4. (Optional) Run a file scan:
   ```bash
   # In SciDK UI: Files > Scan Directory > demo_data/
   ```

### During a Demo

Use the demo users to showcase different workflows:

- **Admin user**: Show user management, settings, backups
- **Facility staff**: Show equipment logging, file scanning
- **Billing team**: Show iLab reconciliation (if plugin installed)

### After a Demo

Clean up for the next demo:
```bash
python scripts/seed_demo_data.py --reset --neo4j
```

## Customizing Demo Data

### Adding Custom Files

1. Create files in `demo_data/` directory
2. Modify `seed_sample_files()` function in `scripts/seed_demo_data.py`
3. Re-run the script

### Adding Custom Labels

1. Modify `seed_labels()` function in `scripts/seed_demo_data.py`
2. Add your custom Cypher queries
3. Re-run with `--neo4j` flag

### Adding Custom Users

1. Modify `seed_users()` function in `scripts/seed_demo_data.py`
2. Add user tuples: `(username, password, role)`
3. Re-run the script

## Troubleshooting

### Problem: Users already exist

**Solution**: This is expected behavior. Existing users are not overwritten unless you use `--reset`.

### Problem: Neo4j connection fails

**Solution**:
1. Check Neo4j is running: `systemctl status neo4j` or check Docker
2. Verify connection settings in `scidk.config.yml`
3. Try without `--neo4j` flag for file/user seeding only

### Problem: Permission denied on demo_data/

**Solution**: Ensure you have write permissions in the SciDK directory.

### Problem: iLab files not created

**Solution**: The iLab plugin must be installed at `plugins/ilab_table_loader/`. If not installed, iLab seeding is skipped automatically.

### Problem: Script fails with import error

**Solution**: Make sure you're running from the SciDK root directory and all dependencies are installed:
```bash
pip install -r requirements.txt
```

## Integration with Testing

The demo data script can be used in automated tests:

```python
import subprocess

def setup_test_environment():
    """Set up test environment with demo data."""
    subprocess.run(['python', 'scripts/seed_demo_data.py', '--reset'])

def test_demo_users_exist():
    """Test that demo users were created."""
    from scidk.core.auth import AuthManager
    auth = AuthManager()
    admin = auth.get_user_by_username('admin')
    assert admin is not None
    assert admin['role'] == 'admin'
```

## Data Structure Reference

### User Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access: user management, settings, backups, all features |
| `user` | Standard access: file scanning, labels, integrations (no user management) |

### Demo Data Tagging

All demo entities in Neo4j are tagged with `source: 'demo'` for easy identification and cleanup:

```cypher
// Find all demo nodes
MATCH (n {source: 'demo'}) RETURN n

// Delete all demo data
MATCH (n {source: 'demo'}) DETACH DELETE n
```

### File Organization

Demo files follow a consistent structure:
- **Project directories**: Top-level organization by project
- **Subdirectories**: Organized by data type (raw_data, analysis, results, etc.)
- **README files**: Every project has a README describing its purpose

## See Also

- [Authentication Documentation](AUTHENTICATION.md)
- [Plugin System](plugins/README.md)
- [iLab Importer Plugin](plugins/ILAB_IMPORTER.md)
- [Neo4j Integration](GRAPH_INTEGRATION.md)

## Support

For issues with demo data seeding:
1. Check the troubleshooting section above
2. Review script output for error messages
3. Check SciDK logs for detailed error information
4. File an issue on the project repository

---

**Last Updated**: 2026-02-10
