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

    # After cleanup: 4 wizard links, 2 file-based script links
    assert len(wizard_links) >= 4, f"Should have at least 4 wizard links, got {len(wizard_links)}"
    assert len(script_links) >= 2, f"Should have at least 2 script links, got {len(script_links)}"
    assert len(all_links) == len(wizard_links) + len(script_links), "All links should be either wizard or script"


def test_script_links_have_validation_status(app):
    """Script links include validation fields that wizard links don't have."""
    service = LinkService(app)
    all_links = service.list_all_links()

    script_links = [l for l in all_links if l['type'] == 'script']
    assert len(script_links) > 0, "Should have at least one script link"

    for link in script_links:
        assert 'validation_status' in link, "Script links must have validation_status"
        assert link['validation_status'] in ['draft', 'validated', 'failed'], \
            f"Invalid validation_status: {link['validation_status']}"
        assert 'is_active' in link, "Script links must have is_active"
        assert isinstance(link['is_active'], bool), "is_active must be boolean"


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
    """After cleanup, should have exactly 4 unique wizard links."""
    service = LinkService(app)
    all_links = service.list_all_links()

    wizard_links = [l for l in all_links if l['type'] == 'wizard']

    # After cleanup: Import Authors, Person to Document, Person to File, CSV Authors
    assert len(wizard_links) == 4, \
        f"After cleanup, should have 4 wizard links, got {len(wizard_links)}"

    # Check names are unique
    names = [l['name'] for l in wizard_links]
    assert len(names) == len(set(names)), "Wizard link names should be unique"


def test_script_links_come_from_files(app):
    """File-based script links are discovered from scripts/links/ directory."""
    scripts_mgr = ScriptsManager()
    script_links = scripts_mgr.list_scripts(category='links')

    # Should find our 2 demo scripts
    assert len(script_links) >= 2, f"Should find at least 2 link scripts, got {len(script_links)}"

    script_ids = {s.id for s in script_links}
    expected_ids = {'semantic-similarity-link', 'author-collaboration-link'}

    assert expected_ids.issubset(script_ids), \
        f"Should find demo scripts {expected_ids}, got {script_ids}"


def test_links_api_returns_unified_list(client):
    """GET /api/links returns both wizard and script links."""
    response = client.get('/api/links')
    assert response.status_code == 200

    data = response.get_json()
    assert data['status'] == 'success'

    links = data['links']
    assert isinstance(links, list)
    assert len(links) >= 6, f"Should have at least 6 total links, got {len(links)}"

    # Check both types are present
    types = {l['type'] for l in links}
    assert 'wizard' in types, "Should include wizard links"
    assert 'script' in types, "Should include script links"
