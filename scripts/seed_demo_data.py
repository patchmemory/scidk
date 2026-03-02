#!/usr/bin/env python3
"""Seed demo data for SciDK testing and demonstrations.

This script creates a consistent set of demo data including:
- Demo users (admin, facility_staff, billing_team)
- Sample files in demo_data directory
- Sample labels (Projects, Samples, Researchers, Equipment)
- Sample links (relationships between entities)
- Sample iLab data (if iLab plugin is installed)

The script can be run multiple times idempotently and supports
a --reset flag to clean all data first.
"""

import click
import os
import sys
import time
import shutil
import sqlite3
from pathlib import Path

# Add parent directory to path so we can import scidk
sys.path.insert(0, str(Path(__file__).parent.parent))

from scidk.core.auth import AuthManager
from scidk.core import path_index_sqlite as pix


@click.command()
@click.option('--reset', is_flag=True, help='Clean all existing data first')
@click.option('--db-path', default='scidk_settings.db', help='Path to settings database')
@click.option('--pix-path', default='data/path_index.db', help='Path to path index database')
@click.option('--neo4j', is_flag=True, help='Also seed Neo4j graph database')
def seed_demo_data(reset, db_path, pix_path, neo4j):
    """Seed demo data for testing and demonstrations.

    Creates a consistent set of sample users, files, labels, and relationships
    that can be used for demos and testing.

    Examples:
        # Seed data (preserving existing data)
        python scripts/seed_demo_data.py

        # Clean and reseed all data
        python scripts/seed_demo_data.py --reset

        # Seed with Neo4j graph sync
        python scripts/seed_demo_data.py --neo4j
    """
    print("🌱 SciDK Demo Data Seeder")
    print("=" * 60)

    if reset:
        print("\n⚠️  Reset mode: Cleaning existing data...")
        clean_demo_data(db_path, pix_path, neo4j)
        print("✓ Existing data cleaned")

    # Create demo data directory
    demo_data_dir = Path('demo_data')
    demo_data_dir.mkdir(exist_ok=True)

    # Seed users
    print("\n👥 Creating demo users...")
    auth = AuthManager(db_path)
    users_created = seed_users(auth)
    print(f"✓ Created {users_created} demo users")

    # Seed sample files
    print("\n📁 Creating sample files...")
    files_created = seed_sample_files(demo_data_dir)
    print(f"✓ Created {files_created} sample files")

    # Seed labels (if Neo4j integration exists)
    if neo4j:
        print("\n🏷️  Creating sample labels...")
        labels_created = seed_labels()
        print(f"✓ Created {labels_created} sample labels")

        print("\n🔗 Creating sample relationships...")
        links_created = seed_relationships()
        print(f"✓ Created {links_created} sample relationships")

    # Seed iLab data (if plugin exists)
    print("\n🧪 Checking for iLab plugin...")
    if check_ilab_plugin():
        print("✓ iLab plugin found, seeding sample data...")
        ilab_records = seed_ilab_data(demo_data_dir)
        print(f"✓ Created {ilab_records} iLab records")
    else:
        print("  (iLab plugin not installed, skipping)")

    # Print summary
    print("\n" + "=" * 60)
    print("✅ Demo data seeded successfully!")
    print("\n📋 Demo User Credentials:")
    print("   • admin / demo123 (Admin role)")
    print("   • facility_staff / demo123 (User role)")
    print("   • billing_team / demo123 (User role)")
    print("\n📂 Sample Data Location:")
    print(f"   • Files: {demo_data_dir.absolute()}")
    print(f"   • Database: {db_path}")
    if neo4j:
        print("   • Neo4j: Labels and relationships synced")
    print("\n💡 Tip: Run with --reset to clean and reseed all data")


def clean_demo_data(db_path: str, pix_path: str, neo4j: bool, demo_data_dir: Path = None):
    """Clean all demo data from databases and file system.

    Args:
        db_path: Path to auth database
        pix_path: Path to path index database
        neo4j: Whether to clean Neo4j data
        demo_data_dir: Path to demo_data directory (defaults to './demo_data')
    """
    # Clean auth database (users and sessions)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        # Delete all users except those that might have been created manually
        conn.execute("DELETE FROM auth_users WHERE username IN ('admin', 'facility_staff', 'billing_team')")
        conn.execute("DELETE FROM auth_sessions")
        conn.execute("DELETE FROM auth_failed_attempts")
        conn.commit()
        conn.close()

    # Clean path index database
    if os.path.exists(pix_path):
        conn = sqlite3.connect(pix_path)
        # Clear scan data
        conn.execute("DELETE FROM scans")
        conn.execute("DELETE FROM scan_paths")
        conn.commit()
        conn.close()

    # Clean Neo4j if requested
    if neo4j:
        try:
            from scidk.core.graph_db import get_neo4j_driver
            driver = get_neo4j_driver()
            with driver.session() as session:
                # Delete all demo labels
                session.run("MATCH (n) WHERE n.source = 'demo' DELETE n")
                # Delete all demo relationships
                session.run("MATCH ()-[r {source: 'demo'}]-() DELETE r")
            driver.close()
        except Exception as e:
            print(f"  Warning: Could not clean Neo4j data: {e}")

    # Clean demo_data directory
    if demo_data_dir is None:
        demo_data_dir = Path('demo_data')
    if demo_data_dir.exists():
        shutil.rmtree(demo_data_dir)


def seed_users(auth: AuthManager) -> int:
    """Create demo users."""
    users = [
        ('admin', 'demo123', 'admin'),
        ('facility_staff', 'demo123', 'user'),
        ('billing_team', 'demo123', 'user'),
    ]

    created = 0
    for username, password, role in users:
        # Check if user already exists
        existing = auth.get_user_by_username(username)
        if existing:
            print(f"  • {username} (already exists)")
            continue

        user_id = auth.create_user(username, password, role=role, created_by='system')
        if user_id:
            print(f"  • {username} ({role})")
            created += 1
        else:
            print(f"  ✗ Failed to create {username}")

    return created


def seed_sample_files(demo_data_dir: Path) -> int:
    """Create sample files in demo_data directory."""
    # Create project directories
    projects = {
        'Project_A_Cancer_Research': [
            'experiments/exp001_cell_culture.xlsx',
            'experiments/exp002_drug_treatment.xlsx',
            'results/microscopy/sample_001.tif',
            'results/microscopy/sample_002.tif',
            'results/flow_cytometry/analysis_20240115.fcs',
            'protocols/cell_culture_protocol.pdf',
            'README.md'
        ],
        'Project_B_Proteomics': [
            'raw_data/mass_spec_run001.raw',
            'raw_data/mass_spec_run002.raw',
            'analysis/protein_identification.xlsx',
            'analysis/go_enrichment.csv',
            'figures/volcano_plot.png',
            'README.md'
        ],
        'Core_Facility_Equipment': [
            'equipment_logs/confocal_microscope_2024.xlsx',
            'equipment_logs/flow_cytometer_2024.xlsx',
            'maintenance/service_records.pdf',
            'training/microscopy_training_slides.pdf',
            'README.md'
        ]
    }

    files_created = 0
    for project, files in projects.items():
        project_dir = demo_data_dir / project
        project_dir.mkdir(exist_ok=True)

        # Create README for project
        readme_path = project_dir / 'README.md'
        if not readme_path.exists():
            readme_content = f"# {project.replace('_', ' ')}\n\nDemo project for SciDK testing.\n"
            readme_path.write_text(readme_content)

        for file_path in files:
            full_path = project_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if not full_path.exists():
                # Create placeholder file with some content
                if full_path.suffix == '.md':
                    content = f"# {full_path.stem}\n\nDemo file for testing.\n"
                elif full_path.suffix in ['.xlsx', '.csv']:
                    content = "Sample,Value\nA,1\nB,2\nC,3\n"
                elif full_path.suffix == '.pdf':
                    content = "Placeholder PDF file for demo\n"
                else:
                    content = f"Demo file: {full_path.name}\n"

                full_path.write_text(content)
                files_created += 1

    return files_created


def seed_labels() -> int:
    """Create sample labels in Neo4j (if available)."""
    try:
        from scidk.core.graph_db import get_neo4j_driver

        driver = get_neo4j_driver()
        with driver.session() as session:
            # Create sample Project labels
            projects = [
                {'name': 'Cancer Research - Project A', 'pi': 'Dr. Alice Smith', 'status': 'active'},
                {'name': 'Proteomics Study - Project B', 'pi': 'Dr. Bob Jones', 'status': 'active'},
                {'name': 'Core Facility Operations', 'pi': 'Dr. Carol Williams', 'status': 'active'}
            ]

            for project in projects:
                session.run(
                    """
                    CREATE (p:Project {
                        name: $name,
                        pi: $pi,
                        status: $status,
                        source: 'demo',
                        created_at: datetime()
                    })
                    """,
                    **project
                )

            # Create sample Researcher labels
            researchers = [
                {'name': 'Dr. Alice Smith', 'department': 'Oncology', 'email': 'alice.smith@university.edu'},
                {'name': 'Dr. Bob Jones', 'department': 'Biochemistry', 'email': 'bob.jones@university.edu'},
                {'name': 'Dr. Carol Williams', 'department': 'Core Facilities', 'email': 'carol.williams@university.edu'}
            ]

            for researcher in researchers:
                session.run(
                    """
                    CREATE (r:Researcher {
                        name: $name,
                        department: $department,
                        email: $email,
                        source: 'demo',
                        created_at: datetime()
                    })
                    """,
                    **researcher
                )

            # Create sample Equipment labels
            equipment = [
                {'name': 'Confocal Microscope LSM 880', 'core': 'Microscopy Core', 'equipment_id': 'EQ-001'},
                {'name': 'Flow Cytometer BD FACS Aria III', 'core': 'Flow Cytometry Core', 'equipment_id': 'EQ-002'},
                {'name': 'Mass Spectrometer Orbitrap Fusion', 'core': 'Proteomics Core', 'equipment_id': 'EQ-003'}
            ]

            for item in equipment:
                session.run(
                    """
                    CREATE (e:Equipment {
                        name: $name,
                        core: $core,
                        equipment_id: $equipment_id,
                        source: 'demo',
                        created_at: datetime()
                    })
                    """,
                    **item
                )

        driver.close()
        return len(projects) + len(researchers) + len(equipment)

    except Exception as e:
        print(f"  Warning: Could not seed Neo4j labels: {e}")
        return 0


def seed_relationships() -> int:
    """Create sample relationships in Neo4j (if available)."""
    try:
        from scidk.core.graph_db import get_neo4j_driver

        driver = get_neo4j_driver()
        with driver.session() as session:
            # Link researchers to projects
            relationships = [
                ("Dr. Alice Smith", "Cancer Research - Project A", "LEADS"),
                ("Dr. Bob Jones", "Proteomics Study - Project B", "LEADS"),
                ("Dr. Carol Williams", "Core Facility Operations", "MANAGES"),
            ]

            created = 0
            for researcher_name, project_name, rel_type in relationships:
                result = session.run(
                    f"""
                    MATCH (r:Researcher {{name: $researcher_name}})
                    MATCH (p:Project {{name: $project_name}})
                    CREATE (r)-[:{rel_type} {{source: 'demo', created_at: datetime()}}]->(p)
                    RETURN r, p
                    """,
                    researcher_name=researcher_name,
                    project_name=project_name
                )
                if result.single():
                    created += 1

        driver.close()
        return created

    except Exception as e:
        print(f"  Warning: Could not seed Neo4j relationships: {e}")
        return 0


def check_ilab_plugin() -> bool:
    """Check if iLab plugin is installed."""
    plugin_dir = Path('plugins/ilab_table_loader')
    return plugin_dir.exists() and (plugin_dir / '__init__.py').exists()


def seed_ilab_data(demo_data_dir: Path) -> int:
    """Create sample iLab data files."""
    try:
        import pandas as pd

        # Use the sample files we already created
        fixtures_dir = Path('tests/fixtures')
        ilab_dir = demo_data_dir / 'iLab_Exports'
        ilab_dir.mkdir(exist_ok=True)

        # Copy sample files if they exist
        sample_files = [
            'ilab_equipment_sample.csv',
            'ilab_services_sample.csv',
            'ilab_pi_directory_sample.csv'
        ]

        copied = 0
        for filename in sample_files:
            src = fixtures_dir / filename
            dst = ilab_dir / filename
            if src.exists() and not dst.exists():
                shutil.copy(src, dst)
                copied += 1
                print(f"  • {filename}")

        return copied

    except ImportError:
        print("  Warning: pandas not available, skipping iLab data creation")
        return 0


if __name__ == '__main__':
    seed_demo_data()
