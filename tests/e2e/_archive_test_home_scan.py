import pytest

pytestmark = pytest.mark.e2e


def test_homepage_loads(page, base_url, no_console_errors):
    # Navigate to home and ensure the request succeeds
    resp = page.goto(base_url, wait_until="domcontentloaded")
    assert resp is not None, "No response when navigating to BASE_URL"
    assert resp.ok, f"Homepage request failed: {resp.status}"
    # Basic sanity checks on content
    body_text = page.text_content("body") or ""
    assert len(body_text) > 0
