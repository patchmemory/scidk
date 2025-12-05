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
        # Navigate to home
        page_helpers.goto_page("/")

        # Fill scan form (adjust selectors to match your HTML)
        page_helpers.page.fill("input[name='path']", temp_test_directory)
        page_helpers.page.click("button[type='submit']")
        page_helpers.page.wait_for_load_state("networkidle")

        # Verify scan completed (adjust selector/text to match your notification)
        page_helpers.expect_notification("Scan")

    def test_scan_form_validation(self, page_helpers):
        """Form validates empty input"""
        page_helpers.goto_page("/")

        # Submit empty form
        page_helpers.page.click("button[type='submit']")

        # Should show validation error (adjust text/selectors for your templates)
        loc = page_helpers.page.locator(
            "text=required, text=invalid, text=error"
        ).first
        error_visible = loc.is_visible()
        assert error_visible or page_helpers.page.is_visible(
            ".error, .alert-danger, [role='alert']"
        )
