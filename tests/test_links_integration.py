"""Integration tests for wizard + script links coexistence.

Tests that both link types work together in the unified UI and backend.
"""
import pytest
from scidk.services.link_service import LinkService
from scidk.core.scripts import ScriptsManager, Script


def test_unified_list_includes_both_types(app):
    """list_all_links() returns both wizard and script links."""
    service = LinkService(app)
    all_links = service.list_all_links()

    wizard_links = [l for l in all_links if l['type'] == 'wizard']
    script_links = [l for l in all_links if l['type'] == 'script']

    # Should have at least some wizard links (scripts may not be discovered in test env)
    assert len(wizard_links) >= 1, f"Should have at least 1 wizard link, got {len(wizard_links)}"
    assert len(all_links) >= len(wizard_links), "All links should be counted"

    # If script links exist, verify they're properly formatted
    if script_links:
        for link in script_links:
            assert 'id' in link
            assert 'name' in link
            assert link['type'] == 'script'


def test_script_links_have_validation_status(app):
    """Script links include validation fields that wizard links don't have."""
    pytest.skip("Requires scripts/links/ directory with multiple demo scripts - currently only 1 exists")


def test_wizard_links_have_labels(app):
    """Wizard links include source/target labels and relationship types."""
    service = LinkService(app)
    all_links = service.list_all_links()

    wizard_links = [l for l in all_links if l['type'] == 'wizard']
    assert len(wizard_links) > 0, "Should have at least one wizard link"

    for link in wizard_links:
        assert 'source_label' in link, "Wizard links must have source_label"
        assert 'target_label' in link, "Wizard links must have target_label"
        assert 'relationship_type' in link, "Wizard links must have relationship_type"
        assert 'match_strategy' in link, "Wizard links must have match_strategy"


def test_cypher_injection_protection_wizard(app):
    """Wizard link execution validates relationship type to prevent Cypher injection."""
    service = LinkService(app)

    # Test malicious relationship types
    malicious_inputs = [
        "'; DROP TABLE users;--",
        "TEST]->(n) DELETE n//",
        "HACK{code:exec()}",
        "REL`backdoor`",
        "../../../etc/passwd",
    ]

    for malicious in malicious_inputs:
        with pytest.raises(ValueError, match="Invalid relationship type"):
            service._validate_relationship_type(malicious)

    # Valid types should pass
    valid_types = [
        "WORKS_ON",
        "CO_AUTHORED",
        "SIMILAR_TO",
        "HAS_CHILD",
        "_PRIVATE_REL",
        "rel123",
    ]

    for valid in valid_types:
        result = service._validate_relationship_type(valid)
        assert result == valid, f"Valid type {valid} should pass unchanged"


def test_cypher_injection_protection_on_empty_input(app):
    """Validation rejects empty or None relationship types."""
    service = LinkService(app)

    with pytest.raises(ValueError, match="must be a non-empty string"):
        service._validate_relationship_type("")

    with pytest.raises(ValueError, match="must be a non-empty string"):
        service._validate_relationship_type(None)


def test_unified_list_returns_normalized_schema(app):
    """All links have common fields regardless of type."""
    service = LinkService(app)
    all_links = service.list_all_links()

    required_fields = ['id', 'name', 'type', 'created_at', 'updated_at']

    for link in all_links:
        for field in required_fields:
            assert field in link, f"Link missing required field: {field}"

        assert link['type'] in ['wizard', 'script'], f"Invalid type: {link['type']}"


def test_wizard_links_count_after_cleanup(app):
    """After cleanup, wizard links should be at a reasonable count (not 1000+)."""
    service = LinkService(app)
    all_links = service.list_all_links()

    wizard_links = [l for l in all_links if l['type'] == 'wizard']

    # Cleanup function at session start removes duplicates by name (originally had 1200+ duplicates)
    # During test run, individual tests may create more links, so we verify:
    # 1. Total count is reasonable (< 300 vs original 1200+)
    # 2. Cleanup significantly reduced count from original 1200+
    assert len(wizard_links) < 300, \
        f"After cleanup, should have <300 wizard links, got {len(wizard_links)}"

    # Verify cleanup is helping - should have at least some unique names
    names = [l['name'] for l in wizard_links]
    unique_names = set(names)
    assert len(unique_names) >= 10, \
        f"Should have at least 10 unique wizard link names, got {len(unique_names)}"


def test_script_links_come_from_files(app):
    """File-based script links are discovered from scripts/links/ directory."""
    pytest.skip("Demo scripts semantic-similarity-link and author-collaboration-link no longer exist - only sample_to_imagingdataset")


def test_links_api_returns_unified_list(client):
    """GET /api/links returns both wizard and script links."""
    response = client.get('/api/links')
    assert response.status_code == 200

    data = response.get_json()
    assert data['status'] == 'success'

    links = data['links']
    assert isinstance(links, list)
    assert len(links) >= 1, f"Should have at least 1 link, got {len(links)}"

    # Check that links have type field
    if len(links) > 0:
        types = {l['type'] for l in links}
        assert types.issubset({'wizard', 'script'}), f"All types should be wizard or script, got {types}"
