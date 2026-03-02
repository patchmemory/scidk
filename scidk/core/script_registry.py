"""
Script registry - in-memory catalog of all scripts loaded from files.
"""
import time
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING
from .script_loader import ScriptFileLoader

if TYPE_CHECKING:
    from .scripts import Script


class ScriptRegistry:
    """In-memory registry of all scripts loaded from files."""

    def __init__(self, scripts_dir: Path):
        """
        Initialize the registry.

        Args:
            scripts_dir: Path to the scripts/ directory
        """
        self.scripts_dir = scripts_dir
        self.scripts: Dict[str, Script] = {}  # id -> Script
        self.file_paths: Dict[str, Path] = {}  # id -> file path
        self._last_reload = 0.0

    def load_all(self):
        """Scan scripts directory and load all scripts."""
        self.scripts.clear()
        self.file_paths.clear()

        # Scan for .py and .cypher files
        for pattern in ['**/*.py', '**/*.cypher']:
            for file_path in self.scripts_dir.glob(pattern):
                # Skip __init__.py and files in __pycache__
                if file_path.name == '__init__.py' or '__pycache__' in file_path.parts:
                    continue

                # Skip README files
                if file_path.name.lower().startswith('readme'):
                    continue

                try:
                    self._load_script_file(file_path)
                except Exception as e:
                    print(f"Warning: Failed to load script {file_path}: {e}")

        self._last_reload = time.time()

    def _load_script_file(self, file_path: Path):
        """Load a single script file."""
        # Import here to avoid circular import
        from .scripts import Script

        metadata, code = ScriptFileLoader.parse_file(file_path)

        # Create Script object
        script = Script(
            id=metadata['id'],
            name=metadata['name'],
            language=metadata['language'],
            category=metadata['category'],
            code=code,
            description=metadata.get('description', ''),
            parameters=metadata.get('parameters', []),
            tags=metadata.get('tags', []),
            created_at=metadata.get('created_at', file_path.stat().st_ctime),
            updated_at=metadata.get('updated_at', file_path.stat().st_mtime)
        )

        # Store in registry
        self.scripts[script.id] = script
        self.file_paths[script.id] = file_path

    def reload_script(self, script_id: str) -> bool:
        """
        Reload a specific script from disk.

        Args:
            script_id: Script ID to reload

        Returns:
            True if reloaded successfully, False otherwise
        """
        if script_id not in self.file_paths:
            return False

        file_path = self.file_paths[script_id]
        if not file_path.exists():
            # File was deleted, remove from registry
            del self.scripts[script_id]
            del self.file_paths[script_id]
            return False

        try:
            self._load_script_file(file_path)
            return True
        except Exception:
            return False

    def get_script(self, script_id: str) -> Optional['Script']:
        """Get a script by ID."""
        return self.scripts.get(script_id)

    def list_scripts(
        self,
        category: Optional[str] = None,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List['Script']:
        """
        List scripts with optional filters.

        Args:
            category: Filter by category (e.g., 'analyses/builtin')
            language: Filter by language (e.g., 'python', 'cypher')
            tags: Filter by tags (must have all specified tags)

        Returns:
            List of Script objects
        """
        scripts = list(self.scripts.values())

        if category:
            scripts = [s for s in scripts if s.category == category]

        if language:
            scripts = [s for s in scripts if s.language == language]

        if tags:
            scripts = [s for s in scripts if all(tag in s.tags for tag in tags)]

        # Sort by category, then name
        scripts.sort(key=lambda s: (s.category, s.name))

        return scripts

    def list_categories(self) -> List[str]:
        """Get list of all unique categories."""
        categories = set(s.category for s in self.scripts.values())
        return sorted(categories)

    def add_script(self, script: 'Script', file_path: Path):
        """
        Add a new script to the registry and save to disk.

        Args:
            script: Script object to add
            file_path: Path where script should be saved
        """
        # Save to disk
        ScriptFileLoader.save_file(
            file_path,
            {
                'id': script.id,
                'name': script.name,
                'language': script.language,
                'category': script.category,
                'description': script.description,
                'parameters': script.parameters,
                'tags': script.tags
            },
            script.code
        )

        # Add to registry
        self.scripts[script.id] = script
        self.file_paths[script.id] = file_path

    def update_script(self, script: 'Script') -> bool:
        """
        Update an existing script in the registry and on disk.

        Args:
            script: Updated Script object

        Returns:
            True if updated successfully, False otherwise
        """
        if script.id not in self.file_paths:
            return False

        file_path = self.file_paths[script.id]

        # Update modified time
        script.updated_at = time.time()

        # Save to disk
        ScriptFileLoader.save_file(
            file_path,
            {
                'id': script.id,
                'name': script.name,
                'language': script.language,
                'category': script.category,
                'description': script.description,
                'parameters': script.parameters,
                'tags': script.tags
            },
            script.code
        )

        # Update in registry
        self.scripts[script.id] = script

        return True

    def delete_script(self, script_id: str) -> bool:
        """
        Delete a script from the registry and disk.

        Args:
            script_id: Script ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if script_id not in self.file_paths:
            return False

        file_path = self.file_paths[script_id]

        # Delete file
        if file_path.exists():
            file_path.unlink()

        # Remove from registry
        del self.scripts[script_id]
        del self.file_paths[script_id]

        return True

    def get_file_path(self, script_id: str) -> Optional[Path]:
        """Get the file path for a script."""
        return self.file_paths.get(script_id)

    @property
    def count(self) -> int:
        """Get total number of scripts in registry."""
        return len(self.scripts)

    def __len__(self) -> int:
        """Get total number of scripts in registry."""
        return len(self.scripts)

    def __contains__(self, script_id: str) -> bool:
        """Check if script exists in registry."""
        return script_id in self.scripts
