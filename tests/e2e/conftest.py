"""
Playwright E2E test configuration - manages Flask app startup
"""
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

FLASK_PORT = 5001
FLASK_HOST = "127.0.0.1"
TEST_DB = os.getenv("SCIDK_TEST_DB", "sqlite:///:memory:")


@pytest.fixture(scope="session", autouse=True)
def flask_app():
    """Start Flask app in test mode for the whole test session."""
    env = os.environ.copy()
    env.update({
        "FLASK_ENV": "testing",
        "FLASK_DEBUG": "0",
        # Make the app listen on the port our tests will hit
        "SCIDK_PORT": str(FLASK_PORT),
        # Use in-memory/throwaway DB by default
        "SCIDK_DB_PATH": TEST_DB,
        # Ensure no real Neo4j connection attempt occurs
        "NEO4J_AUTH": "none",
        # Keep providers simple and reliable for E2E
        "SCIDK_PROVIDERS": "local_fs",
        # Feature flags with safe defaults
        "SCIDK_FEATURE_FILE_INDEX": os.environ.get("SCIDK_FEATURE_FILE_INDEX", "1"),
        "SCIDK_COMMIT_FROM_INDEX": os.environ.get("SCIDK_COMMIT_FROM_INDEX", "1"),
    })

    repo_root = Path(__file__).resolve().parents[2]
    flask_process = subprocess.Popen(
        ["python", "-m", "scidk.app"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=repo_root,
    )

    # Wait for Flask to start
    max_retries = 30
    for _ in range(max_retries):
        try:
            r = requests.get(f"http://{FLASK_HOST}:{FLASK_PORT}/", timeout=0.5)
            if r.status_code < 500:
                break
        except Exception:
            time.sleep(0.5)
    else:
        try:
            out, err = flask_process.communicate(timeout=1)
        except Exception:
            out = err = b""
        raise RuntimeError(
            "Flask app failed to start on E2E bootstrap.\n"
            f"stdout: {out.decode(errors='ignore')}\n"
            f"stderr: {err.decode(errors='ignore')}"
        )

    yield flask_process

    flask_process.terminate()
    try:
        flask_process.wait(timeout=10)
    except Exception:
        flask_process.kill()


@pytest.fixture(scope="session")
def base_url():
    return f"http://{FLASK_HOST}:{FLASK_PORT}"


class PageHelpers:
    """Reusable helpers for common page interactions (sync API)."""
    def __init__(self, page, base_url):
        self.page = page
        self.base_url = base_url

    def goto_page(self, path: str):
        self.page.goto(f"{self.base_url}{path}")
        self.page.wait_for_load_state("networkidle")

    def fill_and_submit_form(self, field_selectors: dict, submit_button="button[type='submit']"):
        for selector, value in field_selectors.items():
            self.page.fill(selector, value)
        self.page.click(submit_button)
        self.page.wait_for_load_state("networkidle")

    def wait_for_element(self, selector: str, timeout=5000):
        self.page.locator(selector).first.wait_for(state="visible", timeout=timeout)

    def expect_notification(self, message: str, timeout=5000):
        self.page.get_by_text(message, exact=False).first.wait_for(timeout=timeout)


@pytest.fixture
def page_helpers(page, base_url):
    return PageHelpers(page, base_url)
