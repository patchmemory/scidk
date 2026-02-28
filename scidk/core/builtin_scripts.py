"""
Built-in scripts for the Scripts page.

Built-in scripts are now loaded from files in scripts/analyses/builtin/.
This module provides compatibility methods to load them.

Provides 7 core scripts:
1. File Distribution by Extension
2. Scan Timeline & Volume
3. Largest Files
4. Interpretation Success Rates
5. Neo4j Node/Relationship Counts
6. Orphaned Files
7. Schema Drift Detection
"""
from pathlib import Path
from typing import List
from .scripts import Script
from .script_loader import ScriptFileLoader


def get_builtin_scripts() -> List[Script]:
    """
    Return all built-in scripts loaded from files.

    Scripts are loaded from designated subdirectories only:
    - scripts/analyses/builtin/ (analyses)
    - scripts/links/ (link scripts)
    - scripts/examples/ (example scripts)

    Root-level scripts/*.py files (like analyze_feedback.py, seed_demo_data.py)
    are utility scripts and are explicitly excluded from loading.
    """
    scripts = []

    # Find project root
    import scidk
    project_root = Path(scidk.__file__).parent.parent

    # Define directories to scan
    # Each tuple: (directory_path, category_override)
    # category_override forces a specific category regardless of path/frontmatter
    #
    # IMPORTANT: Only scan designated subdirectories.
    # DO NOT scan root-level scripts/*.py files - those are utilities,
    # not Scripts page content (e.g., analyze_feedback.py, seed_demo_data.py).
    script_dirs = [
        (project_root / 'scripts' / 'analyses' / 'builtin', None),
        (project_root / 'scripts' / 'links', 'links'),
        (project_root / 'scripts' / 'examples', 'examples'),
    ]

    # Load all .py and .cypher files from each directory
    for script_dir, category_override in script_dirs:
        if not script_dir.exists():
            continue

        for pattern in ['*.py', '*.cypher']:
            for file_path in script_dir.glob(pattern):
                try:
                    metadata, code = ScriptFileLoader.parse_file(file_path)

                    # Override category if specified (directory is source of truth)
                    if category_override:
                        metadata['category'] = category_override

                    script = Script(
                        id=metadata['id'],
                        name=metadata['name'],
                        language=metadata['language'],
                        category=metadata['category'],
                        code=code,
                        description=metadata.get('description', ''),
                        parameters=metadata.get('parameters', []),
                        tags=metadata.get('tags', []),
                        source='built-in',
                        modified=False
                    )
                    scripts.append(script)
                except Exception as e:
                    print(f"Warning: Failed to load builtin script {file_path}: {e}")

    return scripts
