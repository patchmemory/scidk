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

    Scripts are loaded from scripts/analyses/builtin/ directory.
    Falls back to in-memory versions if files don't exist.
    """
    scripts = []

    # Find builtin scripts directory
    import scidk
    project_root = Path(scidk.__file__).parent.parent
    builtin_dir = project_root / 'scripts' / 'analyses' / 'builtin'

    if not builtin_dir.exists():
        print(f"Warning: Builtin scripts directory not found: {builtin_dir}")
        return []

    # Load all .py and .cypher files
    for pattern in ['*.py', '*.cypher']:
        for file_path in builtin_dir.glob(pattern):
            try:
                metadata, code = ScriptFileLoader.parse_file(file_path)
                script = Script(
                    id=metadata['id'],
                    name=metadata['name'],
                    language=metadata['language'],
                    category=metadata['category'],
                    code=code,
                    description=metadata.get('description', ''),
                    parameters=metadata.get('parameters', []),
                    tags=metadata.get('tags', [])
                )
                scripts.append(script)
            except Exception as e:
                print(f"Warning: Failed to load builtin script {file_path}: {e}")

    return scripts
