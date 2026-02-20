"""
Script file loader - parses .py and .cypher files with YAML frontmatter.
"""
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class ScriptFileLoader:
    """Loads and parses script files with YAML frontmatter."""

    @staticmethod
    def parse_file(file_path: Path) -> Tuple[Dict[str, Any], str]:
        """
        Parse a script file with YAML frontmatter.

        Args:
            file_path: Path to the script file

        Returns:
            Tuple of (metadata_dict, code_string)

        Raises:
            ValueError: If file format is invalid
        """
        content = file_path.read_text()

        # Try to extract YAML frontmatter from docstring
        # Pattern: """---\n<yaml>\n---\n"""
        pattern = r'^"""\s*---\s*\n(.*?)\n---\s*"""\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            # No frontmatter, return defaults
            return {
                'id': file_path.stem,
                'name': file_path.stem.replace('_', ' ').title(),
                'language': ScriptFileLoader._detect_language(file_path),
                'category': ScriptFileLoader._detect_category(file_path),
                'description': '',
                'parameters': [],
                'tags': []
            }, content.strip()

        # Parse YAML frontmatter
        yaml_content = match.group(1)
        code = match.group(2).strip()

        try:
            metadata = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter in {file_path}: {e}")

        # Ensure required fields
        if 'id' not in metadata:
            metadata['id'] = file_path.stem
        if 'name' not in metadata:
            metadata['name'] = file_path.stem.replace('_', ' ').title()
        if 'language' not in metadata:
            metadata['language'] = ScriptFileLoader._detect_language(file_path)
        if 'category' not in metadata:
            metadata['category'] = ScriptFileLoader._detect_category(file_path)

        # Set defaults for optional fields
        metadata.setdefault('description', '')
        metadata.setdefault('parameters', [])
        metadata.setdefault('tags', [])
        metadata.setdefault('created_at', file_path.stat().st_ctime)
        metadata.setdefault('updated_at', file_path.stat().st_mtime)

        return metadata, code

    @staticmethod
    def _detect_language(file_path: Path) -> str:
        """Detect language from file extension."""
        ext = file_path.suffix.lower()
        if ext == '.py':
            return 'python'
        elif ext == '.cypher':
            return 'cypher'
        else:
            return 'unknown'

    @staticmethod
    def _detect_category(file_path: Path) -> str:
        """Detect category from file path."""
        # Get relative path from scripts/ directory
        parts = file_path.parts
        try:
            scripts_idx = parts.index('scripts')
            if scripts_idx + 1 < len(parts):
                category_parts = parts[scripts_idx + 1:]
                # Join first 2 parts (e.g., analyses/builtin)
                if len(category_parts) >= 2:
                    return f"{category_parts[0]}/{category_parts[1]}"
                return category_parts[0]
        except (ValueError, IndexError):
            pass
        return 'unknown'

    @staticmethod
    def save_file(file_path: Path, metadata: Dict[str, Any], code: str):
        """
        Save a script with YAML frontmatter.

        Args:
            file_path: Path to save the script
            metadata: Metadata dictionary
            code: Script code
        """
        # Remove fields that shouldn't be in frontmatter
        frontmatter_meta = {
            k: v for k, v in metadata.items()
            if k not in ('created_at', 'created_by', 'updated_at', 'file_path', 'is_file_based')
        }

        # Generate YAML frontmatter
        yaml_content = yaml.dump(frontmatter_meta, default_flow_style=False, sort_keys=False)

        # Build file content
        content = f'"""\n---\n{yaml_content}---\n"""\n{code}\n'

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        file_path.write_text(content)

    @staticmethod
    def validate_metadata(metadata: Dict[str, Any]) -> bool:
        """
        Validate script metadata.

        Args:
            metadata: Metadata dictionary

        Returns:
            True if valid, False otherwise
        """
        required_fields = ['id', 'name', 'language', 'category']
        return all(field in metadata for field in required_fields)
