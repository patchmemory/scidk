"""
E2E demo recording
- Performs a small scan
- Visits key pages
- Captures screenshots and API JSON snapshots
Artifacts are saved under DEMO_ARTIFACTS_DIR or dev/test-runs/<timestamp>.
Run via: make demo-record  (headless) or make demo-record-headed (inspector)
"""
import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest


def _artifact_dir() -> Path:
    base = os.environ.get("DEMO_ARTIFACTS_DIR")
    if base:
        p = Path(base)
        p.mkdir(parents=True, exist_ok=True)
        return p
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = Path("dev/test-runs") / f"demo-{ts}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


@pytest.mark.e2e
@pytest.mark.smoke
def test_demo_recording(page_helpers, base_url):
    artifacts = _artifact_dir()

    # 1) Home page screenshot
    page_helpers.goto_page("/")
    page_helpers.page.screenshot(path=str(artifacts / "01-home.png"), full_page=True)

    # 2) Datasets page before scan
    page_helpers.goto_page("/datasets")
    page_helpers.page.screenshot(path=str(artifacts / "02-datasets-before.png"), full_page=True)

    # 3) Create a tiny temp directory to scan
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "a.txt").write_text("hello\n")
        Path(tmpdir, "b.ipynb").write_text("{}")

        # 4) Perform scan via UI
        page_helpers.page.fill("[data-testid='scan-path']", tmpdir)
        page_helpers.page.click("[data-testid='scan-submit']")
        page_helpers.page.wait_for_load_state("networkidle")

        # Optional wait for tasks list to refresh
        try:
            page_helpers.wait_for_element("#tasks-list", timeout=10000)
        except Exception:
            pass

        page_helpers.page.screenshot(path=str(artifacts / "03-datasets-after.png"), full_page=True)

    # 5) Map page
    page_helpers.goto_page("/map")
    page_helpers.page.screenshot(path=str(artifacts / "04-map.png"), full_page=True)

    # 6) API snapshots
    # Use Playwright's request context to fetch JSON directly
    for endpoint in [
        "/api/health",
        "/api/scans",
        "/api/directories",
        "/api/tasks",
    ]:
        resp = page_helpers.page.request.get(f"{base_url}{endpoint}")
        try:
            data = resp.json()
        except Exception:
            data = {"status": resp.status, "text": resp.text()}
        safe_name = endpoint.strip("/").replace("/", "-") or "root"
        _save_json(artifacts / f"api-{safe_name}.json", data)

    # 7) Record a simple summary file for tagging/review
    summary = {
        "artifacts_dir": str(artifacts.resolve()),
        "timestamp": datetime.now().isoformat(),
        "note": "Demo artifacts collected. Attach this folder to release/tag if desired.",
    }
    _save_json(artifacts / "SUMMARY.json", summary)

    # 8) Emit path to stdout for CI logs
    print(f"[demo] artifacts saved to: {artifacts}")

    # Basic sanity assertion to keep test meaningful
    assert (artifacts / "01-home.png").exists() and (artifacts / "api-api-scans.json").exists()
