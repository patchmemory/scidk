"""
scidk/schema/link_registry.py

LinkRegistry — loads, caches, and validates Link script definitions.

The registry is the source of truth for all link scripts in SciDK.
It is consulted by:
  - The Links execution pipeline (to run link scripts)
  - The Links UI (to display available links)
  - The validation system (to check link script correctness)

Link definitions live in scripts/links/. Built-in links ship with SciDK.
User-defined links are added by dropping .cypher or .py files in the scripts/links/ directory.

Usage:
    from scidk.schema.link_registry import LinkRegistry

    # Get a link definition
    link = LinkRegistry.get("sample_to_imagingdataset")

    # List all registered links
    all_links = LinkRegistry.all()

    # Reload from disk (after adding a new link)
    LinkRegistry.reload()
"""

from __future__ import annotations
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class LinkDefinition:
    """Fully parsed Link definition loaded from Cypher or Python file."""
    id: str
    name: str
    version: str
    format: str                         # 'cypher' or 'python'
    description: str
    from_label: str                     # Source node label
    to_label: str                       # Target node label
    relationship_type: str              # Neo4j relationship type
    matching_strategy: str              # exact | fuzzy | rule-based | manual | computed
    matching_algorithm: Optional[str]   # For fuzzy: jaro_winkler, levenshtein, etc.
    confidence_threshold: Optional[float]  # For fuzzy matching
    idempotent: bool                    # Must be True (enforced by contract)
    relationship_properties: List[Dict]  # Properties to set on created relationships
    test_fixture: Dict                  # Test setup for validation
    source_path: str                    # Full path to source file
    content_hash: str                   # SHA-256 of file content for change detection
    created_at: float
    updated_at: float

    def validate_references(self, label_registry) -> List[str]:
        """
        Validate that from_label and to_label exist in the Label registry.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not label_registry.get(self.from_label):
            errors.append(f"from_label '{self.from_label}' not found in Label registry")

        if not label_registry.get(self.to_label):
            errors.append(f"to_label '{self.to_label}' not found in Label registry")

        # Validate relationship_type is a valid Neo4j identifier
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', self.relationship_type):
            errors.append(
                f"relationship_type '{self.relationship_type}' is invalid. "
                "Must contain only letters, digits, and underscores, and start with a letter or underscore."
            )

        return errors


class _LinkRegistry:
    """
    Singleton registry for Link definitions.
    Loaded once at startup, reloadable on demand.
    """

    def __init__(self):
        self._links: Dict[str, LinkDefinition] = {}
        self._loaded = False
        self._link_dirs: List[str] = []

    def _default_link_dirs(self) -> List[str]:
        """Return default directories to search for Link script files."""
        # Find the project root by going up from this module's location
        module_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        dirs = [
            os.path.join(module_dir, 'scripts', 'links'),
        ]
        # User-configured links directory (from environment)
        user_dir = os.environ.get('SCIDK_LINKS_DIR')
        if user_dir and os.path.isdir(user_dir):
            dirs.append(user_dir)
        return [d for d in dirs if os.path.isdir(d)]

    def load(self, link_dirs: Optional[List[str]] = None):
        """Load all Link definitions from Cypher and Python files."""
        self._link_dirs = link_dirs or self._default_link_dirs()
        self._links = {}

        for link_dir in self._link_dirs:
            if not os.path.exists(link_dir):
                logger.warning(f"Link directory does not exist: {link_dir}")
                continue

            for filename in sorted(os.listdir(link_dir)):
                # Skip Python cache and hidden files
                if filename.startswith('.') or filename.startswith('__'):
                    continue

                # Only process .cypher and .py files
                if not (filename.endswith('.cypher') or filename.endswith('.py')):
                    continue

                filepath = os.path.join(link_dir, filename)
                try:
                    link_def = self._parse_file(filepath)
                    if link_def:
                        self._links[link_def.id] = link_def
                        logger.debug(f"Loaded link: {link_def.id} from {filepath}")
                except Exception as e:
                    logger.error(f"Failed to load link from {filepath}: {e}")

        self._loaded = True
        logger.info(f"LinkRegistry loaded {len(self._links)} links from {len(self._link_dirs)} directories")

    def reload(self):
        """Reload all links from disk. Use after adding or changing Link definitions."""
        self._loaded = False
        self.load(self._link_dirs or None)

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def get(self, link_id: str) -> Optional[LinkDefinition]:
        """Get a link definition by ID. Returns None if not found."""
        self._ensure_loaded()
        return self._links.get(link_id)

    def all(self) -> Dict[str, LinkDefinition]:
        """Return all registered link definitions."""
        self._ensure_loaded()
        return dict(self._links)

    def register(self, link_def: LinkDefinition):
        """Register a link definition programmatically (e.g. from tests)."""
        self._links[link_def.id] = link_def
        self._loaded = True

    def _parse_file(self, filepath: str) -> Optional[LinkDefinition]:
        """Parse a Link Cypher or Python file into a LinkDefinition."""
        import time

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Extract YAML header
        header_yaml = self._extract_yaml_header(content, filepath)
        if not header_yaml:
            logger.warning(f"No valid YAML header found in {filepath}")
            return None

        try:
            header = yaml.safe_load(header_yaml)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML header in {filepath}: {e}")
            return None

        if not header:
            return None

        # Validate required fields
        required_fields = ['id', 'name', 'format', 'from_label', 'to_label', 'relationship_type']
        missing = [f for f in required_fields if f not in header]
        if missing:
            logger.error(f"Missing required fields in {filepath}: {missing}")
            return None

        # Get file timestamps
        stat = os.stat(filepath)
        created_at = stat.st_ctime
        updated_at = stat.st_mtime

        return LinkDefinition(
            id=header['id'],
            name=header['name'],
            version=header.get('version', '1.0.0'),
            format=header['format'],
            description=header.get('description', ''),
            from_label=header['from_label'],
            to_label=header['to_label'],
            relationship_type=header['relationship_type'],
            matching_strategy=header.get('matching_strategy', 'computed'),
            matching_algorithm=header.get('matching_algorithm'),
            confidence_threshold=header.get('confidence_threshold'),
            idempotent=header.get('idempotent', True),
            relationship_properties=header.get('relationship_properties', []),
            test_fixture=header.get('test_fixture', {}),
            source_path=filepath,
            content_hash=content_hash,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _extract_yaml_header(self, content: str, filepath: str) -> Optional[str]:
        """
        Extract YAML header from Cypher or Python file.

        For Cypher files: Look for # --- ... # --- blocks
        For Python files: Look for triple-quote docstring with --- ... ---
        """
        if filepath.endswith('.cypher'):
            # Cypher format: # --- at start of line, # before each line
            lines = content.split('\n')
            in_header = False
            header_lines = []

            for line in lines:
                stripped = line.strip()
                if stripped == '# ---':
                    if in_header:
                        # End of header
                        break
                    else:
                        # Start of header
                        in_header = True
                        continue

                if in_header:
                    # Remove leading # and whitespace
                    if line.startswith('#'):
                        header_lines.append(line[1:].lstrip())
                    elif stripped:
                        # Non-comment line ends header
                        break

            return '\n'.join(header_lines) if header_lines else None

        elif filepath.endswith('.py'):
            # Python format: Look for """ or ''' docstring containing --- markers
            # Try triple double quotes first
            match = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if not match:
                # Try triple single quotes
                match = re.search(r"'''(.*?)'''", content, re.DOTALL)

            if match:
                docstring = match.group(1)
                # Look for YAML between --- markers
                yaml_match = re.search(r'---\s*\n(.*?)\n---', docstring, re.DOTALL)
                if yaml_match:
                    return yaml_match.group(1)

        return None


# Singleton instance
LinkRegistry = _LinkRegistry()
