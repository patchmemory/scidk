"""
Tests for Fuzzy Matching Service.

Tests settings persistence, client-side matching (Phase 1),
and server-side Cypher generation (Phase 2).
"""
import pytest
import tempfile
import os
from scidk.core.fuzzy_matching import FuzzyMatchingService, FuzzyMatchSettings

# Check if rapidfuzz is available for client-side matching tests
try:
    import rapidfuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

requires_rapidfuzz = pytest.mark.skipif(
    not RAPIDFUZZ_AVAILABLE,
    reason="rapidfuzz not installed (optional dependency for Phase 1 client-side matching)"
)


@pytest.fixture
def service():
    """Create a temporary fuzzy matching service for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name

    svc = FuzzyMatchingService(db_path=db_path)

    yield svc

    # Cleanup
    svc.db.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_global_default_seeded(service):
    """Test that global default settings are seeded on initialization."""
    settings = service.get_global_settings()

    assert settings.algorithm == 'levenshtein'
    assert settings.threshold == 0.80
    assert settings.case_sensitive is False
    assert settings.normalize_whitespace is True
    assert settings.strip_punctuation is True


def test_update_global_settings(service):
    """Test updating global fuzzy matching settings."""
    updates = {
        'algorithm': 'jaro_winkler',
        'threshold': 0.75,
        'case_sensitive': True
    }

    updated = service.update_global_settings(updates)

    assert updated.algorithm == 'jaro_winkler'
    assert updated.threshold == 0.75
    assert updated.case_sensitive is True
    # Other fields should remain unchanged
    assert updated.normalize_whitespace is True


def test_settings_to_dict(service):
    """Test serializing settings to dictionary."""
    settings = service.get_global_settings()
    data = settings.to_dict()

    assert isinstance(data, dict)
    assert 'algorithm' in data
    assert 'threshold' in data
    assert data['algorithm'] == 'levenshtein'


def test_settings_from_dict():
    """Test deserializing settings from dictionary."""
    data = {
        'algorithm': 'jaro_winkler',
        'threshold': 0.90,
        'case_sensitive': True
    }

    settings = FuzzyMatchSettings.from_dict(data)

    assert settings.algorithm == 'jaro_winkler'
    assert settings.threshold == 0.90
    assert settings.case_sensitive is True


# ==========================================
# Phase 1: Client-Side Matching Tests
# ==========================================

@requires_rapidfuzz
def test_match_external_data_exact(service):
    """Test exact matching (no fuzzy logic)."""
    external_records = [
        {'name': 'John Smith', 'email': 'john@example.com'},
        {'name': 'Jane Doe', 'email': 'jane@example.com'},
        {'name': 'Unknown Person', 'email': 'unknown@example.com'}
    ]

    existing_nodes = [
        {'name': 'John Smith', 'id': 1},
        {'name': 'Jane Doe', 'id': 2}
    ]

    settings = FuzzyMatchSettings(algorithm='exact')
    matches = service.match_external_data(
        external_records,
        existing_nodes,
        'name',
        settings
    )

    assert len(matches) == 3
    assert matches[0]['is_match'] is True
    assert matches[0]['matched_node']['id'] == 1
    assert matches[1]['is_match'] is True
    assert matches[1]['matched_node']['id'] == 2
    assert matches[2]['is_match'] is False


@requires_rapidfuzz
def test_match_external_data_levenshtein(service):
    """Test Levenshtein fuzzy matching."""
    external_records = [
        {'name': 'Jon Smith'},  # Typo in "John"
        {'name': 'Jane Doe'},   # Exact match
        {'name': 'Completely Different'}
    ]

    existing_nodes = [
        {'name': 'John Smith', 'id': 1},
        {'name': 'Jane Doe', 'id': 2}
    ]

    settings = FuzzyMatchSettings(algorithm='levenshtein', threshold=0.80)
    matches = service.match_external_data(
        external_records,
        existing_nodes,
        'name',
        settings
    )

    # "Jon Smith" should match "John Smith" (high similarity)
    assert matches[0]['is_match'] is True
    assert matches[0]['matched_node']['id'] == 1
    assert matches[0]['confidence'] > 0.80

    # "Jane Doe" exact match
    assert matches[1]['is_match'] is True
    assert matches[1]['confidence'] > 0.95

    # "Completely Different" should not match
    assert matches[2]['is_match'] is False


def test_normalize_string_case_insensitive(service):
    """Test string normalization with case insensitivity."""
    settings = FuzzyMatchSettings(case_sensitive=False)
    result = service._normalize_string('John SMITH', settings)
    assert result == 'john smith'


def test_normalize_string_strip_punctuation(service):
    """Test string normalization with punctuation stripping."""
    settings = FuzzyMatchSettings(strip_punctuation=True)
    result = service._normalize_string("O'Brien, John", settings)
    # Punctuation should be removed
    assert ',' not in result
    assert "'" not in result


def test_normalize_whitespace(service):
    """Test whitespace normalization."""
    settings = FuzzyMatchSettings(normalize_whitespace=True)
    result = service._normalize_string('John   Smith  ', settings)
    assert result == 'john smith'  # Normalized to single spaces, trimmed


@requires_rapidfuzz
def test_match_with_missing_key(service):
    """Test matching when external record is missing the match key."""
    external_records = [
        {'email': 'john@example.com'},  # Missing 'name'
    ]

    existing_nodes = [
        {'name': 'John Smith', 'id': 1}
    ]

    matches = service.match_external_data(
        external_records,
        existing_nodes,
        'name',
        FuzzyMatchSettings()
    )

    assert len(matches) == 1
    assert matches[0]['is_match'] is False
    assert 'reason' in matches[0]


@requires_rapidfuzz
def test_match_with_short_string(service):
    """Test matching with strings below min_string_length."""
    external_records = [
        {'name': 'Jo'},  # Too short (< 3 chars)
    ]

    existing_nodes = [
        {'name': 'John', 'id': 1}
    ]

    settings = FuzzyMatchSettings(min_string_length=3)
    matches = service.match_external_data(
        external_records,
        existing_nodes,
        'name',
        settings
    )

    assert matches[0]['is_match'] is False
    assert 'too short' in matches[0].get('reason', '').lower()


# ==========================================
# Phase 2: Server-Side Cypher Generation Tests
# ==========================================

def test_generate_cypher_exact_match(service):
    """Test Cypher generation for exact matching."""
    cypher = service.generate_cypher_fuzzy_match(
        source_label='Person',
        target_label='Company',
        source_property='name',
        target_property='contact_name',
        relationship_type='WORKS_AT',
        settings=FuzzyMatchSettings(algorithm='exact')
    )

    assert 'MATCH (source:Person)' in cypher
    assert 'MATCH' in cypher and 'target:Company' in cypher
    assert 'source.name = target.contact_name' in cypher
    assert 'CREATE (source)-[:WORKS_AT' in cypher


def test_generate_cypher_levenshtein(service):
    """Test Cypher generation for Levenshtein matching."""
    settings = FuzzyMatchSettings(algorithm='levenshtein', threshold=0.80)
    cypher = service.generate_cypher_fuzzy_match(
        source_label='Person',
        target_label='Company',
        source_property='name',
        target_property='contact_name',
        relationship_type='WORKS_AT',
        settings=settings
    )

    assert 'apoc.text.levenshteinSimilarity' in cypher
    assert '>= 0.8' in cypher
    assert 'confidence' in cypher


def test_generate_cypher_jaro_winkler(service):
    """Test Cypher generation for Jaro-Winkler matching."""
    settings = FuzzyMatchSettings(algorithm='jaro_winkler', threshold=0.85)
    cypher = service.generate_cypher_fuzzy_match(
        source_label='Person',
        target_label='Organization',
        source_property='full_name',
        target_property='owner_name',
        relationship_type='OWNS',
        settings=settings
    )

    assert 'apoc.text.jaroWinklerDistance' in cypher
    assert '>= 0.85' in cypher


def test_generate_cypher_phonetic_soundex(service):
    """Test Cypher generation for phonetic (soundex) matching."""
    settings = FuzzyMatchSettings(
        algorithm='phonetic',
        phonetic_enabled=True,
        phonetic_algorithm='soundex'
    )
    cypher = service.generate_cypher_fuzzy_match(
        source_label='Person',
        target_label='Person',
        source_property='last_name',
        target_property='surname',
        relationship_type='SIMILAR_TO',
        settings=settings
    )

    assert 'apoc.text.phonetic' in cypher
    assert 'soundex' in cypher.lower() or 'phonetic' in cypher.lower()


def test_generate_cypher_phonetic_metaphone(service):
    """Test Cypher generation for phonetic (metaphone) matching."""
    settings = FuzzyMatchSettings(
        algorithm='phonetic',
        phonetic_enabled=True,
        phonetic_algorithm='metaphone'
    )
    cypher = service.generate_cypher_fuzzy_match(
        source_label='Author',
        target_label='Contributor',
        source_property='name',
        target_property='name',
        relationship_type='SAME_PERSON',
        settings=settings
    )

    assert 'apoc.text.doubleMetaphone' in cypher


def test_cypher_includes_labels_and_properties(service):
    """Test that generated Cypher includes correct labels and properties."""
    cypher = service.generate_cypher_fuzzy_match(
        source_label='Customer',
        target_label='Order',
        source_property='customer_email',
        target_property='buyer_email',
        relationship_type='PLACED',
        settings=FuzzyMatchSettings()
    )

    assert 'Customer' in cypher
    assert 'Order' in cypher
    assert 'customer_email' in cypher
    assert 'buyer_email' in cypher
    assert 'PLACED' in cypher
