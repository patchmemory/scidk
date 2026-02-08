"""
Fuzzy Matching Service for Links Integration.

Provides hybrid fuzzy matching capabilities:
- Phase 1: Pre-import matching (client-side) for external data
- Phase 2: Post-import matching (server-side) using Neo4j APOC functions

Supports multiple algorithms:
- Levenshtein Distance (edit distance)
- Jaro-Winkler Distance (name-optimized)
- Phonetic matching (Soundex, Metaphone via APOC)
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import sqlite3
import json
import uuid
from datetime import datetime, timezone


@dataclass
class FuzzyMatchSettings:
    """Configuration for fuzzy matching operations."""
    algorithm: str = 'levenshtein'  # levenshtein, jaro_winkler, phonetic, exact
    threshold: float = 0.80  # 0.0 to 1.0 similarity threshold
    case_sensitive: bool = False
    normalize_whitespace: bool = True
    strip_punctuation: bool = True
    phonetic_enabled: bool = False
    phonetic_algorithm: str = 'metaphone'  # soundex, metaphone, double_metaphone
    min_string_length: int = 3
    max_comparisons: int = 10000
    show_confidence_scores: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'algorithm': self.algorithm,
            'threshold': self.threshold,
            'case_sensitive': self.case_sensitive,
            'normalize_whitespace': self.normalize_whitespace,
            'strip_punctuation': self.strip_punctuation,
            'phonetic_enabled': self.phonetic_enabled,
            'phonetic_algorithm': self.phonetic_algorithm,
            'min_string_length': self.min_string_length,
            'max_comparisons': self.max_comparisons,
            'show_confidence_scores': self.show_confidence_scores
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'FuzzyMatchSettings':
        """Create from dictionary."""
        return FuzzyMatchSettings(
            algorithm=data.get('algorithm', 'levenshtein'),
            threshold=data.get('threshold', 0.80),
            case_sensitive=data.get('case_sensitive', False),
            normalize_whitespace=data.get('normalize_whitespace', True),
            strip_punctuation=data.get('strip_punctuation', True),
            phonetic_enabled=data.get('phonetic_enabled', False),
            phonetic_algorithm=data.get('phonetic_algorithm', 'metaphone'),
            min_string_length=data.get('min_string_length', 3),
            max_comparisons=data.get('max_comparisons', 10000),
            show_confidence_scores=data.get('show_confidence_scores', True)
        )


class FuzzyMatchingService:
    """
    Hybrid fuzzy matching service for entity resolution.

    Phase 1: Client-side matching for pre-import data (using rapidfuzz)
    Phase 2: Server-side matching for in-database entities (using Neo4j APOC)
    """

    def __init__(self, db_path: str):
        """
        Initialize service with settings database.

        Args:
            db_path: Path to settings database
        """
        self.db_path = db_path
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.db.row_factory = sqlite3.Row
        self._matcher = None  # Lazy-load rapidfuzz
        self.init_tables()

    def init_tables(self):
        """Create settings table if it doesn't exist."""
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS fuzzy_match_settings (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                algorithm TEXT NOT NULL,
                threshold REAL NOT NULL,
                case_sensitive INTEGER NOT NULL,
                normalize_whitespace INTEGER NOT NULL,
                strip_punctuation INTEGER NOT NULL,
                phonetic_enabled INTEGER NOT NULL,
                phonetic_algorithm TEXT,
                min_string_length INTEGER NOT NULL,
                max_comparisons INTEGER NOT NULL,
                show_confidence_scores INTEGER NOT NULL,
                is_global INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self.db.commit()

        # Seed global default if it doesn't exist
        self._seed_global_default()

    def _seed_global_default(self):
        """Insert global default settings if they don't exist."""
        cursor = self.db.execute(
            "SELECT id FROM fuzzy_match_settings WHERE is_global = 1"
        )
        if cursor.fetchone():
            return  # Already exists

        default = FuzzyMatchSettings()
        now = datetime.now(timezone.utc).timestamp()

        self.db.execute(
            """
            INSERT INTO fuzzy_match_settings
            (id, name, algorithm, threshold, case_sensitive, normalize_whitespace,
             strip_punctuation, phonetic_enabled, phonetic_algorithm, min_string_length,
             max_comparisons, show_confidence_scores, is_global, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                'global-default',
                'Global Default',
                default.algorithm,
                default.threshold,
                1 if default.case_sensitive else 0,
                1 if default.normalize_whitespace else 0,
                1 if default.strip_punctuation else 0,
                1 if default.phonetic_enabled else 0,
                default.phonetic_algorithm,
                default.min_string_length,
                default.max_comparisons,
                1 if default.show_confidence_scores else 0,
                now,
                now
            )
        )
        self.db.commit()

    def get_global_settings(self) -> FuzzyMatchSettings:
        """Get global fuzzy matching settings."""
        cursor = self.db.execute(
            """
            SELECT algorithm, threshold, case_sensitive, normalize_whitespace,
                   strip_punctuation, phonetic_enabled, phonetic_algorithm,
                   min_string_length, max_comparisons, show_confidence_scores
            FROM fuzzy_match_settings
            WHERE is_global = 1
            """
        )
        row = cursor.fetchone()
        if not row:
            # Fallback to defaults
            return FuzzyMatchSettings()

        return FuzzyMatchSettings(
            algorithm=row['algorithm'],
            threshold=row['threshold'],
            case_sensitive=bool(row['case_sensitive']),
            normalize_whitespace=bool(row['normalize_whitespace']),
            strip_punctuation=bool(row['strip_punctuation']),
            phonetic_enabled=bool(row['phonetic_enabled']),
            phonetic_algorithm=row['phonetic_algorithm'],
            min_string_length=row['min_string_length'],
            max_comparisons=row['max_comparisons'],
            show_confidence_scores=bool(row['show_confidence_scores'])
        )

    def update_global_settings(self, settings: Dict[str, Any]) -> FuzzyMatchSettings:
        """Update global fuzzy matching settings."""
        updates = []
        params = []

        if 'algorithm' in settings:
            updates.append("algorithm = ?")
            params.append(settings['algorithm'])
        if 'threshold' in settings:
            updates.append("threshold = ?")
            params.append(settings['threshold'])
        if 'case_sensitive' in settings:
            updates.append("case_sensitive = ?")
            params.append(1 if settings['case_sensitive'] else 0)
        if 'normalize_whitespace' in settings:
            updates.append("normalize_whitespace = ?")
            params.append(1 if settings['normalize_whitespace'] else 0)
        if 'strip_punctuation' in settings:
            updates.append("strip_punctuation = ?")
            params.append(1 if settings['strip_punctuation'] else 0)
        if 'phonetic_enabled' in settings:
            updates.append("phonetic_enabled = ?")
            params.append(1 if settings['phonetic_enabled'] else 0)
        if 'phonetic_algorithm' in settings:
            updates.append("phonetic_algorithm = ?")
            params.append(settings['phonetic_algorithm'])
        if 'min_string_length' in settings:
            updates.append("min_string_length = ?")
            params.append(settings['min_string_length'])
        if 'max_comparisons' in settings:
            updates.append("max_comparisons = ?")
            params.append(settings['max_comparisons'])
        if 'show_confidence_scores' in settings:
            updates.append("show_confidence_scores = ?")
            params.append(1 if settings['show_confidence_scores'] else 0)

        # Update timestamp
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).timestamp())

        if updates:
            sql = f"UPDATE fuzzy_match_settings SET {', '.join(updates)} WHERE is_global = 1"
            self.db.execute(sql, params)
            self.db.commit()

        return self.get_global_settings()

    # ==========================================
    # Phase 1: Pre-Import Matching (Client-Side)
    # ==========================================

    def _ensure_matcher(self):
        """Lazy-load rapidfuzz library."""
        if self._matcher is None:
            try:
                from rapidfuzz import fuzz, process
                self._matcher = {'fuzz': fuzz, 'process': process}
            except ImportError:
                raise RuntimeError(
                    "rapidfuzz library not installed. "
                    "Install with: pip install rapidfuzz>=3.0"
                )

    def _normalize_string(self, text: str, settings: FuzzyMatchSettings) -> str:
        """Normalize string according to settings."""
        if not isinstance(text, str):
            text = str(text)

        if not settings.case_sensitive:
            text = text.lower()

        if settings.normalize_whitespace:
            text = ' '.join(text.split())

        if settings.strip_punctuation:
            import string
            text = text.translate(str.maketrans('', '', string.punctuation))

        return text.strip()

    def match_external_data(
        self,
        external_records: List[Dict[str, Any]],
        existing_nodes: List[Dict[str, Any]],
        match_key: str,
        settings: Optional[FuzzyMatchSettings] = None
    ) -> List[Dict[str, Any]]:
        """
        Phase 1: Match external data against existing Neo4j nodes (client-side).

        Args:
            external_records: List of external records to match
            existing_nodes: List of existing Neo4j nodes to match against
            match_key: Property key to use for matching (e.g., 'name', 'email')
            settings: Optional fuzzy match settings (uses global if None)

        Returns:
            List of match results with structure:
            {
                'external_record': {...},
                'matched_node': {...} or None,
                'confidence': float (0.0-1.0),
                'is_match': bool
            }
        """
        self._ensure_matcher()
        if settings is None:
            settings = self.get_global_settings()

        if settings.algorithm == 'exact':
            return self._match_exact(external_records, existing_nodes, match_key, settings)

        fuzz = self._matcher['fuzz']
        matches = []

        # Normalize all existing node values for comparison
        existing_normalized = {}
        for node in existing_nodes:
            if match_key in node and node[match_key]:
                original = node[match_key]
                normalized = self._normalize_string(str(original), settings)
                if len(normalized) >= settings.min_string_length:
                    existing_normalized[normalized] = node

        # Match each external record
        for record in external_records:
            if match_key not in record or not record[match_key]:
                matches.append({
                    'external_record': record,
                    'matched_node': None,
                    'confidence': 0.0,
                    'is_match': False,
                    'reason': 'Missing match key'
                })
                continue

            external_value = self._normalize_string(str(record[match_key]), settings)

            if len(external_value) < settings.min_string_length:
                matches.append({
                    'external_record': record,
                    'matched_node': None,
                    'confidence': 0.0,
                    'is_match': False,
                    'reason': f'String too short (< {settings.min_string_length} chars)'
                })
                continue

            # Find best match
            best_match = None
            best_confidence = 0.0

            for norm_value, node in existing_normalized.items():
                confidence = self._compute_similarity(
                    external_value, norm_value, settings.algorithm, fuzz
                )

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = node

            is_match = best_confidence >= settings.threshold

            matches.append({
                'external_record': record,
                'matched_node': best_match if is_match else None,
                'confidence': best_confidence,
                'is_match': is_match
            })

        return matches

    def _match_exact(
        self,
        external_records: List[Dict[str, Any]],
        existing_nodes: List[Dict[str, Any]],
        match_key: str,
        settings: FuzzyMatchSettings
    ) -> List[Dict[str, Any]]:
        """Exact matching (no fuzzy logic)."""
        # Build lookup dict
        lookup = {}
        for node in existing_nodes:
            if match_key in node and node[match_key]:
                normalized = self._normalize_string(str(node[match_key]), settings)
                lookup[normalized] = node

        matches = []
        for record in external_records:
            if match_key not in record or not record[match_key]:
                matches.append({
                    'external_record': record,
                    'matched_node': None,
                    'confidence': 0.0,
                    'is_match': False
                })
                continue

            normalized = self._normalize_string(str(record[match_key]), settings)
            matched_node = lookup.get(normalized)

            matches.append({
                'external_record': record,
                'matched_node': matched_node,
                'confidence': 1.0 if matched_node else 0.0,
                'is_match': matched_node is not None
            })

        return matches

    def _compute_similarity(
        self,
        str1: str,
        str2: str,
        algorithm: str,
        fuzz
    ) -> float:
        """Compute similarity score using specified algorithm."""
        if algorithm == 'levenshtein':
            # Levenshtein ratio (0-100), normalize to 0.0-1.0
            return fuzz.ratio(str1, str2) / 100.0

        elif algorithm == 'jaro_winkler':
            # Jaro-Winkler distance (0-100), normalize to 0.0-1.0
            return fuzz.Jaro.distance(str1, str2)

        else:
            # Default to Levenshtein
            return fuzz.ratio(str1, str2) / 100.0

    # ==========================================
    # Phase 2: Post-Import Matching (Server-Side)
    # ==========================================

    def generate_cypher_fuzzy_match(
        self,
        source_label: str,
        target_label: str,
        source_property: str,
        target_property: str,
        relationship_type: str,
        settings: Optional[FuzzyMatchSettings] = None
    ) -> str:
        """
        Phase 2: Generate Cypher query using Neo4j APOC fuzzy functions (server-side).

        Args:
            source_label: Source node label
            target_label: Target node label
            source_property: Property on source node to match
            target_property: Property on target node to match
            relationship_type: Type of relationship to create
            settings: Optional fuzzy match settings (uses global if None)

        Returns:
            Cypher query string for Neo4j execution
        """
        if settings is None:
            settings = self.get_global_settings()

        if settings.algorithm == 'exact':
            # Exact match using standard Cypher
            cypher = f"""
            MATCH (source:{source_label}), (target:{target_label})
            WHERE source.{source_property} = target.{target_property}
            CREATE (source)-[:{relationship_type} {{confidence: 1.0}}]->(target)
            RETURN source, target, 1.0 as confidence
            """

        elif settings.algorithm == 'levenshtein':
            cypher = f"""
            MATCH (source:{source_label}), (target:{target_label})
            WHERE apoc.text.levenshteinSimilarity(
                source.{source_property},
                target.{target_property}
            ) >= {settings.threshold}
            WITH source, target,
                 apoc.text.levenshteinSimilarity(
                     source.{source_property},
                     target.{target_property}
                 ) as confidence
            CREATE (source)-[:{relationship_type} {{confidence: confidence}}]->(target)
            RETURN source, target, confidence
            """

        elif settings.algorithm == 'jaro_winkler':
            cypher = f"""
            MATCH (source:{source_label}), (target:{target_label})
            WHERE apoc.text.jaroWinklerDistance(
                source.{source_property},
                target.{target_property}
            ) >= {settings.threshold}
            WITH source, target,
                 apoc.text.jaroWinklerDistance(
                     source.{source_property},
                     target.{target_property}
                 ) as confidence
            CREATE (source)-[:{relationship_type} {{confidence: confidence}}]->(target)
            RETURN source, target, confidence
            """

        elif settings.algorithm == 'phonetic' and settings.phonetic_enabled:
            phonetic_func = 'apoc.text.phonetic' if settings.phonetic_algorithm == 'soundex' else 'apoc.text.doubleMetaphone'
            cypher = f"""
            MATCH (source:{source_label}), (target:{target_label})
            WHERE {phonetic_func}(source.{source_property}) = {phonetic_func}(target.{target_property})
            CREATE (source)-[:{relationship_type} {{confidence: 0.9, method: 'phonetic'}}]->(target)
            RETURN source, target, 0.9 as confidence
            """

        else:
            # Fallback to Levenshtein
            cypher = self.generate_cypher_fuzzy_match(
                source_label, target_label, source_property, target_property,
                relationship_type,
                FuzzyMatchSettings(algorithm='levenshtein', threshold=settings.threshold)
            )

        return cypher


def get_fuzzy_matching_service(db_path: str = 'scidk_settings.db') -> FuzzyMatchingService:
    """
    Get or create a FuzzyMatchingService instance.

    Args:
        db_path: Path to settings database

    Returns:
        FuzzyMatchingService instance
    """
    return FuzzyMatchingService(db_path)
