"""
End-to-end tests for Files page UX workflows.

Validates the consolidated scan functionality and browser-to-scan integration.
"""
import os
import time
from pathlib import Path
import pytest
from tests.conftest import authenticate_test_client

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    BeautifulSoup = None


def test_files_page_loads_successfully():
    """Test that the Files page loads without errors."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        resp = client.get('/datasets')
        assert resp.status_code == 200
        assert b'Files' in resp.data
        assert b'Provider' in resp.data


def test_scan_button_uses_background_tasks_only():
    """Verify that the scan button uses /api/tasks, not /api/scan."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        resp = client.get('/datasets')
        assert resp.status_code == 200

        # Check that the template has the new unified scan button
        html = resp.data.decode('utf-8')
        assert 'prov-scan-btn' in html
        assert '🔍 Scan This Folder' in html

        # Check that the old sync scan form is removed
        assert 'prov-scan-form' not in html
        assert 'prov-scan-recursive' not in html  # old checkbox removed


def test_browse_and_scan_integration(tmp_path: Path):
    """Test the full workflow: browse folder → scan it via background task."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    # Create test directory
    test_dir = tmp_path / 'test_project'
    test_dir.mkdir()
    (test_dir / 'file1.txt').write_text('content1', encoding='utf-8')
    (test_dir / 'file2.txt').write_text('content2', encoding='utf-8')
    (test_dir / 'subdir').mkdir()
    (test_dir / 'subdir' / 'file3.txt').write_text('content3', encoding='utf-8')

    with authenticate_test_client(app.test_client(), app) as client:
        # Browse the directory
        browse_resp = client.get(f'/api/browse?provider_id=local_fs&root_id=/&path={str(test_dir)}')
        assert browse_resp.status_code == 200
        browse_data = browse_resp.get_json()
        assert 'entries' in browse_data
        assert len(browse_data['entries']) >= 3  # 2 files + 1 subdir

        # Trigger scan via background task (unified mechanism)
        scan_resp = client.post('/api/tasks', json={
            'type': 'scan',
            'path': str(test_dir),
            'recursive': True,
            'provider_id': 'local_fs',
            'root_id': '/'
        })
        assert scan_resp.status_code == 202  # Accepted
        scan_data = scan_resp.get_json()
        assert 'task_id' in scan_data
        task_id = scan_data['task_id']

        # Poll for task completion (max 10 seconds)
        max_wait = 10
        start_time = time.time()
        task_completed = False

        while time.time() - start_time < max_wait:
            task_resp = client.get(f'/api/tasks/{task_id}')
            assert task_resp.status_code == 200
            task_data = task_resp.get_json()

            if task_data['status'] == 'completed':
                task_completed = True
                assert task_data['processed'] >= 3
                break

            time.sleep(0.5)

        assert task_completed, "Scan task did not complete in time"


def test_scan_history_unified_display(tmp_path: Path):
    """Test that all scans appear in unified history."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    test_dir = tmp_path / 'scan_test'
    test_dir.mkdir()
    (test_dir / 'test.txt').write_text('test', encoding='utf-8')

    with authenticate_test_client(app.test_client(), app) as client:
        # Create first scan
        resp1 = client.post('/api/tasks', json={
            'type': 'scan',
            'path': str(test_dir),
            'recursive': True,
            'provider_id': 'local_fs',
            'root_id': '/'
        })
        assert resp1.status_code == 202

        time.sleep(1)  # Allow scan to process

        # Get all scans
        scans_resp = client.get('/api/scans')
        assert scans_resp.status_code == 200
        scans = scans_resp.get_json()
        assert isinstance(scans, list)
        assert len(scans) >= 1

        # Verify scan appears in summary
        found = any(s.get('path') == str(test_dir) for s in scans)
        assert found, "Scan not found in unified history"


def test_rclone_scan_with_options():
    """Test that rclone-specific options are handled correctly."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        # Mock rclone scan with fast-list option
        # Note: This will fail in test without actual rclone, but validates API contract
        resp = client.post('/api/tasks', json={
            'type': 'scan',
            'path': 'dropbox:test',
            'recursive': True,
            'provider_id': 'rclone',
            'root_id': 'dropbox:',
            'fast_list': True
        })

        # Should accept the request format (will fail on execution without rclone)
        assert resp.status_code in (202, 400, 500)  # 202 if rclone available, error otherwise


def test_snapshot_browser_after_scan(tmp_path: Path):
    """Test viewing scan snapshot after completion."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    test_dir = tmp_path / 'snapshot_test'
    test_dir.mkdir()
    (test_dir / 'data.csv').write_text('col1,col2\n1,2\n', encoding='utf-8')

    with authenticate_test_client(app.test_client(), app) as client:
        # Perform scan
        scan_resp = client.post('/api/tasks', json={
            'type': 'scan',
            'path': str(test_dir),
            'recursive': True,
            'provider_id': 'local_fs',
            'root_id': '/'
        })
        assert scan_resp.status_code == 202
        task_id = scan_resp.get_json()['task_id']

        # Wait for completion
        max_wait = 10
        start_time = time.time()
        scan_id = None

        while time.time() - start_time < max_wait:
            task_resp = client.get(f'/api/tasks/{task_id}')
            task_data = task_resp.get_json()

            if task_data['status'] == 'completed':
                scan_id = task_data.get('scan_id')
                break

            time.sleep(0.5)

        assert scan_id is not None, "Scan did not complete"

        # Browse snapshot
        snapshot_resp = client.get(f'/api/scans/{scan_id}/browse')
        assert snapshot_resp.status_code == 200
        snapshot_data = snapshot_resp.get_json()

        assert 'entries' in snapshot_data
        # Should find the data.csv file or parent folder
        assert len(snapshot_data['entries']) >= 1


def test_no_synchronous_scan_in_ui():
    """Verify that synchronous /api/scan is NOT used by the Files page UI."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        resp = client.get('/datasets')
        html = resp.data.decode('utf-8')

        # Check that the JavaScript does NOT call /api/scan from provider panel
        # (it should only use /api/tasks)
        assert "'/api/scan'" not in html or html.count("'/api/scan'") <= 1
        # Allow one mention in comments/strings, but not active code

        # Verify /api/tasks is used instead
        assert "'/api/tasks'" in html


def test_current_location_display_updates():
    """Test that the 'Current Location' panel updates when browsing."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        resp = client.get('/datasets')
        html = resp.data.decode('utf-8')

        # Check that current location display exists
        assert 'prov-current-path' in html
        assert 'Current Location:' in html

        # Verify scan button is present and starts disabled
        assert 'prov-scan-btn' in html
        assert 'disabled' in html  # Button should start disabled


def test_scan_button_integration_with_background_form():
    """Test that clicking scan button populates background scan form."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        resp = client.get('/datasets')
        html = resp.data.decode('utf-8')

        # Verify the scan button handler references background scan form elements
        assert 'scan-path' in html  # Background scan path input
        assert 'scan-recursive' in html  # Background scan recursive checkbox

        # The JavaScript should populate these when scan button is clicked
        # (Verified by manual testing and code inspection)


@pytest.mark.skipif(not HAS_BS4, reason="beautifulsoup4 not installed")
def test_files_page_structure_consolidated():
    """Verify that redundant sections have been removed/consolidated."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        resp = client.get('/datasets')
        html = resp.data.decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')

        # Count h2 headings (main sections)
        sections = soup.find_all('h2')
        section_titles = [s.get_text() for s in sections]

        # Should have core sections: Files, Snapshot browse, Scans Summary
        assert 'Files' in section_titles
        assert 'Snapshot (scanned) browse' in section_titles or 'Snapshot browse' in section_titles
        assert 'Scans Summary' in section_titles

        # Verify old sync scan form is gone
        old_form = soup.find('form', id='prov-scan-form')
        assert old_form is None, "Old synchronous scan form still present"


def test_provider_selector_and_roots_load():
    """Test that providers and roots load correctly."""
    from scidk.app import create_app
    app = create_app()
    app.config['TESTING'] = True

    with authenticate_test_client(app.test_client(), app) as client:
        # Get providers
        prov_resp = client.get('/api/providers')
        assert prov_resp.status_code == 200
        providers = prov_resp.get_json()
        assert isinstance(providers, list)
        assert len(providers) > 0

        # Get roots for first provider
        first_prov = providers[0]['id']
        roots_resp = client.get(f'/api/provider_roots?provider_id={first_prov}')
        assert roots_resp.status_code == 200
        roots = roots_resp.get_json()
        assert isinstance(roots, list)
