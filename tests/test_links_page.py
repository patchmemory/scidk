"""
Basic smoke tests for the Links page UI.

Tests that the modal-based triple builder renders correctly.
"""
import pytest


def test_links_page_loads(client):
    """Test that /links page loads successfully."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Check for key UI elements
    assert 'tripleBuilder' in html, "tripleBuilder state object should be in page"
    assert 'main-triple-display' in html, "Visual triple pattern should be present"
    assert 'modal-overlay' in html, "Modal overlay should be present"


def test_links_page_has_modal_buttons(client):
    """Test that the new modal-based UI elements are present."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Check for clickable triple nodes
    assert 'source-node-btn' in html, "Source node button should exist"
    assert 'relationship-node-btn' in html, "Relationship node button should exist"
    assert 'target-node-btn' in html, "Target node button should exist"

    # Check for action buttons
    assert 'btn-save-def' in html, "Save Definition button should exist"
    assert 'btn-execute' in html, "Execute button should exist"
    assert 'btn-export-csv' in html, "Export CSV button should exist"
    assert 'btn-import-csv' in html, "Import CSV button should exist"


def test_links_page_has_modal_functions(client):
    """Test that modal-related JavaScript functions are defined."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Check for key functions
    assert 'function openModal(' in html, "openModal function should be defined"
    assert 'function closeModal(' in html, "closeModal function should be defined"
    assert 'function getSourceModalContent(' in html, "getSourceModalContent should be defined"
    assert 'function getRelationshipModalContent(' in html, "getRelationshipModalContent should be defined"
    assert 'function getTargetModalContent(' in html, "getTargetModalContent should be defined"
    assert 'function saveDiscoveredAsDefinition(' in html, "saveDiscoveredAsDefinition should be defined"


def test_links_page_has_csv_validation_functions(client):
    """Test that CSV export/import functions are defined."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    assert 'function exportMatchesCsv(' in html, "exportMatchesCsv should be defined"
    assert 'function importValidatedCsv(' in html, "importValidatedCsv should be defined"


def test_links_page_has_new_ui_not_old_steps(client):
    """Test that new modal UI is present and replaces old 3-step wizard."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # New UI should be present
    assert 'visual-triple-pattern' in html, "New visual triple pattern should be present"
    assert 'main-triple-display' in html, "Main triple display should be present"

    # Old step HTML divs with specific IDs should be gone
    # (CSS classes/JS may remain for backward compat, but actual step container HTML removed)
    assert '<div class="wizard-step-content"' not in html and \
           'id="step-1-content"' not in html and \
           'id="step-2-content"' not in html and \
           'id="step-3-content"' not in html, \
        "Old wizard step HTML containers should be removed"
