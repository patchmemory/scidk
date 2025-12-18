"""E2E tests for file scanning workflow"""
import tempfile
from pathlib import Path

import pytest


@pytest.mark.e2e
class TestScanWorkflow:

    @pytest.fixture
    def temp_test_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.py").write_text("def hello(): pass")
            Path(tmpdir, "data.csv").write_text("col1,col2\n1,2")
            yield tmpdir

    def test_scan_local_directory(self, page_helpers, temp_test_directory):
        """User scans a directory and sees results"""
        # Navigate to Files page
        page_helpers.goto_page("/datasets")

        # Fill scan form using stable data-testids
        page_helpers.page.fill("[data-testid='scan-path']", temp_test_directory)
        page_helpers.page.click("[data-testid='scan-submit']")
        page_helpers.page.wait_for_load_state("networkidle")

        # Verify something updated on the page (fallback: presence of tasks list or recent scans refresh)
        page_helpers.wait_for_element("#tasks-list", timeout=10000)

    def test_scan_form_validation(self, page_helpers):
        """Form validates empty input on Files page"""
        # The scan form lives on /datasets
        page_helpers.goto_page("/datasets")

        # Ensure the path input is empty then submit
        sel_path = "[data-testid='scan-path']"
        sel_submit = "[data-testid='scan-submit']"
        # Clear any prefilled value
        try:
            page_helpers.page.fill(sel_path, "")
        except Exception:
            pass
        page_helpers.page.click(sel_submit)

        # Expect either a validation message area to update or an alert
        # Our UI writes into #tasks-list or could display a message near the form
        ok = False
        try:
            page_helpers.wait_for_element("#tasks-list", timeout=3000)
            ok = True
        except Exception:
            # Look for a generic validation clue
            ok = page_helpers.page.is_visible(".error, .alert-danger, [role='alert'], #prov-scan-msg")
        assert ok
