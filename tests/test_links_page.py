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
    assert 'links-core.js' in html, "links-core.js module should be loaded"
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
    """Test that modal-related JavaScript modules are loaded."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # Check for modular JS files that contain the functions
    assert 'links-wizard.js' in html, "links-wizard.js module should be loaded"
    assert 'links-core.js' in html, "links-core.js module should be loaded"
    assert 'links-discovery.js' in html, "links-discovery.js module should be loaded"
    assert 'links-active.js' in html, "links-active.js module should be loaded"


def test_links_page_has_csv_validation_functions(client):
    """Test that CSV export/import modules are loaded."""
    response = client.get('/links')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    # CSV functions are in links-core.js and links-wizard.js modules
    assert 'links-core.js' in html, "links-core.js module (contains CSV logic) should be loaded"
    assert 'links-wizard.js' in html, "links-wizard.js module should be loaded"


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
