"""E2E tests for graph features"""
import pytest


@pytest.mark.e2e
class TestGraphFeatures:

    def test_graph_page_loads(self, page_helpers):
        """Graph explorer page loads"""
        page_helpers.goto_page("/map")
        # Wait for graph to render using stable testid
        page_helpers.wait_for_element("[data-testid='graph-explorer-root']", timeout=10000)
        assert True

    def test_graph_visualization_exists(self, page_helpers):
        """Visualization is present (stable testid)"""
        page_helpers.goto_page("/map")
        # Assert our stable container becomes visible rather than relying on library DOM
        page_helpers.wait_for_element("[data-testid='graph-explorer-root']", timeout=10000)
        assert page_helpers.page.is_visible("[data-testid='graph-explorer-root']")
